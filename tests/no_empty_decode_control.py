"""Replay recorded no-flush cases without speculative empty decoder calls."""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path, help="directory containing a completed runner summary")
    parser.add_argument("--fixtures", type=Path, default=ROOT / ".work/interop")
    args = parser.parse_args()
    upstream = (ROOT / ".work/upstream").resolve()
    recorded = json.loads((args.results / "summary.json").read_text())
    revision = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True).strip()
    assert revision == recorded["upstream_revision"], "control must use the recorded upstream revision"
    assert not subprocess.check_output(
        ["git", "-C", str(upstream), "status", "--porcelain", "--untracked-files=no"], text=True).strip()
    manifest = json.loads((args.results / "interop-fixtures.json").read_text())
    manifest["cases"] = [case for case in manifest["cases"] if not case["midstream_flush"]]
    manifest["empty_decode_calls"] = 0
    assert len(manifest["cases"]) == 18
    counts, exits = {}, {}
    with tempfile.TemporaryDirectory(prefix="compress-utils-no-empty-") as directory:
        view = Path(directory)
        for case in manifest["cases"]:
            for item in [*case["stages"], case["tail"], case["expected"]]:
                source = (args.fixtures / item["file"]).resolve()
                assert hashlib.sha256(source.read_bytes()).hexdigest() == item["sha256"]
                (view / item["file"]).symlink_to(source)
        (view / "manifest.json").write_text(json.dumps(manifest) + "\n")
        commands = {
            "interop_python_no_empty": [sys.executable, str(ROOT / "tests/interop_python.py"), str(view)],
            "interop_js_no_empty": ["node", str(ROOT / "tests/interop_js.mjs"), str(view),
                                    str(upstream), "compress_utils_js"],
        }
        for binding, command in commands.items():
            result = subprocess.run(command, env=dict(os.environ, PYTHONPATH=str(upstream / "bindings/python")),
                                    text=True, capture_output=True, timeout=300)
            rows = [dict(json.loads(line), binding=binding, empty_decode_calls=0)
                    for line in result.stdout.splitlines() if line.strip()]
            exits[binding] = result.returncode or int(len(rows) != 18)
            counts[binding] = dict(collections.Counter(row["status"] for row in rows))
            (args.results / f"{binding}.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
            (args.results / f"{binding}.stderr").write_text(result.stderr)
            print(binding, counts[binding], f"exit={exits[binding]}", flush=True)
    failed = any(exits.values()) or any(count.get("PASS", 0) != 18 for count in counts.values())
    summary = {"upstream_revision": revision, "transport_chunks": manifest["transport_chunks"],
               "empty_decode_calls": 0, "counts_by_binding": counts, "exit_codes": exits,
               "runner_exit_code": int(failed), "fixture_hashes_verified": True,
               "scope": "18 ordinary no-flush cases per receiver; recorded separately from main suite"}
    (args.results / "no-empty-decode-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
