# Flowing Compute Wave 74 — Carried Reuse Proof vs Audited Reuse

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST TRUST-MODE EVIDENCE`

## Question

Wave 73 showed that revalidating unchanged sleeping contracts can cost more CPU than some changed-contract executors. Can a generation explicitly reuse prior immutable-artifact proof without rereading the body, while keeping a separate audited mode that re-establishes byte identity?

## Results

### Execution-Fabric capability index

Artifact size: **11,255,808 bytes**.

- carried proof median: **0.0324 ms CPU**;
- audited byte rehash median: **7.828 ms**;
- audit/carried multiplier: **241.3x**.

### FrameState dormant mesh

Artifact size: **15,137 bytes**.

- carried proof median: **0.0072 ms**;
- audited byte rehash median: **0.0313 ms**;
- audit/carried multiplier: **4.3x**.

## Corruption control

The content-addressed capability artifact was deliberately changed while its old proof/ref remained untouched.

- carried mode accepted the previously verified identity, as its contract says it will;
- audited mode reread the bytes and rejected the mismatch;
- restoring the exact bytes made audited mode pass again.

This is the intended trust distinction, not a bug.

## Reusable primitive

`tools/AXM_FLOWING_COMPUTE_REUSE_PROOF.py`

The proof records contract id, strong artifact hash, byte count, source identity, semantic metadata, and its own content hash. Proof creation itself performs a full artifact hash and is not free.

## Truth boundary

- carried proof assumes the previously verified content-addressed/immutable object remains unchanged;
- carried mode does not rediscover out-of-band storage mutation;
- audited mode spends compute to re-establish byte identity;
- byte identity implies the same previously verified semantic metadata for that exact artifact, but this does not provide external authentication;
- one host/runtime; CPU time is not joules;
- no claim of compute or energy from nothing.

## Next gate

Bind reuse verification mode into the multi-contract plan/execution receipt. Unaffected contracts should declare `carried` or `audited`, and execution evidence must match that declaration. Periodic/full audit remains separate from fast generation commits.
