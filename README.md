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

Tested on 2026-10-16 (Asia/Taipei) against unmodified compress-utils commit
[`11ea489`](https://github.com/dupontcyborg/compress-utils/commit/11ea489add2435d2eb8360aad0a104a63e714fb3),
source version 0.9.0. Ordinary tests use compress-utils level 5 or equivalent
native zstd level 11; the PUI traffic pattern tests use native level 3 and a
4 MiB window.

**All completed round trips pass. Compress-utils cannot satisfy arbitrary
mid-stream flushes; fzstd can also delay the first decoded payload.** Python
`zstandard` at both ends passes all required flush checkpoints. PUI's normal
startup pattern happens to pass with every tested receiver, but the added
65,537-byte payload still exposes compress-utils' decoder limit.

Each row is one sender/receiver configuration. **No** checks a completed round
trip without requesting a mid-stream flush. **Yes** requires every flushed prefix
to be fully decoded before the next write, continued use of the same open frame,
and an exact final round trip. The pass percentage is the share of tested cases
meeting all requirements, followed by passing/total case counts. These are
fixture results, not estimated success rates for arbitrary traffic.

Transport chunk size is the maximum compressed bytes delivered per receiver
call, independently of application writes and flushes. The last chunk may be
shorter. The irregular pattern repeats; `whole` delivers each write/flush batch
without harness fragmentation. Rust still limits reads to its internal 64 KiB
compressed-input buffer. No profile combines data across flush checkpoints.

| Encoder | Decoder | Mid-stream flush | Transport chunk (bytes) | Pass percentage (pass/all) |
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
| zstandard / Python (PUI traffic pattern) | compress-utils / Rust | Yes | 1, 3, 7, 97, 4093 | 50% (1/2) |
| zstandard / Python (PUI traffic pattern) | compress-utils / Rust | Yes | 1 | 50% (1/2) |
| zstandard / Python (PUI traffic pattern) | compress-utils / Rust | Yes | 4096 | 50% (1/2) |
| zstandard / Python (PUI traffic pattern) | compress-utils / Rust | Yes | whole | 50% (1/2) |
| zstandard / Python (PUI traffic pattern) | compress-utils / Python | Yes | 1, 3, 7, 97, 4093 | 50% (1/2) |
| zstandard / Python (PUI traffic pattern) | compress-utils / Python | Yes | 1 | 50% (1/2) |
| zstandard / Python (PUI traffic pattern) | compress-utils / Python | Yes | 4096 | 50% (1/2) |
| zstandard / Python (PUI traffic pattern) | compress-utils / Python | Yes | whole | 50% (1/2) |
| zstandard / Python (PUI traffic pattern) | compress-utils / JS/WASM | Yes | 1, 3, 7, 97, 4093 | 50% (1/2) |
| zstandard / Python (PUI traffic pattern) | compress-utils / JS/WASM | Yes | 1 | 50% (1/2) |
| zstandard / Python (PUI traffic pattern) | compress-utils / JS/WASM | Yes | 4096 | 50% (1/2) |
| zstandard / Python (PUI traffic pattern) | compress-utils / JS/WASM | Yes | whole | 50% (1/2) |
| zstandard / Python (PUI traffic pattern) | fzstd / JavaScript | Yes | 1, 3, 7, 97, 4093 | 100% (2/2) |
| zstandard / Python (PUI traffic pattern) | fzstd / JavaScript | Yes | 1 | 100% (2/2) |
| zstandard / Python (PUI traffic pattern) | fzstd / JavaScript | Yes | 4096 | 100% (2/2) |
| zstandard / Python (PUI traffic pattern) | fzstd / JavaScript | Yes | whole | 100% (2/2) |

The **No** rows with the same package at both ends cover six one-shot and six
incremental round trips. Mixed-receiver **No** rows cover six payloads through
three sender APIs: one-shot compression, `compressobj()`, and `stream_writer()`
(18 cases per receiver). Incremental senders finalize only after all input has
been written; partial decoded prefixes before finalization are allowed.

Ordinary Python `zstandard` **Yes** rows combine its two block-flush APIs: 22
cases each with its own receiver, or 23 each with mixed receivers, including an
initially empty prefix. The receiver decodes the algorithm in the sender cell.
Untested configurations are not listed.

For compress-utils, **Yes (attempted)** records the required behavior being
probed: Rust's `flush()` only flushes the sink; Python and JS expose no flush
method. Empty writes also fail to flush codec data. In each profile, all 132
midpoint cases recover the complete input after finalization, but none passes
every mid-stream checkpoint.

The **PUI traffic pattern** rows combine its passing 101-checkpoint sequence
with an added boundary test. Their 50% and 100% figures cover those two cases;
the separate startup controls are excluded. The next section explains both.

In every profile, all 256 ordinary mixed-receiver streams round-trip exactly:
72 without mid-stream flush and 184 with it. Every one of the 16 traffic-pattern
and startup-control streams also round-trips exactly. A failed checkpoint means
output was withheld while the stream was open, not that the final bytes changed.

## PUI traffic pattern

This case reproduces a **real traffic pattern from PUI**: a larger initial
`ready` message, followed by small payloads flushed through the same open stream.
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
  bytes. Compress-utils Rust/Python/JS each return only 65,536 `A` bytes at the
  middle checkpoint: 65,958 total bytes decoded versus 65,959 submitted. The next
  payload releases the missing byte. fzstd passes all three checkpoints.

This gives compress-utils **50% (1/2)** and fzstd **100% (2/2)** in every transport
profile. Passing PUI's pattern does not establish support for arbitrary
mid-stream flushes. All final round trips pass, and Python's reference receiver
recovers every prefix while reporting `eof=false`.

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

Compress-utils probes attempt Rust's sink `flush()` and three empty compressor
writes; Python/JS also attempt three empty decoder writes. No `finish()` is
allowed at a midpoint. Rust's source returns `WouldBlock` when temporarily empty
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

## Python zstandard comparison

Python `zstandard==0.25.0` uses its `cext` backend with zstd 1.5.7 at native level
11, matching compress-utils level 5. These tests call that package directly,
with Python `zstandard` as both sender and receiver; they do not use
compress-utils or Python's standard-library `compression.zstd`.

All 62 checks pass: six one-shot and six incremental round trips, 22 midpoint
cases through each of `compressobj()` and `stream_writer()`, four pre-flush
boundary checks, one terminal-flush check, and one truncation check. The 44
midpoint cases verify all four flush checkpoints, continued writes, and final
EOF. The decoder and writer buffer settings are described in [test design](#test-design).

With default irregular transport, the first-checkpoint comparisons are:

- **4,096 random bytes:** compress-utils decodes zero before and after its
  attempted flush. Both reference sender APIs go from zero to all 4,096 bytes
  after block flush, which emits 4,105 compressed bytes.
- **131,072 random bytes:** compress-utils decodes 65,527 before and after the
  attempt. Reference `compressobj()` already exposes all 131,072. The writer
  exposes 104 decoded bytes before block flush and all 131,072 afterward.
- **131,072 repeated bytes:** compress-utils exposes 65,536 before and after the
  attempt; both reference APIs expose all 131,072 before and after block flush.

Ordinary writes can still buffer data in `zstandard`. For the random 131,072-byte
writer case, the write emits 113 compressed bytes, and `FLUSH_BLOCK` emits the
remaining 130,968 without ending the frame. The requirement applies after a
completed flush, not after every ordinary write. Partial sink writes and real
socket backpressure are not exercised by this reference writer.

Use `compressobj.flush(COMPRESSOBJ_FLUSH_BLOCK)` or
`stream_writer.flush(FLUSH_BLOCK)` for nonterminal flushing. Default
`compressobj.flush()` finishes the frame and later compression raises an error;
closing a writer also finalizes it. See the
[versioned compression API](https://python-zstandard.readthedocs.io/en/0.25.0/compressor.html).

A truncated frame does not necessarily cause `decompressobj()` to raise.
Its `flush()` returns no bytes and does not validate completion. The application
must check `eof` at transport closure; our missing-last-byte test passes because
that check rejects `eof=false`. This differs from compress-utils' decoder
`finish()` exception. See the
[decoder EOF documentation](https://python-zstandard.readthedocs.io/en/0.25.0/decompressor.html#zstandard.ZstdDecompressionObj.eof).

## Issues and measured behavior

Unless a profile is named, the byte measurements below use default irregular
transport (`1, 3, 7, 97, 4093`). No upstream fixes were applied.

### No nonterminal codec flush exposed by compress-utils

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

### zstd encoder output remains buffered

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

The [native control](results/2026-10-16/native-control.jsonl) uses the same vendored zstd 1.5.7,
native level 11, and fixture. After consuming all 131,072 input bytes and filling
a 65,536-byte output buffer, a direct empty-input `ZSTD_e_continue` call releases
the remaining **65,545 bytes without a flush or new input**. This establishes an
output-drain defect separate from the missing flush API.

### zstd decoder output remains buffered

**Reproduction:** `midpoint / repeat-131072` in each binding's JSONL file.
The compressor emits 18 bytes for 131,072 repeated `A` bytes. The binding's
decoder initially returns only **65,536 decoded bytes**. Python/JS empty decoder
writes return nothing more; Rust's reader waits for further compressed input.
The later small writes emit no compressed data, so the missing decoded bytes
remain unavailable until finalization supplies more compressed input.

The [zstd decoder loop](https://github.com/dupontcyborg/compress-utils/blob/11ea489add2435d2eb8360aad0a104a63e714fb3/src/algorithms/zstd/zstd.c#L430-L495)
has the corresponding input-consumed condition and skips the codec on an empty
write. The [native control](results/2026-10-16/native-control.jsonl) consumes the same 18-byte
block, produces 65,536 bytes on its first call, then produces the remaining
**65,536 bytes with an empty-input decoder call**. The compressed block already
contains the data; withholding it is not a requirement of the zstd format.

The [mixed-receiver tests](#mixed-receiver-checkpoints-and-transport-effects) reproduce this with
a Python `zstandard` sender that explicitly block-flushes. All three
compress-utils receivers still return only 65,536 of the 131,072 repeated bytes.
Replacing the sender therefore does not resolve this decoder defect.

**Fix direction for both drain defects:** track and drain codec output even when no
caller input remains, report the correct retry status, and ensure empty-input
drain calls actually invoke the codec. Add regression cases with compressible
and incompressible blocks crossing the binding output-buffer boundary.

### Finish cannot substitute for midway flush

Python's docstring says to "flush with .finish()", but it terminates the stream.
Python and JS both reject a write after `finish()`; the captured errors are in
the raw results. Rust's `finish(self)` consumes the compressor and returns its
sink. JS Web Streams closure likewise finishes the frame.

All six binding/codec pairs also reject a stream missing its last byte when
finalized. The tests intentionally keep that truncation check separate from
midway decoding, where an unfinished frame is normal.

### fzstd startup waits for 18 compressed bytes

fzstd fails four initial-payload cases per sender API, in every transport
profile (eight cases total):

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

### Mixed-receiver checkpoints and transport effects

All four receivers pass all 18 ordinary no-flush cases in each profile. Each
explicit-flush case requires all four checkpoints plus the final exact round
trip to pass. Both Python sender APIs produce the same pass/limitation pattern.
There are no corrupt prefixes, final mismatches, or unexpected errors.

With irregular transport, all three compress-utils receivers fail the first
checkpoint for six repeated-prefix sizes per sender API. Below, each tuple is
`submitted input → compressed stage bytes → decoded bytes`:

- `65537 → 18 → 65536`
- `131071 → 18 → 65536` and `131072 → 18 → 65536`
- `131073 → 22 → 131072`
- `262145 → 26 → 262144`
- `1048593 → 50 → 1048576`

Empty decoder writes release nothing. In this profile, the next 37-byte payload
and its four compressed bytes release the pending output, and later checkpoints
pass. All random-prefix cases and the initially empty case pass, as do the
repeated prefixes up to 65,536 bytes. The reference decoder recovers every
prefix from the same bytes, confirming that a working sender alone does not
resolve the decoder output-drain defect.

Changing chunk size affects compress-utils' codec calls:

- **1 byte:** only repeated prefixes of 65,537, 131,071, and 131,072 bytes fail
  in each binding, giving 40/46 passing cases.
- **4,096 bytes:** 34/46 cases pass, as in the irregular profile, although
  intermediate recovery can differ. For 131,071/131,072 repeated bytes, output
  still lags after the following 37-byte payload.
- **Whole batches:** Python/JS additionally withhold output for random prefixes
  of 65,537, 131,071, 131,072, 131,073, 262,145, and 1,048,593 bytes, giving 22/46
  passing cases. Rust remains at 34/46 because its internal 64 KiB input buffer
  subdivides larger batches before passing them to the codec.

fzstd fails the same eight startup cases in every profile. Splitting a 17-byte
initial batch does not increase the total bytes available. PUI's larger initial
payload changes the compressed data, independently of transport fragmentation.

### Initial buffering without a codec flush

The following pseudorandom-input observations agree across compress-utils
Rust/Python/JS with irregular transport. Empty writes and Rust's sink `flush()`
add no compressed output:

- Input sizes 1, 4,096, and 65,535: zstd emits nothing; LZ4 emits only its
  seven-byte frame header. Neither decodes application data.
- Input sizes 65,536, 65,537, and 131,071: zstd still emits nothing. LZ4 emits
  65,547 bytes and decodes 65,536, leaving partial blocks pending.
- Input 131,072: zstd emits 65,536 bytes and decodes 65,527; LZ4 emits 131,087
  and decodes all 131,072.
- Input 131,073: zstd emits 131,081 and decodes 131,072; LZ4 emits 131,087 and
  decodes 131,072.
- Input 1,048,593: zstd emits 1,048,606 and LZ4 emits 1,048,647; both decode
  1,048,576 bytes.

Automatic full-block output does not satisfy the arbitrary flush requirement.
These measurements are specific to this revision, level, and fixtures; aligned
application writes are not a general solution.

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
message size, content, and flush boundaries. The traffic-pattern probe adds
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

Run the PUI traffic pattern cases and startup controls for a receiver with:

```sh
.work/venv/bin/python tests/preamble_stream_probe.py .work/fixtures
.work/venv/bin/python tests/preamble_stream_probe.py .work/fixtures --receiver compress_utils_rust
.work/venv/bin/python tests/preamble_stream_probe.py .work/fixtures --receiver compress_utils_python
.work/venv/bin/python tests/preamble_stream_probe.py .work/fixtures --receiver compress_utils_js
```

The default receiver is `fzstd`. All four receivers are part of the full runner;
no external application checkout is needed. Each emits two `preamble_stream`
observations and two `startup_control` observations. The PUI traffic pattern rows
count only `preamble_stream`. The raw 17-byte startup control records the fzstd
limitation even after three additional empty block flushes; compress-utils passes
that control. Individual probes return 0 when integrity checks and final round
trips pass, recording incomplete checkpoints as `LIMITATION`.

Run only the ordinary Python-sender mixed-receiver cases (18 no-flush and
46 explicit-flush cases per receiver) after fixture generation:

```sh
PYTHONPATH=.work/upstream/bindings/python .work/venv/bin/python tests/interop_python.py .work/interop
node tests/interop_js.mjs .work/interop .work/upstream compress_utils_js
node tests/interop_js.mjs .work/interop .work/upstream fzstd
cargo run --locked --release --manifest-path tests/rust/Cargo.toml -- .work/interop --interop
```

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
[summary.json](results/2026-10-16/summary.json). The dependency versions are locked
in the upstream npm lockfile and this repository's [Cargo.lock](tests/rust/Cargo.lock).
The comparison uses Python `zstandard` 0.25.0 with the `cext` backend, and
msgpack 1.2.3 generates the traffic-pattern fixture. Mixed receivers also use npm
`fzstd` 0.1.1, pinned in the test [package lockfile](tests/package-lock.json).

## Recorded evidence

All explanations and results are in this README. The files below contain raw
observations, reproducibility metadata, and diagnostic output.

Each run has 552 binding/comparison observations, with two native controls
counted separately. In strict mode all four runs exit 1 for unmet flush
requirements; every individual probe exits 0 and there are zero unexpected
failures. Runner totals include diagnostics that are excluded from the main
result table:

- [Irregular chunks](results/2026-10-16/summary.json): 370 PASS / 182 LIMITATION.
- [1-byte chunks](results/2026-10-16/chunks-1/summary.json): 388 PASS / 164 LIMITATION.
- [4,096-byte chunks](results/2026-10-16/chunks-4096/summary.json): 370 PASS / 182 LIMITATION.
- [Whole batches](results/2026-10-16/chunks-whole/summary.json): 346 PASS / 206 LIMITATION.

For the irregular run, compress-utils self-round-trip probes contribute 84
passes and 134 limitations: 72 ordinary round trips plus six finalization and
six truncation checks pass; 132 midpoint and two JS Web Streams checks record
limitations. The reference package adds 62 passes, ordinary mixed receivers add
212 passes / 44 limitations, and traffic-pattern/startup cases add 12 passes /
four limitations. The two native drain controls both pass.

Raw default-profile observations are linked here; the other profile folders
use the same filenames:

- Compress-utils self-tests: [Rust](results/2026-10-16/rust.jsonl),
  [Python](results/2026-10-16/python.jsonl), [JS/WASM](results/2026-10-16/js.jsonl).
- Reference comparison: [Python zstandard](results/2026-10-16/python_zstandard.jsonl).
- Ordinary mixed receivers: [Rust](results/2026-10-16/interop_rust.jsonl),
  [Python](results/2026-10-16/interop_python.jsonl),
  [JS/WASM](results/2026-10-16/interop_js.jsonl), [fzstd](results/2026-10-16/interop_fzstd.jsonl).
- Traffic-pattern cases and startup controls: [Rust](results/2026-10-16/preamble_rust.jsonl),
  [Python](results/2026-10-16/preamble_python.jsonl),
  [JS/WASM](results/2026-10-16/preamble_js.jsonl), [fzstd](results/2026-10-16/preamble_fzstd.jsonl).
- [Shared sender-stage metadata](results/2026-10-16/interop-fixtures.json),
  [native controls](results/2026-10-16/native-control.jsonl), and
  [PUI source compatibility check](results/2026-10-16/pui-source-check.json).

Implementation: [setup](tests/setup.sh), [runner](tests/run.py),
[self-test Python](tests/python_probe.py), [self-test JS](tests/js_probe.mjs),
[self-test Rust](tests/rust/src/main.rs), [reference comparison](tests/python_zstandard_probe.py),
[mixed sender](tests/interop_fixtures.py), [Python receiver](tests/interop_python.py),
[JS/fzstd receiver](tests/interop_js.mjs), [Rust receiver](tests/rust/src/interop.rs),
[traffic-pattern sender](tests/preamble_stream_probe.py),
[traffic-pattern fzstd receiver](tests/preamble_fzstd_receiver.mjs), and
[native control source](tests/native_zstd_control.c).

## Scope and remaining work

These results cover one frame per case, no dictionaries, zstd native levels 11
and 3 as specified, deterministic in-memory transport, and Node for JS/WASM.
All bindings use the same unmodified upstream source. No upstream fixes or
issue submissions are included.

Still to test: other compression levels, larger windows, broader malformed-input
cases, additional sender/receiver combinations, LZ4 interoperability, concatenated
frames, external tools, and real network backpressure. Truncation detection and
terminal finalization are covered separately from mid-stream behavior. Browser
runtimes, performance, latency, and memory bounds are not established here.

When extending the suite, record the upstream commit, environment, algorithm,
compression settings, input and stage hashes, exact command, and expected versus
actual behavior. Use the upstream
[development guide](https://github.com/dupontcyborg/compress-utils/blob/main/DEVELOPMENT.md)
for its build/test setup. Keep generated builds and large datasets out of version
control; record source, checksum, and preparation steps for external fixtures.
