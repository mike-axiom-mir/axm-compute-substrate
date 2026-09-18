# Flowing Compute Wave 13 — Multi-Generation Dormant Continuity

Date: 2026-09-15  
Status: `EXPERIMENTAL SINGLE-HOST RUNTIME EVIDENCE`

## Question

Can a derived AXM state body survive multiple cycles of:

`serialize -> process death -> wake -> source mutation -> verified transition -> serialize again`

without silently drifting away from a cold reconstruction of the same source generation?

## Real contract

Wave 13 continues the monolith `EXECUTION_GRAPH.json` dormant-signature contract from Wave 12.

Every transition launches in a fresh process, loads the previous dormant state + semantic delta, SHA-256 rehashes the complete current source, rejects topology drift, produces the next dormant generation, and is compared with a separate fresh cold reconstruction. Exact state SHA-256 equivalence is mandatory.

## Generation sequence

- **G0 -> G1:** 13 changed edges; 58 affected components.
- **G1 -> G2:** 36 additional changed edges; 77 affected components.
- **G2 -> G3:** 27 additional changed edges; 68 affected components.
- **G3 -> G4:** 6 additional changed edges; 46 affected components.
- **G4 -> G5:** mutate one edge that had already been mutated earlier; 42 affected components.
- **G5 -> G6:** revert that same edge to its G4 value; 42 affected components.

Each transition consumes the state produced by the previous fresh process. No generation silently reloads the G0 state.

## Three independent full-chain runs

The complete six-transition chain was executed **three times**. At all 18 measured transitions:

`dormant transitioned state SHA-256 == fresh cold-rebuild state SHA-256`

Median transition CPU versus cold reconstruction CPU:

| transition | affected | dormant transition | cold rebuild | CPU saved |
|---|---:|---:|---:|---:|
| G0 -> G1 | 58 | 16.47 ms | 44.64 ms | **63.12%** |
| G1 -> G2 | 77 | 17.04 ms | 45.03 ms | **62.16%** |
| G2 -> G3 | 68 | 16.94 ms | 43.93 ms | **61.43%** |
| G3 -> G4 | 46 | 16.31 ms | 47.47 ms | **65.64%** |
| G4 -> G5 | 42 | 15.99 ms | 45.20 ms | **64.61%** |
| G5 -> G6 | 42 | 16.07 ms | 45.88 ms | **64.97%** |

The retained computational structure therefore remained advantageous after repeated serialization/process-death cycles rather than only on first resume.

## Reversibility / drift control

G5 deliberately changed an already-changed edge. G6 reverted only that edge to the G4 value while all other accumulated mutations remained.

- `G6 source SHA-256 == G4 source SHA-256` — **PASS**
- `G6 dormant state SHA-256 == G4 dormant state SHA-256` — **PASS**

This is the strongest continuity control in the chain: when the deterministic source returns to the earlier generation, the derived state returns to the identical earlier state hash instead of accumulating hidden historical baggage.

## Generation-chain verifier

Adds:

- `tools/AXM_FLOWING_COMPUTE_GENERATION_CHAIN.py`
- `tools/AXM_FLOWING_COMPUTE_GENERATION_CHAIN_SELFTEST.py`
- `schemas/generation-chain.v0.1.schema.json`

The chain verifier requires contiguous source/state ancestry, cold equivalence at every hop, previous-transition hash linkage, and deterministic same-source -> same-state behavior.

Self-test: **5 checks PASS**. Real chain schema validation: **PASS**.

Real chain SHA-256:

`2d17fdc14fdcd7c65ce2b5a1fd7d092fc04b11eea01590c35f7c707b6e69bbe3`

## Truth boundary

- one host / one monolith state contract;
- CPU process time is not direct energy measurement;
- source mutations are controlled research fixtures;
- topology-changing deltas remain HOLD/rebuild;
- the CPU advantage is contract-specific, not universal;
- no compute/energy from nothing or physical-over-unity claim.

## Interpretation

Waves 11–13 now establish three separate properties for this measured contract:

1. useful derived state can survive process death;
2. it can cross a changed source generation without rebuilding everything;
3. it can repeat that process across multiple generations without accumulating hidden drift in the tested chain.

That is substantially closer to a dormant capability/state body than ordinary in-process caching.

## Next gate

Measure **state density**: how much of the 662 KB dormant body is irreducible evidence, how much is representation overhead, and how much can be packed/content-addressed without increasing resume/update compute enough to erase the advantage. Smaller is not assumed to be better; storage and compute cost must both remain visible.
