'use strict';

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const Core = require('../src/core.js');
const Host = require('../src/fs-host.js');

function dirBytes(dir) {
  if (!fs.existsSync(dir)) return 0;
  let total = 0;
  for (const name of fs.readdirSync(dir)) {
    const file = path.join(dir, name);
    const st = fs.statSync(file);
    if (st.isFile()) total += st.size;
  }
  return total;
}

function objectCount(dir) {
  if (!fs.existsSync(dir)) return 0;
  return fs.readdirSync(dir).filter((name) => name.endsWith('.blob')).length;
}

function currentRuntimeBytes(root) {
  const pointer = JSON.parse(fs.readFileSync(path.join(root, 'CURRENT.json'), 'utf8'));
  const file = path.join(root, 'objects', 'runtime', pointer.runtime_object_sha256 + '.blob');
  return fs.statSync(file).size;
}

function run(generations = 256) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'axm-neutral-storage-probe-'));
  const samples = new Set([0,1,2,4,8,16,32,64,128,256].filter((n) => n <= generations));
  const rows = [];
  try {
    const base = { value: 0 };
    let runtime = Core.createRuntime({
      label: 'storage-growth-probe',
      contracts: [{ id: 'state', depends_on: ['source:**'], allowed_routes: ['rewrite'] }],
      artifacts: { state: Core.artifactRef(base) },
    });
    Host.initializeHost(root, runtime, { state: base });

    function sample(sequence) {
      const runtimeDir = path.join(root, 'objects', 'runtime');
      const artifactDir = path.join(root, 'objects', 'artifact');
      const runtimeTotal = dirBytes(runtimeDir);
      const latestRuntime = currentRuntimeBytes(root);
      rows.push({
        sequence,
        runtime_objects: objectCount(runtimeDir),
        runtime_bytes_total: runtimeTotal,
        latest_runtime_bytes: latestRuntime,
        cumulative_vs_latest: Number((runtimeTotal / latestRuntime).toFixed(3)),
        artifact_objects: objectCount(artifactDir),
        artifact_bytes_total: dirBytes(artifactDir),
      });
    }

    if (samples.has(0)) sample(0);

    for (let i = 1; i <= generations; i++) {
      const recovered = Host.recoverHost(root);
      runtime = recovered.runtime;
      const plan = Core.planMutation(runtime, {
        selectors: ['source:item/' + i],
        reason: 'storage-growth-probe',
      });
      if (plan.status !== 'PLANNED') throw new Error('plan failed at ' + i + ': ' + JSON.stringify(plan));

      const value = { value: i };
      const stage = Core.stageGeneration(runtime, plan, {
        state: Object.assign(Core.artifactRef(value), { route: 'rewrite' }),
      });
      if (stage.status !== 'STAGED') throw new Error('stage failed at ' + i + ': ' + JSON.stringify(stage));

      const committed = Host.commitDurable(root, runtime, stage, { state: value }, { actor: 'storage-growth-probe' });
      if (committed.status !== 'DURABLE_COMMITTED') throw new Error('commit failed at ' + i + ': ' + JSON.stringify(committed));
      runtime = committed.runtime;
      if (samples.has(i)) sample(i);
    }

    const first = rows[0], last = rows[rows.length - 1];
    const report = {
      format: 'axm-neutral-storage-growth-probe/v0.1',
      generations,
      claim_boundary: 'filesystem bytes for the tested whole-runtime-snapshot host only; not a performance or universal storage claim',
      rows,
      summary: {
        final_sequence: last.sequence,
        final_runtime_objects: last.runtime_objects,
        final_runtime_bytes_total: last.runtime_bytes_total,
        final_latest_runtime_bytes: last.latest_runtime_bytes,
        final_cumulative_vs_latest: last.cumulative_vs_latest,
        runtime_total_growth_vs_base: Number((last.runtime_bytes_total / first.runtime_bytes_total).toFixed(3)),
      },
    };
    process.stdout.write(JSON.stringify(report, null, 2) + '\n');
    return report;
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
}

if (require.main === module) run(Number(process.argv[2] || 256));

module.exports = { run };
