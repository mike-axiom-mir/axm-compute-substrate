const test = require('node:test');
const assert = require('node:assert');
const Core = require('../index.js');

const art = (value, options) => Core.artifactRef(value, options);

function runtime() {
  return Core.createRuntime({
    label: 'neutral-test',
    contracts: [
      { id: 'graph', depends_on: ['source:graph/**'], allowed_routes: ['incremental', 'rebuild'] },
      { id: 'snapshot', depends_on: ['source:**'], allowed_routes: ['merkle', 'full-audit'] },
      { id: 'mesh', depends_on: ['source:mesh/**'], allowed_routes: ['compile', 'reuse-parser'] },
    ],
    artifacts: {
      graph: art({ graph: 0 }),
      snapshot: art({ snapshot: 0 }),
      mesh: art(Buffer.from('mesh-v0'), { hash_kind: 'bytes', representation: 'bytes' }),
    },
  });
}

function updatePlan(rt, selector) {
  const plan = Core.planMutation(rt, { selectors: [selector], reason: 'test' });
  assert.equal(plan.status, 'PLANNED');
  return plan;
}

test('selector matching supports exact, prefix, recursive prefix and global', () => {
  assert.equal(Core.selectorMatches('a:b', 'a:b'), true);
  assert.equal(Core.selectorMatches('a:*', 'a:thing'), true);
  assert.equal(Core.selectorMatches('a/**', 'a'), true);
  assert.equal(Core.selectorMatches('a/**', 'a/b/c'), true);
  assert.equal(Core.selectorMatches('**', 'anything'), true);
  assert.equal(Core.selectorMatches('a/**', 'ab/c'), false);
});

test('one mutation updates only affected contracts and reuses exact others', () => {
  const rt = runtime();
  const before = Core.currentHead(rt);
  const plan = updatePlan(rt, 'source:graph/node-7');

  assert.equal(plan.contracts.graph.action, 'UPDATE_REQUIRED');
  assert.equal(plan.contracts.snapshot.action, 'UPDATE_REQUIRED');
  assert.equal(plan.contracts.mesh.action, 'REUSE_EXACT');

  const stage = Core.stageGeneration(rt, plan, {
    graph: Object.assign(art({ graph: 1 }), { route: 'incremental' }),
    snapshot: Object.assign(art({ snapshot: 1 }), { route: 'merkle' }),
  });
  assert.equal(stage.status, 'STAGED');
  assert.equal(Core.currentHead(rt).generation_sha256, before.generation_sha256, 'stage is not current');

  const committed = Core.commitGeneration(rt, stage, 'test');
  assert.equal(committed.status, 'COMMITTED');

  const after = Core.currentHead(rt);
  assert.equal(after.sequence, 1);
  assert.notEqual(after.generation_sha256, before.generation_sha256);
  assert.equal(after.contracts.mesh.artifact_sha256, before.contracts.mesh.artifact_sha256);
  assert.equal(after.contracts.mesh.decision, 'REUSED_EXACT');
  assert.equal(after.contracts.graph.decision, 'UPDATED');
});

test('unknown selector HOLDs instead of being assumed irrelevant', () => {
  const rt = runtime();
  const result = Core.planMutation(rt, { selectors: ['mystery:unmapped'] });
  assert.equal(result.status, 'HOLD_UNKNOWN_SELECTOR');
  assert.deepEqual(result.unknown_selectors, ['mystery:unmapped']);
});

test('affected contract requires an allowed contract-local route', () => {
  const rt = runtime();
  const plan = updatePlan(rt, 'source:graph/node-1');

  let stage = Core.stageGeneration(rt, plan, {
    graph: art({ graph: 1 }),
    snapshot: Object.assign(art({ snapshot: 1 }), { route: 'merkle' }),
  });
  assert.equal(stage.status, 'HOLD_ROUTE_REQUIRED');

  stage = Core.stageGeneration(rt, plan, {
    graph: Object.assign(art({ graph: 1 }), { route: 'universal-magic' }),
    snapshot: Object.assign(art({ snapshot: 1 }), { route: 'merkle' }),
  });
  assert.equal(stage.status, 'HOLD_ROUTE_NOT_ALLOWED');
});

test('reused contract cannot be silently replaced', () => {
  const rt = runtime();
  const plan = updatePlan(rt, 'source:graph/node-1');
  const stage = Core.stageGeneration(rt, plan, {
    graph: Object.assign(art({ graph: 1 }), { route: 'incremental' }),
    snapshot: Object.assign(art({ snapshot: 1 }), { route: 'merkle' }),
    mesh: Object.assign(art(Buffer.from('mesh-v1'), { hash_kind: 'bytes' }), { route: 'compile' }),
  });
  assert.equal(stage.status, 'HOLD_REUSE_OVERRIDE');
});

test('plan and stage are bound to the exact current generation', () => {
  const rt = runtime();
  const planA = updatePlan(rt, 'source:graph/a');
  const planB = updatePlan(rt, 'source:graph/b');

  const stageA = Core.stageGeneration(rt, planA, {
    graph: Object.assign(art({ graph: 'a' }), { route: 'incremental' }),
    snapshot: Object.assign(art({ snapshot: 'a' }), { route: 'merkle' }),
  });
  assert.equal(Core.commitGeneration(rt, stageA).status, 'COMMITTED');

  assert.equal(Core.stageGeneration(rt, planB, {}).status, 'HOLD_STALE_BASE');
});

test('hot artifacts are verified session state and are not exported', () => {
  const rt = runtime();
  const mesh = Buffer.from('mesh-v0');
  assert.equal(Core.wakeContract(rt, 'mesh', mesh).status, 'AWAKE_VERIFIED');
  assert.deepEqual(Core.hotArtifact(rt, 'mesh'), mesh);

  const exported = Core.exportRuntime(rt);
  assert.equal(exported.hot, undefined);

  const resumed = Core.importRuntime(JSON.parse(JSON.stringify(exported)));
  assert.equal(Core.hotArtifact(resumed, 'mesh'), null);
  assert.equal(Core.currentHead(resumed).generation_sha256, Core.currentHead(rt).generation_sha256);

  const mismatch = Core.wakeContract(resumed, 'mesh', Buffer.from('wrong'));
  assert.equal(mismatch.status, 'HOLD_ARTIFACT_HASH_MISMATCH');
});

test('canonical JSON identity is key-order stable and byte identity is byte-exact', () => {
  assert.equal(Core.hashCanonical({ b: 2, a: 1 }), Core.hashCanonical({ a: 1, b: 2 }));
  const ref = Core.artifactRef(Buffer.from([1, 2, 3]), { hash_kind: 'bytes' });
  assert.equal(Core.verifyArtifact(ref, Buffer.from([1, 2, 3])).ok, true);
  assert.equal(Core.verifyArtifact(ref, Buffer.from([1, 2, 4])).ok, false);
});

test('rollback accepts ancestors, reactivation accepts descendants, siblings are neither', () => {
  const rt = runtime();
  const g0 = Core.currentHead(rt).generation_sha256;

  const p1 = updatePlan(rt, 'source:graph/a');
  const s1 = Core.stageGeneration(rt, p1, {
    graph: Object.assign(art({ graph: 'a' }), { route: 'incremental' }),
    snapshot: Object.assign(art({ snapshot: 'a' }), { route: 'merkle' }),
  });
  Core.commitGeneration(rt, s1);
  const branchA = Core.currentHead(rt).generation_sha256;

  assert.equal(Core.rollback(rt, g0).status, 'ROLLED_BACK');

  const p2 = updatePlan(rt, 'source:graph/b');
  const s2 = Core.stageGeneration(rt, p2, {
    graph: Object.assign(art({ graph: 'b' }), { route: 'incremental' }),
    snapshot: Object.assign(art({ snapshot: 'b' }), { route: 'merkle' }),
  });
  Core.commitGeneration(rt, s2);
  const branchB = Core.currentHead(rt).generation_sha256;

  assert.equal(Core.rollback(rt, branchA).status, 'HOLD_TARGET_NOT_ANCESTOR');
  assert.equal(Core.rollback(rt, g0).status, 'ROLLED_BACK');
  assert.equal(Core.reactivate(rt, branchA).status, 'REACTIVATED');
  assert.equal(Core.rollback(rt, g0).status, 'ROLLED_BACK');
  assert.equal(Core.reactivate(rt, branchB).status, 'REACTIVATED');
  assert.equal(Core.reactivate(rt, branchA).status, 'HOLD_TARGET_NOT_DESCENDANT');
});

test('same output artifact may be retained after real recomputation without pretending it was reuse', () => {
  const rt = runtime();
  const before = Core.currentHead(rt);
  const plan = updatePlan(rt, 'source:graph/no-semantic-change');
  const stage = Core.stageGeneration(rt, plan, {
    graph: Object.assign(before.contracts.graph, { route: 'rebuild' }),
    snapshot: Object.assign(before.contracts.snapshot, { route: 'full-audit' }),
  });
  assert.equal(stage.status, 'STAGED');
  assert.equal(stage.generation.contracts.graph.decision, 'UPDATED');
  assert.equal(stage.generation.contracts.graph.artifact_sha256, before.contracts.graph.artifact_sha256);
});

test('commitRecord is a host-facing pointer candidate, not durable authority by itself', () => {
  const rt = runtime();
  const plan = updatePlan(rt, 'source:graph/a');
  const stage = Core.stageGeneration(rt, plan, {
    graph: Object.assign(art({ graph: 'a' }), { route: 'incremental' }),
    snapshot: Object.assign(art({ snapshot: 'a' }), { route: 'merkle' }),
  });
  const pointer = Core.commitRecord(stage);
  assert.match(pointer.pointer_sha256, /^[0-9a-f]{64}$/);
  assert.equal(pointer.generation_sha256, stage.generation.generation_sha256);
  assert.equal(Core.currentHead(rt).sequence, 0, 'making a pointer record does not commit');
});

test('export/import rejects tampering and broken lineage', () => {
  const rt = runtime();
  const exported = Core.exportRuntime(rt);

  const tampered = JSON.parse(JSON.stringify(exported));
  tampered.generations[tampered.current_generation_sha256].contracts.graph.representation = 'changed';
  assert.throws(() => Core.importRuntime(tampered), /hash mismatch/);

  const broken = JSON.parse(JSON.stringify(exported));
  const root = broken.generations[broken.current_generation_sha256];
  root.parent_generation_sha256 = 'f'.repeat(64);
  delete broken.runtime_sha256;
  broken.runtime_sha256 = Core.hashCanonical({
    format: broken.format,
    version: broken.version,
    label: broken.label,
    registry: broken.registry,
    generations: broken.generations,
    current_generation_sha256: broken.current_generation_sha256,
    receipts: broken.receipts,
  });
  assert.throws(() => Core.importRuntime(broken), /generation hash mismatch|missing parent/);
});
