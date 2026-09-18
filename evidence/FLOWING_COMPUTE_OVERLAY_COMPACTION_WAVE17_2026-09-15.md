# Flowing Compute Wave 17 — Native Overlay Chain and Compaction Policy

Date: 2026-09-15  
Status: `EXPERIMENTAL SINGLE-HOST RUNTIME EVIDENCE`

## Question

Can native packed dormant state avoid rewriting the entire ~261 KB body on every generation by appending tiny content-addressed overlays, while preserving exact state identity and compacting before replay cost becomes wasteful?

## Real six-generation chain

Wave 17 reuses the proven Wave-13 G0→G6 cumulative chain. Each overlay records only changed edge digests, changed component-local digests, changed propagated signatures, generation/source identities, delta identity, and the previous artifact hash. The base is validated once; overlay artifact/semantic/source linkage is verified in order; final semantic identity is recomputed after replay.

- native G0 base: **261,596 bytes**
- six real overlays: **3,340, 5,596, 4,661, 2,443, 1,956, 1,956**
- base + six overlays: **281,548 bytes**
- seven full packed snapshots: **1,831,161 bytes**
- history storage reduction: **84.62%**

At depth 64, using the reversible G4↔G5 transition to extend the chain without changing the state contract:
- base + 64 overlays: **395,021 bytes**
- equivalent full-snapshot history: **~17.0 MB**

Exact compacted-state equality and overlay chain integrity pass. Tampered or reordered overlays reject.

## Overlay emission cost

31 trials per real transition after the transition already knows its changed edge/component sets:

| transition | full snapshot emit | overlay emit | CPU saved | overlay bytes | bytes saved |
|---|---:|---:|---:|---:|---:|
| G0->G1 | 3.052 ms | 0.343 ms | **88.7%** | 3,308 | **98.7%** |
| G1->G2 | 3.115 ms | 0.426 ms | **86.3%** | 5,566 | **97.9%** |
| G2->G3 | 3.128 ms | 0.417 ms | **86.7%** | 4,630 | **98.2%** |
| G3->G4 | 3.034 ms | 0.362 ms | **88.1%** | 2,410 | **99.1%** |
| G4->G5 | 3.090 ms | 0.379 ms | **87.7%** | 1,926 | **99.3%** |
| G5->G6 | 3.087 ms | 0.385 ms | **87.5%** | 1,925 | **99.3%** |

The patch writer no longer scans every digest block to rediscover what changed; it consumes the exact changed/affected indices already produced by the transition.

## Wake replay cost

31 alternating in-process trials per measured depth. Compact means opening one full native snapshot; overlay means opening the G0 base, replaying the overlay chain, and verifying the final semantic identity.

| depth | compact wake | overlay wake | overlay CPU penalty | base + overlays |
|---:|---:|---:|---:|---:|
| 1 | 2.650 ms | 3.778 ms | **42.6%** | 264,936 |
| 2 | 2.695 ms | 3.992 ms | **48.1%** | 270,532 |
| 4 | 2.823 ms | 4.125 ms | **46.1%** | 277,636 |
| 6 | 2.779 ms | 4.219 ms | **51.8%** | 281,548 |
| 8 | 2.837 ms | 4.317 ms | **52.2%** | 285,460 |
| 12 | 2.802 ms | 4.444 ms | **58.6%** | 293,287 |
| 16 | 2.991 ms | 4.711 ms | **57.5%** | 301,113 |
| 24 | 3.004 ms | 5.012 ms | **66.9%** | 316,764 |
| 32 | 2.975 ms | 5.232 ms | **75.9%** | 332,415 |
| 48 | 3.039 ms | 5.942 ms | **95.5%** | 363,717 |
| 64 | 2.962 ms | 6.028 ms | **103.5%** | 395,021 |

Overlay wake cost grows with chain depth; it is not promoted as a permanently faster wake format.

## CPU-only compaction planner

The measured planner compares:

`append overlay = overlay emit + expected future wakes × overlay wake`

`compact snapshot = full emit + expected future wakes × compact wake`

It uses only measured depths and HOLDs on unmeasured depths rather than interpolating silently. Storage bytes are reported separately and are not converted into a hidden CPU/money score.

- depth 1: measured CPU break-even ≈ **2.40 future wakes**
- depth 6: measured CPU break-even ≈ **1.88 future wakes**
- depth 24: measured CPU break-even ≈ **1.35 future wakes**
- depth 48: measured CPU break-even ≈ **0.93 future wakes**
- depth 64: measured CPU break-even ≈ **0.88 future wakes**

So CPU policy tends to append patches for low-wake/update-heavy periods and checkpoint/compact for read/wake-heavy periods. A compaction checkpoint does not require deleting the prior base/overlay history.

## Reusable primitives

- `tools/AXM_FLOWING_COMPUTE_NATIVE_OVERLAY.py`
- `tools/AXM_FLOWING_COMPUTE_OVERLAY_COMPACTION.py`
- `tools/AXM_FLOWING_COMPUTE_NATIVE_OVERLAY_SELFTEST.py`
- `calibration/overlay-compaction-calibration.v0.1.json`

Self-test: **8 checks PASS**.

## Truth boundary

- one host and one dormant graph contract;
- wake benchmark is in-process operation CPU, not process startup or joules;
- OS page cache is not flushed;
- expected future wake count is an external assumption, not something this calibration knows;
- overlay history optimizes write/storage history while compact snapshots optimize wake; neither is universally superior;
- current overlay wake eagerly replays patches; a lazy/memory-mapped overlay reader could have different economics;
- no compute/energy from nothing or universal threshold claim.

## Next gate

Make overlays **lazy**: build an index of newest digest blocks across base + overlays without eagerly copying/replaying every block. Then measure whether the wake penalty can be reduced while preserving the same exact final semantic identity.
