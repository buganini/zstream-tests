# Streaming round-trip and midway-flush results

Test date: 2026-10-16 (Asia/Taipei).

**Completed round trips pass for Rust, Python, and JavaScript with both zstd and
LZ4. None meets the requirement to flush arbitrary pending input while keeping
the compressed stream open.** In addition to the missing flush operation, the
zstd wrapper can leave already-produced encoder or decoder output undrained.

## Version and environment

- Upstream: [11ea489add2435d2eb8360aad0a104a63e714fb3](https://github.com/dupontcyborg/compress-utils/commit/11ea489add2435d2eb8360aad0a104a63e714fb3).
  All three bindings were built from this same, unmodified source revision.
  The source reports version 0.9.0; these are source-build results, not claims
  about independently downloaded PyPI/npm/crates.io packages.
- Vendored codecs: zstd 1.5.7 and LZ4 1.10.0; compress-utils level 5 throughout.
  The zstd mapping selects native level 11.
- Linux x86_64, Ubuntu 26.04.1; GCC 16.0.1 development snapshot, CMake 4.2.3,
  Ninja 1.13.2, Python 3.14.4, pybind11 3.0.1, Node 22.22.1, npm 10.9.4,
  Rust/Cargo 1.90.0, Zig 0.14.1.
- Python is the native pybind11 binding. JavaScript is the upstream WASM binding
  running in Node. Rust uses the upstream native C build through its safe API.
  Native Python and WASM builds enable zstd/LZ4; Cargo builds its default codecs.

Exact fixture hashes, commands, toolchain details, and exit codes are in
[summary.json](summary.json). The dependency versions are locked in the upstream
npm lockfile and this repository's [Cargo.lock](../../tests/rust/Cargo.lock).

## Test design

Each binding/codec pair runs six one-shot and six streaming round trips: empty
input, one byte, 4,096 bytes of text, 65,537 bytes of binary data, and 1,048,593
bytes each of repeated and deterministic pseudorandom data. Streaming input
chunks cycle through 1, 7, 63, 1,024, and 65,521 bytes; compressed transport
chunks cycle through 1, 3, 7, 97, and 4,093 bytes. Every result is compared byte
for byte with the input.

Midpoint probes use both repeated and pseudorandom data at 11 prefix sizes:
1, 17, 4,096, 65,535, 65,536, 65,537, 131,071, 131,072, 131,073, 262,145,
and 1,048,593 bytes. Each uses one compressor/decompressor pair throughout:

1. Write the prefix and measure output and decoded bytes before more input.
2. Invoke Rust's `flush()`; Python/JS have no such method. Also attempt three
   empty compressor writes. Python/JS additionally attempt three empty decoder
   writes. Record all output; do not call `finish()` at these checkpoints.
3. Append 37 `B` bytes, repeat the checks, then append 4,096 bytes cycling through
   values 0–255 and repeat. Finally perform an empty-input checkpoint.
4. Finish the encoder, consume the remaining output, finish the decoder, and
   verify the entire input exactly. Every intermediate decoded result must also
   be an exact prefix of the data sent so far.

Rust's in-memory transport returns `WouldBlock` while temporarily empty, and EOF
only after encoder finalization. Its sink accepts at most 257 bytes per write,
and decoded reads use 113-byte buffers. Thus a temporary lack of data is never
mistaken for end-of-stream. Python/JS use their incremental push APIs. These are
in-memory transport tests; no timing, socket, or browser behavior is assumed.

## Results

| Binding | Codec | One-shot | Streaming | Midpoint probes: full data after finish | Mid-stream requirement |
| --- | --- | --- | --- | --- | --- |
| Rust | zstd | 6/6 | 6/6 | 22/22 | Not met |
| Rust | LZ4 | 6/6 | 6/6 | 22/22 | Not met |
| Python | zstd | 6/6 | 6/6 | 22/22 | Not met |
| Python | LZ4 | 6/6 | 6/6 | 22/22 | Not met |
| JavaScript | zstd | 6/6 | 6/6 | 22/22 | Not met |
| JavaScript | LZ4 | 6/6 | 6/6 | 22/22 | Not met |

Across the binding probes: **84 PASS observations and 134 LIMITATION observations;
zero round-trip mismatches or unexpected errors.** The 84 passes comprise 72
primary round trips, six finalization checks, and six truncation checks. The
134 limitations comprise 132 midpoint probes and two JS Web Streams API probes.
The two native zstd diagnostic controls also pass, outside those counts.

These counts deliberately distinguish completed data integrity from the unmet
flush requirement. In strict mode the runner exits **1**, as recorded in the
summary. `LIMITATION` is not a passing acceptance result.

### Bytes available before the next write

The following first-checkpoint observations were identical across all three
bindings. Each row starts with a new stream and a pseudorandom prefix. Empty
writes and Rust `flush()` added no compressed output.

| Input submitted | zstd wire bytes | zstd decoded bytes | LZ4 wire bytes | LZ4 decoded bytes |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 0 | 0 | 7 | 0 |
| 4,096 | 0 | 0 | 7 | 0 |
| 65,535 | 0 | 0 | 7 | 0 |
| 65,536 | 0 | 0 | 65,547 | 65,536 |
| 65,537 | 0 | 0 | 65,547 | 65,536 |
| 131,071 | 0 | 0 | 65,547 | 65,536 |
| 131,072 | 65,536 | 65,527 | 131,087 | 131,072 |
| 131,073 | 131,081 | 131,072 | 131,087 | 131,072 |
| 1,048,593 | 1,048,606 | 1,048,576 | 1,048,647 | 1,048,576 |

LZ4's seven initial bytes are a frame header, not decoded application data.
Full blocks can emerge automatically, but partial blocks remain pending. These
measurements are specific to this revision, level, and input; block-size-aligned
writes are not a general solution to the flush requirement.

## Issues

### 1. No nonterminal codec flush exposed by compress-utils

**Impact:** small requests on a long-lived stream can remain unreadable at the
receiver indefinitely if the sender waits for a response before writing more.
The 4,096-byte probes decode zero bytes for both codecs, even after the next
37-byte and 4,096-byte writes and the empty-input checks.

The [C API](https://github.com/dupontcyborg/compress-utils/blob/11ea489add2435d2eb8360aad0a104a63e714fb3/include/compress_utils.h#L269-L326)
provides create/write/finish/destroy, with no nonterminal flush operation.

- [Rust `Write::flush`](https://github.com/dupontcyborg/compress-utils/blob/11ea489add2435d2eb8360aad0a104a63e714fb3/bindings/rust/src/stream.rs#L185-L195)
  calls only `sink.flush()`. All four calls per midpoint probe reached the sink
  successfully but emitted zero additional compressed bytes.
- [Python `CompressStream`](https://github.com/dupontcyborg/compress-utils/blob/11ea489add2435d2eb8360aad0a104a63e714fb3/bindings/python/compress_utils_py.cpp#L128-L138)
  exposes `compress()` and `finish()`, with no `flush()` method.
- [JavaScript `CompressStream`](https://github.com/dupontcyborg/compress-utils/blob/11ea489add2435d2eb8360aad0a104a63e714fb3/bindings/wasm/src/core/dispatch.ts#L284-L316)
  exposes `write()` and `finish()`, with no `flush()` method. The Web Streams
  writer likewise has no flush method; closing it produces a correct complete
  stream. The internal
  [`TransformStream` flush callback](https://github.com/dupontcyborg/compress-utils/blob/11ea489add2435d2eb8360aad0a104a63e714fb3/bindings/wasm/src/core/dispatch.ts#L527-L545)
  calls `finish()` during closure, so it does not expose midway flushing.

**Fix direction:** add a C-level flush operation and surface it in each binding.
The vendored codecs provide
[`ZSTD_e_flush`](https://github.com/dupontcyborg/compress-utils/blob/11ea489add2435d2eb8360aad0a104a63e714fb3/third_party/zstd/lib/zstd.h#L750-L757)
and [`LZ4F_flush`](https://github.com/dupontcyborg/compress-utils/blob/11ea489add2435d2eb8360aad0a104a63e714fb3/third_party/lz4/lib/lz4frame.h#L337-L350).
The wrapper needs to retain pending output, expose flush completion, and accept
later input without starting a new frame. This direction is based on source
inspection; no upstream fix was applied in this test run.

### 2. zstd encoder output can remain undrained after all input is consumed

**Reproduction:** `midpoint / random-131072` in each binding's JSONL file.
A single 131,072-byte write returns only 65,536 compressed bytes. The decoder can
recover 65,527 bytes. Three empty writes return nothing; Rust `flush()` also
returns successfully without releasing output. Writing the next 37 bytes releases
65,545 more compressed bytes, allowing the original 131,072 bytes to be decoded.

The [zstd encoder loop](https://github.com/dupontcyborg/compress-utils/blob/11ea489add2435d2eb8360aad0a104a63e714fb3/src/algorithms/zstd/zstd.c#L290-L328)
requests another drain only when the output buffer is full **and input remains**.
It can return `CU_OK` when all input was consumed but zstd still has output
buffered. An empty wrapper write then skips the codec call entirely. The binding
scratch buffers are 64 KiB, making this boundary visible in all three languages.

The [native control](native-control.jsonl) uses the same vendored zstd 1.5.7,
native level 11, and fixture. After consuming all 131,072 input bytes and filling
a 65,536-byte output buffer, a direct empty-input `ZSTD_e_continue` call releases
the remaining **65,545 bytes without a flush or new input**. This establishes an
output-drain defect separate from issue 1.

### 3. zstd decoder output can remain undrained after compressed input is consumed

**Reproduction:** `midpoint / repeat-131072` in each binding's JSONL file.
The compressor emits 18 bytes for 131,072 repeated `A` bytes. The binding's
decoder initially returns only **65,536 decoded bytes**. Python/JS empty decoder
writes return nothing more; Rust's reader waits for further compressed input.
The later small writes emit no compressed data, so the missing decoded bytes
remain unavailable until finalization supplies more compressed input.

The [zstd decoder loop](https://github.com/dupontcyborg/compress-utils/blob/11ea489add2435d2eb8360aad0a104a63e714fb3/src/algorithms/zstd/zstd.c#L430-L495)
has the corresponding input-consumed condition and skips the codec on an empty
write. The [native control](native-control.jsonl) consumes the same 18-byte
block, produces 65,536 bytes on its first call, then produces the remaining
**65,536 bytes with an empty-input decoder call**. The compressed block already
contains the data; withholding it is not a requirement of the zstd format.

**Fix direction for issues 2 and 3:** track and drain codec output even when no
caller input remains, report the correct retry status, and ensure empty-input
drain calls actually invoke the codec. Add regression cases with compressible
and incompressible blocks crossing the binding output-buffer boundary.

### 4. `finish()` cannot substitute for midway flush

Python's docstring says to "flush with .finish()", but it terminates the stream.
Python and JS both reject a write after `finish()`; the captured errors are in
the raw results. Rust's `finish(self)` consumes the compressor and returns its
sink. JS Web Streams closure likewise finishes the frame.

All six binding/codec pairs also reject a stream missing its last byte when
finalized. The tests intentionally keep that truncation check separate from
midway decoding, where an unfinished frame is normal.

## Evidence and reproduction

- [Python observations](python.jsonl), [JavaScript observations](js.jsonl),
  [Rust observations](rust.jsonl), and [native controls](native-control.jsonl).
- [Python probe](../../tests/python_probe.py), [JS probe](../../tests/js_probe.mjs),
  [Rust probe](../../tests/rust/src/main.rs), and
  [native control source](../../tests/native_zstd_control.c).
- [Setup](../../tests/setup.sh) and [runner](../../tests/run.py).

With the prerequisites in the root README on `PATH`:

```sh
bash tests/setup.sh
.work/venv/bin/python tests/run.py --require-midstream-flush --output results/latest
```

Expected current exit status: **1** for the unmet streaming requirement. Without
the strict flag the runner exits 0 while retaining the limitation observations.
The raw results were captured with the strict flag enabled. No upstream files
were modified, no upstream issues were submitted, and no fixes are included.

Not covered: other levels or codecs, cross-binding interoperability, independent
frame concatenation, real network backpressure, browser runtimes, performance,
memory bounds, and broader malformed-input testing.
