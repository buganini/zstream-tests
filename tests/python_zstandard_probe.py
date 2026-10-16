"""Compare python-zstandard against the same fixtures and live-stream contract."""
import io
import json
from pathlib import Path
import sys

import zstandard as zstd

NATIVE_LEVEL = 11  # compress-utils level 5 maps to (5 * 22) // 10.
DECODE_CHUNK = 65536
TRANSPORT_CHUNKS = [1, 3, 7, 97, 4093]


def chunks(data, sizes=None):
    if sizes is None:
        sizes = TRANSPORT_CHUNKS
    offset = index = 0
    while offset < len(data):
        size = sizes[index % len(sizes)] if sizes else len(data)
        yield data[offset:offset + size]
        offset += size
        index += 1


def receive(decoder, wire, sizes=None):
    return b"".join(decoder.decompress(part) for part in chunks(wire, sizes))


def decoder():
    return zstd.ZstdDecompressor().decompressobj(write_size=DECODE_CHUNK)


def complete(dec):
    # decompressobj.flush() does not validate EOF. Check this explicitly.
    assert dec.eof, "transport ended before the zstd frame completed"
    assert not dec.unused_data and not dec.unconsumed_tail


class ObjectEncoder:
    def __init__(self):
        self.obj = zstd.ZstdCompressor(level=NATIVE_LEVEL).compressobj()

    def compress(self, data):
        return self.obj.compress(data)

    def flush_block(self):
        return self.obj.flush(zstd.COMPRESSOBJ_FLUSH_BLOCK)

    def finish(self):
        return self.obj.flush(zstd.COMPRESSOBJ_FLUSH_FINISH)


class Sink(io.BytesIO):
    def write(self, data):
        assert len(data) <= 113, "stream_writer exceeded its configured output chunk"
        return super().write(data)


class WriterEncoder:
    def __init__(self):
        self.sink = Sink()
        self.offset = 0
        self.obj = zstd.ZstdCompressor(level=NATIVE_LEVEL).stream_writer(
            self.sink, write_size=113, write_return_read=True, closefd=False)

    def take(self):
        data = self.sink.getvalue()
        result = data[self.offset:]
        self.offset = len(data)
        return result

    def compress(self, data):
        assert self.obj.write(data) == len(data)
        return self.take()

    def flush_block(self):
        self.obj.flush(zstd.FLUSH_BLOCK)
        return self.take()

    def finish(self):
        self.obj.close()
        return self.take()


def roundtrip(data, streaming):
    if not streaming:
        packed = zstd.ZstdCompressor(level=NATIVE_LEVEL).compress(data)
        restored = zstd.ZstdDecompressor().decompress(packed)
    else:
        encoder, dec = ObjectEncoder(), decoder()
        packed_parts, decoded_parts = [], []
        for part in chunks(data, (1, 7, 63, 1024, 65521)):
            wire = encoder.compress(part)
            packed_parts.append(wire)
            decoded_parts.append(receive(dec, wire))
        wire = encoder.finish()
        packed_parts.append(wire)
        decoded_parts.append(receive(dec, wire))
        complete(dec)
        packed, restored = b"".join(packed_parts), b"".join(decoded_parts)
    assert restored == data
    return {"input_bytes": len(data), "compressed_bytes": len(packed)}


def midpoint(data, encoder_type):
    encoder, dec = encoder_type(), decoder()
    expected = decoded = b""
    stages = []
    for part in (data, b"B" * 37, bytes(range(256)) * 16, b""):
        expected += part
        wire = encoder.compress(part)
        decoded += receive(dec, wire)
        before_flush = len(decoded)
        extra = encoder.flush_block()
        decoded += receive(dec, extra)
        empty_output = b"".join(encoder.compress(b"") for _ in range(3))
        decoded += receive(dec, empty_output)
        empty_decoded = b"".join(dec.decompress(b"") for _ in range(3))
        decoded += empty_decoded
        assert decoded == expected, f"midway decoded {len(decoded)} / {len(expected)}"
        assert not dec.eof, "block flush unexpectedly ended the frame"
        assert not dec.unused_data and not dec.unconsumed_tail
        stages.append({"submitted": len(expected), "decoded_before_flush": before_flush,
                       "decoded": len(decoded), "write_output": len(wire),
                       "flush_output": len(extra), "empty_write_output": len(empty_output),
                       "empty_decode_output": len(empty_decoded), "eof": dec.eof})
    decoded += receive(dec, encoder.finish())
    complete(dec)
    assert decoded == expected
    return {"flush_api": True, "stages": stages, "final_roundtrip": True, "final_eof": dec.eof}


def no_flush_boundary(data, encoder_type):
    """Measure pre-flush buffering, then require a block flush to drain it."""
    encoder, dec = encoder_type(), decoder()
    wire = encoder.compress(data)
    restored = receive(dec, wire)
    assert restored == data[:len(restored)]
    assert not dec.eof
    before_flush = len(restored)
    extra = encoder.flush_block()
    restored += receive(dec, extra)
    assert restored == data, f"after block flush decoded {len(restored)} / {len(data)}"
    assert not dec.eof
    restored += receive(dec, encoder.finish())
    complete(dec)
    assert restored == data
    return {"input_bytes": len(data), "write_output": len(wire),
            "decoded_before_flush": before_flush, "flush_output": len(extra),
            "decoded_after_flush": len(restored), "final_roundtrip": True}


def finish_is_terminal():
    encoder, dec = ObjectEncoder(), decoder()
    # Demonstrate the default flush mode: it FINISHES, unlike block flushing.
    wire = encoder.compress(b"A") + encoder.obj.flush()
    assert receive(dec, wire) == b"A"
    complete(dec)
    try:
        encoder.compress(b"B")
    except zstd.ZstdError as error:
        return {"write_after_finish_error": str(error), "finish_mode": "default flush()"}
    raise AssertionError("write after finish unexpectedly accepted")


def truncated():
    encoder, dec = ObjectEncoder(), decoder()
    wire = encoder.compress(b"A" * 4096) + encoder.finish()
    decoded = receive(dec, wire[:-1])
    flushed = dec.flush()
    assert not dec.eof, "incomplete frame incorrectly reported EOF"
    try:
        complete(dec)
    except AssertionError as error:
        return {"detection": "application checks decoder.eof", "eof": dec.eof,
                "automatic_exception": False, "decoded_bytes": len(decoded),
                "decoder_flush_output": len(flushed), "application_error": str(error)}
    raise AssertionError("application completion check accepted truncation")


def run(test, case, api, operation):
    row = {"binding": "python_zstandard", "codec": "zstd", "test": test, "case": case,
           "api": api, "level": NATIVE_LEVEL, "compress_utils_equivalent_level": 5,
           "package_version": zstd.__version__, "zstd_version": list(zstd.ZSTD_VERSION),
           "backend": zstd.backend,
           "transport_chunks": TRANSPORT_CHUNKS,
           "decoder_write_size": None if api == "oneshot" else DECODE_CHUNK}
    if api == "stream_writer":
        row["encoder_write_size"] = 113
    try:
        row.update(operation(), status="PASS")
    except Exception as error:
        row.update(status="FAIL", error=f"{type(error).__name__}: {error}")
    print(json.dumps(row), flush=True)
    return row["status"] == "FAIL"


def main():
    global TRANSPORT_CHUNKS
    root = Path(sys.argv[1])
    manifest = json.loads((root / "manifest.json").read_text())
    TRANSPORT_CHUNKS = manifest.get("transport_chunks", TRANSPORT_CHUNKS)
    failed = False
    for case in manifest["roundtrip"]:
        data = (root / case["file"]).read_bytes()
        for streaming in (False, True):
            failed |= run("stream_roundtrip" if streaming else "oneshot_roundtrip", case["name"],
                          "compressobj" if streaming else "oneshot", lambda: roundtrip(data, streaming))
    for kind in ("random", "repeat"):
        source = (root / f"{kind}.bin").read_bytes()
        for api, encoder_type in (("compressobj", ObjectEncoder), ("stream_writer", WriterEncoder)):
            for size in manifest["midpoint_sizes"]:
                failed |= run("midpoint" if api == "compressobj" else "midpoint_writer", f"{kind}-{size}",
                              api, lambda: midpoint(source[:size], encoder_type))
            failed |= run("no_flush_boundary", f"{kind}-131072", api,
                          lambda: no_flush_boundary(source[:131072], encoder_type))
    failed |= run("finish_is_terminal", "A-then-B", "compressobj", finish_is_terminal)
    failed |= run("truncated", "missing-last-byte", "compressobj", truncated)
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
