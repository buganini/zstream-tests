// Replay the exact same sender stages through compress-utils WASM or fzstd.
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import assert from 'node:assert/strict';
import * as fzstd from 'fzstd';

const [root, upstream, receiver] = process.argv.slice(2);
assert.ok(['compress_utils_js', 'fzstd'].includes(receiver));
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'manifest.json')));
const api = receiver === 'compress_utils_js'
  ? await import(pathToFileURL(path.join(upstream, 'bindings/wasm/dist/algorithms/zstd/index.js')))
  : null;
const fzstdVersion = JSON.parse(fs.readFileSync(new URL('./node_modules/fzstd/package.json', import.meta.url))).version;

async function probe(testCase) {
  const expected = fs.readFileSync(path.join(root, testCase.expected.file));
  const output = [];
  let finalCallbacks = 0;
  const decoder = api ? await api.createDecompressStream() : new fzstd.Decompress((chunk, final) => {
    output.push(Buffer.from(chunk)); // Copy: callback storage can be reused.
    if (final) finalCallbacks++;
  });
  const push = part => {
    if (api) output.push(Buffer.from(decoder.write(part)));
    else decoder.push(part, false);
  };
  const feed = wire => {
    for (let offset = 0, i = 0; offset < wire.length; i++) {
      const size = manifest.transport_chunks[i % manifest.transport_chunks.length];
      push(wire.subarray(offset, offset + size));
      offset += size;
    }
  };
  try {
    const stages = [];
    for (const stage of testCase.stages) {
      const wire = fs.readFileSync(path.join(root, stage.file));
      feed(wire);
      const beforeEmpty = output.reduce((sum, part) => sum + part.length, 0);
      for (let i = 0; i < 3; i++) push(new Uint8Array());
      const decoded = Buffer.concat(output);
      assert.deepEqual(decoded, expected.subarray(0, decoded.length));
      assert.ok(decoded.length <= stage.submitted);
      assert.equal(finalCallbacks, 0, 'receiver declared completion before transport end');
      stages.push({submitted: stage.submitted, decoded: decoded.length, wire_bytes: wire.length,
                   empty_decode_output: decoded.length - beforeEmpty,
                   complete: decoded.length === stage.submitted});
    }
    feed(fs.readFileSync(path.join(root, testCase.tail.file)));
    if (api) output.push(Buffer.from(decoder.finish()));
    else { decoder.push(new Uint8Array(), true); assert.equal(finalCallbacks, 1); }
    const decoded = Buffer.concat(output);
    assert.deepEqual(decoded, expected);
    return {status: stages.every(s => s.complete) ? 'PASS' : 'LIMITATION', stages,
            final_roundtrip: true, final_bytes: decoded.length};
  } finally { if (api) decoder.destroy(); }
}

let failed = false;
for (const testCase of manifest.cases) {
  const row = {binding: receiver === 'fzstd' ? 'interop_fzstd' : 'interop_js',
               test: 'sender_flush', codec: 'zstd', sender: 'python_zstandard', receiver,
               case: testCase.name, sender_api: testCase.sender_api, native_level: manifest.native_level};
  if (receiver === 'fzstd') row.receiver_version = fzstdVersion;
  try { Object.assign(row, await probe(testCase)); }
  catch (error) { Object.assign(row, {status: 'FAIL', error: String(error)}); failed = true; }
  console.log(JSON.stringify(row));
}
process.exitCode = failed ? 1 : 0;
