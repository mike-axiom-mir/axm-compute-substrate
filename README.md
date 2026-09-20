# AXM Compute Substrate — Neutral Runtime Core v0.1

A small deterministic substrate for **preserving useful derived state instead of rebuilding everything from zero**.

This branch is intentionally clean. The large experimental Flowing Compute research remains in PR #2 as evidence/history. This package extracts only the reusable neutral runtime pattern.

## What the core does

A host registers independent state contracts:

```text
source mutation
      |
      v
which contracts depend on it?
      |
      +---- affected ------> caller chooses that contract's route ------> new artifact ref
      |
      +---- unaffected -----------------------------------------------> exact old artifact ref
                                                                         |
                                                                         v
                                                               staged generation
                                                               (not current yet)
                                                                         |
                                                                  one logical commit
                                                                         |
                                                                         v
                                                                  current generation
```

The core provides:

- contract registration + dependency selectors;
- `UPDATE_REQUIRED` vs `REUSE_EXACT` planning;
- HOLD on unknown mutation selectors;
- contract-local route allowlists;
- exact content-addressed artifact references;
- staged generations with no authority;
- one logical current-generation pointer;
- append-only commit / rollback / reactivation receipts;
- ancestor-only rollback and descendant-only reactivation;
- non-canonical verified hot/session artifacts;
- sealed export/import with lineage validation;
- a deterministic host-facing commit pointer record.

## What the core does **not** do

It deliberately does not own:

- artifact storage;
- filesystem/database durability;
- a universal incremental algorithm;
- a universal cache policy;
- a universal audit cadence;
- network consensus or distributed uniqueness;
- cryptographic witnesses, key custody or key rotation;
- merge/CANON authority;
- energy accounting.

Those belong in adapters or optional layers when a real workload requires them.

## Why routes are contract-local

Flowing Compute research measured different behavior for different bodies:

- dependency graphs can benefit from affected-closure recomputation;
- render assets may benefit mainly when fresh workers repeatedly pay parse/setup cost;
- large capability registries can benefit from compact dormant lookup state;
- large file-identity bodies can benefit from Merkle-style local verification;
- broad invalidation can make incremental work lose.

So the neutral core answers **what is affected**. It does not invent one algorithm for **how every affected contract should update**.

## Minimal use

```js
const Core = require('@axm/compute-substrate');

const runtime = Core.createRuntime({
  contracts: [
    { id: 'graph', depends_on: ['source:graph/**'], allowed_routes: ['incremental', 'rebuild'] },
    { id: 'snapshot', depends_on: ['source:**'], allowed_routes: ['merkle', 'full-audit'] },
  ],
  artifacts: {
    graph: Core.artifactRef({ nodes: [] }),
    snapshot: Core.artifactRef({ root: 'initial' }),
  },
});

const plan = Core.planMutation(runtime, {
  selectors: ['source:graph/node-7'],
});

const stage = Core.stageGeneration(runtime, plan, {
  graph: { ...Core.artifactRef({ nodes: ['changed'] }), route: 'incremental' },
  snapshot: { ...Core.artifactRef({ root: 'changed' }), route: 'merkle' },
});

// Still old state here.
Core.commitGeneration(runtime, stage);

// Both new refs are now one logical generation.
```

## Dormant / hot

A generation stores **artifact identity**, not necessarily loaded artifact bytes.

`wakeContract(runtime, id, bytesOrValue)` verifies a body against the current artifact reference, then retains it only in the non-canonical hot/session plane.

`exportRuntime` omits hot bodies. Restart therefore returns to dormant references without changing current generation truth.

## Durable hosts

`commitGeneration` is atomic only inside the in-memory runtime object.

For filesystem/database durability, a host should:

1. persist all new artifact bodies;
2. persist the sealed staged generation / history as needed;
3. obtain `commitRecord(stage)`;
4. publish that pointer with the host's own atomic primitive (rename, transaction, compare-and-swap, etc.);
5. recover/verify from durable state after restart.

The core does not call `fsync` and does not pretend memory mutation is a durable commit.

## Relationship to MorphTile

MorphTile has its own native experimental integration because it already had sleeping capabilities, sparse waking and Cold Matter. MorphTile should depend on this neutral package only if doing so remains simpler and preserves its standalone/no-dependency direction; equivalence can also be kept at the contract level instead.

## Research provenance

The neutral core is distilled from the experimental lane in PR #2. That research established both positive and negative boundaries: retained state sometimes saves substantial repeated work, sometimes only a little, and sometimes loses.

The later witness/key-rotation/security research remains valuable evidence but is deliberately **not** part of this core.

## Status

Experimental v0.1. Not CANON. No merge implied by green tests.
