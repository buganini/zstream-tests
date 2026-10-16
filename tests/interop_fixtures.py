"""Produce shared, phased zstandard sender streams for all receiver bindings."""
import hashlib
import json
from pathlib import Path

import zstandard as zstd
from python_zstandard_probe import ObjectEncoder, WriterEncoder, decoder, receive, complete, NATIVE_LEVEL


def generate(fixture_dir, directory):
    directory.mkdir(parents=True, exist_ok=True)
    fixtures = json.loads((fixture_dir / "manifest.json").read_text())
    inputs = [("empty", b"")]
    for kind in ("random", "repeat"):
        data = (fixture_dir / f"{kind}.bin").read_bytes()
        inputs.extend((f"{kind}-{size}", data[:size]) for size in fixtures["midpoint_sizes"])

    def save(name, data):
        (directory / name).write_bytes(data)
        return {"file": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

    cases = []
    for api, encoder_type in (("compressobj", ObjectEncoder), ("stream_writer", WriterEncoder)):
        for name, data in inputs:
            case_id = f"{api}-{name}"
            encoder, reference = encoder_type(), decoder()
            expected = decoded = b""
            stages = []
            for i, part in enumerate((data, b"B" * 37, bytes(range(256)) * 16, b"")):
                expected += part
                write_output = encoder.compress(part)
                flush_output = encoder.flush_block()
                wire = write_output + flush_output
                decoded += receive(reference, wire)
                assert decoded == expected and not reference.eof
                stages.append({**save(f"{case_id}-{i}.zst", wire),
                               "submitted": len(expected), "write_output": len(write_output),
                               "flush_output": len(flush_output), "reference_decoded": len(decoded),
                               "reference_eof": reference.eof})
            tail = encoder.finish()
            decoded += receive(reference, tail)
            complete(reference)
            assert decoded == expected
            cases.append({"name": case_id, "payload": name, "sender_api": api, "stages": stages,
                          "tail": save(f"{case_id}-finish.zst", tail),
                          "expected": save(f"{case_id}.bin", expected), "reference_final_eof": True})
    manifest = {"sender": "python_zstandard", "package_version": zstd.__version__,
                "zstd_version": list(zstd.ZSTD_VERSION), "backend": zstd.backend,
                "native_level": NATIVE_LEVEL, "transport_chunks": [1, 3, 7, 97, 4093], "cases": cases}
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    import sys
    generate(Path(sys.argv[1]), Path(sys.argv[2]))
