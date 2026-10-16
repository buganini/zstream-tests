// Exercise the public JS/WASM binding without a browser or test framework.
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import assert from 'node:assert/strict';

const root = process.argv[2];
const upstream = process.argv[3];
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'manifest.json')));
const level = 5;
const cat = (...parts) => Buffer.concat(parts.map(p => Buffer.from(p)));
function* chunks(data, sizes = [1, 3, 7, 97, 4093]) {
  for (let offset = 0, i = 0; offset < data.length; i++) {
    const size = sizes[i % sizes.length];
    yield data.subarray(offset, offset + size);
    offset += size;
  }
}
function receive(decoder, wire) {
  return cat(...Array.from(chunks(wire), part => decoder.write(part)));
}
async function roundtrip(api, data, streaming) {
  let packed, restored;
  if (!streaming) {
    packed = await api.compress(data, { level });
    restored = await api.decompress(packed);
  } else {
    const encoder = await api.createCompressStream({ level });
    const decoder = await api.createDecompressStream();
    try {
      const wireParts = [], decodedParts = [];
      for (const part of chunks(data, [1, 7, 63, 1024, 65521])) {
        const wire = encoder.write(part);
        wireParts.push(wire);
        decodedParts.push(receive(decoder, wire));
      }
      const tail = encoder.finish();
      wireParts.push(tail);
      decodedParts.push(receive(decoder, tail), decoder.finish());
      packed = cat(...wireParts);
      restored = cat(...decodedParts);
    } finally { encoder.destroy(); decoder.destroy(); }
  }
  assert.deepEqual(Buffer.from(restored), data);
  return { status: 'PASS', input_bytes: data.length, compressed_bytes: packed.length };
}
async function midpoint(api, data) {
  const encoder = await api.createCompressStream({ level });
  const decoder = await api.createDecompressStream();
  try {
    let expected = Buffer.alloc(0), decoded = Buffer.alloc(0);
    const stages = [], hasFlush = typeof encoder.flush === 'function';
    const suffix = Buffer.from(Array.from({length: 4096}, (_, i) => i % 256));
    for (const part of [data, Buffer.alloc(37, 66), suffix, Buffer.alloc(0)]) {
      expected = cat(expected, part);
      const wire = encoder.write(part);
      decoded = cat(decoded, receive(decoder, wire));
      const extra = hasFlush ? (encoder.flush() ?? new Uint8Array()) : new Uint8Array();
      const emptyOutput = cat(...Array.from({length: 3}, () => encoder.write(new Uint8Array())));
      decoded = cat(decoded, receive(decoder, cat(extra, emptyOutput)));
      const emptyDecoded = cat(...Array.from({length: 3}, () => decoder.write(new Uint8Array())));
      decoded = cat(decoded, emptyDecoded);
      assert.deepEqual(decoded, expected.subarray(0, decoded.length));
      stages.push({submitted: expected.length, decoded: decoded.length, write_output: wire.length,
                   flush_output: extra.length, empty_write_output: emptyOutput.length,
                   empty_decode_output: emptyDecoded.length});
    }
    decoded = cat(decoded, receive(decoder, encoder.finish()), decoder.finish());
    assert.deepEqual(decoded, expected);
    return {status: hasFlush && stages.every(s => s.decoded === s.submitted) ? 'PASS' : 'LIMITATION',
            flush_api: hasFlush, stages, final_roundtrip: true};
  } finally { encoder.destroy(); decoder.destroy(); }
}
async function finishIsTerminal(api) {
  const encoder = await api.createCompressStream({ level });
  const decoder = await api.createDecompressStream();
  try {
    const wire = cat(encoder.write(Buffer.from('A')), encoder.finish());
    assert.deepEqual(cat(receive(decoder, wire), decoder.finish()), Buffer.from('A'));
    let error;
    try { encoder.write(Buffer.from('B')); } catch (e) { error = e.message; }
    assert.ok(error, 'write after finish unexpectedly accepted');
    return {status: 'PASS', write_after_finish_error: error};
  } finally { encoder.destroy(); decoder.destroy(); }
}
async function truncated(api) {
  const encoder = await api.createCompressStream({ level });
  const decoder = await api.createDecompressStream();
  try {
    const wire = cat(encoder.write(Buffer.alloc(4096, 65)), encoder.finish());
    let error;
    try { receive(decoder, wire.subarray(0, -1)); decoder.finish(); } catch (e) { error = e.message; }
    assert.ok(error, 'missing final byte was not detected');
    return {status: 'PASS', truncated_error: error};
  } finally { encoder.destroy(); decoder.destroy(); }
}
async function webStream(api) {
  const data = Buffer.from('live stream payload');
  const stream = api.compressionStream({ level });
  const wire = [];
  const consume = (async () => { for await (const part of stream.readable) wire.push(part); })();
  const writer = stream.writable.getWriter();
  await writer.write(data);
  // No timing assertion: API inspection plus close/finalization round trip.
  const hasFlush = typeof writer.flush === 'function';
  await writer.close();
  await consume;
  const decoder = await api.createDecompressStream();
  try {
    assert.deepEqual(cat(receive(decoder, cat(...wire)), decoder.finish()), data);
    return {status: hasFlush ? 'PASS' : 'LIMITATION', writer_flush_api: hasFlush,
            close_roundtrip: true};
  } finally { decoder.destroy(); }
}
let failed = false;
async function run(codec, test, name, operation) {
  const row = {binding: 'js', codec, test, case: name, level};
  try { Object.assign(row, await operation()); }
  catch (error) { Object.assign(row, {status: 'FAIL', error: String(error)}); failed = true; }
  console.log(JSON.stringify(row));
}
for (const codec of ['zstd', 'lz4']) {
  const api = await import(pathToFileURL(path.join(upstream, 'bindings/wasm/dist/algorithms', codec, 'index.js')));
  for (const testCase of manifest.roundtrip) {
    const data = fs.readFileSync(path.join(root, testCase.file));
    for (const streaming of [false, true]) {
      await run(codec, streaming ? 'stream_roundtrip' : 'oneshot_roundtrip', testCase.name,
                () => roundtrip(api, data, streaming));
    }
  }
  for (const kind of ['random', 'repeat']) {
    const source = fs.readFileSync(path.join(root, `${kind}.bin`));
    for (const size of manifest.midpoint_sizes) {
      await run(codec, 'midpoint', `${kind}-${size}`, () => midpoint(api, source.subarray(0, size)));
    }
  }
  await run(codec, 'finish_is_terminal', 'A-then-B', () => finishIsTerminal(api));
  await run(codec, 'truncated', 'missing-last-byte', () => truncated(api));
  await run(codec, 'web_stream_close', 'small-text', () => webStream(api));
}
process.exitCode = failed ? 1 : 0;
