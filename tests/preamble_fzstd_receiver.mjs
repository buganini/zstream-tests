// Check each complete envelope before delivering any bytes from the next one.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createHash } from 'node:crypto';
import { Decompress } from 'fzstd';

const { cases, ...metadata } = JSON.parse(fs.readFileSync(0, 'utf8'));
const version = JSON.parse(fs.readFileSync(new URL('./node_modules/fzstd/package.json', import.meta.url))).version;
const bytes = value => {
  const result = Buffer.from(value.base64, 'base64');
  assert.equal(result.length, value.bytes);
  assert.equal(createHash('sha256').update(result).digest('hex'), value.sha256);
  return result;
};

function probe(testCase) {
  const expected = bytes(testCase.expected), output = [];
  let finalCallbacks = 0, wireTotal = 0;
  const decoder = new Decompress((chunk, final) => {
    output.push(Buffer.from(chunk));
    if (final) finalCallbacks++;
  });
  const feed = wire => {
    const sizes = metadata.transport_chunks;
    for (let offset = 0, i = 0; offset < wire.length; i++) {
      const size = sizes.length ? sizes[i % sizes.length] : wire.length;
      decoder.push(wire.subarray(offset, offset + size), false);
      offset += size;
    }
  };
  const stages = testCase.stages.map(({wire, ...stage}) => {
    feed(bytes(wire));
    wireTotal += wire.bytes;
    // No extra pushes, final=true, or next-message bytes to release this message.
    const decoded = Buffer.concat(output);
    assert.ok(decoded.length <= stage.submitted);
    assert.deepEqual(decoded, expected.subarray(0, decoded.length));
    assert.equal(finalCallbacks, 0);
    return {...stage, wire_bytes: wire.bytes, wire_sha256: wire.sha256,
            cumulative_wire_bytes: wireTotal, decoded: decoded.length,
            complete: decoded.length === stage.submitted};
  });
  feed(bytes(testCase.tail));
  decoder.push(new Uint8Array(), true);
  assert.equal(finalCallbacks, 1);
  assert.deepEqual(Buffer.concat(output), expected);
  return {status: stages.every(stage => stage.complete) ? 'PASS' : 'LIMITATION',
          stages, final_roundtrip: true, final_bytes: expected.length,
          finalization: 'test integrity check after all midstream checkpoints',
          expected_sha256: testCase.expected.sha256, tail_sha256: testCase.tail.sha256};
}

let failed = false;
for (const testCase of cases) {
  const row = {...metadata, receiver_version: version, test: testCase.test, case: testCase.name};
  try { Object.assign(row, probe(testCase)); }
  catch (error) { Object.assign(row, {status: 'FAIL', error: String(error)}); failed = true; }
  console.log(JSON.stringify(row));
}
process.exitCode = failed ? 1 : 0;
