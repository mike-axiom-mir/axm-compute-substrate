# Flowing Compute Wave 19 — Proof-Carrying Overlay Wake

Date: 2026-09-15  
Status: `EXPERIMENTAL SINGLE-HOST RUNTIME EVIDENCE`

## Question

Wave 17 self-verifying overlay wake recomputes the final effective semantic hash every time. Wave 18 showed that making the effective view lazy does not help while that flat proof still touches every block.

Wave 19 tests a different trust contract:

> if an exact immutable overlay artifact was fully verified against an exact target generation when it was created, can a later fresh process verify the immutable artifact/proof chain and reuse that already-earned semantic identity instead of recomputing the entire effective-state proof on every wake?

This is **proof reuse**, not stronger self-verification. Both modes remain available.

## Creation-time proof

A checkpoint proof binds an exact compact artifact SHA-256 to its source generation and native semantic identity after full semantic validation.

An overlay-generation proof is minted only after:

1. parent compact checkpoint is fully semantically validated;
2. target compact checkpoint is fully semantically validated;
3. overlay parent/source/target fields match those checkpoints;
4. applying the overlay patch to the validated parent recomputes the exact target semantic identity.

The proof is content-addressed. It provides integrity/provenance inside this deterministic experiment; it is **not external authentication/signing**.

## In-process wake result

Compared with Wave-17 self-verifying wake, proof-carrying wake still checks base/overlay artifact integrity, ordered artifact chain, parent semantic identity, source-generation linkage, proof integrity, and changed block ranges, but does not recompute the final flat effective-state semantic hash.

31-trial medians:

- depth 1: **48.0% less CPU / 1.92x yield**;
- depth 6: **38.6% less / 1.63x**;
- depth 24: **33.9% less / 1.51x**;
- depth 64: **22.9% less / 1.30x**.

At every depth a full effective semantic recomputation was performed outside the timed path and matched the carried target identity exactly.

## Fresh-process control

The producing process was killed and a new process read the base/overlay/proof evidence.

Using individual JSON proof files:

- depth 6: proof-carrying wake saved about **32% CPU/wall**;
- depth 64: advantage collapsed to about **3.5%** because opening/parsing 64 separate proof files became the new bottleneck.

This was treated as research machinery debt, not as a failure of proof reuse.

## Compact proof manifest

The verified proof receipts were compacted into one content-addressed manifest. The manifest does not create new semantic proof; it is a compact index of already verified overlay artifacts/checkpoints.

- 64 individual proof JSON files: about **79.8 KB**;
- one 64-generation proof manifest: **18.7 KB**.

Fresh-process wake with the single manifest versus self-verifying wake:

- depth 1: **~37% less CPU/wall**;
- depth 6: **~35.6% less**;
- depth 24: **~24.1% less**;
- depth 64: **~29.3% less**.

So the proof reuse advantage survives process death once the proof metadata itself is not fragmented into dozens of files.

## Fair compaction comparison

A compact snapshot can carry a prior checkpoint proof too. Therefore Wave 19 compares **proven compact wake** against **proven overlay wake** rather than giving only overlays the proof-reuse advantage.

31-trial operation CPU:

- depth 1: compact **1.639 ms**, overlay **1.868 ms**;
- depth 6: **1.779 vs 2.263 ms**;
- depth 24: **1.799 vs 2.834 ms**;
- depth 64: **1.733 vs 3.709 ms**.

Overlay replay still gets more expensive with depth; proof reuse reduces the penalty but does not remove it.

## Proof creation is not free

With parent and target state already resident/validated and the overlay artifact already available, creation-time semantic attestation was measured over the six real G0→G6 transitions:

- median per generation: **~0.87–0.88 ms CPU**.

Wave-17 optimized overlay emit is about **0.38 ms**; therefore proof-carrying overlay creation is about **1.25 ms** versus about **3.09 ms** for a full packed snapshot emit.

So proof reuse still saves roughly **1.8 ms creation CPU per generation** rather than merely moving an unaccounted proof cost off the wake path.

Using those measured creation costs, CPU-only future-wake break-even becomes approximately:

- depth 1: **8.0 wakes**;
- depth 6: **3.8**;
- depth 24: **1.8**;
- depth 64: **0.9**.

This is preserved as a separate proof-aware calibration; Wave 17's self-verifying calibration is not overwritten.

## Reusable primitives

- `tools/AXM_FLOWING_COMPUTE_PROVEN_OVERLAY.py`
- `tools/AXM_FLOWING_COMPUTE_PROOF_MANIFEST.py`
- `calibration/overlay-compaction-proven-calibration.v0.1.json`

## Truth boundary

- proof reuse depends on prior verified immutable evidence; it is not equivalent to recomputing the semantic proof now;
- SHA/content addressing gives integrity, not external actor authentication;
- a bug in the trusted proof-producing implementation remains a possible failure mode;
- full self-verifying wake remains available and periodic full revalidation/compaction is still useful;
- proof creation CPU is counted, but manifest persistence/write cost is not yet separately calibrated;
- one host / one state contract;
- CPU time is not joules;
- no claim of compute/energy from nothing.

## Next gate

Avoid replaying a long overlay history even in proof-carrying mode. Build a small **resolved overlay-head index** that contains the newest changed block values, ordered chain-head identity, and carried target semantic evidence while preserving the full append-only overlay history separately. Measure whether a ~few-KB head index can wake nearly as fast as a compact snapshot without rewriting the full ~261 KB state each generation.
