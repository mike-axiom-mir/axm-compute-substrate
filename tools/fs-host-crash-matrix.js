'use strict';

const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const Host = require('../src/fs-host.js');
const { buildScenario } = require('../test/fs-host-fixture.js');

const worker = path.join(__dirname, 'fs-host-worker.js');
const temp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'axm-neutral-fs-matrix-'));
const cleanup = (dir) => {
  fs.rmSync(dir, { recursive: true, force: true });
  for (const file of fs.readdirSync(path.dirname(dir))) {
    if (file.startsWith(path.basename(dir) + '.crash-marker-')) fs.rmSync(path.join(path.dirname(dir), file), { force: true });
  }
};

function initialize(dir) {
  const s = buildScenario();
  const result = Host.initializeHost(dir, s.runtime, s.baseArtifacts);
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
  ['after_runtime_object', 0],
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
    const recovered = Host.recoverHost(dir);
    assert.equal(recovered.head.sequence, expectedSequence, point + ' recovered wrong sequence');
    assert.equal(
      recovered.head.generation_sha256,
      expectedSequence === 0 ? s.baseGeneration : s.targetGeneration,
      point + ' recovered wrong generation identity',
    );
    const inspected = Host.inspectHost(dir);
    if (point === 'after_pointer_temp_fsync') {
      assert.ok(inspected.pending_pointer_files.length >= 1, 'pending pointer evidence should remain before rename');
    }
    if (point === 'after_runtime_object') {
      assert.ok(inspected.runtime_objects.length >= 2, 'orphan candidate runtime object should remain visible');
      assert.equal(inspected.current_sequence, 0, 'orphan runtime object must not promote itself');
    }
    report.push({ point, expected_sequence: expectedSequence, recovered_sequence: recovered.head.sequence, pass: true });
  } finally {
    cleanup(dir);
  }
}

process.stdout.write(JSON.stringify({
  format: 'axm-neutral-fs-crash-matrix/v0.1',
  platform: process.platform,
  cases: report,
  pass: report.length === cases.length && report.every((x) => x.pass),
}, null, 2) + '\n');
