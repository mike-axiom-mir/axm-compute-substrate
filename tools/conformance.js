'use strict';

const fs = require('node:fs');
const path = require('node:path');
const Core = require('../src/core.js');
const { referenceAdapter, runVectors } = require('../src/conformance.js');

const vectorsPath = path.join(__dirname, '../conformance/vectors.json');
const vectors = JSON.parse(fs.readFileSync(vectorsPath, 'utf8'));
const report = runVectors(referenceAdapter(Core), vectors);

if (!report.ok) {
  console.error(JSON.stringify(report, null, 2));
  process.exit(1);
}

if (process.argv.includes('--json')) {
  process.stdout.write(JSON.stringify(report, null, 2) + '\n');
} else {
  console.log('neutral compute conformance:', report.passed + '/' + report.cases.length + ' cases PASS');
  for (const p of report.primitives || []) console.log('primitive', p.id, p.ok ? 'PASS' : 'FAIL');
  for (const c of report.cases) console.log(c.id, c.ok ? 'PASS' : 'FAIL');
}
