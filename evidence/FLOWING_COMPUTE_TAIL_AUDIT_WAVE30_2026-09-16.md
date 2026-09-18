# Flowing Compute Wave 30 — Audited Tail Semantics for Live Pointers

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST TRUST-MODE EVIDENCE`

## Question

Wave 28/29 can carry a live accumulator inside a checksummed committed pointer. Fast recovery can reuse that proof, but an outer checksum proves only that the pointer bytes are internally intact — not that the accumulator root was semantically computed correctly.

Can an audited recovery mode recompute only the current unsealed tail from the last sealed checkpoint and require the result to exactly match the accumulator carried by the selected pointer?

## Contract

Wave 30 adds `AXM_FLOWING_COMPUTE_TAIL_AUDIT_RECOVERY.py`.

Given a prior validated checkpoint and candidate pointer, audited-tail recovery derives the tail start from the checkpoint, then rereads generation frames only through the candidate pointer target. It verifies generation sequence continuity, generation parent identity/placement, pointer target generation identity/placement, accumulator start, and final accumulator count/placement/root.

Later history beyond the pointer target is not scanned.

## Normal case

Prior checkpoint: generation 1,024. Current pointer: generation 1,500. Tail audited: **476 generations**.

Both modes selected generation 1,500:

- carried proof: trusts commit-time accumulator;
- audited tail: re-establishes the accumulator from immutable spine history.

## Semantic corruption control

The highest pointer's accumulator root was deliberately altered, then the entire pointer was reserialized with a fresh valid outer checksum. The pointer was therefore byte-integrity-valid but semantically false.

Observed behavior:

- carried mode selected generation **1,500** as expected for its trust contract;
- audited-tail mode detected `pointer_accumulator_semantic_mismatch`, rejected generation 1,500, audited the older pointer, and selected generation **1,499**.

Then the older pointer accumulator was also semantically altered/rechecksummed. Audited-tail recovery returned **HOLD** because no semantically valid committed pointer remained.

This proves pointer checksum and accumulator semantic proof are intentionally distinct layers.

## Cost of proof re-establishment

476-record current tail:

- carried pointer selection median: **0.0253 ms CPU**;
- audited-tail recovery median: **4.928 ms CPU**;
- audited/carried CPU ratio: **~194x**.

The audited path is more expensive by design because it rereads/recomputes the current-tail proof. It remains bounded to the unsealed tail rather than the whole retained history.

## Truth boundary

- test uses exact valid generation frames under the current record contract;
- semantic corruption is deliberate test mutation with a recomputed pointer checksum, not an observed production fault;
- carried mode intentionally does not rediscover commit-time semantic mistakes;
- audited mode is still one-host/filesystem evidence;
- pointer/current-state authority and full historical audit remain separate responsibilities;
- CPU process time is not joules;
- hashes provide content identity/integrity, not external authentication;
- no claim of compute/energy from nothing.

## Next gate

Remove Wave-29 checkpoint-history rewrite amplification. Store each sealed 1,024-generation segment proof as an immutable content-addressed object, append a tiny parent-linked checkpoint-spine record, and keep only a tiny current checkpoint pointer. Audit/rollback must reconstruct the chain without copying old segment proofs into every new seal.
