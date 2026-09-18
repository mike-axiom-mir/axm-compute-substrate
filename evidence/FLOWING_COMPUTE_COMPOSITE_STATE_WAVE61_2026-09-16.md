# Flowing Compute Wave 61 — Atomic Composite State Commit

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST REAL-MONOLITH MULTI-CONTRACT EVIDENCE`

## Question
Can one real source mutation advance two independently proven retained-state contracts — Execution Graph runtime state and whole-monolith snapshot/file identity — under one atomic visibility boundary, so recovery cannot observe a split generation?

## Real mutation
Preserved real `EXECUTION_GRAPH.json` G0 -> G1 delta:
- G0 source SHA-256 `8a4ec3b92167a57091f63eb17158fe580eff97e84a4a4444b5efdebb749923c4`
- G1 source SHA-256 `82a85a927b3b1575d2b44a5cd96b30ef8e74a0e9668d8d9b385b0a9d0936f4d8`
- delta SHA-256 `434bdd00807cafc468b330c745830a140f5d3dcc32d5418665c0e563e6c23ecd`
- 13 changed edges; 58 / 127 affected SCC components.

The same changed file is one leaf in the 24,965-file monolith snapshot identity.

## Composite transaction
Prepared first:
1. graph overlay + exact-difference proof + manifest + resolved head;
2. snapshot fixed-Merkle node overlay.

A composite pointer binds both target identities. Prepared artifacts may exist while sequence 0 remains current. Only one atomic pointer replacement exposes sequence 1.

## Controls
PASS:
- G1 artifacts durable, pointer still G0 -> graph G0 + snapshot G0 remain current;
- atomic pointer move -> graph G1 + snapshot G1 become current together;
- graph-head tamper rejected;
- snapshot-overlay tamper rejected;
- graph logical state exactly equals cold rebuild;
- snapshot root exactly equals full 24,965-file audit.

Target graph logical SHA-256: `028b2b4812dbfeb5757d7b5df1991b6025c39a565f2ac9d1bd19ad0f03bb14b1`.
Target snapshot root: `bd869f47270b628de6664b8c1cc94e92fc8700c69f9e0bfc8a9b26da42009760`.

## Compute benchmark
Independent alternating-order runs:
- run 1: cold both identities ~1.314 s CPU; retained composite ~21.09 ms; **98.40% less / 62.33x**;
- run 2: cold ~1.362 s; retained ~21.37 ms; **98.43% / 63.72x**.

The large ratio is dominated by avoiding a full ~558 MB snapshot audit. It is not a 63x graph-algorithm claim.

## Durable benchmark
Both routes use fsync + atomic temp replacement. Cold persists full graph packed state + full 2.1 MB snapshot Merkle tree and deliberately excludes rebuilding/persisting the ~8 MB snapshot path-index DB, favoring cold.

Run 1:
- cold ~1.322 s CPU;
- retained ~20.73 ms;
- **98.43% less / 63.76x**;
- writes **2,359,213 -> 10,517 bytes** (**99.55% fewer**).

Independent run 2:
- cold ~1.417 s;
- retained ~20.93 ms;
- **98.52% / 67.73x**;
- byte result unchanged.

## Truth boundary
- snapshot work dominates the ratio;
- snapshot contract assumes known changed path(s) and unchanged path topology here;
- carried creation proof is not full re-audit on recovery;
- software fsync/atomic-replace evidence is not a universal hardware power-loss guarantee;
- one host/runtime/filesystem;
- CPU is not joules; no usable hardware energy counter is exposed here;
- no compute/energy-from-nothing claim.

## Next gate
Create two distinct fully prepared composite children of the same current composite parent. Generic resolution must HOLD on ambiguity; only an exact selected composite intent may commit one branch while preserving the other as evidence.
