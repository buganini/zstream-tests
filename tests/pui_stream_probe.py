"""Reproduce PUI's ready-first, one-MessagePack-envelope-per-block-flush stream."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import msgpack
import zstandard as zstd

PUI_REVISION = "8a8ef99da854c75d5c9abfd24e03bc21f8f5a880"


def messages():
    """Representative downstream envelopes; fixed IDs make the fixture repeatable."""
    def envelope(kind, seq, body):
        return {"v": 1, "type": kind, "session": "test-session-0123456789abcdef",
                "seq": seq, "body": body}

    yield envelope("ready", 1, {
        "server_build": "0123456789abcdef",
        "capabilities": ["render.snapshot", "render.patch", "binding.object_id",
                         "canvas.geometry", "canvas.text", "canvas.input", "canvas.path",
                         "canvas.image", "canvas.patch"],
        "limits": {"max_wire_bytes": 8 * 1024 * 1024,
                   "max_decoded_bytes": 32 * 1024 * 1024,
                   "max_window_bytes": 16 * 1024 * 1024, "max_items": 5000000,
                   "max_depth": 64, "max_pending_actions": 64},
        "resume_id": "r" * 32, "resumed": False, "session_ttl": 900,
    })
    for i in range(100):
        yield envelope("result", i + 2, {"reply_to": i + 1, "status": "processed", "code": None})


def encoder():
    parameters = zstd.ZstdCompressionParameters.from_level(
        3, window_log=22, write_content_size=False, write_checksum=False)
    return zstd.ZstdCompressor(compression_params=parameters).compressobj()


def blob(data):
    return {"base64": base64.b64encode(data).decode("ascii"), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def make_case(name, parts, *, test, extra_flushes=0):
    compressor, reference = encoder(), zstd.ZstdDecompressor().decompressobj()
    expected = decoded = b""
    stages = []
    for i, part in enumerate(parts):
        expected += part
        write_output = compressor.compress(part)
        flush_output = compressor.flush(zstd.COMPRESSOBJ_FLUSH_BLOCK)
        wire = write_output + flush_output
        decoded += reference.decompress(wire)
        assert decoded == expected and not reference.eof
        # Diagnostic only: an extra flush with no new input cannot warm up fzstd.
        extra = b""
        calls = extra_flushes if i == 0 else 0
        for _ in range(calls):
            extra += compressor.flush(zstd.COMPRESSOBJ_FLUSH_BLOCK)
        decoded += reference.decompress(extra)
        assert decoded == expected and not reference.eof
        stages.append({"wire": blob(wire + extra), "submitted": len(expected),
                       "message_bytes": len(part), "write_output": len(write_output),
                       "flush_output": len(flush_output), "extra_flush_calls": calls,
                       "extra_flush_output": len(extra), "reference_decoded": len(decoded),
                       "reference_eof": reference.eof})
    # PUI drops the context on close. Finalize only AFTER every measured checkpoint
    # here, as an additional test integrity check, never to release a message.
    tail = compressor.flush(zstd.COMPRESSOBJ_FLUSH_FINISH)
    decoded += reference.decompress(tail)
    assert decoded == expected and reference.eof and not reference.unused_data
    return {"name": name, "test": test, "stages": stages, "expected": blob(expected),
            "tail": blob(tail), "reference_final_eof": True}


def cases():
    packed = [msgpack.packb(message, use_bin_type=True, strict_types=True) for message in messages()]
    return [
        make_case("ready-then-100-results", packed, test="pui_stream"),
        make_case("raw-17-first-plus-three-empty-flushes", [b"A" * 17, b"B" * 37],
                  test="startup_control", extra_flushes=3),
        make_case("ready-then-raw-17", [packed[0], b"A" * 17, b"B" * 37],
                  test="startup_control"),
    ]


def main():
    manifest = json.loads((Path(sys.argv[1]) / "manifest.json").read_text())
    suite = {"binding": "pui_fzstd", "codec": "zstd", "sender": "python_zstandard",
             "receiver": "fzstd", "sender_api": "compressobj", "midstream_flush": True,
             "native_level": 3, "window_log": 22, "write_content_size": False,
             "write_checksum": False, "transport_chunks": manifest["transport_chunks"],
             "package_version": zstd.__version__, "zstd_version": list(zstd.ZSTD_VERSION),
             "backend": zstd.backend, "msgpack_version": msgpack.__version__,
             "pui_source_revision": PUI_REVISION, "cases": cases()}
    result = subprocess.run(["node", str(Path(__file__).with_name("pui_fzstd_receiver.mjs"))],
                            input=json.dumps(suite), text=True, capture_output=True, timeout=60)
    print(result.stdout, end="")
    print(result.stderr, end="", file=sys.stderr)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
