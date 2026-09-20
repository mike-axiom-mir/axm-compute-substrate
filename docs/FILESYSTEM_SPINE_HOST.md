# Durable Filesystem History-Spine Host v0.2

Status: **experimental / local-host adapter / not CANON**

`src/fs-spine-host.js` is a storage-shape alternative to the v0.1 whole-runtime-snapshot host.

It keeps the same Neutral Compute logical state contract and the same authority principle:

> immutable work may exist before commit; only the durable CURRENT pointer makes one generation current.

## Why a second host format exists

The v0.1 durable host stores one complete sealed runtime snapshot for every committed generation.

That is intentionally simple, but a complete runtime contains all known generations and receipts. Repeating the whole body at every generation causes cumulative storage amplification as history grows.

v0.2 separates:

- registry/runtime metadata;
- immutable generation objects;
- immutable receipt objects;
- append-only history linkage;
- current authority.

## Layout

```text
HOST/
  META.json
  HISTORY.log
  CURRENT.json

  objects/
    artifact/
      <raw-sha256>.blob
    generation/
      <raw-object-sha256>.blob
    receipt/
      <raw-object-sha256>.blob
```

`META.json` is created once and binds the neutral runtime format/version, label and contract registry.

Each generation and receipt is stored once as an immutable object.

`HISTORY.log` contains canonical JSON lines. Each record binds:

- append index;
- semantic generation SHA;
- raw generation-object SHA;
- generation parent;
- semantic receipt SHA when present;
- raw receipt-object SHA;
- previous history-record SHA;
- its own record SHA.

This is an append-order chain, not a claim that append order equals generation ancestry. Sibling generations may share one parent and appear later in the same physical history.

`CURRENT.json` contains only:

- current generation SHA;
- exact history-record SHA;
- append index;
- pointer integrity SHA.

## Commit order

A new generation is prepared in this order:

```text
updated artifact objects
        ↓ durable
generation object
        ↓ durable
receipt object
        ↓ durable
append history record
        ↓ fsync HISTORY.log
CURRENT temp pointer
        ↓ fsync
atomic rename -> CURRENT.json
        ↓
host-directory fsync
```

The history record may therefore become durable before CURRENT moves.

That is intentional. Such a record is an **unpointed candidate/evidence object**, not current authority.

## Recovery

Recovery:

1. verifies immutable META;
2. verifies CURRENT;
3. scans the history from its root;
4. verifies the record hash chain;
5. verifies every referenced generation and receipt object in the valid prefix;
6. reconstructs the Neutral Compute runtime from the valid objects;
7. requires CURRENT to name one exact valid history record and generation;
8. verifies artifacts referenced by the current generation.

Recovery never selects "the latest generation" by filename, sequence or append order.

## Invalid tail boundary

A process may die while appending a history record, or unrelated corruption may leave bytes after the last valid record.

The scanner therefore distinguishes:

- **valid prefix**
- **invalid tail**

If CURRENT names a record in the valid prefix, recovery may return that committed state while reporting the invalid tail explicitly.

The invalid tail is not silently deleted.

New commits HOLD while an invalid tail exists.

If CURRENT depends on the invalid/missing record or object, recovery fails closed.

This is prefix-tolerant recovery, not automatic repair or garbage collection.

## Semantic identity vs object identity

Generation/receipt formats already carry their own semantic SHA fields.

The filesystem store separately content-addresses the serialized object bytes.

Those are different identities with different jobs:

- semantic SHA proves the Neutral Compute record body;
- raw object SHA proves the exact stored serialized bytes.

The host verifies both rather than assuming they must be equal.

## Relationship to Global State

Before implementing this format, the following AXM-owned donor was inspected:

- repository: `mike-axiom-mir/axm-global-state`
- modules: `src/durable-receipt-history.mjs`, `src/compacted-receipt-history.mjs`, `src/replay-checkpoint.mjs`

Reusable architectural lesson:

- history continuity/checkpoint evidence should be separable from live current state;
- compaction/recovery must retain enough explicit evidence to reject conflicts and gaps.

The Neutral Compute host does **not** copy Global State's mutation authority or receipt schemas. Its durability ordering remains the fsync + immutable-object + current-pointer discipline already proven by the Neutral Compute v0.1 host.

## Relationship to earlier Flowing Compute research

The format is also a small production-shaped expression of earlier experimental findings around:

- immutable base/body versus current head;
- append-only history;
- content-addressed object reuse;
- unpointed evidence;
- current pointer as authority.

The large research implementation remains in PR #2 and is not imported.

## Deliberate remaining cost

v0.2 reconstructs the in-memory Neutral Compute runtime by scanning the valid history prefix.

So v0.2 fixes **persistent byte amplification**, but recovery/commit work still grows with history length.

That is intentional for this stage. A checkpoint/index layer should be added only after measuring the real recovery cost and proving it preserves the same history/refusal behavior.

## Truth boundary

The host does not prove:

- physical power-loss finality;
- arbitrary filesystem/controller failure;
- distributed/multi-host atomicity;
- hostile root/kernel resistance;
- automatic orphan or invalid-tail repair;
- constant-time recovery;
- semantic correctness of artifact contents;
- performance, RAM or energy improvement merely because storage bytes are lower.

The relevant evidence receipt records the exact tested process-crash and storage-comparison boundaries.
