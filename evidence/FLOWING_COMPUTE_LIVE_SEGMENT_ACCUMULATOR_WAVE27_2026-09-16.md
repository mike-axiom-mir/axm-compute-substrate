# Flowing Compute Wave 27 — Live Segment Proof Accumulator

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST CHECKPOINT-WRITE EVIDENCE`

## Question

Wave 26 bounded checkpoint creation to the newest 1,024-generation segment, but still reread/reparsed those records after they had already been written. Can the transactional writer build the next segment proof *while* it creates each generation so checkpoint sealing becomes metadata work instead of rediscovery?

## Proof contract

Wave 27 uses a deterministic generation-chain root rather than a flat byte-prefix SHA.

For each generation already being committed, the writer already knows generation sequence, generation content SHA-256, generation payload offset, and payload length. The live accumulator updates one 32-byte chain root from those values. It therefore commits ordered generation identity + placement without rereading the spine.

The serialized/checksummed accumulator state is only **112 bytes**.

A sealed segment records start/end offsets, start/end generation sequence, record count, and final generation-chain root. A later audit can reread the spine and recompute the exact same chain.

## 1,024-generation benchmark

Segment: generations 18,433..19,456; **1,024 records / 303,104 bytes**.

Generation metadata was prepared outside timing, matching values the normal writer already owns at commit time.

- live accumulator updates for all 1,024 generations: **1.350 ms CPU**;
- live updates + serialize the 112-byte accumulator after every generation: **2.306 ms CPU**;
- seal completed segment: **0.0005 ms CPU**;
- later full segment audit from the spine: **4.860 ms CPU**.

Amortized over 1,024 generations:

- accumulator math only: ~**1.32 microseconds/generation**;
- math + serialization every generation: ~**2.25 microseconds/generation**.

The intended integration is to carry that 112-byte state inside the existing dual-slot committed pointer, avoiding a separate durable sidecar write.

## Restart continuity

Accumulator state was serialized/deserialized after generation cuts 1, 17, 511, and 1,023, then continued to the exact same final segment root every time.

This proves restartable accumulator state; it is not yet pointer-integrated crash recovery.

## Audit equivalence

The live-built segment root exactly matched a later audit recomputation from all 1,024 spine records.

Self-test: **4/4 PASS**:

- serialized-state round trip;
- audit equivalence;
- accumulator-state tamper rejection;
- sequence/offset gap rejection.

## Tradeoff

The live chain is cheaper to create because it reuses values already known at generation commit time. Full audit is deliberately more expensive because it re-reads and revalidates immutable history.

Responsibilities remain separate:

- normal checkpoint creation: carried live chain;
- audit: recompute from immutable spine;
- full authoritative recovery: remains available.

## Truth boundary

- benchmark prepares writer-owned generation metadata outside timing; it does not measure the full generation writer;
- one host/runtime;
- CPU time is not joules;
- restart continuity here is accumulator serialization continuity, not yet pointer-integrated crash recovery;
- carried generation hashes provide content identity/integrity, not external authentication;
- full audit remains more expensive by design;
- no claim of compute/energy from nothing.

## Next gate

Extend the dual-slot transactional pointer with the 112-byte live accumulator state. Inject crashes before/after pointer replacement, prove the accumulator resumes only from the last committed generation, seal a 1,024-generation segment without rereading the spine, and recover correctly when the checkpoint seal itself is missing after a crash.
