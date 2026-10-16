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


def fixtures(directory):
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
    manifest = {"roundtrip": cases, "midpoint_sizes":
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
    args = parser.parse_args()
    upstream = (ROOT / ".work/upstream").resolve()
    revision = output(["git", "-C", str(upstream), "rev-parse", "HEAD"])
    if revision != REVISION:
        raise SystemExit(f"Expected upstream {REVISION}, got {revision}")
    dirty = output(["git", "-C", str(upstream), "status", "--porcelain", "--untracked-files=no"])
    if dirty:
        raise SystemExit(f"Upstream tracked files changed; refuse mislabeled results:\n{dirty}")
    fixture_dir = ROOT / ".work/fixtures"
    manifest = fixtures(fixture_dir)
    args.output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONPATH=str(upstream / "bindings/python"))
    commands = {
        "python": [sys.executable, str(ROOT / "tests/python_probe.py"), str(fixture_dir)],
        "js": ["node", str(ROOT / "tests/js_probe.mjs"), str(fixture_dir), str(upstream)],
        "rust": ["cargo", "run", "--locked", "--quiet", "--release", "--manifest-path",
                 str(ROOT / "tests/rust/Cargo.toml"), "--", str(fixture_dir)],
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
    midstream_ok = not any(r["test"] == "midpoint" and r["status"] != "PASS" for r in rows)
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
               "midstream_acceptance_passed": midstream_ok and not any(exits.values()),
               "require_midstream_flush": args.require_midstream_flush, "runner_exit_code": int(bad),
               "counts": dict(collections.Counter(r["status"] for r in rows)),
               "commands": commands}
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return int(bad)


if __name__ == "__main__":
    sys.exit(main())
