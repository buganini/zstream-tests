#!/usr/bin/env bash
# Build unmodified upstream source; generated dependencies/builds are ignored.
set -euo pipefail
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_dir"
# compress-utils v0.10.1
revision=e70d4e319c707636467e1cb7c29a7283f6738609
for tool in git cmake ninja node npm cargo rustc zig; do
    command -v "$tool" >/dev/null || { echo "Missing required tool: $tool" >&2; exit 1; }
done
mkdir -p .work
if [[ ! -d .work/upstream ]]; then
    git clone --no-checkout https://github.com/dupontcyborg/compress-utils.git .work/upstream
    git -C .work/upstream checkout --detach "$revision"
fi
if [[ $(git -C .work/upstream rev-parse HEAD) != "$revision" ]]; then
    echo "Existing .work/upstream is not at $revision; use a separate clean checkout." >&2
    exit 1
fi
if [[ -n $(git -C .work/upstream status --porcelain --untracked-files=no) ]]; then
    echo "Upstream has tracked changes; refusing to test a modified source tree." >&2
    exit 1
fi
if [[ ! -x .work/venv/bin/python ]]; then
    "${PYTHON:-python3}" -m venv .work/venv
fi
.work/venv/bin/python -m pip install pybind11==3.0.1 zstandard==0.25.0 msgpack==1.2.3
npm ci --prefix tests --ignore-scripts --cache "$repo_dir/.work/npm-cache"
pybind_dir=$(.work/venv/bin/python -m pybind11 --cmakedir)
cmake -S .work/upstream -B .work/build -G Ninja \
    -DCMAKE_BUILD_TYPE=Release -DENABLE_TESTS=OFF \
    -DBUILD_PYTHON_BINDINGS=ON -DBUILD_CPP_BINDINGS=OFF \
    -DINCLUDE_BROTLI=OFF -DINCLUDE_ZLIB=OFF -DINCLUDE_GZIP=OFF \
    -DINCLUDE_BZ2=OFF -DINCLUDE_XZ=OFF -DINCLUDE_SNAPPY=OFF -DINCLUDE_LZO=OFF \
    -DPython3_EXECUTABLE="$repo_dir/.work/venv/bin/python" \
    -Dpybind11_DIR="$pybind_dir" \
    -DBUILD_WASM_BINDINGS=ON '-DCU_WASM_ALGOS=zstd;lz4' -DCU_WASM_DIR=both
export ZIG_GLOBAL_CACHE_DIR="$repo_dir/.work/zig-cache"
cmake --build .work/build --target compress_utils_py compress_utils_wasm -j "${JOBS:-4}"
(
    cd .work/upstream/bindings/wasm
    npm ci --ignore-scripts --cache "$repo_dir/.work/npm-cache"
    node node_modules/typescript/bin/tsc -p tsconfig.json
)
cargo build --locked --release --manifest-path tests/rust/Cargo.toml
"${CC:-cc}" -O2 -I .work/upstream/third_party/zstd/lib tests/native_zstd_control.c \
    .work/build/algorithms/zstd/libzstd_library.a -o .work/native_zstd_control
echo "Ready: .work/venv/bin/python tests/run.py"
