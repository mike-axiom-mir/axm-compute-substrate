'use strict';

const Core = require('../src/core.js');

function buildScenario() {
  const baseArtifacts = {
    graph: { graph: 0 },
    snapshot: { snapshot: 0 },
    mesh: { mesh: 0 },
  };
  const runtime = Core.createRuntime({
    label: 'fs-host-crash-fixture',
    contracts: [
      { id: 'graph', depends_on: ['source:graph/**'], allowed_routes: ['incremental', 'rebuild'] },
      { id: 'snapshot', depends_on: ['source:**'], allowed_routes: ['merkle', 'full-audit'] },
      { id: 'mesh', depends_on: ['source:mesh/**'], allowed_routes: ['compile'] },
    ],
    artifacts: {
      graph: Core.artifactRef(baseArtifacts.graph),
      snapshot: Core.artifactRef(baseArtifacts.snapshot),
      mesh: Core.artifactRef(baseArtifacts.mesh),
    },
  });

  const plan = Core.planMutation(runtime, { selectors: ['source:graph/node-7'], reason: 'durable fixture' });
  if (plan.status !== 'PLANNED') throw new Error('fixture plan failed: ' + JSON.stringify(plan));

  const updatedArtifacts = {
    graph: { graph: 1 },
    snapshot: { snapshot: 1 },
  };
  const stage = Core.stageGeneration(runtime, plan, {
    graph: Object.assign(Core.artifactRef(updatedArtifacts.graph), { route: 'incremental' }),
    snapshot: Object.assign(Core.artifactRef(updatedArtifacts.snapshot), { route: 'merkle' }),
  });
  if (stage.status !== 'STAGED') throw new Error('fixture stage failed: ' + JSON.stringify(stage));

  return {
    runtime,
    plan,
    stage,
    baseArtifacts,
    updatedArtifacts,
    baseGeneration: Core.currentHead(runtime).generation_sha256,
    targetGeneration: stage.generation.generation_sha256,
  };
}

module.exports = { buildScenario };
