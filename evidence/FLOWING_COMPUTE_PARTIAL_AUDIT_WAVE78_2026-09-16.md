# Flowing Compute Wave 78 — Per-Contract Partial Audit in One Atomic Generation

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST BOOKKEEPING / COMMIT EVIDENCE`

## Question

Wave 77 bound generation state and verification-freshness state to one atomic commit. Can different unchanged/sleeping contracts use different verification modes in the same generation without collapsing freshness into one global machine age?

## Result

Two real retained-contract identities from the prior waves were used:

- `axm.execution-fabric.capability-index/v0.1` — artifact size **11,255,808 bytes**;
- `axm.framestate.dormant-mesh/v0.1` — artifact size **15,137 bytes**.

Generation 1 advanced them with different reuse modes:

- capability index: `audited_reuse` -> audit age **0**;
- dormant mesh: `carried_immutable_proof` -> audit age **1**.

Generation 2 deliberately reversed the modes:

- capability index: carried -> audit age **1**;
- dormant mesh: audited -> audit age **0**.

The complete freshness set remained bound to the same atomic generation pointer.

## Transactional in-memory transition

Wave 78 adds `AXM_FLOWING_COMPUTE_PARTIAL_AUDIT.py`.

It requires an explicit verification mode for every registered freshness state and stages the full next set before returning success. If any contract cannot advance — for example because an explicit caller-supplied carried-generation limit requires audit — the function returns `HOLD` and exposes **no partially advanced freshness set**.

A control configured mesh `max_carried_generations=0` while asking capability to audit and mesh to carry. Mesh returned `HOLD_AUDIT_REQUIRED`; capability's staged audit did not become a returned/committable partial state.

## Crash / integrity controls

Passed:

- prepared G1 without pointer move -> persisted state remains G0 with both audit ages 0;
- pointer move -> G1 appears with capability age 0 / mesh age 1 together;
- nested mesh-freshness tamper plus recomputed outer pointer hash -> rejected by nested freshness-state identity;
- complete per-contract mode coverage required;
- one-contract HOLD prevents partial freshness transition.

## Cost

Median CPU for **freshness bookkeeping + constructing the two-contract generation pointer** over 2,000 iterations: **~64.3 microseconds** on this host.

This timing deliberately **does not include the byte cost of a real audited artifact rehash**. Wave 75 separately measured the large difference between carried and audited reuse. This wave tests composition/atomicity, not audit-throughput performance.

## Truth boundary

- audit age is compute/freshness evidence, not a corruption probability;
- no audit cadence is invented by this experiment;
- explicit carried-generation limits are caller configuration, not recommendations;
- partial audit does not grant generation authority; generation authority remains the atomic pointer/commit layer;
- CPU time is not joules;
- one host/runtime.

## Next gate

Bind per-contract audit **work receipts** to the partial-audit transition so an `audited_reuse` freshness reset cannot be claimed merely by choosing the word `audited_reuse`. The reset should require evidence that the exact artifact bytes were actually read/verified during that generation; carried mode should continue to reuse prior proof without fabricating a fresh audit.
