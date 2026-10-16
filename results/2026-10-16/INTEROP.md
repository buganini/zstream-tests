# Python zstandard sender with compress-utils and fzstd receivers

Test date: 2026-10-16 (Asia/Taipei).

**All 184 mixed-receiver streams round-trip exactly after finalization. Neither
compress-utils nor fzstd passes every required mid-stream flush checkpoint.**
The Python `zstandard` reference receiver recovers every flushed prefix from the
same compressed bytes while the frame remains open.

## Sender, receivers, and method

Sender: Python `zstandard==0.25.0`, `cext` backend, zstd 1.5.7, native level 11
(equivalent to compress-utils level 5). Both sender APIs are exercised:

- `compressobj().flush(COMPRESSOBJ_FLUSH_BLOCK)`.
- `stream_writer(write_size=113).flush(FLUSH_BLOCK)` with a sink that accepts each
  write in full. The sender also uses `write_return_read=True, closefd=False`.

Receivers: unmodified compress-utils source version 0.9.0 at
[`11ea489`](https://github.com/dupontcyborg/compress-utils/commit/11ea489add2435d2eb8360aad0a104a63e714fb3)
through Rust, Python, and JS/WASM; and npm `fzstd==0.1.1` through its JavaScript
`Decompress` streaming API in Node 22.22.1. See the [environment](README.md#version-and-environment)
and [npm lockfile](../../tests/package-lock.json).

Each sender API generates 23 cases: repeated and deterministic pseudorandom
prefixes at the 11 sizes in the [main report](README.md#test-design), plus an
initially empty prefix. Thus each receiver runs 46 cases. Each case uses one
compressor and one receiver throughout four stages:

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

The generator independently verifies every stage with Python `zstandard`:
decoded bytes exactly equal all submitted input, `eof` stays false, and the
finalized stream subsequently matches all input with `eof` true. Saved stage
hashes, sizes, reference checks, and sender versions are in
[interop-fixtures.json](interop-fixtures.json). This adds two initially empty
cases to the 44-case Python-to-Python midway comparison in the main report.

## Results

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
The reference decoder passes every checkpoint in all 46 generated streams.

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

Source inspection explains these observations: before creating its frame state,
`Decompress.push()` buffers non-final input until at least **18 compressed bytes**
have accumulated. See `ncs < 18` in the published
[0.1.1 ESM source](https://cdn.jsdelivr.net/npm/fzstd@0.1.1/esm/index.mjs), also
installed as `tests/node_modules/fzstd/esm/index.mjs` at lines 678–692. A valid
shorter frame header plus flushed block can already be decoded by the reference
receiver, but fzstd waits for more compressed input. Consequently, even a 4 KiB
application message can stall when highly compressible. The 18-byte threshold
describes startup buffering; it is not a general output-latency guarantee.

For a request/response stream, these bytes can remain unavailable if the sender
waits for the response before writing more. Setting `final=true` at a midpoint
would signal completion of an unfinished stream and does not meet the required
same-stream contract. A possible fix is incremental header parsing based on the
actual available header/block lengths; no fzstd changes or workarounds were
implemented or validated here.

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
well as all mixed receivers. [summary.json](summary.json) records 286 PASS and
178 LIMITATION observations, with the two native controls counted separately.

After fixture generation, run just the Python sender → fzstd receiver cases:

```sh
node tests/interop_js.mjs .work/interop .work/upstream fzstd
```

For the other receivers:

```sh
PYTHONPATH=.work/upstream/bindings/python .work/venv/bin/python tests/interop_python.py .work/interop
node tests/interop_js.mjs .work/interop .work/upstream compress_utils_js
cargo run --locked --release --manifest-path tests/rust/Cargo.toml -- .work/interop --interop
```

Individual receiver probes exit 0 when final round trips and integrity checks
pass, while recording unmet checkpoints as `LIMITATION`. Use the runner's strict
flag to enforce the mid-stream requirement as an exit-status failure.

Scope: one zstd frame per case, no dictionaries, native level 11, deterministic
in-memory transport, and Node rather than a browser. This does not establish
behavior for other levels, larger windows, malformed/truncated input to fzstd,
concatenated frames, network backpressure, or timing and memory limits.
