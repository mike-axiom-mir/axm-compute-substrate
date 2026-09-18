# Flowing Compute Wave 49 — FrameState Dormant Parsed Mesh

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST REAL-RENDER EVIDENCE`

## Question
Can a real parsed FrameState mesh survive process death as compact dormant state and preserve exact rendering without reparsing its source OBJ?

## Source / dormant body
Real relay OBJ: 63,280 bytes, 1,224 vertices, 2,384 triangulated faces. The selected dormant representation is canonical parsed-mesh JSON compressed with zlib and bound to the exact source SHA-256. Artifact size: **15,137 bytes**.

A smaller custom binary attempt (~13.2 KB) was rejected because Python tuple reconstruction made wake slower than the slightly larger JSON/zlib body.

## Exact render equality
Cold, dormant, and source-SHA-audited dormant paths produced identical PPM hashes and FrameState state digests for the measured frames.

## Fresh-process results
### One rendered frame (11 trials)
- cold OBJ/media startup: **24.66 ms CPU**
- dormant parsed mesh: **20.69 ms** -> **16.10% less / 1.19x**
- dormant + full OBJ SHA recheck: **20.76 ms** -> **15.82% less / 1.19x**

### 18-frame continuous process (3 trials)
- cold: ~343 ms CPU
- dormant: ~347 ms
- audited dormant: ~342 ms

No meaningful advantage; one cold process parses once and reuses MediaCache for the remaining frames.

### 18 frames / 18 fresh workers
Independent batches:
- batch 1: **14.73% less CPU / 1.17x** dormant vs cold;
- batch 2: **16.28% less / 1.19x**.

## Interpretation
Process lifetime is part of the state contract. Dormant mesh state is useful for short-lived/parallel workers, while a long-lived renderer already amortizes parse cost through ordinary resident MediaCache reuse.

## Truth boundary
- dormant state does not improve renderer math itself;
- one asset/renderer/host;
- CPU time is not joules; hardware energy counters are unavailable here;
- no compute/energy-from-nothing claim.
