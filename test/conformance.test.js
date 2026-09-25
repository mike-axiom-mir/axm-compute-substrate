const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const Core = require('../src/core.js');
const { matchesExpected, referenceAdapter, runVectors } = require('../src/conformance.js');

const vectors = JSON.parse(fs.readFileSync(path.join(__dirname, '../conformance/vectors.json'), 'utf8'));

test('committed neutral conformance vectors pass the reference implementation', () => {
  const report = runVectors(referenceAdapter(Core), vectors);
  assert.equal(report.ok, true, JSON.stringify(report, null, 2));
  assert.equal(report.failed, 0);
  assert.equal(report.passed, vectors.cases.length);
  assert.ok(report.primitives.every((x) => x.ok));
});

test('expected matching is partial but never hides contradictory nested values', () => {
  assert.equal(matchesExpected({ status: 'PLANNED', extra: 1 }, { status: 'PLANNED' }).ok, true);
  const bad = matchesExpected({ actions: { graph: 'REUSE_EXACT' } }, { actions: { graph: 'UPDATE_REQUIRED' } });
  assert.equal(bad.ok, false);
  assert.equal(bad.path, '$.actions.graph');
});
