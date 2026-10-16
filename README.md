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
(source version 0.9.0), using compression level 5. The separate 294-byte preamble
case uses native zstd level 3 and a 4 MiB window.

Each row is one sender/receiver configuration. **No** checks a completed round
trip without requesting a mid-stream flush. **Yes** requires every flushed prefix
to be fully decoded before the next write, continued use of the same open frame,
and an exact final round trip. The pass percentage is the share of tested cases
meeting all requirements, followed by passing/total case counts. Anything below
100% leaves the requested behavior unmet. These percentages describe the
fixtures, not estimated success rates for arbitrary traffic.

Transport chunk size controls compressed bytes delivered to the receiver, not
the application payload size before a flush. A fixed size is a maximum: the last
chunk can be shorter. The irregular pattern repeats; `whole` delivers each
write/flush batch without harness fragmentation. Rust still limits source reads
to its internal read buffer. No profile combines data across flush checkpoints.

| Sender | Receiver (package/binding) | Mid-stream flush | Transport chunk (bytes) | Pass percentage (pass/all) |
| --- | --- | --- | --- | --- |
| compress-utils / Rust · zstd | compress-utils / Rust | No | 1, 3, 7, 97, 4093 | 100% (12/12) |
| compress-utils / Rust · zstd | compress-utils / Rust | No | 1 | 100% (12/12) |
| compress-utils / Rust · zstd | compress-utils / Rust | No | 4096 | 100% (12/12) |
| compress-utils / Rust · zstd | compress-utils / Rust | No | whole | 100% (12/12) |
| compress-utils / Rust · zstd | compress-utils / Rust | Yes (attempted) | 1, 3, 7, 97, 4093 | 0% (0/22) |
| compress-utils / Rust · zstd | compress-utils / Rust | Yes (attempted) | 1 | 0% (0/22) |
| compress-utils / Rust · zstd | compress-utils / Rust | Yes (attempted) | 4096 | 0% (0/22) |
| compress-utils / Rust · zstd | compress-utils / Rust | Yes (attempted) | whole | 0% (0/22) |
| compress-utils / Rust · LZ4 | compress-utils / Rust | No | 1, 3, 7, 97, 4093 | 100% (12/12) |
| compress-utils / Rust · LZ4 | compress-utils / Rust | No | 1 | 100% (12/12) |
| compress-utils / Rust · LZ4 | compress-utils / Rust | No | 4096 | 100% (12/12) |
| compress-utils / Rust · LZ4 | compress-utils / Rust | No | whole | 100% (12/12) |
| compress-utils / Rust · LZ4 | compress-utils / Rust | Yes (attempted) | 1, 3, 7, 97, 4093 | 0% (0/22) |
| compress-utils / Rust · LZ4 | compress-utils / Rust | Yes (attempted) | 1 | 0% (0/22) |
| compress-utils / Rust · LZ4 | compress-utils / Rust | Yes (attempted) | 4096 | 0% (0/22) |
| compress-utils / Rust · LZ4 | compress-utils / Rust | Yes (attempted) | whole | 0% (0/22) |
| compress-utils / Python · zstd | compress-utils / Python | No | 1, 3, 7, 97, 4093 | 100% (12/12) |
| compress-utils / Python · zstd | compress-utils / Python | No | 1 | 100% (12/12) |
| compress-utils / Python · zstd | compress-utils / Python | No | 4096 | 100% (12/12) |
| compress-utils / Python · zstd | compress-utils / Python | No | whole | 100% (12/12) |
| compress-utils / Python · zstd | compress-utils / Python | Yes (attempted) | 1, 3, 7, 97, 4093 | 0% (0/22) |
| compress-utils / Python · zstd | compress-utils / Python | Yes (attempted) | 1 | 0% (0/22) |
| compress-utils / Python · zstd | compress-utils / Python | Yes (attempted) | 4096 | 0% (0/22) |
| compress-utils / Python · zstd | compress-utils / Python | Yes (attempted) | whole | 0% (0/22) |
| compress-utils / Python · LZ4 | compress-utils / Python | No | 1, 3, 7, 97, 4093 | 100% (12/12) |
| compress-utils / Python · LZ4 | compress-utils / Python | No | 1 | 100% (12/12) |
| compress-utils / Python · LZ4 | compress-utils / Python | No | 4096 | 100% (12/12) |
| compress-utils / Python · LZ4 | compress-utils / Python | No | whole | 100% (12/12) |
| compress-utils / Python · LZ4 | compress-utils / Python | Yes (attempted) | 1, 3, 7, 97, 4093 | 0% (0/22) |
| compress-utils / Python · LZ4 | compress-utils / Python | Yes (attempted) | 1 | 0% (0/22) |
| compress-utils / Python · LZ4 | compress-utils / Python | Yes (attempted) | 4096 | 0% (0/22) |
| compress-utils / Python · LZ4 | compress-utils / Python | Yes (attempted) | whole | 0% (0/22) |
| compress-utils / JS/WASM · zstd | compress-utils / JS/WASM | No | 1, 3, 7, 97, 4093 | 100% (12/12) |
| compress-utils / JS/WASM · zstd | compress-utils / JS/WASM | No | 1 | 100% (12/12) |
| compress-utils / JS/WASM · zstd | compress-utils / JS/WASM | No | 4096 | 100% (12/12) |
| compress-utils / JS/WASM · zstd | compress-utils / JS/WASM | No | whole | 100% (12/12) |
| compress-utils / JS/WASM · zstd | compress-utils / JS/WASM | Yes (attempted) | 1, 3, 7, 97, 4093 | 0% (0/22) |
| compress-utils / JS/WASM · zstd | compress-utils / JS/WASM | Yes (attempted) | 1 | 0% (0/22) |
| compress-utils / JS/WASM · zstd | compress-utils / JS/WASM | Yes (attempted) | 4096 | 0% (0/22) |
| compress-utils / JS/WASM · zstd | compress-utils / JS/WASM | Yes (attempted) | whole | 0% (0/22) |
| compress-utils / JS/WASM · LZ4 | compress-utils / JS/WASM | No | 1, 3, 7, 97, 4093 | 100% (12/12) |
| compress-utils / JS/WASM · LZ4 | compress-utils / JS/WASM | No | 1 | 100% (12/12) |
| compress-utils / JS/WASM · LZ4 | compress-utils / JS/WASM | No | 4096 | 100% (12/12) |
| compress-utils / JS/WASM · LZ4 | compress-utils / JS/WASM | No | whole | 100% (12/12) |
| compress-utils / JS/WASM · LZ4 | compress-utils / JS/WASM | Yes (attempted) | 1, 3, 7, 97, 4093 | 0% (0/22) |
| compress-utils / JS/WASM · LZ4 | compress-utils / JS/WASM | Yes (attempted) | 1 | 0% (0/22) |
| compress-utils / JS/WASM · LZ4 | compress-utils / JS/WASM | Yes (attempted) | 4096 | 0% (0/22) |
| compress-utils / JS/WASM · LZ4 | compress-utils / JS/WASM | Yes (attempted) | whole | 0% (0/22) |
| zstandard / Python | zstandard / Python | No | 1, 3, 7, 97, 4093 | 100% (12/12) |
| zstandard / Python | zstandard / Python | No | 1 | 100% (12/12) |
| zstandard / Python | zstandard / Python | No | 4096 | 100% (12/12) |
| zstandard / Python | zstandard / Python | No | whole | 100% (12/12) |
| zstandard / Python | zstandard / Python | Yes | 1, 3, 7, 97, 4093 | 100% (44/44) |
| zstandard / Python | zstandard / Python | Yes | 1 | 100% (44/44) |
| zstandard / Python | zstandard / Python | Yes | 4096 | 100% (44/44) |
| zstandard / Python | zstandard / Python | Yes | whole | 100% (44/44) |
| zstandard / Python | compress-utils / Rust | No | 1, 3, 7, 97, 4093 | 100% (18/18) |
| zstandard / Python | compress-utils / Rust | No | 1 | 100% (18/18) |
| zstandard / Python | compress-utils / Rust | No | 4096 | 100% (18/18) |
| zstandard / Python | compress-utils / Rust | No | whole | 100% (18/18) |
| zstandard / Python | compress-utils / Rust | Yes | 1, 3, 7, 97, 4093 | 73.91% (34/46) |
| zstandard / Python | compress-utils / Rust | Yes | 1 | 86.96% (40/46) |
| zstandard / Python | compress-utils / Rust | Yes | 4096 | 73.91% (34/46) |
| zstandard / Python | compress-utils / Rust | Yes | whole | 73.91% (34/46) |
| zstandard / Python | compress-utils / Python | No | 1, 3, 7, 97, 4093 | 100% (18/18) |
| zstandard / Python | compress-utils / Python | No | 1 | 100% (18/18) |
| zstandard / Python | compress-utils / Python | No | 4096 | 100% (18/18) |
| zstandard / Python | compress-utils / Python | No | whole | 100% (18/18) |
| zstandard / Python | compress-utils / Python | Yes | 1, 3, 7, 97, 4093 | 73.91% (34/46) |
| zstandard / Python | compress-utils / Python | Yes | 1 | 86.96% (40/46) |
| zstandard / Python | compress-utils / Python | Yes | 4096 | 73.91% (34/46) |
| zstandard / Python | compress-utils / Python | Yes | whole | 47.83% (22/46) |
| zstandard / Python | compress-utils / JS/WASM | No | 1, 3, 7, 97, 4093 | 100% (18/18) |
| zstandard / Python | compress-utils / JS/WASM | No | 1 | 100% (18/18) |
| zstandard / Python | compress-utils / JS/WASM | No | 4096 | 100% (18/18) |
| zstandard / Python | compress-utils / JS/WASM | No | whole | 100% (18/18) |
| zstandard / Python | compress-utils / JS/WASM | Yes | 1, 3, 7, 97, 4093 | 73.91% (34/46) |
| zstandard / Python | compress-utils / JS/WASM | Yes | 1 | 86.96% (40/46) |
| zstandard / Python | compress-utils / JS/WASM | Yes | 4096 | 73.91% (34/46) |
| zstandard / Python | compress-utils / JS/WASM | Yes | whole | 47.83% (22/46) |
| zstandard / Python | fzstd / JavaScript | No | 1, 3, 7, 97, 4093 | 100% (18/18) |
| zstandard / Python | fzstd / JavaScript | No | 1 | 100% (18/18) |
| zstandard / Python | fzstd / JavaScript | No | 4096 | 100% (18/18) |
| zstandard / Python | fzstd / JavaScript | No | whole | 100% (18/18) |
| zstandard / Python | fzstd / JavaScript | Yes | 1, 3, 7, 97, 4093 | 82.61% (38/46) |
| zstandard / Python | fzstd / JavaScript | Yes | 1 | 82.61% (38/46) |
| zstandard / Python | fzstd / JavaScript | Yes | 4096 | 82.61% (38/46) |
| zstandard / Python | fzstd / JavaScript | Yes | whole | 82.61% (38/46) |
| zstandard / Python (294-byte preamble) | compress-utils / Rust | Yes | 1, 3, 7, 97, 4093 | 50% (1/2) |
| zstandard / Python (294-byte preamble) | compress-utils / Rust | Yes | 1 | 50% (1/2) |
| zstandard / Python (294-byte preamble) | compress-utils / Rust | Yes | 4096 | 50% (1/2) |
| zstandard / Python (294-byte preamble) | compress-utils / Rust | Yes | whole | 50% (1/2) |
| zstandard / Python (294-byte preamble) | compress-utils / Python | Yes | 1, 3, 7, 97, 4093 | 50% (1/2) |
| zstandard / Python (294-byte preamble) | compress-utils / Python | Yes | 1 | 50% (1/2) |
| zstandard / Python (294-byte preamble) | compress-utils / Python | Yes | 4096 | 50% (1/2) |
| zstandard / Python (294-byte preamble) | compress-utils / Python | Yes | whole | 50% (1/2) |
| zstandard / Python (294-byte preamble) | compress-utils / JS/WASM | Yes | 1, 3, 7, 97, 4093 | 50% (1/2) |
| zstandard / Python (294-byte preamble) | compress-utils / JS/WASM | Yes | 1 | 50% (1/2) |
| zstandard / Python (294-byte preamble) | compress-utils / JS/WASM | Yes | 4096 | 50% (1/2) |
| zstandard / Python (294-byte preamble) | compress-utils / JS/WASM | Yes | whole | 50% (1/2) |
| zstandard / Python (294-byte preamble) | fzstd / JavaScript | Yes | 1, 3, 7, 97, 4093 | 100% (2/2) |
| zstandard / Python (294-byte preamble) | fzstd / JavaScript | Yes | 1 | 100% (2/2) |
| zstandard / Python (294-byte preamble) | fzstd / JavaScript | Yes | 4096 | 100% (2/2) |
| zstandard / Python (294-byte preamble) | fzstd / JavaScript | Yes | whole | 100% (2/2) |

The **No** rows with the same package at both ends cover six one-shot and six
incremental round trips. The mixed-receiver **No** rows cover six payloads through
each of three sender APIs: one-shot compression, `compressobj()`, and
`stream_writer()` (18 cases per receiver). Neither incremental sender calls a
mid-stream flush; both finalize only after all input has been written. Partial
decoded prefixes before finalization are allowed in these tests.

The ordinary Python `zstandard` **Yes** rows combine its `compressobj()` and
`stream_writer()` block flush APIs: 22 cases each with its own receiver, or 23
cases each with mixed receivers (including an initially empty prefix). Untested
configurations are not listed. The receiver always decodes the algorithm
specified in the sender cell.

Each **294-byte preamble** row covers two connection cases: the preamble followed
by 100 payloads, and the preamble followed by 65,537 repeated bytes
and a 37-byte follow-up. Here, **294 bytes is the compressed preamble size**,
including the frame header; it decodes to 422 bytes of application data. Each
payload is block-flushed through the same compressor and must decode before the
next payload arrives. All receivers pass the 101-checkpoint payload sequence,
including packets down to 14 compressed bytes. Compress-utils Rust/Python/JS
each withhold one byte at the 65,537-byte boundary; fzstd passes both cases.
The preamble is ordinary data, not padding or an extra flush. `whole` delivers
one complete batch at a time; the other rows split each batch before decoding.
These rows keep Python `zstandard` as sender and test the receiver's behavior.
See the
[preamble test and controls](results/2026-10-16/INTEROP.md#294-byte-preamble-stream).

For compress-utils, **Yes (attempted)** records the required behavior being
probed: Rust's `flush()` only flushes the sink; Python and JS expose no flush
method. Empty writes also fail to flush pending codec data. In each transport
profile, all 132 midpoint cases still recover the complete input after
finalization, but none passes every mid-stream checkpoint.

The ordinary Python `zstandard` 0.25.0 comparison uses zstd 1.5.7 at native
level 11, matching compress-utils level 5. With Python `zstandard` at both ends,
all 44 explicit block-flush cases pass. See the
[comparison details](results/2026-10-16/README.md#python-zstandard-comparison).

In each transport profile, all 256 ordinary mixed-receiver cases (72 without
mid-stream flush and 184 with it) recover the full input after finalization, but
some flushed prefixes stay buffered. Compress-utils returns only 65,536 of 131,072
repeated bytes at a checkpoint. fzstd 0.1.1 waits for at least 18 initial
compressed bytes, so a flushed 4,096-byte repeated payload compressed to 17 bytes
yields zero decoded bytes. Neither receiver meets the arbitrary mid-stream flush
requirement. See the [mixed-receiver results](results/2026-10-16/INTEROP.md).

The 18-byte startup wait is an **fzstd implementation limitation**. Zstandard
uses a variable-length frame header and permits decoding a block without the
following block. The 17-byte test prefix already contains a complete header and
block, and Python `zstandard` decodes it immediately. See the
[format and implementation explanation](results/2026-10-16/INTEROP.md#fzstd-receiver).

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

Choose compressed transport fragmentation with `--transport-chunk-size`:

```sh
.work/venv/bin/python tests/run.py --transport-chunk-size 1 --require-midstream-flush --output results/latest/byte
.work/venv/bin/python tests/run.py --transport-chunk-size 4096 --require-midstream-flush --output results/latest/4k
.work/venv/bin/python tests/run.py --transport-chunk-size whole --require-midstream-flush --output results/latest/whole
```

Omitting the option, or using `irregular`, cycles through 1, 3, 7, 97, and 4,093
bytes. The setting applies to streaming receivers in every language, including
the Python reference decoder; one-shot decoder calls and native diagnostic
controls keep their existing behavior. It is recorded in the fixture manifests,
JSONL observations, and summary (`[]` means whole batches). Standalone probes use
the most recently generated manifest's setting.

Application writes in ordinary streaming tests still cycle through 1, 7, 63,
1,024, and 65,521 bytes. Flush tests retain their 11 initial payload sizes from
1 to 1,048,593 bytes, followed by 37 bytes, 4,096 bytes, and an empty flush.
Changing transport chunk size therefore tests fragmentation independently of
message size, content, and flush boundaries. The separate preamble probe adds
the initial 294 compressed bytes using its level-3 compression settings.

Setup downloads the pinned upstream source and build dependencies, builds its
unmodified bindings, and compiles the probes. It installs pybind11 3.0.1,
zstandard 0.25.0, and msgpack 1.2.3 into a local virtual environment, and fzstd
0.1.1 into `tests/node_modules/`. Generated dependencies, builds, and fixtures
stay in ignored directories: `.work/`, `node_modules/`, and Rust's `target/`.

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

Run the two 294-byte preamble cases and two startup controls for a receiver with:

```sh
.work/venv/bin/python tests/preamble_stream_probe.py .work/fixtures
.work/venv/bin/python tests/preamble_stream_probe.py .work/fixtures --receiver compress_utils_rust
.work/venv/bin/python tests/preamble_stream_probe.py .work/fixtures --receiver compress_utils_python
.work/venv/bin/python tests/preamble_stream_probe.py .work/fixtures --receiver compress_utils_js
```

The default receiver is `fzstd`. All four receivers are part of the full runner;
no external application checkout is needed. Each emits two `preamble_stream`
observations and two `startup_control` observations. The preamble table rows
count only `preamble_stream`. The raw 17-byte startup control records the fzstd
limitation even after three additional empty block flushes; compress-utils passes
that control. Individual probes return 0 when integrity checks and final round
trips pass, recording incomplete checkpoints as `LIMITATION`.

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
- A 294-byte compressed preamble followed by 100 messages or a 65,537-byte
  payload is checked with compress-utils Rust/Python/JS and fzstd under all four
  transport profiles. Separate controls distinguish startup from extra empty flushes.
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
