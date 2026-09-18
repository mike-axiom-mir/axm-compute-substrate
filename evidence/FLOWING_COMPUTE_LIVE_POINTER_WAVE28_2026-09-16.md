# Flowing Compute Wave 28 — Atomic Pointer + Live Checkpoint State

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST POINTER-INTEGRATION EVIDENCE`

## Question

Can the current dual-slot pointer atomically commit both the selected generation and the live checkpoint accumulator, so process death cannot advance one without the other?

## Pointer shape

Wave 28 extends the committed pointer with the 112-byte Wave-27 live accumulator.

Observed pointer size: **202 bytes**.

The pointer now binds:

- committed generation sequence;
- generation spine offset/length;
- generation content hash;
- current live segment start/last/count/root.

The complete pointer is checksummed and moved through the same dual-slot atomic replacement discipline.

## 1,024-generation segment

A fresh spine was rebuilt through generation 1,024 using exact valid generation frames and alternating pointer slots.

Recovered pointer state at generation 1,024:

- selected sequence: **1,024**;
- accumulator count: **1,024**.

Sealing the completed segment directly from the committed pointer:

- pointer-only seal median: **~0.861 microseconds CPU**;
- later full spine audit of the sealed segment: **PASS**.

No segment reread is required to mint the normal seal.

## Crash boundary — generation 1,025

### Record appended, pointer not moved

Generation-1,025 frame was appended but the pointer replacement was deliberately omitted.

Recovery selected:

- generation **1,024**;
- accumulator count **1,024**.

So uncommitted spine progress does not advance checkpoint-proof progress either.

### Pointer committed

After sealing generation 1,024 and committing the generation-1,025 pointer:

- selected generation: **1,025**;
- new segment accumulator count: **1**.

Generation selection and checkpoint accumulator therefore move together.

### Corrupt new pointer slot

After corrupting the generation-1,025 pointer slot, recovery fell back to the older valid slot:

- generation **1,024**;
- its matching accumulator state.

The checkpoint-progress state cannot remain newer than the committed generation through this failure path.

## Pointer CPU overhead

Serializing the 202-byte live pointer measured about **2.54 microseconds CPU** median in the local microbenchmark.

That is the intended per-generation persistence surface for the live accumulator; there is no separate durable accumulator sidecar.

## Truth boundary

- the test reconstructs a fresh valid spine from real generation frames but does not rerun full AXM state mutations for all 1,025 generations;
- same host/filesystem/runtime;
- CPU time is not joules;
- dual-slot pointer selection here validates pointer integrity/sequence coupling; full state dependency validation remains the wider crash-recovery responsibility;
- filesystem atomicity/fsync guarantees remain platform dependent;
- no claim of compute/energy from nothing.

## Next gate

Test a crash after the pointer commits a completed 1,024-generation accumulator but before the segmented checkpoint file is sealed. Recovery should synthesize the missing checkpoint from committed pointer state without rereading the spine, while a corrupt/missing older checkpoint history must HOLD or fall back rather than silently invent prior segment proofs.
