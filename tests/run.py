"""Generate shared fixtures, run every binding, and preserve raw JSONL evidence."""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REVISION = "11ea489add2435d2eb8360aad0a104a63e714fb3"
DEFAULT_TRANSPORT_CHUNKS = [1, 3, 7, 97, 4093]


def transport_chunk_size(value):
    if value == "irregular":
        return DEFAULT_TRANSPORT_CHUNKS.copy()
    if value == "whole":
        return []
    try:
        size = int(value)
        if 1 <= size <= 2147483647:
            return [size]
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("expected irregular, whole, or a byte count from 1 to 2147483647")


def fixtures(directory, transport_chunks):
    directory.mkdir(parents=True, exist_ok=True)
    size, state = 1024 * 1024 + 17, 0x12345678
    random_data = bytearray()
    for _ in range(size):
        state ^= (state << 13) & 0xFFFFFFFF
        state ^= state >> 17
        state ^= (state << 5) & 0xFFFFFFFF
        state &= 0xFFFFFFFF
        random_data.append(state & 255)
    data = {"empty": b"", "byte": b"A", "text": (b"stream bearer\n" * 300)[:4096],
            "binary": (bytes(range(256)) * 257)[:65537],
            "repeat": b"A" * size, "random": bytes(random_data)}
    cases = []
    for name, value in data.items():
        filename = f"{name}.bin"
        (directory / filename).write_bytes(value)
        cases.append({"name": name, "file": filename, "bytes": len(value),
                      "sha256": hashlib.sha256(value).hexdigest()})
    manifest = {"roundtrip": cases, "transport_chunks": transport_chunks, "midpoint_sizes":
                [1, 17, 4096, 65535, 65536, 65537, 131071, 131072, 131073, 262145, size],
                "random_generator": "xorshift32(13,17,5), seed 0x12345678, low byte per step"}
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def output(command):
    result = subprocess.run(command, text=True, capture_output=True, check=True)
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "results/latest")
    parser.add_argument("--require-midstream-flush", action="store_true")
    parser.add_argument("--transport-chunk-size", type=transport_chunk_size, default="irregular",
                        metavar="BYTES|whole|irregular",
                        help="compressed transport delivery: fixed maximum bytes, unsplit batches, "
                             "or the default repeating 1,3,7,97,4093 pattern")
    args = parser.parse_args()
    upstream = (ROOT / ".work/upstream").resolve()
    revision = output(["git", "-C", str(upstream), "rev-parse", "HEAD"])
    if revision != REVISION:
        raise SystemExit(f"Expected upstream {REVISION}, got {revision}")
    dirty = output(["git", "-C", str(upstream), "status", "--porcelain", "--untracked-files=no"])
    if dirty:
        raise SystemExit(f"Upstream tracked files changed; refuse mislabeled results:\n{dirty}")
    fixture_dir = ROOT / ".work/fixtures"
    manifest = fixtures(fixture_dir, args.transport_chunk_size)
    from interop_fixtures import generate
    interop_dir = ROOT / ".work/interop"
    interop_manifest = generate(fixture_dir, interop_dir)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "interop-fixtures.json").write_text(json.dumps(interop_manifest, indent=2) + "\n")
    env = dict(os.environ, PYTHONPATH=str(upstream / "bindings/python"))
    commands = {
        "python": [sys.executable, str(ROOT / "tests/python_probe.py"), str(fixture_dir)],
        "python_zstandard": [sys.executable, str(ROOT / "tests/python_zstandard_probe.py"), str(fixture_dir)],
        "js": ["node", str(ROOT / "tests/js_probe.mjs"), str(fixture_dir), str(upstream)],
        "rust": ["cargo", "run", "--locked", "--quiet", "--release", "--manifest-path",
                 str(ROOT / "tests/rust/Cargo.toml"), "--", str(fixture_dir)],
        "interop_python": [sys.executable, str(ROOT / "tests/interop_python.py"), str(interop_dir)],
        "interop_js": ["node", str(ROOT / "tests/interop_js.mjs"), str(interop_dir), str(upstream), "compress_utils_js"],
        "interop_fzstd": ["node", str(ROOT / "tests/interop_js.mjs"), str(interop_dir), str(upstream), "fzstd"],
        "interop_rust": ["cargo", "run", "--locked", "--quiet", "--release", "--manifest-path",
                         str(ROOT / "tests/rust/Cargo.toml"), "--", str(interop_dir), "--interop"],
        "preamble_fzstd": [sys.executable, str(ROOT / "tests/preamble_stream_probe.py"), str(fixture_dir)],
        "preamble_python": [sys.executable, str(ROOT / "tests/preamble_stream_probe.py"), str(fixture_dir),
                            "--receiver", "compress_utils_python"],
        "preamble_js": [sys.executable, str(ROOT / "tests/preamble_stream_probe.py"), str(fixture_dir),
                        "--receiver", "compress_utils_js"],
        "preamble_rust": [sys.executable, str(ROOT / "tests/preamble_stream_probe.py"), str(fixture_dir),
                          "--receiver", "compress_utils_rust"],
    }
    rows, exits = [], {}
    for binding, command in commands.items():
        try:
            result = subprocess.run(command, env=env, text=True, capture_output=True, timeout=300)
            stdout, stderr, code = result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired as error:
            stdout = (error.stdout or b"").decode() if isinstance(error.stdout, bytes) else (error.stdout or "")
            stderr, code = "Timed out after 300 seconds\n", 124
        (args.output / f"{binding}.jsonl").write_text(stdout)
        (args.output / f"{binding}.stderr").write_text(stderr)
        exits[binding] = code
        binding_rows = [json.loads(line) for line in stdout.splitlines() if line.strip()]
        expected_rows = 2 * (2 * len(manifest["roundtrip"]) + 2 * len(manifest["midpoint_sizes"]) + 2)
        if binding == "js":
            expected_rows += 2  # Web Streams close/API probe.
        elif binding == "python_zstandard":
            # One codec: round trips, both flush APIs, four boundary controls,
            # and terminal/truncated checks.
            expected_rows = 2 * len(manifest["roundtrip"]) + 4 * len(manifest["midpoint_sizes"]) + 6
        elif binding.startswith("interop_"):
            expected_rows = len(interop_manifest["cases"])
        elif binding.startswith("preamble_"):
            expected_rows = 4  # Message sequence, 64 KiB boundary, two startup controls.
        if len(binding_rows) != expected_rows:
            exits[binding] = code or 1
        rows.extend(binding_rows)
        print(binding, dict(collections.Counter(r["status"] for r in binding_rows)), f"exit={exits[binding]}", flush=True)
    control = subprocess.run([str(ROOT / ".work/native_zstd_control"), str(fixture_dir / "random.bin")],
                             text=True, capture_output=True, timeout=30)
    (args.output / "native-control.jsonl").write_text(control.stdout)
    (args.output / "native-control.stderr").write_text(control.stderr)
    exits["native_control"] = control.returncode
    bad = any(exits.values()) or any(r["status"] == "FAIL" for r in rows)
    midstream_tests = ("midpoint", "midpoint_writer", "sender_flush", "preamble_stream")
    midstream_ok = not any(r["test"] in midstream_tests and r["status"] != "PASS" for r in rows)
    by_binding = {binding: [r for r in rows if r["binding"] == binding] for binding in commands}
    reference = by_binding["python_zstandard"][0] if by_binding["python_zstandard"] else {}
    if args.require_midstream_flush:
        bad |= any(r["status"] == "LIMITATION" for r in rows)
    summary = {"upstream_revision": revision, "upstream_tracked_clean": not dirty,
               "platform": platform.platform(), "machine": platform.machine(),
               "python": sys.version, "node": output(["node", "--version"]),
               "rustc": output(["rustc", "--version"]), "cargo": output(["cargo", "--version"]),
               "cmake": output(["cmake", "--version"]).splitlines()[0],
               "cc": output(["cc", "--version"]).splitlines()[0],
               "zig": output(["zig", "version"]),
               "codec_versions": json.loads((upstream / "codec-versions.json").read_text()),
               "level": 5, "fixtures": manifest, "exit_codes": exits,
               "transport_chunks": args.transport_chunk_size,
               "midstream_acceptance_passed": midstream_ok and not any(exits.values()),
               "require_midstream_flush": args.require_midstream_flush, "runner_exit_code": int(bad),
               "counts": dict(collections.Counter(r["status"] for r in rows)),
               "counts_by_binding": {binding: dict(collections.Counter(r["status"] for r in observations))
                                     for binding, observations in by_binding.items()},
               "midstream_acceptance_by_binding": {
                   binding: not exits[binding] and any(r["test"] in midstream_tests for r in observations)
                   and all(r["status"] == "PASS" for r in observations if r["test"] in midstream_tests)
                   for binding, observations in by_binding.items()},
               "python_zstandard": {"package_version": reference.get("package_version"),
                                    "zstd_version": reference.get("zstd_version"),
                                    "backend": reference.get("backend"),
                                    "native_level": reference.get("level"),
                                    "compress_utils_equivalent_level": 5},
               "fzstd": json.loads((ROOT / "tests/node_modules/fzstd/package.json").read_text())["version"],
               "commands": commands}
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return int(bad)


if __name__ == "__main__":
    sys.exit(main())
