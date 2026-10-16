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

This repository currently contains documentation only. No test harness, fixtures,
or test results have been added yet. Whether compress-utils satisfies these
streaming requirements has not been verified.

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

## Planned coverage

- Mid-stream flush and continued decoding for both zstd and LZ4, as described
  above. This is the primary acceptance criterion.
- Incremental input and output: tiny buffers, irregular transport chunks, and
  repeated write/flush cycles.
- Round-trip correctness for empty inputs, binary data, and large inputs.
- Error handling: invalid options, malformed data, and truncated streams.
- Compatibility between language bindings and external compression tools where
  their formats are compatible.
- Flush latency, compression ratio, and runtime measurements using reproducible
  inputs and documented flush frequency.

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
