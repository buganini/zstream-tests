"""Exercise the public Python binding; print one JSON object per observation."""
import json
import pathlib
import sys

import compress_utils as cu

ROOT = pathlib.Path(sys.argv[1])
MANIFEST = json.loads((ROOT / "manifest.json").read_text())
LEVEL = 5


def chunks(data, sizes=None):
    if sizes is None:
        sizes = MANIFEST.get("transport_chunks", [1, 3, 7, 97, 4093])
    offset = index = 0
    while offset < len(data):
        size = sizes[index % len(sizes)] if sizes else len(data)
        yield data[offset:offset + size]
        offset += size
        index += 1


def receive(decoder, data):
    return b"".join(decoder.decompress(part) for part in chunks(data))


def roundtrip(codec, data, streaming):
    if not streaming:
        packed = cu.compress(data, codec, LEVEL)
        restored = cu.decompress(packed, codec)
    else:
        encoder = cu.CompressStream(codec, LEVEL)
        decoder = cu.DecompressStream(codec)
        packed_parts, decoded_parts = [], []
        for part in chunks(data, (1, 7, 63, 1024, 65521)):
            wire = encoder.compress(part)
            packed_parts.append(wire)
            decoded_parts.append(receive(decoder, wire))
        wire = encoder.finish()
        packed_parts.append(wire)
        decoded_parts.extend((receive(decoder, wire), decoder.finish()))
        packed = b"".join(packed_parts)
        restored = b"".join(decoded_parts)
    assert restored == data, f"decoded {len(restored)} / {len(data)} bytes"
    return {"status": "PASS", "input_bytes": len(data), "compressed_bytes": len(packed)}


def midpoint(codec, data):
    encoder, decoder = cu.CompressStream(codec, LEVEL), cu.DecompressStream(codec)
    expected = decoded = b""
    stages = []
    has_flush = callable(getattr(encoder, "flush", None))
    for part in (data, b"B" * 37, bytes(range(256)) * 16, b""):
        expected += part
        wire = encoder.compress(part)
        decoded += receive(decoder, wire)
        extra = encoder.flush() if has_flush else b""
        extra = extra or b""
        # An empty write is a drain attempt, not a substitute flush operation.
        empty_output = b"".join(encoder.compress(b"") for _ in range(3))
        decoded += receive(decoder, extra + empty_output)
        empty_decoded = b"".join(decoder.decompress(b"") for _ in range(3))
        decoded += empty_decoded
        assert decoded == expected[:len(decoded)]
        stages.append({"submitted": len(expected), "decoded": len(decoded),
                       "write_output": len(wire), "flush_output": len(extra),
                       "empty_write_output": len(empty_output), "empty_decode_output": len(empty_decoded)})
    decoded += receive(decoder, encoder.finish()) + decoder.finish()
    assert decoded == expected, f"after finish: {len(decoded)} / {len(expected)}"
    return {"status": "PASS" if has_flush and all(s["decoded"] == s["submitted"] for s in stages)
            else "LIMITATION", "flush_api": has_flush, "stages": stages,
            "final_roundtrip": True}


def finish_is_terminal(codec):
    encoder = cu.CompressStream(codec, LEVEL)
    wire = encoder.compress(b"A") + encoder.finish()
    decoder = cu.DecompressStream(codec)
    assert receive(decoder, wire) + decoder.finish() == b"A"
    try:
        encoder.compress(b"B")
    except Exception as error:
        return {"status": "PASS", "write_after_finish_error": str(error)}
    raise AssertionError("write after finish unexpectedly accepted")


def truncated(codec):
    encoder = cu.CompressStream(codec, LEVEL)
    wire = encoder.compress(b"A" * 4096) + encoder.finish()
    decoder = cu.DecompressStream(codec)
    try:
        receive(decoder, wire[:-1])
        decoder.finish()
    except Exception as error:
        return {"status": "PASS", "truncated_error": str(error)}
    raise AssertionError("missing final byte was not detected")


def run(codec, name, case, operation):
    row = {"binding": "python", "codec": codec, "test": name, "case": case, "level": LEVEL,
           "transport_chunks": MANIFEST.get("transport_chunks", [1, 3, 7, 97, 4093])}
    try:
        row.update(operation())
    except Exception as error:
        row.update(status="FAIL", error=f"{type(error).__name__}: {error}")
    print(json.dumps(row), flush=True)
    return row["status"] == "FAIL"


failed = False
for codec in ("zstd", "lz4"):
    for case in MANIFEST["roundtrip"]:
        data = (ROOT / case["file"]).read_bytes()
        for streaming in (False, True):
            failed |= run(codec, "stream_roundtrip" if streaming else "oneshot_roundtrip", case["name"],
                          lambda: roundtrip(codec, data, streaming))
    for kind in ("random", "repeat"):
        source = (ROOT / f"{kind}.bin").read_bytes()
        for size in MANIFEST["midpoint_sizes"]:
            failed |= run(codec, "midpoint", f"{kind}-{size}", lambda: midpoint(codec, source[:size]))
    failed |= run(codec, "finish_is_terminal", "A-then-B", lambda: finish_is_terminal(codec))
    failed |= run(codec, "truncated", "missing-last-byte", lambda: truncated(codec))
sys.exit(1 if failed else 0)
