# Python zstandard sender with compress-utils and fzstd receivers

Test date: 2026-10-16 (Asia/Taipei).

Unless stated otherwise, counts and stage measurements below use the default
irregular transport chunks. The [transport comparison](#transport-chunk-size-comparison)
also tests fixed 1-byte, fixed 4,096-byte, and whole-batch delivery.
The separate [294-byte preamble case](#294-byte-preamble-stream) uses native level 3 and
has its own case counts; the ordinary mixed-receiver counts below exclude it.

**All 256 mixed-receiver streams round-trip exactly after finalization: 72 without
mid-stream flush and 184 with it. Neither
compress-utils nor fzstd passes every required mid-stream flush checkpoint.**
The Python `zstandard` reference receiver recovers every flushed prefix from the
same compressed bytes while the frame remains open.

## Sender, receivers, and method

Sender: Python `zstandard==0.25.0`, `cext` backend, zstd 1.5.7, native level 11
(equivalent to compress-utils level 5). The sender APIs are:

- One-shot `ZstdCompressor.compress()` for the no-flush cases.
- `compressobj()`, with `flush(COMPRESSOBJ_FLUSH_BLOCK)` only in the mid-stream
  flush cases and `flush(COMPRESSOBJ_FLUSH_FINISH)` at finalization.
- `stream_writer(write_size=113)`, with `flush(FLUSH_BLOCK)` only in the
  mid-stream flush cases and `close()` at finalization. Its sink accepts each
  write in full; the sender also uses `write_return_read=True, closefd=False`.

Receivers: unmodified compress-utils source version 0.9.0 at
[`11ea489`](https://github.com/dupontcyborg/compress-utils/commit/11ea489add2435d2eb8360aad0a104a63e714fb3)
through Rust, Python, and JS/WASM; and npm `fzstd==0.1.1` through its JavaScript
`Decompress` streaming API in Node 22.22.1. See the [environment](README.md#version-and-environment)
and [npm lockfile](../../tests/package-lock.json).

For mid-stream flush, each streaming sender API generates 23 cases: repeated and
deterministic pseudorandom prefixes at the 11 sizes in the
[main report](README.md#test-design), plus an initially empty prefix. Thus each
receiver runs 46 mid-stream flush cases. Each uses one compressor and one receiver
throughout four stages:

1. Write the initial prefix and block-flush.
2. Write 37 `B` bytes and block-flush.
3. Write 4,096 bytes cycling through 0–255 and block-flush.
4. Perform an empty write and block-flush.

The generator saves all compressed output from each write and completed flush as
a separate stage. Every receiver replays these exact stage bytes, split into
transport chunks cycling through 1, 3, 7, 97, and 4,093 bytes. The receiver's
decoded output is checked **before the next stage is delivered**. No final bytes
are supplied until all four checkpoints have been measured.

Python/JS receivers additionally receive three empty non-final decoder writes at
each checkpoint. Rust uses 113-byte output reads and a source that returns
`WouldBlock` when temporarily empty; EOF is supplied only after sender finish.
fzstd receives `push(chunk, false)` throughout the checkpoints, then
`push(empty, true)` only after the final compressed bytes. This follows its
[streaming API](https://github.com/101arrowz/fzstd#usage); the `final` argument
marks transport completion and is not a mid-stream flush operation.

For these 46 flush cases, the generator independently verifies every stage with
Python `zstandard`: decoded bytes exactly equal all submitted input, `eof` stays false, and the
finalized stream subsequently matches all input with `eof` true. Saved stage
hashes, sizes, reference checks, and sender versions are in
[interop-fixtures.json](interop-fixtures.json). This adds two initially empty
cases to the 44-case Python-to-Python midway comparison in the main report.

### Without mid-stream flush

Each receiver also runs 18 no-flush cases: six payloads through each of the three
sender APIs. The payloads are empty input, one byte, 4,096 bytes of text, 65,537
bytes of binary data, and 1,048,593 bytes each of repeated and deterministic
pseudorandom data, using the same fixtures as the main round-trip suite.

The two incremental senders write chunks cycling through 1, 7, 63, 1,024, and
65,521 bytes and finalize once after all writes. No block flush is called. Every
write's compressed output is saved as a stage and delivered to the same receiver
in the irregular transport chunks above, followed by finalization output. For
one-shot compression, the complete frame is delivered in those same transport
chunks and then the receiver is finalized. Thus the one-shot label describes the
sender API; receivers use their streaming APIs in all mixed tests.

Intermediate decoded data must be an exact prefix of submitted input, but may
be incomplete. Passing requires byte-for-byte recovery of the full payload after
finalization. The Python reference decoder independently checks every prefix and
requires `eof` at completion. The manifest and receiver observations distinguish
these cases using `midstream_flush: false` and `oneshot_roundtrip` or
`stream_roundtrip`, so they do not contribute to mid-stream acceptance counts.

## Results

All **18/18 no-flush cases pass for each receiver**: compress-utils Rust, Python,
JS/WASM, and fzstd. This is six one-shot, six `compressobj()`, and six
`stream_writer()` cases per receiver, or 72 passing observations in total.

The following table covers only the 46 mid-stream flush cases per receiver.
Each row uses Python `zstandard` as sender. A case passes only if **all four
flush checkpoints and the final exact round trip** pass. Counts describe these
fixtures, not estimated success rates for arbitrary traffic.

| Receiver | Every flush checkpoint passes | Withheld prefix at a checkpoint | Exact final round trip |
| --- | ---: | ---: | ---: |
| compress-utils Rust | 34/46 | 12/46 | 46/46 |
| compress-utils Python | 34/46 | 12/46 | 46/46 |
| compress-utils JS/WASM | 34/46 | 12/46 | 46/46 |
| fzstd 0.1.1 | 38/46 | 8/46 | 46/46 |

Both sender APIs produce the same pass/limitation pattern for each receiver.
There are no corrupt decoded prefixes, final mismatches, or unexpected errors.
The reference decoder passes every flush checkpoint in all 46 generated streams
that use mid-stream flush, and all 18 no-flush streams round-trip exactly.

### compress-utils receivers

All three bindings agree. Only these repeated-byte prefixes fail, in both sender
API variants, at the first checkpoint:

| Submitted bytes after flush | Compressed stage bytes | Decoded bytes |
| ---: | ---: | ---: |
| 65,537 | 18 | 65,536 |
| 131,071 | 18 | 65,536 |
| 131,072 | 18 | 65,536 |
| 131,073 | 22 | 131,072 |
| 262,145 | 26 | 262,144 |
| 1,048,593 | 50 | 1,048,576 |

Empty decoder writes release nothing. The next 37-byte write plus block flush
supplies four more compressed bytes, after which all pending input is recovered;
the later checkpoints also pass. All random-prefix cases and the initially empty
case pass every checkpoint, as do the tested repeated prefixes up to 65,536 bytes.

This reproduces the [decoder output-drain defect](README.md#3-zstd-decoder-output-can-remain-undrained-after-compressed-input-is-consumed)
with a sender that does support explicit nonterminal flush. The reference decoder
recovers the entire prefix from the same stage, and the direct native zstd control
shows that zero-input decoding can drain the withheld output. A working sender
alone therefore does not satisfy the requirement with these receivers.

### fzstd receiver

fzstd fails four cases per sender API. The following checkpoints have incomplete
output; compressed bytes are cumulative from the start of the frame:

| Initial prefix | Checkpoint | Submitted bytes | Compressed bytes received | Decoded bytes |
| --- | --- | ---: | ---: | ---: |
| Empty | After the following 37 `B` bytes | 37 | 16 | 0 |
| 1 random byte | Initial flush | 1 | 10 | 0 |
| 1 random byte | After the following 37 `B` bytes | 38 | 14 | 0 |
| 1 repeated byte | Initial flush | 1 | 10 | 0 |
| 1 repeated byte | After the following 37 `B` bytes | 38 | 14 | 0 |
| 4,096 repeated bytes | Initial flush | 4,096 | 17 | 0 |

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

### Transport chunk size comparison

The [single consolidated result table](../../README.md#current-status) shows
pass percentages for all bindings, algorithms, flush modes, and four transport
profiles. All four runs use identical application input, sender parameters, and
flush boundaries. Changing delivery chunks does not change the saved compressed
bytes or coalesce separate stages. `whole` sends each stage without harness
splitting; Rust still reads through the binding's 64 KiB compressed-input buffer.

Every profile passes all 18 no-flush mixed cases per receiver. Mid-stream results
depend on receiver and delivery pattern:

- Default irregular delivery: compress-utils Rust/Python/JS each pass 34/46
  (73.91%); fzstd passes 38/46 (82.61%).
- Fixed 1-byte delivery: compress-utils Rust/Python/JS each pass 40/46 (86.96%);
  fzstd remains at 38/46 (82.61%).
- Fixed 4,096-byte delivery: compress-utils Rust/Python/JS each pass 34/46
  (73.91%); fzstd remains at 38/46 (82.61%).
- Whole-batch delivery: compress-utils Python/JS each pass 22/46 (47.83%), Rust
  passes 34/46 (73.91%), and fzstd remains at 38/46 (82.61%).

All complete round trips still pass. Whole-batch Python/JS decoding additionally
withholds output for random prefixes of 65,537, 131,071, 131,072, 131,073,
262,145, and 1,048,593 bytes, through both sender APIs. Rust's internal input
buffer subdivides larger batches, so its `whole` mode does not deliver the same
codec-call sizes as the Python/JS push APIs. With 1-byte delivery, only repeated
prefixes of 65,537, 131,071, and 131,072 bytes fail in each compress-utils binding.
These observations reinforce the output-drain issue; none of the transport
profiles makes compress-utils satisfy every flush checkpoint.

fzstd fails the same eight cases in all profiles. In particular, a 17-byte first
stage stays 17 bytes regardless of the delivery chunk size. The 294-byte preamble
case changes the initial compressed batch, which is a different variable from
splitting that batch for transport.

Raw observations and summaries are in [chunks-1](chunks-1/summary.json),
[chunks-4096](chunks-4096/summary.json), and [chunks-whole](chunks-whole/summary.json).
The complete runner counts are respectively 388 PASS / 164 LIMITATION,
370 PASS / 182 LIMITATION, and 346 PASS / 206 LIMITATION. The default is
370 PASS / 182 LIMITATION. These include two preamble cases and two startup
controls through all four receivers (12 additional passes and four limitations
per profile, beyond the ordinary suites). These
are separate runs; native controls are counted separately. Every strict run
exits 1 for unmet flush requirements, with zero unexpected failures.

### 294-byte preamble stream

The reproducible [Python sender](../../tests/preamble_stream_probe.py) sends the
same bytes to compress-utils Rust, Python, and JS/WASM, and the
[fzstd receiver](../../tests/preamble_fzstd_receiver.mjs). The initial message
produces **294 compressed bytes**, including the frame header, before the
subsequent messages. Those bytes decode to 422 bytes of application data. The
preamble is ordinary data in the same stream, not padding, an extra flush, or
a separate frame. The tested behavior is:

- One persistent `compressobj()` at native level 3, `window_log=22` (4 MiB),
  without a content size or checksum.
- For the message-sequence case, pack each complete envelope with MessagePack,
  compress it, and call
  `flush(COMPRESSOBJ_FLUSH_BLOCK)` once. Send the concatenated output of
  `compress()` and that flush as one message batch. The boundary case uses raw
  payload bytes after the MessagePack preamble, with the same flush procedure.
- Send the preamble first, then retain both codec contexts for subsequent
  messages. fzstd receives `push(packet, false)`; it is not finalized between
  messages. There is no padding or additional empty flush.

Every transport profile runs two acceptance cases per receiver:

- **Preamble then 100 messages:** all four receivers pass **101/101 checkpoints**.
  The MessagePack bytes must match before the next message is supplied. The
  preamble is 422 uncompressed bytes and 294 compressed bytes, above fzstd's
  startup threshold. Later packets shrink to 14 bytes and still decode
  immediately. These are deterministic envelopes with fixed IDs, not captured
  application traffic.
- **Preamble then 65,537 repeated bytes:** flush the preamble, flush 65,537 `A`
  bytes, then flush 37 `B` bytes, checking output before each next write. The
  repeated payload compresses to 4 bytes. All three compress-utils bindings
  return only 65,536 of its 65,537 bytes: 65,958 total decoded bytes versus
  65,959 submitted including the preamble. The next payload releases the missing
  byte. fzstd passes all three checkpoints. This case uses raw payloads after
  the preamble to exercise the decoder's 64 KiB boundary.

The consolidated table therefore reports **50% (1/2)** for each compress-utils
receiver and **100% (2/2)** for fzstd, in every chunk profile. A preamble avoids
fzstd's startup delay in these cases, but does not correct compress-utils'
output-drain defect. All final round trips pass. The Python reference receiver
recovers every flushed prefix with `eof=false` and validates EOF after finalization.

`whole` delivers one complete flushed batch per message. The other three
profiles split each batch before the receiver as an extra fragmentation check.
The same generated bytes are replayed through the existing compress-utils
interop probes, with zero extra empty decoder writes at checkpoints. Rust reads
until `WouldBlock`, without declaring EOF. After all checkpoints, the test
finalizes solely to verify full-stream integrity;
none of the measured messages relies on finalization.

Two diagnostic controls use the same level-3 encoder in every profile:

- **Raw 17-byte prefix first:** 17 repeated `A` bytes produce 17 compressed bytes.
  The reference and all compress-utils receivers decode all 17 bytes, while
  fzstd returns none. Three additional empty block flushes produce **zero bytes**
  and do not resolve the stall. Only the
  following 37-byte payload and its 4 compressed bytes allow fzstd to catch up.
- **Preamble, then the same raw prefix:** after decoding the preamble, the 17-byte payload
  compresses to 4 bytes and decodes immediately in all receivers, as does the
  next 37-byte payload.
  This control uses raw data after the preamble to isolate decoder startup;
  those later raw payloads are not MessagePack envelopes.

The initial preamble initializes the decoder without an extra flush after a
message. This case's level-3 settings also
differ from the ordinary level-11 comparison: 4,096 repeated bytes compress to
18 initial bytes at level 3, versus 17 at level 11. Neither this preamble case nor
its controls establish arbitrary small-first-payload support in fzstd.

Fixture provenance: in the 101-checkpoint case, the preamble is a `ready`
envelope and the following messages are `result` envelopes, derived from PUI commit
`8a8ef99da854c75d5c9abfd24e03bc21f8f5a880`. As a source compatibility check,
all 101 generated packets matched the actual
PUI `StreamCodec.encode()` output byte-for-byte, and PUI's packaged JavaScript
`StreamDecoder` decoded and body-validated every envelope under Node. Source
hashes and results are in [pui-source-check.json](pui-source-check.json). This
check used a local PUI checkout; the permanent reproduction runs without it.
PUI delivers one complete batch per WebSocket message to `StreamDecoder.decode()`
and discards its context on close. The fragmentation profiles call fzstd directly,
not PUI's envelope decoder per fragment. No live WebSocket/browser UI was exercised.

Default observations: [Rust](preamble_rust.jsonl), [Python](preamble_python.jsonl),
[JS/WASM](preamble_js.jsonl), and [fzstd](preamble_fzstd.jsonl). The same filenames
under [chunks-1](chunks-1/summary.json), [chunks-4096](chunks-4096/summary.json),
and [chunks-whole](chunks-whole/summary.json) record the other delivery profiles.
Each file contains two `preamble_stream` cases and two `startup_control` cases;
controls are excluded from the preamble percentage in the consolidated table.
Per-stage compressed hashes and expected-payload hashes match across receivers.

## Evidence and reproduction

- Raw observations: [Rust](interop_rust.jsonl), [Python](interop_python.jsonl),
  [JS/WASM](interop_js.jsonl), and [fzstd](interop_fzstd.jsonl).
- [Shared sender generator](../../tests/interop_fixtures.py),
  [Rust receiver](../../tests/rust/src/interop.rs),
  [Python receiver](../../tests/interop_python.py), and
  [JS/WASM and fzstd receiver](../../tests/interop_js.mjs).

From the repository root with prerequisites on `PATH`:

```sh
bash tests/setup.sh
.work/venv/bin/python tests/run.py --require-midstream-flush
```

Expected strict exit: **1**, because some checkpoints are unmet. The complete
runner includes the original binding probes and Python-to-Python comparison as
well as all mixed receivers and the preamble cases with their startup controls.
[summary.json](summary.json) records 370 PASS and 182 LIMITATION observations,
with the two native controls counted separately.

After fixture generation, run just the Python sender → fzstd receiver cases
(18 without mid-stream flush and 46 with it):

```sh
node tests/interop_js.mjs .work/interop .work/upstream fzstd
```

For the other receivers, also running both modes:

```sh
PYTHONPATH=.work/upstream/bindings/python .work/venv/bin/python tests/interop_python.py .work/interop
node tests/interop_js.mjs .work/interop .work/upstream compress_utils_js
cargo run --locked --release --manifest-path tests/rust/Cargo.toml -- .work/interop --interop
```

Individual receiver probes exit 0 when final round trips and integrity checks
pass, while recording unmet checkpoints as `LIMITATION`. Use the runner's strict
flag to enforce the mid-stream requirement as an exit-status failure.

Scope: one zstd frame per case, no dictionaries, native level 11 (level 3 for the
preamble case and its controls), deterministic
in-memory transport, and Node rather than a browser. This does not establish
behavior for other levels, larger windows, malformed/truncated input to fzstd,
concatenated frames, network backpressure, or timing and memory limits.
