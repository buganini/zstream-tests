# compress-utils testing

This repository is a workspace for testing
[dupontcyborg/compress-utils](https://github.com/dupontcyborg/compress-utils),
a compression and decompression library with bindings for multiple languages.

The intended use is to use compress-utils as the compression layer of a live byte
stream (a stream bearer), using **Zstandard (zstd)** or **LZ4**. Data arrives
incrementally, and the receiver must be able to consume it while the stream
remains open.

Use this repository to collect test cases, reproducible bug reports, and results
for that use case.

## Required streaming behavior

**Flushing in the middle of the stream is required.** A flush must make all input
submitted so far available to the receiver without ending the compressed stream.

- The sender can write data, flush, then write more data using the same compressor
  and stream.
- After receiving all output through a completed flush, the receiver can recover
  every byte submitted before that flush without waiting for more input or EOF.
- Flush completion must be observable so the caller knows when all pending output
  has been drained, including when output buffers are small.
- The same decompressor continues across repeated flushes. A flush must not
  require finalizing and restarting the stream.
- Finalization is a separate operation performed when the sender closes the
  stream.

Test this behavior independently for zstd and LZ4 through the compress-utils API
and the selected language binding. Support in an underlying codec alone does not
establish that the wrapper exposes the required behavior.

## Current status

Tested on 2026-10-16 against upstream commit
[`11ea489`](https://github.com/dupontcyborg/compress-utils/commit/11ea489add2435d2eb8360aad0a104a63e714fb3)
(source version 0.9.0), using compression level 5.

Each row is one sender/receiver configuration. **No** checks a completed round
trip without requesting a mid-stream flush. **Yes** requires every flushed prefix
to be fully decoded before the next write, continued use of the same open frame,
and an exact final round trip. Counts show passing cases out of tested cases;
**NG** means the configuration does not satisfy that row's requirement.

| Sender (package/binding · algorithm) | Receiver (package/binding) | Mid-stream flush | OK / NG |
| --- | --- | --- | --- |
| compress-utils / Rust · zstd | compress-utils / Rust | No | OK (12/12) |
| compress-utils / Rust · zstd | compress-utils / Rust | Yes (attempted) | NG (0/22) |
| compress-utils / Rust · LZ4 | compress-utils / Rust | No | OK (12/12) |
| compress-utils / Rust · LZ4 | compress-utils / Rust | Yes (attempted) | NG (0/22) |
| compress-utils / Python · zstd | compress-utils / Python | No | OK (12/12) |
| compress-utils / Python · zstd | compress-utils / Python | Yes (attempted) | NG (0/22) |
| compress-utils / Python · LZ4 | compress-utils / Python | No | OK (12/12) |
| compress-utils / Python · LZ4 | compress-utils / Python | Yes (attempted) | NG (0/22) |
| compress-utils / JS/WASM · zstd | compress-utils / JS/WASM | No | OK (12/12) |
| compress-utils / JS/WASM · zstd | compress-utils / JS/WASM | Yes (attempted) | NG (0/22) |
| compress-utils / JS/WASM · LZ4 | compress-utils / JS/WASM | No | OK (12/12) |
| compress-utils / JS/WASM · LZ4 | compress-utils / JS/WASM | Yes (attempted) | NG (0/22) |
| zstandard / Python · zstd | zstandard / Python | No | OK (12/12) |
| zstandard / Python · zstd | zstandard / Python | Yes | OK (44/44) |
| zstandard / Python · zstd | compress-utils / Rust | Yes | NG (34/46) |
| zstandard / Python · zstd | compress-utils / Python | Yes | NG (34/46) |
| zstandard / Python · zstd | compress-utils / JS/WASM | Yes | NG (34/46) |
| zstandard / Python · zstd | fzstd / JavaScript | Yes | NG (38/46) |

Each **No** row covers six one-shot and six incremental round trips. The Python
`zstandard` **Yes** rows combine its `compressobj()` and `stream_writer()` block
flush APIs: 22 cases each with its own receiver, or 23 cases each with mixed
receivers (including an initially empty prefix). Untested configurations are not
listed. The receiver always decodes the algorithm specified in the sender cell.

For compress-utils, **Yes (attempted)** records the required behavior being
probed: Rust's `flush()` only flushes the sink; Python and JS expose no flush
method. Empty writes also fail to flush pending codec data. All 132 midpoint
cases still recover the complete input after finalization, but none passes every
mid-stream checkpoint.

Python `zstandard` 0.25.0 uses zstd 1.5.7 at native level 11, matching
compress-utils level 5. With Python `zstandard` at both ends, all 44 explicit
block-flush cases pass. See the [comparison details](results/2026-10-16/README.md#python-zstandard-comparison).

With mixed receivers, all 184 cases recover the full input after finalization,
but some flushed prefixes stay buffered. Compress-utils returns only 65,536 of
131,072 repeated bytes at a checkpoint. fzstd 0.1.1 waits for at least 18 initial
compressed bytes, so a flushed 4,096-byte repeated payload compressed to 17 bytes
yields zero decoded bytes. Neither receiver meets the arbitrary mid-stream flush
requirement. See the [mixed-receiver results](results/2026-10-16/INTEROP.md).

The [detailed report](results/2026-10-16/README.md) contains buffering measurements,
source references, additional diagnostic checks, and raw observations.

## Run the tests

Prerequisites: Git, a C/C++ compiler, CMake, Ninja, Python with `venv`/pip, Node.js
with npm, Rust/Cargo, and Zig on `PATH`. The recorded run used Python 3.14.4,
Node 22.22.1, npm 10.9.4, Rust 1.90.0, CMake 4.2.3, and Zig 0.14.1.

```sh
bash tests/setup.sh
.work/venv/bin/python tests/run.py --require-midstream-flush
```

Setup downloads the pinned upstream source and build dependencies, builds its
unmodified bindings, and compiles the probes. It installs pybind11 3.0.1 and
zstandard 0.25.0 into a local virtual environment and fzstd 0.1.1 into
`tests/node_modules/`. Generated dependencies, builds, and fixtures stay in ignored
directories: `.work/`, `node_modules/`, and Rust's `target/`.

The strict command currently **exits 1**, because the compress-utils and fzstd
tests include unmet flush checkpoints; Python `zstandard` at both ends passes.
Raw JSONL observations and a summary are written to `results/latest/`.
Omit `--require-midstream-flush` to check completed round trips while recording
known flush limitations without failing the command. A round-trip mismatch,
missing observations, or a probe execution error still fails that mode.

`tests/run.py --output <directory>` selects another result directory. The shared
fixtures are generated deterministically; their SHA-256 hashes are recorded in
the result summary. The native zstd control isolates the two drain defects and
is counted separately from the binding tests.

Once the runner has generated `.work/fixtures`, run just the comparison with:

```sh
.work/venv/bin/python tests/python_zstandard_probe.py .work/fixtures
```

This comparison exits 0 only when all 62 checks pass. Use
`compressobj.flush(zstandard.COMPRESSOBJ_FLUSH_BLOCK)` or
`stream_writer.flush(zstandard.FLUSH_BLOCK)` for midway flushing. The default
`compressobj.flush()` finishes the frame. At transport closure, verify the
incremental decoder's `eof` flag; its `flush()` method does not validate completion.

## Core acceptance test

Run the following sequence for each codec:

1. Create one compressor and one decompressor.
2. Write payload A and complete a flush, draining all compressed output.
3. Deliver the output to the decompressor in small, irregular chunks. Assert that
   payload A is fully recovered while the compressed stream remains open and
   before payload B is written.
4. Write payload B through the same compressor and flush again.
5. Feed the new output to the same decompressor. Assert that the accumulated
   decoded bytes equal A followed by B, with no loss or duplication.
6. Repeat with further payloads and flushes, including an empty flush.
7. Finalize the compressor, deliver its remaining output, and verify successful
   end-of-stream detection and an exact match with all original input.

The write, flush, and finish steps must handle partial consumption and output
buffer limits according to the API. Passing only a round trip after finalization
does not satisfy this acceptance test.

## Coverage and remaining work

- Mid-stream flush and continued decoding for both zstd and LZ4, as described
  above. This is the primary acceptance criterion; compress-utils fails it,
  while the Python `zstandard` comparison passes for zstd.
- Incremental input and output: tiny buffers, irregular transport chunks, and
  repeated write/flush cycles.
- Round-trip correctness for empty inputs, binary data, and large inputs.
- Truncation detection and the terminal behavior of `finish()` are tested.
- Python `zstandard` sender interoperability with compress-utils receivers in
  Rust/Python/JS and the JS fzstd receiver is tested, including mid-stream flush.
- Still to test: invalid options, broader malformed-data cases, other
  sender/receiver combinations, LZ4 interoperability, external tools, and real
  network transports.
- Performance benchmarking (including flush latency and memory use) remains
  future work. The current results are correctness and buffering observations.

## Testing workflow

1. Choose the upstream revision and language binding to evaluate.
2. Follow the upstream [development guide](https://github.com/dupontcyborg/compress-utils/blob/main/DEVELOPMENT.md)
   to set up the library and run its existing tests in a separate checkout.
3. Add focused test cases or reproductions here, with exact commands and required
   dependencies.
4. Record the upstream commit, operating system, architecture, toolchain versions,
   algorithm, compression settings, and input details with each result.
5. Document expected and actual behavior. For failures, include the smallest
   practical reproduction and relevant output.

Keep generated build artifacts and large datasets out of version control. When a
test needs external data, document its source, checksum, and preparation steps.
