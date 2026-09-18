# Flowing Compute Wave 31 — Content-Addressed Checkpoint Spine

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST CHECKPOINT-HISTORY EVIDENCE`

## Question

Wave 29 can recreate missing newest checkpoint seals cheaply, but checkpoint v0.3 copies the full list of older segment proofs into every newer checkpoint file. Can checkpoint history use the same separation already proven for state history: immutable objects + append-only parent links + a tiny current pointer?

## Structure

Wave 31 adds `AXM_FLOWING_COMPUTE_CHECKPOINT_SPINE.py`:

```text
content-addressed immutable segment-proof store
        +
append-only parent-linked checkpoint spine
        +
88-byte current checkpoint pointer
```

Each completed 1,024-generation proof becomes one immutable segment object. A checkpoint-spine record points to that segment object and to the exact parent checkpoint record by hash/offset/length. The mutable pointer names only the current checkpoint record.

No new checkpoint copies the previous segment list.

## Real two-segment control

The real Wave-29 two-segment checkpoint was converted into Wave-31 representation.

Results:

- current wake -> generation **2,048**;
- full checkpoint-chain audit -> **2 segments**, PASS;
- pointer rollback to first checkpoint -> generation **1,024**, PASS;
- each content-addressed segment proof was independently re-audited against the generation spine -> PASS.

Physical checkpoint metadata for the real two-segment example:

- segment-object store: **718 bytes**;
- checkpoint spine: **1,061 bytes**;
- current pointer: **88 bytes**.

## Persistence scaling

Synthetic-but-contract-faithful 1,024-generation segment proofs were used only to measure history-shape growth.

| segments | Wave 29 cumulative rewrite | Wave 31 append + pointer | saved |
|---:|---:|---:|---:|
| 2 | 1,334 B | 1,955 B | **-46.6%** — Wave 31 loses |
| 16 | 32,203 B | 16,095 B | **50.0%** |
| 64 | 427,659 B | 64,843 B | **84.8%** |
| 256 | 6,549,867 B | 260,660 B | **96.0%** |

The fixed content-addressing/spine overhead is therefore not worthwhile at tiny history depth. The scalable representation earns its cost as checkpoint history grows.

## Serialization CPU at segment 256

Median microbenchmark:

- Wave-29 full-history checkpoint serialization: **0.683 ms CPU**;
- Wave-31 new segment + record + pointer serialization: **0.0209 ms**;
- reduction: **96.94%**.

This is metadata construction CPU, not a complete durable filesystem transaction benchmark.

## Truth boundary

- 2-segment correctness uses real generation history; long depth scaling uses synthetic segment-proof objects under the same format;
- CPU process time is not joules;
- the new representation is worse for very short history and is not presented as a universal replacement threshold;
- current checkpoint pointer remains acceleration/proof state rather than application-state authority;
- full audit traverses parent records and segment objects; fast wake reads only current checkpoint metadata;
- hashes provide identity/integrity, not external authentication;
- one host/runtime/filesystem;
- no claim of compute/energy from nothing.

## Next gate

Give the checkpoint spine its own crash-consistent dual-slot commit protocol. Segment object and checkpoint record must become durable before the new checkpoint pointer can become current. Failure injection must prove an unpointed new checkpoint is never auto-promoted, a torn/corrupt current pointer falls back to the older pointer, and valid old checkpoint history remains rollback-accessible.
