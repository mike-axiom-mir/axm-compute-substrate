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

This repo now also contains an **optional local filesystem host** in `src/fs-host.js`. It keeps immutable content-addressed artifact/runtime objects behind one mutable `CURRENT.json` pointer and uses file fsync + atomic rename + directory fsync.

Its real-SIGKILL matrix proves the tested Linux process-crash boundary:

- crash after artifacts are durable -> recover old generation;
- crash after runtime object is durable -> recover old generation;
- crash after temporary pointer fsync -> recover old generation;
- crash after atomic pointer rename -> recover new generation;
- crash after directory fsync -> recover new generation.

Run it with:

```bash
npm run crash-matrix
```

The adapter deliberately preserves pre-commit orphan objects without promoting them. Recovery follows only the verified `CURRENT` pointer.

This is **not** a physical power-loss/controller/filesystem-journal proof. Other hosts may instead use a database transaction, compare-and-swap service, embedded store, etc. See `docs/FILESYSTEM_HOST.md` and `evidence/DURABLE_FS_HOST_V01.md`.

## Linear history-spine host

The v0.1 filesystem host is intentionally simple but rewrites a complete sealed runtime snapshot every generation. A 256-generation tiny-state probe measured **39.57 MB** of total host files for a final logical runtime of about **307 KB**.

`src/fs-spine-host.js` is the experimental v0.2 physical format:

```text
META
 +
immutable generation objects
 +
immutable receipt objects
 +
append-only hash-chained HISTORY
 +
tiny CURRENT pointer
```

On the same 256-generation fixture it reconstructed the **exact same logical runtime SHA-256** while using **473,196 bytes** total: **98.804% fewer file bytes / 83.614× smaller** than the whole-runtime-snapshot host.

Its separate SIGKILL matrix covers seven durability boundaries, including a fully durable history record that remains non-current until CURRENT moves.

The history scanner also distinguishes a valid committed prefix from a broken uncommitted tail. The tail remains visible; it is never auto-truncated or promoted.

Run:

```bash
npm run spine-crash-matrix
npm run storage-compare
```

This fixes the measured persistent-byte amplification. It does **not** make recovery constant-time: v0.2 currently scans/verifies the valid history prefix. See `docs/FILESYSTEM_SPINE_HOST.md` and `evidence/FS_SPINE_HOST_V02.md`.

## Conformance kit

`conformance/vectors.json` is the portable v0.1 behavioral contract.

Run the reference implementation against it:

```bash
npm test
npm run conformance
```

An independent implementation does **not** need this package internally. It may pin the vector file, write a small native adapter/test, and prove the same observable results.

The first independent consumer is **MorphTile PR #5**. It keeps its own native Flow runtime and passed the exact pinned Neutral Compute v0.1 vector bytes after the vectors exposed and forced repairs to byte identity, recursive selector routing, and descendant reactivation.

The second independent consumer is **Universal Creation PR #223**. It implements the contract natively in Python, passes the same pinned vectors under Python 3.11 and 3.13, and uses real UC shape-recipe/material-response state: changing a retained shape recipe updates source + compiled realization while an unrelated material-response catalog is exact-reused. The same PR passed UC's full 1201-test Python 3.11 suite.

So v0.1 currently has three tested shapes:

1. neutral JavaScript reference runtime;
2. MorphTile-native JavaScript runtime;
3. UC-native Python runtime.

See `evidence/CONFORMANCE_V01.md` and `evidence/THIRD_CONSUMER_UC_V01.md`.

Expected HOLD/refusal outcomes are part of conformance. An implementation does not pass by guessing past an unknown mutation or incompatible route.

## Relationship to MorphTile

MorphTile has its own native experimental integration because it already had sleeping capabilities, sparse waking and Cold Matter. MorphTile should depend on this neutral package only if doing so remains simpler and preserves its standalone/no-dependency direction; equivalence can also be kept at the contract level instead.

## Research provenance

The neutral core is distilled from the experimental lane in PR #2. That research established both positive and negative boundaries: retained state sometimes saves substantial repeated work, sometimes only a little, and sometimes loses.

The later witness/key-rotation/security research remains valuable evidence but is deliberately **not** part of this core.

## Status

Experimental v0.1. Not CANON. No merge implied by green tests.


## Durable filesystem host

`src/fs-host.js` is the first host adapter that turns the core's logical generation pointer into a Linux filesystem commit:

```text
artifact objects -> fsync
runtime object   -> fsync
CURRENT temp     -> fsync
CURRENT rename
directory fsync
```

`npm run crash-matrix` kills a real child process with SIGKILL at five boundaries and requires recovery to expose either the old or the fully prepared new generation, never a mixed one.

Current tested boundary: process death on Linux. This is not a literal hardware power-cut claim. See `evidence/FS_HOST_V01.md`.

## Independent consumers

Neutral Compute v0.1 currently has:

1. the JavaScript reference runtime in this repository;
2. MorphTile's independent native Flow runtime;
3. Universal Creation's independent Python runtime.

MorphTile and UC pin the vector data but do not import this runtime implementation. See `evidence/CONFORMANCE_V01.md` and `evidence/UC_CONSUMER_V01.md`.

## Reusable simulation method

[Simulation experience and reuse](SIMULATION_EXPERIENCE_REUSE.md) connects the shared method to this repository, with existing machinery, proposed experiments and explicit evidence limits.
