'use strict';

const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const Host = require('../src/fs-spine-host.js');
const { buildScenario } = require('../test/fs-host-fixture.js');

const worker = path.join(__dirname, 'fs-spine-host-worker.js');
const temp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'axm-neutral-spine-matrix-'));

function cleanup(dir) {
  fs.rmSync(dir, { recursive: true, force: true });
  const parent = path.dirname(dir), base = path.basename(dir);
  for (const file of fs.readdirSync(parent)) {
    if (file.startsWith(base + '.crash-marker-')) fs.rmSync(path.join(parent, file), { force: true });
  }
}

function initialize(dir) {
  const s = buildScenario();
  const result = Host.initializeSpineHost(dir, s.runtime, s.baseArtifacts);
  assert.equal(result.status, 'INITIALIZED');
  return s;
}

function killWorkerAt(dir, point) {
  const marker = dir + '.crash-marker-' + point;
  fs.rmSync(marker, { force: true });
  const env = Object.assign({}, process.env, { AXM_FS_HOST_PAUSE_MARKER: marker });
  delete env.NODE_TEST_CONTEXT;
  const script = [
    '"$1" "$2" "$3" "$4" &',
    'pid=$!',
    'found=0',
    'for i in $(seq 1 1000); do',
    '  if [ -f "$5" ]; then found=1; break; fi',
    '  sleep 0.01',
    'done',
    'if [ "$found" -ne 1 ]; then kill -9 "$pid" 2>/dev/null; wait "$pid" 2>/dev/null; exit 99; fi',
    'kill -9 "$pid"',
    'wait "$pid"',
    'exit $?'
  ].join('\n');
  const result = spawnSync('bash', ['-c', script, '--', process.execPath, worker, dir, point, marker], { encoding: 'utf8', env });
  fs.rmSync(marker, { force: true });
  return result;
}

const cases = [
  ['after_artifacts', 0],
  ['after_generation_object', 0],
  ['after_receipt_object', 0],
  ['after_history_append', 0],
  ['after_pointer_temp_fsync', 0],
  ['after_pointer_rename', 1],
  ['after_pointer_dir_fsync', 1],
];

const report = [];
for (const [point, expectedSequence] of cases) {
  const dir = temp();
  try {
    const s = initialize(dir);
    const child = killWorkerAt(dir, point);
    assert.equal(child.status, 137, 'worker did not die by external SIGKILL at ' + point + '\n' + child.stderr);
    const recovered = Host.recoverSpineHost(dir);
    assert.equal(recovered.head.sequence, expectedSequence, point + ' recovered wrong sequence');
    assert.equal(
      recovered.head.generation_sha256,
      expectedSequence === 0 ? s.baseGeneration : s.targetGeneration,
      point + ' recovered wrong generation identity',
    );
    if (point === 'after_history_append') {
      assert.ok(recovered.history.unpointed_records.length >= 1, 'durable unpointed history record must remain visible');
      assert.equal(recovered.head.sequence, 0, 'unpointed history must not promote itself');
    }
    report.push({ point, expected_sequence: expectedSequence, recovered_sequence: recovered.head.sequence, pass: true });
  } finally {
    cleanup(dir);
  }
}

process.stdout.write(JSON.stringify({
  format: 'axm-neutral-fs-spine-crash-matrix/v0.1',
  platform: process.platform,
  cases: report,
  pass: report.length === cases.length && report.every((x) => x.pass),
}, null, 2) + '\n');
