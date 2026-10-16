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

Jump to [results](#current-status), [PUI traffic pattern](#pui-traffic-pattern),
[test design](#test-design), [Python zstandard comparison](#python-zstandard-comparison),
[issues](#issues-and-measured-behavior), [running the tests](#run-the-tests), or
[recorded evidence](#recorded-evidence).

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

Tested on **2026-10-17 (Asia/Taipei)** against unmodified compress-utils
**v0.10.1**, commit
[`e70d4e3`](https://github.com/dupontcyborg/compress-utils/commit/e70d4e319c707636467e1cb7c29a7283f6738609).
All three runtime bindings report `0.10.1`. Ordinary tests use compress-utils
level 5, equivalent to native zstd level 11. The PUI traffic pattern uses native
level 3 and a 4 MiB window.

**All required compress-utils mid-stream flush cases now pass for zstd and LZ4
in Rust, Python, and JavaScript, across all four transport profiles.** The
Python `zstandard` sender also passes all 46 flush cases with each compress-utils
receiver. The previous encoder/decoder drain failures and the PUI boundary
failure are resolved in these tests. JavaScript Web Streams also pass with
`flushEachChunk: true`.

Two qualifications remain:

- The original no-flush interoperability probes make three extra empty decoder
  calls after every sender write. Python and JS/WASM now throw a zstd no-progress
  error in four of those 18 cases. Replaying the identical compressed bytes with
  **zero extra empty calls passes 18/18** in both bindings and every profile.
  Both policies appear in the table; the original failures remain recorded.
- The independent JavaScript npm package **fzstd@0.1.1** still delays small
  initial flushed batches. Its ordinary flush result remains **82.61% (38/46)**.

Each row is one encoder/decoder/flush/transport configuration. **No** checks an
exact completed round trip without requesting a nonterminal flush. **Yes**
requires complete decoding after every flush, continued use of the same open
frame, and an exact final round trip. Percentages describe these test cases,
not estimated success rates for arbitrary traffic. All `zstandard` rows use zstd.

Transport chunk size is the maximum compressed bytes delivered per receiver
call, independently of application writes and flushes. The last chunk may be
shorter. The irregular pattern repeats; `whole` delivers each write/flush batch
without harness fragmentation. Rust still limits reads to its internal 64 KiB
compressed-input buffer. No profile combines bytes across flush checkpoints.

| Encoder | Decoder | Mid-stream flush | Transport chunk (bytes) | Pass percentage (pass/all) |
| --- | --- | --- | --- | --- |
| compress-utils / Rust · zstd | compress-utils / Rust | No | 1, 3, 7, 97, 4093 | 100% (12/12) |
| compress-utils / Rust · zstd | compress-utils / Rust | No | 1 | 100% (12/12) |
| compress-utils / Rust · zstd | compress-utils / Rust | No | 4096 | 100% (12/12) |
| compress-utils / Rust · zstd | compress-utils / Rust | No | whole | 100% (12/12) |
| compress-utils / Rust · zstd | compress-utils / Rust | Yes | 1, 3, 7, 97, 4093 | 100% (22/22) |
| compress-utils / Rust · zstd | compress-utils / Rust | Yes | 1 | 100% (22/22) |
| compress-utils / Rust · zstd | compress-utils / Rust | Yes | 4096 | 100% (22/22) |
| compress-utils / Rust · zstd | compress-utils / Rust | Yes | whole | 100% (22/22) |
| compress-utils / Rust · LZ4 | compress-utils / Rust | No | 1, 3, 7, 97, 4093 | 100% (12/12) |
| compress-utils / Rust · LZ4 | compress-utils / Rust | No | 1 | 100% (12/12) |
| compress-utils / Rust · LZ4 | compress-utils / Rust | No | 4096 | 100% (12/12) |
| compress-utils / Rust · LZ4 | compress-utils / Rust | No | whole | 100% (12/12) |
| compress-utils / Rust · LZ4 | compress-utils / Rust | Yes | 1, 3, 7, 97, 4093 | 100% (22/22) |
| compress-utils / Rust · LZ4 | compress-utils / Rust | Yes | 1 | 100% (22/22) |
| compress-utils / Rust · LZ4 | compress-utils / Rust | Yes | 4096 | 100% (22/22) |
| compress-utils / Rust · LZ4 | compress-utils / Rust | Yes | whole | 100% (22/22) |
| compress-utils / Python · zstd | compress-utils / Python | No | 1, 3, 7, 97, 4093 | 100% (12/12) |
| compress-utils / Python · zstd | compress-utils / Python | No | 1 | 100% (12/12) |
| compress-utils / Python · zstd | compress-utils / Python | No | 4096 | 100% (12/12) |
| compress-utils / Python · zstd | compress-utils / Python | No | whole | 100% (12/12) |
| compress-utils / Python · zstd | compress-utils / Python | Yes | 1, 3, 7, 97, 4093 | 100% (22/22) |
| compress-utils / Python · zstd | compress-utils / Python | Yes | 1 | 100% (22/22) |
| compress-utils / Python · zstd | compress-utils / Python | Yes | 4096 | 100% (22/22) |
| compress-utils / Python · zstd | compress-utils / Python | Yes | whole | 100% (22/22) |
| compress-utils / Python · LZ4 | compress-utils / Python | No | 1, 3, 7, 97, 4093 | 100% (12/12) |
| compress-utils / Python · LZ4 | compress-utils / Python | No | 1 | 100% (12/12) |
| compress-utils / Python · LZ4 | compress-utils / Python | No | 4096 | 100% (12/12) |
| compress-utils / Python · LZ4 | compress-utils / Python | No | whole | 100% (12/12) |
| compress-utils / Python · LZ4 | compress-utils / Python | Yes | 1, 3, 7, 97, 4093 | 100% (22/22) |
| compress-utils / Python · LZ4 | compress-utils / Python | Yes | 1 | 100% (22/22) |
| compress-utils / Python · LZ4 | compress-utils / Python | Yes | 4096 | 100% (22/22) |
| compress-utils / Python · LZ4 | compress-utils / Python | Yes | whole | 100% (22/22) |
| compress-utils / JS/WASM · zstd | compress-utils / JS/WASM | No | 1, 3, 7, 97, 4093 | 100% (12/12) |
| compress-utils / JS/WASM · zstd | compress-utils / JS/WASM | No | 1 | 100% (12/12) |
| compress-utils / JS/WASM · zstd | compress-utils / JS/WASM | No | 4096 | 100% (12/12) |
| compress-utils / JS/WASM · zstd | compress-utils / JS/WASM | No | whole | 100% (12/12) |
| compress-utils / JS/WASM · zstd | compress-utils / JS/WASM | Yes | 1, 3, 7, 97, 4093 | 100% (22/22) |
| compress-utils / JS/WASM · zstd | compress-utils / JS/WASM | Yes | 1 | 100% (22/22) |
| compress-utils / JS/WASM · zstd | compress-utils / JS/WASM | Yes | 4096 | 100% (22/22) |
| compress-utils / JS/WASM · zstd | compress-utils / JS/WASM | Yes | whole | 100% (22/22) |
| compress-utils / JS/WASM · LZ4 | compress-utils / JS/WASM | No | 1, 3, 7, 97, 4093 | 100% (12/12) |
| compress-utils / JS/WASM · LZ4 | compress-utils / JS/WASM | No | 1 | 100% (12/12) |
| compress-utils / JS/WASM · LZ4 | compress-utils / JS/WASM | No | 4096 | 100% (12/12) |
| compress-utils / JS/WASM · LZ4 | compress-utils / JS/WASM | No | whole | 100% (12/12) |
| compress-utils / JS/WASM · LZ4 | compress-utils / JS/WASM | Yes | 1, 3, 7, 97, 4093 | 100% (22/22) |
| compress-utils / JS/WASM · LZ4 | compress-utils / JS/WASM | Yes | 1 | 100% (22/22) |
| compress-utils / JS/WASM · LZ4 | compress-utils / JS/WASM | Yes | 4096 | 100% (22/22) |
| compress-utils / JS/WASM · LZ4 | compress-utils / JS/WASM | Yes | whole | 100% (22/22) |
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
| zstandard / Python | compress-utils / Rust | Yes | 1, 3, 7, 97, 4093 | 100% (46/46) |
| zstandard / Python | compress-utils / Rust | Yes | 1 | 100% (46/46) |
| zstandard / Python | compress-utils / Rust | Yes | 4096 | 100% (46/46) |
| zstandard / Python | compress-utils / Rust | Yes | whole | 100% (46/46) |
| zstandard / Python | compress-utils / Python | No | 1, 3, 7, 97, 4093 | 77.78% (14/18) |
| zstandard / Python | compress-utils / Python | No | 1 | 77.78% (14/18) |
| zstandard / Python | compress-utils / Python | No | 4096 | 77.78% (14/18) |
| zstandard / Python | compress-utils / Python | No | whole | 77.78% (14/18) |
| zstandard / Python | compress-utils / Python | Yes | 1, 3, 7, 97, 4093 | 100% (46/46) |
| zstandard / Python | compress-utils / Python | Yes | 1 | 100% (46/46) |
| zstandard / Python | compress-utils / Python | Yes | 4096 | 100% (46/46) |
| zstandard / Python | compress-utils / Python | Yes | whole | 100% (46/46) |
| zstandard / Python | compress-utils / Python (0 extra empty calls) | No | 1, 3, 7, 97, 4093 | 100% (18/18) |
| zstandard / Python | compress-utils / Python (0 extra empty calls) | No | 1 | 100% (18/18) |
| zstandard / Python | compress-utils / Python (0 extra empty calls) | No | 4096 | 100% (18/18) |
| zstandard / Python | compress-utils / Python (0 extra empty calls) | No | whole | 100% (18/18) |
| zstandard / Python | compress-utils / JS/WASM | No | 1, 3, 7, 97, 4093 | 77.78% (14/18) |
| zstandard / Python | compress-utils / JS/WASM | No | 1 | 77.78% (14/18) |
| zstandard / Python | compress-utils / JS/WASM | No | 4096 | 77.78% (14/18) |
| zstandard / Python | compress-utils / JS/WASM | No | whole | 77.78% (14/18) |
| zstandard / Python | compress-utils / JS/WASM | Yes | 1, 3, 7, 97, 4093 | 100% (46/46) |
| zstandard / Python | compress-utils / JS/WASM | Yes | 1 | 100% (46/46) |
| zstandard / Python | compress-utils / JS/WASM | Yes | 4096 | 100% (46/46) |
| zstandard / Python | compress-utils / JS/WASM | Yes | whole | 100% (46/46) |
| zstandard / Python | compress-utils / JS/WASM (0 extra empty calls) | No | 1, 3, 7, 97, 4093 | 100% (18/18) |
| zstandard / Python | compress-utils / JS/WASM (0 extra empty calls) | No | 1 | 100% (18/18) |
| zstandard / Python | compress-utils / JS/WASM (0 extra empty calls) | No | 4096 | 100% (18/18) |
| zstandard / Python | compress-utils / JS/WASM (0 extra empty calls) | No | whole | 100% (18/18) |
| zstandard / Python | fzstd / JavaScript | No | 1, 3, 7, 97, 4093 | 100% (18/18) |
| zstandard / Python | fzstd / JavaScript | No | 1 | 100% (18/18) |
| zstandard / Python | fzstd / JavaScript | No | 4096 | 100% (18/18) |
| zstandard / Python | fzstd / JavaScript | No | whole | 100% (18/18) |
| zstandard / Python | fzstd / JavaScript | Yes | 1, 3, 7, 97, 4093 | 82.61% (38/46) |
| zstandard / Python | fzstd / JavaScript | Yes | 1 | 82.61% (38/46) |
| zstandard / Python | fzstd / JavaScript | Yes | 4096 | 82.61% (38/46) |
| zstandard / Python | fzstd / JavaScript | Yes | whole | 82.61% (38/46) |
| zstandard / Python (PUI traffic pattern) | compress-utils / Rust | Yes | 1, 3, 7, 97, 4093 | 100% (2/2) |
| zstandard / Python (PUI traffic pattern) | compress-utils / Rust | Yes | 1 | 100% (2/2) |
| zstandard / Python (PUI traffic pattern) | compress-utils / Rust | Yes | 4096 | 100% (2/2) |
| zstandard / Python (PUI traffic pattern) | compress-utils / Rust | Yes | whole | 100% (2/2) |
| zstandard / Python (PUI traffic pattern) | compress-utils / Python | Yes | 1, 3, 7, 97, 4093 | 100% (2/2) |
| zstandard / Python (PUI traffic pattern) | compress-utils / Python | Yes | 1 | 100% (2/2) |
| zstandard / Python (PUI traffic pattern) | compress-utils / Python | Yes | 4096 | 100% (2/2) |
| zstandard / Python (PUI traffic pattern) | compress-utils / Python | Yes | whole | 100% (2/2) |
| zstandard / Python (PUI traffic pattern) | compress-utils / JS/WASM | Yes | 1, 3, 7, 97, 4093 | 100% (2/2) |
| zstandard / Python (PUI traffic pattern) | compress-utils / JS/WASM | Yes | 1 | 100% (2/2) |
| zstandard / Python (PUI traffic pattern) | compress-utils / JS/WASM | Yes | 4096 | 100% (2/2) |
| zstandard / Python (PUI traffic pattern) | compress-utils / JS/WASM | Yes | whole | 100% (2/2) |
| zstandard / Python (PUI traffic pattern) | fzstd / JavaScript | Yes | 1, 3, 7, 97, 4093 | 100% (2/2) |
| zstandard / Python (PUI traffic pattern) | fzstd / JavaScript | Yes | 1 | 100% (2/2) |
| zstandard / Python (PUI traffic pattern) | fzstd / JavaScript | Yes | 4096 | 100% (2/2) |
| zstandard / Python (PUI traffic pattern) | fzstd / JavaScript | Yes | whole | 100% (2/2) |

Same-package **No** rows cover six one-shot and six incremental cases (12).
Mixed-receiver **No** rows cover six payloads through one-shot compression,
`compressobj()`, and `stream_writer()` (18). Partial output before finalization
is allowed when no block flush is requested.

Python `zstandard` **Yes** rows combine its two block-flush APIs: 22 cases each
with its own receiver (44), or 23 each with mixed receivers (46), including an
initially empty prefix. Compress-utils **Yes** rows contain 22 cases per
binding/algorithm and now call actual nonterminal flush APIs.

Ordinary Python/JS/fzstd mixed-receiver rows retain three extra empty decoder
calls per sender stage, as in the v0.9.0 baseline. Rows marked **0 extra empty
calls** replay all 18 no-flush cases using the same data, finalization bytes,
and fragmentation, while feeding only nonempty compressed chunks. Rust waits
for data using `WouldBlock` and does not make these speculative calls.

The **PUI traffic pattern** rows combine the 101-message application sequence
and an added 64 KiB boundary test. Both now pass, giving **100% (2/2)** for every
receiver. Two separate startup controls are excluded from these percentages.
Web Streams, finalization, truncation, and native diagnostic checks are also
reported separately from the table.

## PUI traffic pattern

This case reproduces a **real traffic pattern from
[PUI](https://github.com/buganini/PUI)**: a larger initial `ready` message,
followed by small payloads flushed through the same open stream.
**This pattern happens to pass the mid-stream flush test** with fzstd and all
three compress-utils receivers. The fixture uses fixed IDs and payloads; its
101 packets were verified against PUI's actual sender and packaged JavaScript
receiver. It reproduces application behavior using deterministic data.

The first `ready` payload is a fixed **422-byte data record** containing text
fields, identifiers, numeric limits, and booleans. Writing it to a new compressor
and block-flushing produces **294 compressed bytes, including the zstd frame
header**. The receiver must recover the complete 422-byte record before the next
write, then reuse the same decoder. This normal startup message happens to
exceed fzstd's 18-byte startup wait; no padding, extra empty flush, or separate
frame is added to make it pass. The 294-byte size is measured for this fixture.

The sender keeps one `compressobj()` at native level 3 with `window_log=22`
(4 MiB), no content size, and no checksum. Each payload is compressed and
block-flushed once; the output of both calls forms one batch. Every receiver
must recover all input so far before any bytes of the next batch arrive.

Each **PUI traffic pattern** row combines these two cases. All sequence sizes
are bytes. A comma means **write, block-flush, deliver, and check decoding before
the next write**. `98 × 100` means 100 separate 98-byte writes, each flushed;
their contents vary slightly. Compressed sizes describe complete batches before
transport fragmentation and exclude finalization bytes.

- **PUI traffic pattern:** input `422, 98 × 100` → compressed batches
  `294, 57, 15, 14 × 98`. All receivers pass all 101 checkpoints.
- **Added 64 KiB boundary test:** input `422, 65537, 37` → compressed batches
  `294, 4, 4`. After the same initial payload, write 65,537 `A` bytes, then 37 `B`
  bytes. All receivers now recover all 65,537 `A` bytes at the middle
  checkpoint: 65,959 total bytes decoded, matching the submitted input.
  Compress-utils v0.9.0 withheld one byte here; v0.10.1 passes all three
  checkpoints, as does fzstd. This is an added stress case, not observed PUI traffic.

This gives every receiver **100% (2/2)** in every transport profile. Passing
PUI's pattern does not establish support for arbitrary mid-stream flushes.
All final round trips pass, and Python's reference receiver recovers every
prefix while reporting `eof=false`.

Two additional controls use the same level-3 encoder:

- **Small first payload:** input `17, 37` (repeated `A`, then `B`) → compressed
  batches `17, 4`. The reference and all compress-utils receivers decode the
  first payload immediately; fzstd returns none. Three additional empty block
  flushes produce zero bytes and do not resolve the stall. The next four
  compressed bytes let fzstd catch up.
- **Initial ready payload, then small payloads:** input `422, 17, 37` →
  compressed batches `294, 4, 4`. All receivers decode every batch immediately.

These controls are not included in the table's two-case percentages. Also,
level affects compressed sizes: 4,096 repeated bytes produce 18 initial bytes
at level 3, versus 17 at the ordinary comparison's level 11.

`whole` matches delivery of one complete batch per message. The other profiles
fragment that batch before the codec. There are no extra empty decoder writes
in these cases; Rust reads until `WouldBlock`, without declaring EOF. The test
finalizes only after all checkpoints as an additional integrity check. Actual
PUI discards the codec context on close.

Fixture provenance: the first record and 100 following payloads are
MessagePack-encoded `ready` and `result` envelopes derived from PUI commit
`8a8ef99da854c75d5c9abfd24e03bc21f8f5a880`. Their compressed bytes exactly match
PUI's `StreamCodec.encode()` output, and its packaged JavaScript `StreamDecoder`
decodes and body-validates every envelope under Node. Source hashes and results
are in [pui-source-check.json](results/2026-10-16/pui-source-check.json).
The compression tests compare bytes; the serialization format is incidental.
The added boundary test uses repeated raw bytes after the first record. No live
WebSocket or browser UI was exercised. PUI's envelope decoder expects complete
batches; the fragmentation profiles exercise codecs directly.

## Test design

Each binding/codec pair runs six one-shot and six incremental round trips:
empty input, one byte, 4,096 bytes of text, 65,537 bytes of binary data, and
1,048,593 bytes each of repeated and deterministic pseudorandom data. Input
writes cycle through `1, 7, 63, 1024, 65521` bytes. All four receiver transport
profiles replay identical compressed bytes, application input, and flush
boundaries; hashes are recorded with the observations.

Midpoint probes use repeated and pseudorandom prefixes at 11 sizes:
`1, 17, 4096, 65535, 65536, 65537, 131071, 131072, 131073, 262145, 1048593`.
After each initial prefix, the same stream receives 37 `B` bytes, 4,096 bytes
cycling through 0–255, and an empty-input checkpoint. Every decoded result must
be an exact prefix of submitted input, even when incomplete. All input must be
recovered exactly after finalization.

Compress-utils probes call Rust's `Write::flush()`, Python's `.flush()`, or
JavaScript's low-level `.flush()`. All now perform a codec flush. Three empty
compressor writes and Python/JS empty decoder writes remain diagnostic checks.
No `finish()` is allowed at a midpoint. Rust's source returns `WouldBlock` when temporarily empty
and EOF only after encoder finalization. Its sink accepts at most 257 bytes per
write, and decoded reads use 113-byte buffers. Python/JS use incremental push APIs.

For a Python `zstandard` sender, each explicit block flush must recover the
entire prefix while the reference decoder reports `eof=false`. Only finalization
may produce `eof=true`. The `stream_writer` variant uses `write_size=113`,
`write_return_read=True`, and `closefd=False`; its sink accepts each write in full.
The Python reference decoder uses `decompressobj(write_size=65536)`.

Mixed-receiver tests save each compressed stage and replay it through all four
receivers. Each sender API adds an initially empty prefix, giving 46 flush cases
per receiver. Python/JS/fzstd get three empty non-final decoder writes per ordinary
checkpoint. fzstd gets `push(chunk, false)` until finalization, followed by
`push(empty, true)`; `true` marks transport completion, not a mid-stream flush.
The traffic-pattern cases instead use zero extra decoder writes.

For the 18 no-flush mixed cases, one-shot compression creates a whole frame;
`compressobj()` and `stream_writer()` finalize once after all writes, without
block flushing. Receivers use streaming APIs for all three sender variants.
Intermediate output may be incomplete, but must match the submitted prefix;
the final output must match the complete payload.

The core acceptance sequence is: create one compressor/decoder pair; write A;
complete a nonterminal flush; deliver all its bytes; require A immediately;
write B and repeat; finalize only after every checkpoint. Draining small buffers,
continued use of the same frame, and complete final integrity are all required.

The two JavaScript Web Streams probes use `compressionStream({level: 5,
flushEachChunk: true})`. They write a small text payload, 65,537 repeated bytes,
and 131,072 pseudorandom bytes, and require full decoding before the next write
or close. The standard writer still has no `.flush()` method; automatic flushing
is requested through the stream option. This replaces the old close-only API
inspection probe, which could not test the new option.

## Python zstandard comparison

Python `zstandard==0.25.0` uses the `cext` backend with zstd 1.5.7 at native level
11, matching compress-utils level 5. The reference runs that package directly
at both ends, independently of compress-utils and the standard-library
`compression.zstd` module.

All 62 checks pass in every profile: six one-shot and six incremental round
trips, 22 midpoint cases through each of `compressobj()` and `stream_writer()`,
four pre-flush boundary checks, one terminal-flush check, and one truncation
check. The writer uses `write_size=113`; the reference decoder uses
`decompressobj(write_size=65536)`.

Use `compressobj.flush(COMPRESSOBJ_FLUSH_BLOCK)` or
`stream_writer.flush(FLUSH_BLOCK)` for nonterminal flushing. Default
`compressobj.flush()` finishes the frame. The decoder's `.flush()` does not
validate completion: check `eof` at transport closure. See the versioned
[compression API](https://python-zstandard.readthedocs.io/en/0.25.0/compressor.html)
and [decoder EOF documentation](https://python-zstandard.readthedocs.io/en/0.25.0/decompressor.html#zstandard.ZstdDecompressionObj.eof).

## Issues and measured behavior

### Nonterminal flush and zstd drain fixes verified in v0.10.1

The [C flush API](https://github.com/dupontcyborg/compress-utils/blob/e70d4e319c707636467e1cb7c29a7283f6738609/include/compress_utils.h#L324-L342)
now emits everything needed to decode submitted input without ending the frame.
It exposes retry/completion status for small output buffers. Rust flushes the
codec and then the sink; Python and JavaScript expose `.flush()`. `finish()`
remains terminal and separate from flushing.

In all three bindings with irregular transport:

- **131,072 pseudorandom bytes:** the write now emits 131,081 compressed bytes
  and decodes all 131,072 before flush. Previously it emitted 65,536 compressed
  bytes and decoded only 65,527. No extra input is needed to drain the block.
- **131,072 repeated bytes:** the 18-byte compressed block now decodes all
  131,072 before flush. Previously only 65,536 were available.
- **4,096 repeated LZ4 bytes:** the write emits the seven-byte frame header and
  no decoded data; the nonterminal flush emits 30 more bytes and makes all
  4,096 input bytes available while keeping the frame open.

The updated zstd [encoder pump](https://github.com/dupontcyborg/compress-utils/blob/e70d4e319c707636467e1cb7c29a7283f6738609/src/algorithms/zstd/zstd.c#L300-L310)
and [decoder pump](https://github.com/dupontcyborg/compress-utils/blob/e70d4e319c707636467e1cb7c29a7283f6738609/src/algorithms/zstd/zstd.c#L475-L492)
continue draining when output fills even after input is consumed. The native
controls still demonstrate that the same underlying zstd codec can release
65,545 pending encoded bytes or 65,536 pending decoded bytes with empty input;
the wrappers now recover that output in the tested cases.

All six binding/algorithm pairs also pass terminal-finalization and truncated
frame detection. No upstream source changes were applied locally.

### Repeated empty decoder calls can trigger a no-progress error

The original mixed-receiver harness attempts three empty decoder calls after
**every application write**, including writes whose compressor emits no bytes.
In v0.10.1, four no-flush cases per Python/JS receiver now fail with:

```text
zstd: Operation made no progress over multiple calls, due to input being empty
```

The cases are `no-flush-{compressobj,stream_writer}-{repeat,random}`, each using
1,048,593 input bytes. All four transport profiles behave identically. These are
exceptions before finalization, not measured final-data mismatches. The other
14 no-flush cases and all 46 block-flush cases pass in each receiver.

The wrapper now invokes zstd for empty-input drains. After output is already
exhausted, repeated calls reach the vendored codec's
[16-call no-progress guard](https://github.com/dupontcyborg/compress-utils/blob/e70d4e319c707636467e1cb7c29a7283f6738609/third_party/zstd/lib/decompress/zstd_decompress.c#L2356-L2365).
A focused check decodes all 131,072 repeated bytes from an 18-byte flushed batch,
then gets the exception on the **15th extra public empty call** in both Python
and JS; the binding's internal drain already used one no-progress call.
The [recorded recheck](results/2026-10-17-v0.10.1/empty-decode-recheck.json)
also identifies the failing stage in an original no-flush case.

The [control](tests/no_empty_decode_control.py) replays all 18 no-flush cases
through Python and JS with **zero extra empty decoder calls**. It verifies
fixture hashes and changes only that call policy. Both receivers pass
**18/18 in every profile**, including all four cases above. These controls are
additional rows in the same result table and are recorded separately from the
552 main observations. They do not replace or erase the original failures.

For these push APIs, feed available compressed bytes and use `finish()` once at
transport closure; repeatedly polling with empty input after output is drained
is not needed for successful delivery. The main suite deliberately retains its
original empty-call policy to make this behavior visible.

### fzstd startup waits for 18 compressed bytes

The JavaScript npm package **fzstd@0.1.1** fails four initial-payload cases per
sender API, in every transport profile (eight cases total):

- Initially empty, followed by 37 `B` bytes: 16 compressed bytes received,
  zero of 37 input bytes decoded.
- One random or repeated byte: 10 compressed bytes received, zero decoded.
  After the next 37 `B` bytes, 14 cumulative compressed bytes still decode zero
  of the 38 submitted bytes.
- 4,096 repeated bytes: 17 compressed bytes received, zero decoded.

The 4,096-byte repeated case catches up after the 37-byte follow-up, when the
compressed total reaches 21 bytes. The other cases catch up only after the
4,096-byte binary follow-up. Three empty pushes add no output. All other tested
prefix cases, including 131,072 repeated bytes, pass every checkpoint.

A separate rerun reproduced the same 38 PASS and 8 LIMITATION observations. A
focused check sent the entire 17-byte initial stage for `repeat-4096` in one
`push(..., false)`: it still produced zero decoded bytes, as did three empty
non-final pushes. Delivering just the first byte of the next stage raised the
compressed total to 18 and immediately released the original 4,096 bytes. The
rest of that stage released the 37 new bytes, and the final round trip remained
exact. Both Python sender APIs gave this result, confirming that the stall also
occurs when the initial stage arrives in a single transport chunk.

Source inspection explains these observations: before creating its frame state,
`Decompress.push()` buffers non-final input until at least **18 compressed bytes**
have accumulated. See `ncs < 18` in the published
[0.1.1 ESM source](https://cdn.jsdelivr.net/npm/fzstd@0.1.1/esm/index.mjs), also
installed as `tests/node_modules/fzstd/esm/index.mjs` at lines 678–692. A valid
shorter frame header plus flushed block can already be decoded by the reference
receiver, but fzstd waits for more compressed input. Consequently, even a 4 KiB
application message can stall when highly compressible. The 18-byte threshold
describes startup buffering; it is not a general output-latency guarantee.

This is an implementation buffering limit, not a Zstandard format requirement.
The [Zstandard format specification](https://github.com/facebook/zstd/blob/v1.5.7/doc/zstd_compression_format.md#frame_header)
defines a 2–14-byte frame header after the 4-byte magic number, so 18 bytes is
the maximum combined header length, not a required minimum before producing
output. The descriptor identifies the actual header length, and blocks can be
decoded without waiting for their successors. Our 17-byte prefix consists of
6 header bytes including the magic, a 3-byte block header, and 8 bytes of
compressed block content. Python `zstandard` decodes all 4,096 bytes from it;
fzstd's unconditional `ncs < 18` check postpones parsing that complete block.

For a request/response stream, these bytes can remain unavailable if the sender
waits for the response before writing more. Setting `final=true` at a midpoint
would signal completion of an unfinished stream and does not meet the required
same-stream contract. A possible fix is incremental header parsing based on the
actual available header/block lengths; no fzstd changes or workarounds were
implemented or validated here.

## Run the tests

Prerequisites: Git, a C/C++ compiler, CMake, Ninja, Python with venv/pip, Node/npm,
Rust/Cargo, and Zig on `PATH`. Setup pins v0.10.1 to commit `e70d4e3` and builds
its unmodified bindings. If `.work/upstream` or `.work/build` contains an older
checkout/build, move those directories aside first; setup refuses a mismatched
upstream revision. The previous checkout and results need not be deleted.

```sh
bash tests/setup.sh
.work/venv/bin/python tests/run.py --require-midstream-flush --output results/latest/irregular
.work/venv/bin/python tests/no_empty_decode_control.py results/latest/irregular
```

The first test command currently **exits 1** because it records eight no-progress
exceptions and nine fzstd limitations. Omitting `--require-midstream-flush`
still exits 1 for those eight exceptions. The separate no-empty-call control
exits **0**. Run it after the main suite, even when that suite exits 1.

Repeat for other transport profiles (each main run currently exits 1):

```sh
.work/venv/bin/python tests/run.py --transport-chunk-size 1 --require-midstream-flush --output results/latest/byte
.work/venv/bin/python tests/no_empty_decode_control.py results/latest/byte
.work/venv/bin/python tests/run.py --transport-chunk-size 4096 --require-midstream-flush --output results/latest/4k
.work/venv/bin/python tests/no_empty_decode_control.py results/latest/4k
.work/venv/bin/python tests/run.py --transport-chunk-size whole --require-midstream-flush --output results/latest/whole
.work/venv/bin/python tests/no_empty_decode_control.py results/latest/whole
```

Omitting `--transport-chunk-size`, or using `irregular`, cycles through
1, 3, 7, 97, and 4,093 bytes. The setting controls compressed delivery, not
application message sizes or flush boundaries. `whole` is represented by `[]`
in JSON. One-shot decoder calls and native diagnostic controls are unchanged.

Setup installs pybind11 3.0.1, Python zstandard 0.25.0, and msgpack 1.2.3 into
`.work/venv`, and npm fzstd 0.1.1 into `tests/node_modules`. Generated builds,
dependencies, and shared fixtures stay in ignored directories. The runner
checks the upstream commit, tracked-source cleanliness, and runtime version of
each compress-utils binding before accepting its results. Run profiles
sequentially because they share `.work/fixtures` and `.work/interop`.

After generating fixtures, individual probes can be run with:

```sh
.work/venv/bin/python tests/python_zstandard_probe.py .work/fixtures
PYTHONPATH=.work/upstream/bindings/python .work/venv/bin/python tests/interop_python.py .work/interop
node tests/interop_js.mjs .work/interop .work/upstream compress_utils_js
node tests/interop_js.mjs .work/interop .work/upstream fzstd
cargo run --locked --release --manifest-path tests/rust/Cargo.toml -- .work/interop --interop
.work/venv/bin/python tests/preamble_stream_probe.py .work/fixtures --receiver compress_utils_rust
.work/venv/bin/python tests/preamble_stream_probe.py .work/fixtures --receiver compress_utils_python
.work/venv/bin/python tests/preamble_stream_probe.py .work/fixtures --receiver compress_utils_js
.work/venv/bin/python tests/preamble_stream_probe.py .work/fixtures
```

The traffic-pattern probe defaults to fzstd and needs no external application
checkout. Each receiver emits two `preamble_stream` observations counted in the
table, plus two `startup_control` observations. Internal file/test identifiers
retain their original names. Individual probes exit 1 for `FAIL`, while
incomplete checkpoints without integrity errors are recorded as `LIMITATION`.

## Version and environment

- Upstream: **v0.10.1**, commit `e70d4e319c707636467e1cb7c29a7283f6738609`.
  Rust, Python, and WASM were built from the same unmodified source and each
  reported runtime version `0.10.1`. These are source-build results, not a test
  of independently downloaded PyPI/npm/crates.io artifacts.
- Vendored codecs: zstd 1.5.7 and LZ4 1.10.0; compress-utils level 5. The Python
  zstandard comparison uses native level 11; PUI cases use native level 3.
- Linux x86_64, Ubuntu 26.04.1; GCC 16.0.1 development snapshot, CMake 4.2.3,
  Ninja 1.13.2, Python 3.14.4, pybind11 3.0.1, Node 22.22.1, npm 10.9.4,
  Rust/Cargo 1.90.0, Zig 0.14.1.
- Python uses native pybind11; JavaScript uses WASM under Node. Rust builds the
  C core through its safe API. Native Python/WASM enable zstd and LZ4 families;
  Cargo builds its default codecs.
- Comparison packages: Python **zstandard==0.25.0** (`cext`, zstd 1.5.7) and
  JavaScript npm **fzstd@0.1.1**. Python msgpack 1.2.3 generates the PUI fixture.

Dependency versions are locked in upstream's npm lockfile,
[tests/package-lock.json](tests/package-lock.json), and
[tests/rust/Cargo.lock](tests/rust/Cargo.lock). Fixture hashes, commands, and
runtime details are recorded with each run.

## Recorded evidence

All four v0.10.1 profiles have **535 PASS / 8 FAIL / 9 LIMITATION** among 552
main observations. The native controls add two passes, and the no-empty-call
controls add 36 passes per profile; both are counted separately.

- [Irregular chunks](results/2026-10-17-v0.10.1/summary.json) and
  [no-empty-call controls](results/2026-10-17-v0.10.1/no-empty-decode-summary.json).
- [1-byte chunks](results/2026-10-17-v0.10.1/chunks-1/summary.json) and
  [no-empty-call controls](results/2026-10-17-v0.10.1/chunks-1/no-empty-decode-summary.json).
- [4,096-byte chunks](results/2026-10-17-v0.10.1/chunks-4096/summary.json) and
  [no-empty-call controls](results/2026-10-17-v0.10.1/chunks-4096/no-empty-decode-summary.json).
- [Whole batches](results/2026-10-17-v0.10.1/chunks-whole/summary.json) and
  [no-empty-call controls](results/2026-10-17-v0.10.1/chunks-whole/no-empty-decode-summary.json).

Per main run, the self-tests contribute 72 Rust passes, 72 Python passes, and
74 JS passes (including two Web Streams probes). Python zstandard adds 62
passes. Mixed receivers add 240 passes, eight exceptions, and eight fzstd
limitations. Traffic-pattern/startup cases add 15 passes and one fzstd startup
limitation. All completed final round trips are exact; the eight exception
cases abort before finalization.

Raw default-profile observations (other profiles use the same filenames):

- Compress-utils self-tests: [Rust](results/2026-10-17-v0.10.1/rust.jsonl),
  [Python](results/2026-10-17-v0.10.1/python.jsonl), [JS/WASM](results/2026-10-17-v0.10.1/js.jsonl).
- Reference: [Python zstandard](results/2026-10-17-v0.10.1/python_zstandard.jsonl).
- Mixed receivers: [Rust](results/2026-10-17-v0.10.1/interop_rust.jsonl),
  [Python](results/2026-10-17-v0.10.1/interop_python.jsonl),
  [JS/WASM](results/2026-10-17-v0.10.1/interop_js.jsonl), [fzstd](results/2026-10-17-v0.10.1/interop_fzstd.jsonl).
- No-empty-call controls: [Python](results/2026-10-17-v0.10.1/interop_python_no_empty.jsonl),
  [JS/WASM](results/2026-10-17-v0.10.1/interop_js_no_empty.jsonl).
- PUI and startup cases: [Rust](results/2026-10-17-v0.10.1/preamble_rust.jsonl),
  [Python](results/2026-10-17-v0.10.1/preamble_python.jsonl),
  [JS/WASM](results/2026-10-17-v0.10.1/preamble_js.jsonl), [fzstd](results/2026-10-17-v0.10.1/preamble_fzstd.jsonl).
- [Sender-stage metadata](results/2026-10-17-v0.10.1/interop-fixtures.json),
  [native controls](results/2026-10-17-v0.10.1/native-control.jsonl), and
  [empty-call recheck](results/2026-10-17-v0.10.1/empty-decode-recheck.json).

### Previous v0.9.0 baseline

The 2026-10-16 results at commit `11ea489` remain unchanged. Main observation
totals were [370 PASS / 182 LIMITATION for irregular](results/2026-10-16/summary.json),
[388 / 164 for 1-byte chunks](results/2026-10-16/chunks-1/summary.json),
[370 / 182 for 4,096-byte chunks](results/2026-10-16/chunks-4096/summary.json), and
[346 / 206 for whole batches](results/2026-10-16/chunks-whole/summary.json), with
zero `FAIL` observations. All completed round trips passed.

At that revision, each compress-utils binding/algorithm passed **0/22** required
flush cases. Python zstandard → compress-utils passed **34/46** flush cases
with irregular/4,096-byte chunks, **40/46** with 1-byte chunks, and **22/46**
with whole batches in Python/JS (**34/46** in Rust). PUI rows were **1/2** for
compress-utils. All these flush subsets now pass in v0.10.1. The fzstd results
are unchanged. The new empty-call exceptions are documented above rather than
silently removing those calls to make the original suite pass.

The 550 non-Web-Streams main observations preserve the previous test scenarios.
The two old Web Streams close-only probes have been replaced by actual
`flushEachChunk` checkpoint tests; 36 no-empty-call controls are additional.
Original detailed documentation is available in the
[baseline README](https://github.com/buganini/zstream-tests/blob/be7e4a5525ed9309b9b55a8e6a3a8512d9ad2d14/README.md).

## Scope and remaining work

These runs cover one frame per case, no dictionaries, the stated compression
levels and fixtures, deterministic in-memory transport, and Node for JS/WASM.
Passing these cases is evidence for the tested flush contract, not a guarantee
for all inputs, workloads, or package builds. No upstream fixes or issue
submissions were made by this test run.

Still to test: other compression levels, larger windows, broader malformed-input
cases, additional encoder/decoder combinations, LZ4 interoperability,
concatenated frames, real network backpressure, and browser runtimes.
Performance, latency, and memory bounds are not established here.

When extending the suite, record the upstream commit, environment, algorithm,
compression settings, input/stage hashes, exact commands, and expected versus
actual behavior. Keep generated builds and large fixtures out of version control.
