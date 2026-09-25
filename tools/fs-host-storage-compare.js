'use strict';

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const Core = require('../src/core.js');
const SnapshotHost = require('../src/fs-host.js');
const SpineHost = require('../src/fs-spine-host.js');

function recursiveBytes(root) {
  let total = 0;
  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
    const p = path.join(root, entry.name);
    if (entry.isDirectory()) total += recursiveBytes(p);
    else if (entry.isFile()) total += fs.statSync(p).size;
  }
  return total;
}

function initialRuntime() {
  const value = { value: 0 };
  return {
    value,
    runtime: Core.createRuntime({
      label: 'storage-compare',
      contracts: [{ id: 'state', depends_on: ['source:**'], allowed_routes: ['rewrite'] }],
      artifacts: { state: Core.artifactRef(value) },
    }),
  };
}

function nextStage(runtime, i) {
  const plan = Core.planMutation(runtime, {
    selectors: ['source:item/' + i],
    reason: 'storage-compare',
  });
  if (plan.status !== 'PLANNED') throw new Error('plan failed: ' + JSON.stringify(plan));
  const value = { value: i };
  const stage = Core.stageGeneration(runtime, plan, {
    state: Object.assign(Core.artifactRef(value), { route: 'rewrite' }),
  });
  if (stage.status !== 'STAGED') throw new Error('stage failed: ' + JSON.stringify(stage));
  return { value, stage };
}

function runSnapshot(root, generations) {
  const init = initialRuntime();
  SnapshotHost.initializeHost(root, init.runtime, { state: init.value });
  for (let i = 1; i <= generations; i++) {
    const recovered = SnapshotHost.recoverHost(root);
    const next = nextStage(recovered.runtime, i);
    const result = SnapshotHost.commitDurable(root, recovered.runtime, next.stage, { state: next.value }, { actor: 'storage-compare' });
    if (result.status !== 'DURABLE_COMMITTED') throw new Error('snapshot commit failed: ' + JSON.stringify(result));
  }
  const recovered = SnapshotHost.recoverHost(root);
  return {
    sequence: recovered.head.sequence,
    total_file_bytes: recursiveBytes(root),
    logical_runtime_bytes: Buffer.byteLength(Core.canonicalize(Core.exportRuntime(recovered.runtime)), 'utf8'),
    logical_runtime_sha256: Core.hashCanonical(Core.exportRuntime(recovered.runtime)),
    inspect: SnapshotHost.inspectHost(root),
  };
}

function runSpine(root, generations) {
  const init = initialRuntime();
  SpineHost.initializeSpineHost(root, init.runtime, { state: init.value });
  for (let i = 1; i <= generations; i++) {
    const recovered = SpineHost.recoverSpineHost(root);
    const next = nextStage(recovered.runtime, i);
    const result = SpineHost.commitSpineDurable(root, recovered.runtime, next.stage, { state: next.value }, { actor: 'storage-compare' });
    if (result.status !== 'DURABLE_COMMITTED') throw new Error('spine commit failed: ' + JSON.stringify(result));
  }
  const recovered = SpineHost.recoverSpineHost(root);
  const inspect = SpineHost.inspectSpineHost(root);
  return {
    sequence: recovered.head.sequence,
    total_file_bytes: recursiveBytes(root),
    logical_runtime_bytes: Buffer.byteLength(Core.canonicalize(Core.exportRuntime(recovered.runtime)), 'utf8'),
    logical_runtime_sha256: Core.hashCanonical(Core.exportRuntime(recovered.runtime)),
    history_bytes: fs.statSync(path.join(root, 'HISTORY.log')).size,
    inspect,
  };
}

function run(generations = 256) {
  const parent = fs.mkdtempSync(path.join(os.tmpdir(), 'axm-neutral-storage-compare-'));
  const v1 = path.join(parent, 'snapshot');
  const v2 = path.join(parent, 'spine');
  fs.mkdirSync(v1); fs.mkdirSync(v2);
  try {
    const snapshot = runSnapshot(v1, generations);
    const spine = runSpine(v2, generations);
    if (snapshot.sequence !== generations || spine.sequence !== generations) throw new Error('sequence mismatch');
    if (snapshot.logical_runtime_bytes !== spine.logical_runtime_bytes) {
      throw new Error('reconstructed logical runtime byte size mismatch');
    }
    if (snapshot.logical_runtime_sha256 !== spine.logical_runtime_sha256) {
      throw new Error('reconstructed logical runtime identity mismatch');
    }
    const report = {
      format: 'axm-neutral-fs-storage-compare/v0.1',
      generations,
      claim_boundary: 'logical file byte counts on the tested host formats; excludes filesystem block allocation and makes no energy/performance claim',
      whole_runtime_snapshot_host: snapshot,
      history_spine_host: spine,
      comparison: {
        bytes_saved: snapshot.total_file_bytes - spine.total_file_bytes,
        percent_fewer_file_bytes: Number((100 * (1 - spine.total_file_bytes / snapshot.total_file_bytes)).toFixed(3)),
        snapshot_to_spine_ratio: Number((snapshot.total_file_bytes / spine.total_file_bytes).toFixed(3)),
      },
    };
    process.stdout.write(JSON.stringify(report, null, 2) + '\n');
    return report;
  } finally {
    fs.rmSync(parent, { recursive: true, force: true });
  }
}

if (require.main === module) run(Number(process.argv[2] || 256));

module.exports = { run };
