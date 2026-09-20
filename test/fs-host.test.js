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
    const child = spawnSync(process.execPath, [worker, dir, 'none'], { encoding: 'utf8' });
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

for (const [point, expectedSequence] of [
  ['after_artifacts', 0],
  ['after_runtime_object', 0],
  ['after_pointer_temp_fsync', 0],
  ['after_pointer_rename', 1],
  ['after_pointer_dir_fsync', 1],
]) {
  test('SIGKILL ' + point + ' recovers one complete generation', () => {
    const dir = temp();
    try {
      const s = initialize(dir);
      const child = spawnSync(process.execPath, [worker, dir, point], { encoding: 'utf8' });
      assert.equal(child.signal, 'SIGKILL', 'child should die by SIGKILL at ' + point + ': ' + child.stderr);
      const recovered = Host.recoverHost(dir);
      assert.equal(recovered.head.sequence, expectedSequence);
      assert.equal(
        recovered.head.generation_sha256,
        expectedSequence === 0 ? s.baseGeneration : s.targetGeneration,
      );
      const inspected = Host.inspectHost(dir);
      assert.equal(inspected.current_sequence, expectedSequence);
      if (point === 'after_pointer_temp_fsync') {
        assert.ok(inspected.pending_pointer_files.length >= 1, 'uncommitted temp pointer remains visible evidence');
      }
    } finally {
      cleanup(dir);
    }
  });
}

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

test('pre-pointer crash may leave orphan objects but never promotes them', () => {
  const dir = temp();
  try {
    const s = initialize(dir);
    const child = spawnSync(process.execPath, [worker, dir, 'after_runtime_object'], { encoding: 'utf8' });
    assert.equal(child.signal, 'SIGKILL');
    const inspected = Host.inspectHost(dir);
    assert.equal(inspected.current_sequence, 0);
    assert.ok(inspected.runtime_objects.length >= 2, 'old current + orphan new runtime object should both remain');
    const recovered = Host.recoverHost(dir);
    assert.equal(recovered.head.generation_sha256, s.baseGeneration);
  } finally {
    cleanup(dir);
  }
});
