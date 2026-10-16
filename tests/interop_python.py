"""Python zstandard sender -> compress-utils Python receiver."""
import json
from pathlib import Path
import sys

import compress_utils as cu
from python_zstandard_probe import receive


def probe(root, case):
    decoder = cu.DecompressStream("zstd")
    expected = (root / case["expected"]["file"]).read_bytes()
    decoded = b""
    stages = []
    for stage in case["stages"]:
        wire = (root / stage["file"]).read_bytes()
        decoded += receive(decoder, wire)
        empty = b"".join(decoder.decompress(b"") for _ in range(3))
        decoded += empty
        assert decoded == expected[:len(decoded)] and len(decoded) <= stage["submitted"]
        stages.append({"submitted": stage["submitted"], "decoded": len(decoded),
                       "wire_bytes": len(wire), "empty_decode_output": len(empty),
                       "complete": len(decoded) == stage["submitted"]})
    decoded += receive(decoder, (root / case["tail"]["file"]).read_bytes())
    decoded += decoder.finish()
    assert decoded == expected
    passed = not case["midstream_flush"] or all(s["complete"] for s in stages)
    return {"status": "PASS" if passed else "LIMITATION",
            "stages": stages, "final_roundtrip": True, "final_bytes": len(decoded)}


def main():
    root = Path(sys.argv[1])
    manifest = json.loads((root / "manifest.json").read_text())
    failed = False
    for case in manifest["cases"]:
        row = {"binding": "interop_python", "test": case["test"], "codec": "zstd",
               "sender": "python_zstandard", "receiver": "compress_utils_python",
               "case": case["name"], "sender_api": case["sender_api"],
               "midstream_flush": case["midstream_flush"],
               "native_level": manifest["native_level"], "receiver_version": cu.version()}
        try:
            row.update(probe(root, case))
        except Exception as error:
            row.update(status="FAIL", error=f"{type(error).__name__}: {error}")
        print(json.dumps(row), flush=True)
        failed |= row["status"] == "FAIL"
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
