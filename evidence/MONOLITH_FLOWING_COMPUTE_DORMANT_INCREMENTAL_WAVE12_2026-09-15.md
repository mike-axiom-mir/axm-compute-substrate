# Flowing Compute Wave 12 — Dormant Resume Into a Changed Generation

Date: 2026-09-15  
Status: `EXPERIMENTAL SINGLE-HOST RUNTIME EVIDENCE`

## Question

Can an AXM state body survive process death, wake after its source has changed, prove which prior generation it came from, verify the new source generation, update only the affected dependency closure, and produce exactly the same new state as a full cold reconstruction?

Wave 12 combines Wave 11 process-independent dormant state with Waves 5–6 dependency-closure propagation.

## Real state contract

Source: monolith `EXECUTION_GRAPH.json`.

- source bytes: **1,282,158**
- source SHA-256: `8a4ec3b92167a57091f63eb17158fe580eff97e84a4a4444b5efdebb749923c4`
- wired candidate edges: **3,618**
- active endpoint nodes: **160**
- SCC components: **127**
- hardened dormant state: **662,225 bytes**

The dormant body retains component topology, per-edge semantic hashes, per-edge topology identity, local component hashes, propagated signatures, and predecessor/successor structure. It does not contain the full source JSON.

## Source transitions

Five controlled semantic mutations reused the real Wave-6 surface:

- 1 mutated source component -> 22/127 affected;
- 13 -> 58/127;
- 49 -> 94/127;
- 76 -> 121/127;
- 82 -> 127/127.

Only `source_evidence_status` values were intentionally changed. Endpoint/wiring topology was not changed.

Each delta is tied to old/new source SHA-256, before/after edge hashes, changed edge content, and a delta SHA-256. The dormant body independently retains edge-topology identity; a deliberately falsified delta that changed an endpoint while claiming `topology_change=false` was rejected with `HOLD: edge topology changed`.

## Three fresh-process routes

Every sample launches a fresh Python process.

1. **cold rebuild** — hash/parse the changed source and reconstruct graph state.
2. **dormant-global** — load old dormant state + delta, SHA-256 rehash the entire changed source, validate/apply the delta, globally propagate all signatures, and materialize the new dormant generation.
3. **dormant-incremental** — identical wake/validation path, but propagate only the affected closure before materializing the same new generation.

All three routes produced the **same final state SHA-256 for every case**.

## Hardened end-to-end evidence

Two independent hardened runs used 5 fresh-process samples per route/case in each run (10 samples/route/case combined).

Combined median operation CPU:

| affected | cold rebuild | dormant global | dormant incremental | incremental vs cold |
|---:|---:|---:|---:|---:|
| 22 / 127 | 44.23 ms | 14.76 ms | 13.78 ms | **68.84% less** |
| 58 / 127 | 44.89 ms | 15.23 ms | 14.75 ms | **67.13% less** |
| 94 / 127 | 45.59 ms | 16.23 ms | 15.80 ms | **65.35% less** |
| 121 / 127 | 45.87 ms | 17.01 ms | 16.78 ms | **63.42% less** |
| 127 / 127 | 45.42 ms | 17.68 ms | 17.74 ms | **60.94% less** |

The persistence/reconstruction benefit remained large even when every component was affected. Fresh-process wall-time improvements were much smaller/noisier because interpreter startup dominates this small workload; no universal wall-time claim is made.

## Route-phase decomposition

The transition was then split into:

1. common wake/verify/delta preparation;
2. route-specific signature propagation;
3. common next-generation serialization/hash.

A 5-trial fresh-process phase check measured only the route-specific propagation kernel:

| affected | global propagation | incremental propagation | incremental kernel saving |
|---:|---:|---:|---:|
| 22 / 127 | 0.970 ms | 0.394 ms | **59.4%** |
| 58 / 127 | 0.954 ms | 0.701 ms | **26.6%** |
| 94 / 127 | 0.944 ms | 0.829 ms | **12.2%** |
| 121 / 127 | 0.969 ms | 0.925 ms | **4.6%** |
| 127 / 127 | 0.961 ms | 0.948 ms | **~1.3% / timing-noise region** |

This restores the expected locality curve once common wake/finalization work is removed from the routing measurement.

## Lifecycle interpretation

Wave 12 establishes that lifecycle phase belongs in compute policy.

**Dormant resume:** avoiding reconstruction is the dominant gain; route selection is secondary and can disappear into noise near broad invalidation.

**Resident update:** common wake/finalization costs are absent from each update; Wave-6-style fine-grained routing therefore remains a different valid contract with a stronger signal.

The correct rule is not one global threshold. It is:

> select compute policy by **state contract and lifecycle phase**.

## Reusable primitive

Adds:

- `tools/AXM_FLOWING_COMPUTE_DORMANT_GRAPH_TRANSITION.py`
- `tools/AXM_FLOWING_COMPUTE_DORMANT_GRAPH_TRANSITION_SELFTEST.py`
- `schemas/dormant-graph-state.v0.1.schema.json`
- `schemas/dormant-graph-delta.v0.1.schema.json`
- `schemas/dormant-graph-transition-receipt.v0.1.schema.json`

Self-test: **7 checks PASS**. Real state/delta/receipt schema validation: **PASS**.

## Truth boundary

- one host / one monolith snapshot;
- CPU process time is not joules;
- OS page cache was not flushed;
- controlled mutations are probe fixtures, not canonical product edits;
- dormant state is derived state, not lossless compression;
- topology changes HOLD/rebuild in v0.1;
- route-specific gains shrink toward full invalidation and can become timing noise;
- no compute/energy from nothing or physical-over-unity claim.

## Next gate

Carry the newly produced dormant generation through another process death and another source mutation:

`generation 0 dormant -> wake/mutate -> generation 1 dormant -> process death -> wake/mutate -> generation 2 ...`

The next question is whether useful computational structure can remain truthful and advantageous across multiple serialized generations without accumulating silent drift.
