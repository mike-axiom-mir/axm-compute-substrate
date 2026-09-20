const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const Core = require('../src/core.js');
const Host = require('../src/fs-host.js');
const { buildScenario } = require('./fs-host-fixture.js');

const temp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'axm-neutral-fs-'));
const cleanup = (dir) => fs.rmSync(dir, { recursive: true, force: true });
const worker = path.join(__dirname, '../tools/fs-host-worker.js');

function runWorker(dir, point) {
  const env = Object.assign({}, process.env);
  delete env.NODE_TEST_CONTEXT;
  delete env.NODE_TEST_REPORTER;
  delete env.NODE_TEST_REPORTER_DESTINATION;
  if (point === 'none') return spawnSync(process.execPath, [worker, dir, point], { encoding: 'utf8', env });

  const marker = dir + '.crash-marker-' + point;
  fs.rmSync(marker, { force: true });
  env.AXM_FS_HOST_PAUSE_MARKER = marker;
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

function initialize(dir) {
  const s = buildScenario();
  const result = Host.initializeHost(dir, s.runtime, s.baseArtifacts);
  assert.equal(result.status, 'INITIALIZED');
  const recovered = Host.recoverHost(dir);
  assert.equal(recovered.head.sequence, 0);
  assert.equal(recovered.head.generation_sha256, s.baseGeneration);
  return s;
}

test('clean durable commit survives a fresh-process recovery', () => {
  const dir = temp();
  try {
    const s = initialize(dir);
    const child = runWorker(dir, 'none');
    assert.equal(child.status, 0, child.stderr);
    const recovered = Host.recoverHost(dir);
    assert.equal(recovered.status, 'RECOVERED');
    assert.equal(recovered.head.sequence, 1);
    assert.equal(recovered.head.generation_sha256, s.targetGeneration);
    assert.deepEqual(recovered.runtime.hot, {});
  } finally {
    cleanup(dir);
  }
});

test('wrong updated artifact bytes fail before CURRENT moves', () => {
  const dir = temp();
  try {
    const s = initialize(dir);
    assert.throws(
      () => Host.commitDurable(dir, s.runtime, s.stage, {
        graph: { graph: 'wrong' },
        snapshot: s.updatedArtifacts.snapshot,
      }),
      /artifact body does not match staged ref/,
    );
    const recovered = Host.recoverHost(dir);
    assert.equal(recovered.head.sequence, 0);
    assert.equal(recovered.head.generation_sha256, s.baseGeneration);
  } finally {
    cleanup(dir);
  }
});

test('tampered CURRENT pointer fails closed instead of guessing the newest runtime object', () => {
  const dir = temp();
  try {
    initialize(dir);
    const file = path.join(dir, 'CURRENT.json');
    const pointer = JSON.parse(fs.readFileSync(file, 'utf8'));
    pointer.current_generation_sha256 = 'f'.repeat(64);
    fs.writeFileSync(file, JSON.stringify(pointer));
    assert.throws(() => Host.recoverHost(dir), /pointer failed integrity/);
  } finally {
    cleanup(dir);
  }
});

test('missing current artifact fails recovery even when pointer and runtime object are intact', () => {
  const dir = temp();
  try {
    const s = initialize(dir);
    const head = Core.currentHead(s.runtime);
    const ref = head.contracts.graph;
    fs.unlinkSync(path.join(dir, 'objects', 'artifact', ref.artifact_sha256 + '.blob'));
    assert.throws(() => Host.recoverHost(dir), /current artifact missing for graph/);
  } finally {
    cleanup(dir);
  }
});


test('process-kill crash matrix exposes only old or fully prepared new generation', () => {
  const cases = [
    { point: 'after_artifacts', sequence: 0, target: 'old' },
    { point: 'after_runtime_object', sequence: 0, target: 'old' },
    { point: 'after_pointer_temp_fsync', sequence: 0, target: 'old' },
    { point: 'after_pointer_rename', sequence: 1, target: 'new' },
    { point: 'after_pointer_dir_fsync', sequence: 1, target: 'new' },
  ];

  for (const item of cases) {
    const dir = temp();
    try {
      const s = initialize(dir);
      const child = runWorker(dir, item.point);
      assert.notEqual(child.status, 99, item.point + ' worker never reached crash marker');
      assert.notEqual(child.status, 0, item.point + ' worker unexpectedly exited cleanly');

      const recovered = Host.recoverHost(dir);
      assert.equal(recovered.status, 'RECOVERED', item.point);
      assert.equal(recovered.head.sequence, item.sequence, item.point);
      assert.equal(
        recovered.head.generation_sha256,
        item.target === 'old' ? s.baseGeneration : s.targetGeneration,
        item.point,
      );

      const audit = Host.inspectHost(dir);
      assert.equal(audit.current_sequence, item.sequence, item.point);
      if (item.point === 'after_pointer_temp_fsync') {
        assert.ok(audit.pending_pointer_files.length >= 1, 'crashed temp pointer remains visible evidence');
      }

      if (item.target === 'new') {
        assert.deepEqual(recovered.runtime.hot, {});
        assert.equal(recovered.head.contracts.graph.decision, 'UPDATED');
        assert.equal(recovered.head.contracts.snapshot.decision, 'UPDATED');
        assert.equal(recovered.head.contracts.mesh.decision, 'REUSED_EXACT');
      }
    } finally {
      cleanup(dir);
    }
  }
});
