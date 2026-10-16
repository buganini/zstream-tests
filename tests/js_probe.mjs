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
function* chunks(data, sizes = manifest.transport_chunks ?? [1, 3, 7, 97, 4093]) {
  for (let offset = 0, i = 0; offset < data.length; i++) {
    const size = sizes.length ? sizes[i % sizes.length] : data.length;
    yield data.subarray(offset, offset + size);
    offset += size;
  }
}
function receive(decoder, wire) {
  return Buffer.concat(Array.from(chunks(wire), part => Buffer.from(decoder.write(part))));
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
      const decodedBeforeFlush = decoded.length;
      const extra = hasFlush ? (encoder.flush() ?? new Uint8Array()) : new Uint8Array();
      const emptyOutput = cat(...Array.from({length: 3}, () => encoder.write(new Uint8Array())));
      decoded = cat(decoded, receive(decoder, cat(extra, emptyOutput)));
      const emptyDecoded = cat(...Array.from({length: 3}, () => decoder.write(new Uint8Array())));
      decoded = cat(decoded, emptyDecoded);
      assert.deepEqual(decoded, expected.subarray(0, decoded.length));
      stages.push({submitted: expected.length, decoded: decoded.length, write_output: wire.length,
                   decoded_before_flush: decodedBeforeFlush,
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
  const stream = api.compressionStream({ level, flushEachChunk: true });
  const reader = stream.readable.getReader();
  const writer = stream.writable.getWriter();
  const decoder = await api.createDecompressStream();
  try {
    let expected = Buffer.alloc(0), decoded = Buffer.alloc(0);
    const stages = [];
    const payloads = [Buffer.from('live stream payload'), Buffer.alloc(65537, 65),
                      fs.readFileSync(path.join(root, 'random.bin')).subarray(0, 131072)];
    for (const data of payloads) {
      // Read concurrently to satisfy TransformStream backpressure. A flushed
      // batch must arrive before the next write or close, not after a timeout.
      const next = reader.read();
      await writer.write(data);
      const {value, done} = await next;
      assert.equal(done, false, 'stream closed at a midpoint');
      expected = cat(expected, data);
      decoded = cat(decoded, receive(decoder, value));
      assert.deepEqual(decoded, expected);
      stages.push({submitted: expected.length, decoded: decoded.length, wire_bytes: value.length});
    }
    const consumeTail = (async () => {
      while (true) {
        const {value, done} = await reader.read();
        if (done) break;
        decoded = cat(decoded, receive(decoder, value));
      }
    })();
    await writer.close();
    await consumeTail;
    decoded = cat(decoded, decoder.finish());
    assert.deepEqual(decoded, expected);
    return {status: 'PASS', flush_each_chunk: true, writer_flush_api: typeof writer.flush === 'function',
            stages, final_roundtrip: true};
  } finally { decoder.destroy(); }
}
let failed = false;
const libraryVersions = {};
async function run(codec, test, name, operation) {
  const row = {binding: 'js', codec, test, case: name, level,
               library_version: libraryVersions[codec],
               transport_chunks: manifest.transport_chunks ?? [1, 3, 7, 97, 4093]};
  try { Object.assign(row, await operation()); }
  catch (error) { Object.assign(row, {status: 'FAIL', error: String(error)}); failed = true; }
  console.log(JSON.stringify(row));
}
for (const codec of ['zstd', 'lz4']) {
  const api = await import(pathToFileURL(path.join(upstream, 'bindings/wasm/dist/algorithms', codec, 'index.js')));
  libraryVersions[codec] = await api.version();
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
  await run(codec, 'web_stream_flush_each_chunk', 'text-repeat65537-random131072', () => webStream(api));
}
process.exitCode = failed ? 1 : 0;
