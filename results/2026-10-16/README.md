# Streaming round-trip and midway-flush results

Test date: 2026-10-16 (Asia/Taipei).

This report's counts and byte measurements use the default repeating transport
chunks of 1, 3, 7, 97, and 4,093 bytes. Additional fixed 1-byte, fixed 4,096-byte,
and whole-batch runs are recorded in [chunks-1](chunks-1/summary.json),
[chunks-4096](chunks-4096/summary.json), and [chunks-whole](chunks-whole/summary.json).
The [root result table](../../README.md#current-status) lists every tested profile;
the [mixed-receiver report](INTEROP.md#transport-chunk-size-comparison) explains
where outcomes change.

**Completed round trips pass for Rust, Python, and JavaScript with both zstd and
LZ4. None of these compress-utils bindings meets the requirement to flush
arbitrary pending input while keeping the compressed stream open.** In addition
to the missing flush operation, the
zstd wrapper can leave already-produced encoder or decoder output undrained.
The added Python `zstandard` comparison meets that requirement with an explicit
block flush through both tested compression APIs, using Python `zstandard` for
both the sender and receiver.
With a Python `zstandard` sender and a different receiver, every completed round
trip passes, but some mid-stream flush checkpoints fail: see the
[compress-utils and fzstd receiver results](INTEROP.md).

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
The mixed-receiver tests also use npm `fzstd` 0.1.1, pinned in the test
[package lockfile](../../tests/package-lock.json).

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

Across the compress-utils binding probes: **84 PASS observations and 134 LIMITATION observations;
zero round-trip mismatches or unexpected errors.** The 84 passes comprise 72
primary round trips, six finalization checks, and six truncation checks. The
134 limitations comprise 132 midpoint probes and two JS Web Streams API probes.
The two native zstd diagnostic controls also pass, outside those counts.

The separate Python `zstandard` comparison adds **62 PASS observations**. The
[ordinary mixed-receiver tests](INTEROP.md) add **212 PASS and 44 LIMITATION
observations**. The [PUI reproduction and startup controls](INTEROP.md#pui-ready-first-stream)
add **2 PASS and 1 LIMITATION**, bringing the combined runner summary to
**360 PASS and 179 LIMITATION**. Python `zstandard` at both ends and the PUI
ready-first sequence have midway acceptance results of `true`; the ordinary
compress-utils and fzstd suites include failed checkpoints. The raw-startup
controls are separate diagnostics, not PUI message acceptance cases. See
`counts_by_binding` and `midstream_acceptance_by_binding` in the summary for the
separate results. All 256 mixed-receiver cases recover the complete input after
finalization: 72 without mid-stream flush and 184 with it, including those
classified as `LIMITATION`. Each of the four mixed receivers passes all 18
no-flush cases.

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

## Python zstandard comparison

Tested PyPI `zstandard==0.25.0`, C extension backend (`cext`), bundling zstd 1.5.7.
The comparison uses **native level 11**, equivalent to compress-utils user level
5, with the same deterministic fixtures, input chunking, transport chunking,
and 11 midpoint sizes. It tests zstd only. These are separate package tests,
not calls through compress-utils or Python's `compression.zstd` standard library.

**Sender: Python `zstandard`. Receiver: Python `zstandard`.** The sender uses
either `ZstdCompressor.compressobj()` or `ZstdCompressor.stream_writer()`; the
receiver uses `ZstdDecompressor.decompressobj()` in both variants. Interoperability
with compress-utils and fzstd receivers is tested separately in the
[mixed-receiver report](INTEROP.md); the table below describes only Python
`zstandard` at both ends.

| Check | Result |
| --- | --- |
| One-shot round trips | 6/6 pass |
| Incremental round trips using `compressobj()` | 6/6 pass |
| Midway-flush round trips: `compressobj()` → `decompressobj()` | 22/22 pass |
| Midway-flush round trips: `stream_writer()` → `decompressobj()` | 22/22 pass |
| Pre-flush buffering and subsequent flush at 128 KiB | 4/4 pass |
| Default compressor flush is terminal | Pass |
| Application detects truncation using decoder `eof` | Pass |

Both midpoint variants assert exact recovery **after every block flush, before
the next input arrives**. They check `decoder.eof == False` at all four
checkpoints, including the empty-input flush, then require `eof == True` only
after finalization. One compressor and one decoder remain in use throughout.
Thus each passing midway-flush case proves both immediate prefix recovery at
every flush and an exact full round trip after further writes and finalization.

The decoder uses `decompressobj(write_size=65536)` to exercise the same output
chunk size as the compress-utils bindings. The writer variant additionally uses
`stream_writer(write_size=113, write_return_read=True, closefd=False)`; its sink
asserts that each compressed output write is at most 113 bytes. The sink accepts
each write in full. This does not test partial sink writes or socket backpressure.

### Observed buffering comparison

These are decoded bytes at the first checkpoint, before and after a block flush
where available. The three compress-utils bindings agree; Python is shown here.

| Input | compress-utils Python: before / after attempted flush | zstandard `compressobj`: before / after block flush | zstandard writer (113-byte output): before / after block flush |
| --- | ---: | ---: | ---: |
| 4,096 random bytes | 0 / 0 | 0 / 4,096 | 0 / 4,096 |
| 131,072 random bytes | 65,527 / 65,527 | 131,072 / 131,072 | 104 / 131,072 |
| 131,072 repeated bytes | 65,536 / 65,536 | 131,072 / 131,072 | 131,072 / 131,072 |

For compress-utils, an attempted flush means the empty-write probes; Python has
no flush method. For `zstandard`, both APIs emit 4,105 compressed bytes when
flushing the 4,096-byte random prefix, making all 4,096 bytes decodable immediately.
Later payloads and repeated empty flushes also preserve the same open frame.

Buffering before a flush still occurs with `zstandard`. In the small-output
writer case, the 131,072-byte random write emits only 113 compressed bytes;
`FLUSH_BLOCK` then emits the remaining 130,968 bytes without ending the frame.
The four boundary checks measure this behavior and require complete recovery
after block flush; they do not require every ordinary write to drain all output.

### API details that matter

- `compressobj.flush(COMPRESSOBJ_FLUSH_BLOCK)` preserves the frame. Its default
  `flush()` instead finishes the frame and further compression raises an error.
  `stream_writer.flush(FLUSH_BLOCK)` preserves the frame; closing the writer
  finalizes it. These mode distinctions match the
  [versioned compression API documentation](https://python-zstandard.readthedocs.io/en/0.25.0/compressor.html).
- The incremental decoder does **not** raise merely because the final byte is
  missing, and `decompressobj.flush()` returns empty bytes without completing
  or validating that frame. Our truncated-input probe passes because the
  application completion check rejects `eof == False` at transport closure.
  This differs from compress-utils' decoder `finish()` exception. See the
  [decoder EOF and flush documentation](https://python-zstandard.readthedocs.io/en/0.25.0/decompressor.html#zstandard.ZstdDecompressionObj.eof).

Raw evidence: [python_zstandard.jsonl](python_zstandard.jsonl). Implementation:
[python_zstandard_probe.py](../../tests/python_zstandard_probe.py). The root
runner includes this comparison automatically; after fixture generation, the
probe can also be run alone and exits 0 for the recorded 62 passing checks.

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

The [mixed-receiver tests](INTEROP.md#compress-utils-receivers) reproduce this with
a Python `zstandard` sender that explicitly block-flushes. All three
compress-utils receivers still return only 65,536 of the 131,072 repeated bytes.
Replacing the sender therefore does not resolve this decoder defect.

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
  [Rust observations](rust.jsonl), [Python zstandard comparison](python_zstandard.jsonl),
  [mixed-receiver results and raw evidence](INTEROP.md), and
  [native controls](native-control.jsonl).
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

Not covered: other levels or codecs, other sender/receiver combinations, LZ4
interoperability, independent frame concatenation, real network backpressure,
browser runtimes, performance, memory bounds, and broader malformed-input testing.
