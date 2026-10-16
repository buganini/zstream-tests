"""Send a 294-byte compressed preamble, then block-flush each subsequent message."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

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
    # Finalize only AFTER every measured checkpoint as an additional test
    # integrity check, never to release a message.
    tail = compressor.flush(zstd.COMPRESSOBJ_FLUSH_FINISH)
    decoded += reference.decompress(tail)
    assert decoded == expected and reference.eof and not reference.unused_data
    return {"name": name, "test": test, "stages": stages, "expected": blob(expected),
            "tail": blob(tail), "reference_final_eof": True}


def cases():
    packed = [msgpack.packb(message, use_bin_type=True, strict_types=True) for message in messages()]
    return [
        make_case("294-byte-preamble-then-100-messages", packed, test="preamble_stream"),
        make_case("raw-17-first-plus-three-empty-flushes", [b"A" * 17, b"B" * 37],
                  test="startup_control", extra_flushes=3),
        make_case("preamble-then-raw-17", [packed[0], b"A" * 17, b"B" * 37],
                  test="startup_control"),
        make_case("294-byte-preamble-then-repeat-65537", [packed[0], b"A" * 65537, b"B" * 37],
                  test="preamble_stream"),
    ]


def write_receiver_fixtures(directory, suite):
    """Expose the same bytes to the existing file-based compress-utils probes."""
    def save(name, value):
        data = base64.b64decode(value["base64"])
        assert len(data) == value["bytes"] and hashlib.sha256(data).hexdigest() == value["sha256"]
        (directory / name).write_bytes(data)
        return {"file": name, "bytes": value["bytes"], "sha256": value["sha256"]}

    saved = []
    for case in suite["cases"]:
        name = case["name"]
        stages = [{**{key: value for key, value in stage.items() if key != "wire"},
                   **save(f"{name}-{i}.zst", stage["wire"])}
                  for i, stage in enumerate(case["stages"])]
        saved.append({**case, "stages": stages, "sender_api": "compressobj", "midstream_flush": True,
                      "expected": save(f"{name}.bin", case["expected"]),
                      "tail": save(f"{name}-finish.zst", case["tail"])})
    (directory / "manifest.json").write_text(json.dumps({
        "native_level": suite["native_level"], "transport_chunks": suite["transport_chunks"],
        "empty_decode_calls": 0, "cases": saved,
    }))


def compress_utils_receiver(suite, receiver):
    root = Path(__file__).resolve().parents[1]
    upstream = (root / ".work/upstream").resolve()
    with tempfile.TemporaryDirectory(prefix="compress-utils-preamble-") as temporary:
        directory = Path(temporary)
        write_receiver_fixtures(directory, suite)
        if receiver == "compress_utils_python":
            command = [sys.executable, str(root / "tests/interop_python.py"), str(directory)]
        elif receiver == "compress_utils_js":
            command = ["node", str(root / "tests/interop_js.mjs"), str(directory), str(upstream), receiver]
        else:
            command = ["cargo", "run", "--locked", "--quiet", "--release", "--manifest-path",
                       str(root / "tests/rust/Cargo.toml"), "--", str(directory), "--interop"]
        env = dict(os.environ, PYTHONPATH=str(upstream / "bindings/python"))
        result = subprocess.run(command, env=env, text=True, capture_output=True, timeout=120)
    source_cases = {case["name"]: case for case in suite["cases"]}
    metadata = {key: value for key, value in suite.items() if key != "cases"}
    for line in result.stdout.splitlines():
        row = {**metadata, **json.loads(line), "binding": suite["binding"]}
        case = source_cases[row["case"]]
        if "stages" in row:
            wire_total = 0
            for observed, original in zip(row["stages"], case["stages"], strict=True):
                wire_total += original["wire"]["bytes"]
                observed.update({key: value for key, value in original.items() if key != "wire"})
                observed.update(wire_sha256=original["wire"]["sha256"], cumulative_wire_bytes=wire_total)
            row.update(finalization="test integrity check after all midstream checkpoints",
                       expected_sha256=case["expected"]["sha256"], tail_sha256=case["tail"]["sha256"])
        print(json.dumps(row), flush=True)
    print(result.stderr, end="", file=sys.stderr)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixtures", type=Path)
    parser.add_argument("--receiver", choices=["fzstd", "compress_utils_rust", "compress_utils_python",
                                              "compress_utils_js"], default="fzstd")
    args = parser.parse_args()
    manifest = json.loads((args.fixtures / "manifest.json").read_text())
    suffix = args.receiver.removeprefix("compress_utils_")
    suite = {"binding": f"preamble_{suffix}", "codec": "zstd", "sender": "python_zstandard",
             "receiver": args.receiver, "sender_api": "compressobj", "midstream_flush": True,
             "native_level": 3, "window_log": 22, "write_content_size": False,
             "write_checksum": False, "transport_chunks": manifest["transport_chunks"],
             "package_version": zstd.__version__, "zstd_version": list(zstd.ZSTD_VERSION),
             "backend": zstd.backend, "msgpack_version": msgpack.__version__,
             "pui_source_revision": PUI_REVISION, "cases": cases()}
    if args.receiver != "fzstd":
        return compress_utils_receiver(suite, args.receiver)
    result = subprocess.run(["node", str(Path(__file__).with_name("preamble_fzstd_receiver.mjs"))],
                            input=json.dumps(suite), text=True, capture_output=True, timeout=60)
    print(result.stdout, end="")
    print(result.stderr, end="", file=sys.stderr)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
