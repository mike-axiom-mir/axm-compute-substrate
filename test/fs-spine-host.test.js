const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const Core = require('../src/core.js');
const Host = require('../src/fs-spine-host.js');
const { buildScenario } = require('./fs-host-fixture.js');

const temp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'axm-neutral-spine-'));
const cleanup = (dir) => fs.rmSync(dir, { recursive: true, force: true });
const worker = path.join(__dirname, '../tools/fs-spine-host-worker.js');

function initialize(dir) {
  const s = buildScenario();
  const result = Host.initializeSpineHost(dir, s.runtime, s.baseArtifacts);
  assert.equal(result.status, 'INITIALIZED');
  const recovered = Host.recoverSpineHost(dir);
  assert.equal(recovered.head.sequence, 0);
  assert.equal(recovered.head.generation_sha256, s.baseGeneration);
  assert.equal(recovered.history.valid_records, 1);
  return s;
}

test('spine host clean commit survives fresh-process recovery without full runtime snapshots', () => {
  const dir = temp();
  try {
    const s = initialize(dir);
    const child = spawnSync(process.execPath, [worker, dir, 'none'], { encoding: 'utf8' });
    assert.equal(child.status, 0, child.stderr);
    const recovered = Host.recoverSpineHost(dir);
    assert.equal(recovered.status, 'RECOVERED');
    assert.equal(recovered.head.sequence, 1);
    assert.equal(recovered.head.generation_sha256, s.targetGeneration);
    assert.equal(recovered.history.valid_records, 2);
    assert.equal(recovered.history.invalid_tail, null);
    assert.deepEqual(recovered.runtime.hot, {});
    const inspect = Host.inspectSpineHost(dir);
    assert.equal(inspect.objects.generation.count, 2);
    assert.equal(inspect.objects.receipt.count, 1);
  } finally {
    cleanup(dir);
  }
});

test('spine host rejects wrong updated artifact bytes before history/pointer authority advances', () => {
  const dir = temp();
  try {
    const s = initialize(dir);
    assert.throws(
      () => Host.commitSpineDurable(dir, s.runtime, s.stage, {
        graph: { graph: 'wrong' },
        snapshot: s.updatedArtifacts.snapshot,
      }),
      /artifact body does not match staged ref/,
    );
    const recovered = Host.recoverSpineHost(dir);
    assert.equal(recovered.head.sequence, 0);
    assert.equal(recovered.history.valid_records, 1);
  } finally {
    cleanup(dir);
  }
});

test('corrupt uncommitted history tail remains visible but does not erase an older committed CURRENT', () => {
  const dir = temp();
  try {
    initialize(dir);
    fs.appendFileSync(path.join(dir, 'HISTORY.log'), '{"torn":');
    const recovered = Host.recoverSpineHost(dir);
    assert.equal(recovered.head.sequence, 0);
    assert.ok(recovered.history.invalid_tail);
    assert.equal(recovered.history.invalid_tail.reason, 'invalid-json');
    assert.ok(recovered.history.invalid_tail.bytes > 0);
  } finally {
    cleanup(dir);
  }
});

test('commit refuses to append after a known invalid history tail', () => {
  const dir = temp();
  try {
    const s = initialize(dir);
    fs.appendFileSync(path.join(dir, 'HISTORY.log'), '{"torn":');
    const result = Host.commitSpineDurable(dir, s.runtime, s.stage, s.updatedArtifacts);
    assert.equal(result.status, 'HOLD_INVALID_HISTORY_TAIL');
    assert.equal(Host.recoverSpineHost(dir).head.sequence, 0);
  } finally {
    cleanup(dir);
  }
});

test('CURRENT that depends on missing generation object fails closed', () => {
  const dir = temp();
  try {
    const s = initialize(dir);
    const committed = Host.commitSpineDurable(dir, s.runtime, s.stage, s.updatedArtifacts);
    assert.equal(committed.status, 'DURABLE_COMMITTED');
    const generationFile = path.join(dir, 'objects', 'generation', committed.record.generation_object_sha256 + '.blob');
    fs.unlinkSync(generationFile);
    assert.throws(() => Host.recoverSpineHost(dir), /generation object missing/);
  } finally {
    cleanup(dir);
  }
});

test('CURRENT that depends on tampered history record fails closed', () => {
  const dir = temp();
  try {
    const s = initialize(dir);
    const committed = Host.commitSpineDurable(dir, s.runtime, s.stage, s.updatedArtifacts);
    assert.equal(committed.status, 'DURABLE_COMMITTED');
    const history = path.join(dir, 'HISTORY.log');
    const lines = fs.readFileSync(history, 'utf8').trimEnd().split('\n');
    const second = JSON.parse(lines[1]);
    second.generation_sha256 = 'f'.repeat(64);
    lines[1] = JSON.stringify(second);
    fs.writeFileSync(history, lines.join('\n') + '\n');
    assert.throws(() => Host.recoverSpineHost(dir), /CURRENT points beyond valid history prefix|CURRENT.*history/);
  } finally {
    cleanup(dir);
  }
});

test('durable unpointed generation after crash stays evidence and never auto-promotes', () => {
  const dir = temp();
  try {
    const s = initialize(dir);
    const marker = dir + '.marker';
    const env = Object.assign({}, process.env, { AXM_FS_HOST_PAUSE_MARKER: marker });
    const script = [
      '"$1" "$2" "$3" "$4" &',
      'pid=$!',
      'for i in $(seq 1 1000); do [ -f "$5" ] && break; sleep 0.01; done',
      '[ -f "$5" ] || { kill -9 "$pid" 2>/dev/null; wait "$pid" 2>/dev/null; exit 99; }',
      'kill -9 "$pid"',
      'wait "$pid"',
      'exit $?'
    ].join('\n');
    const child = spawnSync('bash', ['-c', script, '--', process.execPath, worker, dir, 'after_history_append', marker], { encoding: 'utf8', env });
    fs.rmSync(marker, { force: true });
    assert.equal(child.status, 137, child.stderr);
    const recovered = Host.recoverSpineHost(dir);
    assert.equal(recovered.head.sequence, 0);
    assert.equal(recovered.head.generation_sha256, s.baseGeneration);
    assert.equal(recovered.history.valid_records, 2);
    assert.equal(recovered.history.unpointed_records.length, 1);
    assert.equal(recovered.history.unpointed_records[0].generation_sha256, s.targetGeneration);
  } finally {
    cleanup(dir);
  }
});
