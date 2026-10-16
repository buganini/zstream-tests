"""Produce shared, phased zstandard sender streams for all receiver bindings."""
import hashlib
import json
from pathlib import Path

import zstandard as zstd
from python_zstandard_probe import ObjectEncoder, WriterEncoder, chunks, decoder, receive, complete, NATIVE_LEVEL


def generate(fixture_dir, directory):
    directory.mkdir(parents=True, exist_ok=True)
    fixtures = json.loads((fixture_dir / "manifest.json").read_text())
    transport_chunks = fixtures.get("transport_chunks", [1, 3, 7, 97, 4093])
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
                decoded += receive(reference, wire, transport_chunks)
                assert decoded == expected and not reference.eof
                stages.append({**save(f"{case_id}-{i}.zst", wire),
                               "submitted": len(expected), "write_output": len(write_output),
                               "flush_output": len(flush_output), "reference_decoded": len(decoded),
                               "reference_eof": reference.eof})
            tail = encoder.finish()
            decoded += receive(reference, tail, transport_chunks)
            complete(reference)
            assert decoded == expected
            cases.append({"name": case_id, "payload": name, "sender_api": api, "stages": stages,
                          "test": "sender_flush", "midstream_flush": True,
                          "tail": save(f"{case_id}-finish.zst", tail),
                          "expected": save(f"{case_id}.bin", expected), "reference_final_eof": True})

    # No nonterminal flush: a complete one-shot frame or incremental writes
    # followed by exactly one finalization. Partial prefixes are allowed here.
    input_chunks = (1, 7, 63, 1024, 65521)
    for api, encoder_type in (("oneshot", None), ("compressobj", ObjectEncoder),
                              ("stream_writer", WriterEncoder)):
        for fixture in fixtures["roundtrip"]:
            data = (fixture_dir / fixture["file"]).read_bytes()
            case_id = f"no-flush-{api}-{fixture['name']}"
            reference, decoded, stages = decoder(), b"", []
            if encoder_type is None:
                tail = zstd.ZstdCompressor(level=NATIVE_LEVEL).compress(data)
            else:
                encoder, submitted = encoder_type(), 0
                for i, part in enumerate(chunks(data, input_chunks)):
                    submitted += len(part)
                    wire = encoder.compress(part)
                    decoded += receive(reference, wire, transport_chunks)
                    assert len(decoded) <= submitted and decoded == data[:len(decoded)]
                    assert not reference.eof
                    stages.append({**save(f"{case_id}-{i}.zst", wire),
                                   "submitted": submitted, "write_output": len(wire),
                                   "flush_output": 0, "reference_decoded": len(decoded),
                                   "reference_eof": reference.eof})
                tail = encoder.finish()
            decoded += receive(reference, tail, transport_chunks)
            complete(reference)
            assert decoded == data
            cases.append({"name": case_id, "payload": fixture["name"], "sender_api": api,
                          "test": "oneshot_roundtrip" if encoder_type is None else "stream_roundtrip",
                          "midstream_flush": False, "stages": stages,
                          "tail": save(f"{case_id}-finish.zst", tail),
                          "expected": save(f"{case_id}.bin", data), "reference_final_eof": True})
    manifest = {"sender": "python_zstandard", "package_version": zstd.__version__,
                "zstd_version": list(zstd.ZSTD_VERSION), "backend": zstd.backend,
                "native_level": NATIVE_LEVEL, "transport_chunks": transport_chunks,
                "no_flush_input_chunks": list(input_chunks), "cases": cases}
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    import sys
    generate(Path(sys.argv[1]), Path(sys.argv[2]))
