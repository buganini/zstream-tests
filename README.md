# compress-utils testing

This repository is a workspace for testing
[dupontcyborg/compress-utils](https://github.com/dupontcyborg/compress-utils),
a compression and decompression library with bindings for multiple languages.

Use this repository to collect test cases, reproducible bug reports, and results
from evaluating the upstream library.

## Current status

This repository currently contains documentation only. No test harness, fixtures,
or test results have been added yet.

## Planned coverage

- Round-trip correctness: decompression restores the original bytes.
- Edge cases: empty inputs, binary data, and large inputs.
- Error handling: invalid options, malformed data, and truncated streams.
- Compatibility between language bindings and external compression tools where
  their formats are compatible.
- Compression ratio and runtime measurements using reproducible inputs.

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
