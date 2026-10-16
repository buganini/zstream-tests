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

| Sender → receiver | zstd round trips | LZ4 round trips | Required mid-stream flush round trip |
| --- | --- | --- | --- |
| compress-utils Rust → compress-utils Rust | Pass | Pass | Fails: `flush()` only flushes the sink |
| compress-utils Python → compress-utils Python | Pass | Pass | Unavailable: no flush method |
| compress-utils JS/WASM → compress-utils JS/WASM | Pass | Pass | Unavailable: no flush method |
| Python `zstandard` → Python `zstandard` | Pass | Not applicable | Pass: explicit block flush |

Each row above uses the named implementation at **both ends**. The Python
`zstandard` comparison does not use a compress-utils receiver. A pass in the
last column means that every block flush makes all bytes submitted so far
decodable **before the next write**, the same compressor/decompressor pair
continues with the frame still open, and the final round trip matches all input.
A completed round trip alone does not establish midway-flush support.

All 72 primary compress-utils round trips passed, and all 132 midpoint probes
recovered the complete input after finalization. **None of the compress-utils
bindings satisfies the live stream requirement.** Small pending payloads cannot
be forced through without ending the stream. Two additional zstd output-drain
defects affect both encoding and decoding at buffer boundaries.

The separate Python `zstandard` 0.25.0 comparison uses a `zstandard` sender and
`zstandard` receiver. It passes 12 round trips and all 44 midway-flush round-trip
cases across the sender's `compressobj()` and `stream_writer()` APIs. It uses zstd
1.5.7 at native level 11, matching compress-utils level 5. A completed block flush
makes all pending bytes decodable, and subsequent writes continue the same frame.
See the [comparison details](results/2026-10-16/README.md#python-zstandard-comparison)
for API differences and buffering measurements.

The mixed-receiver tests use Python `zstandard` as the sender, with explicit
block flushes through both sender APIs. Each receiver replays the same 46 streams
and checks every flushed prefix before receiving the next stage:

| Sender → receiver | Exact full round trip after finish | Every mid-stream flush checkpoint passes |
| --- | --- | --- |
| Python `zstandard` → compress-utils Rust | 46/46 | 34/46; decoder leaves output buffered |
| Python `zstandard` → compress-utils Python | 46/46 | 34/46; decoder leaves output buffered |
| Python `zstandard` → compress-utils JS/WASM | 46/46 | 34/46; decoder leaves output buffered |
| Python `zstandard` → JS `fzstd` 0.1.1 | 46/46 | 38/46; short initial compressed blocks stay buffered |

**Neither mixed receiver implementation meets the arbitrary mid-stream flush
requirement.** For example, a flushed 131,072-byte repeated prefix yields only
65,536 bytes through compress-utils. With fzstd, a flushed 4,096-byte repeated
prefix occupies 17 compressed bytes and yields zero decoded bytes: its initial
non-final input buffering waits for at least 18 compressed bytes. All flushed
prefixes decode fully with the Python `zstandard` reference receiver. See the
[mixed-receiver results](results/2026-10-16/INTEROP.md) for cases, causes, and
reproduction commands.

See the [results and issue details](results/2026-10-16/README.md), including exact
byte counts, source references, and raw observations.

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
