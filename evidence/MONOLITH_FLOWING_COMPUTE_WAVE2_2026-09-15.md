# Monolith Flowing-Compute Probe — Wave 2 — 2026-09-15

Status: `EXPERIMENTAL RUNTIME EVIDENCE`

Subject: copied upload `AXM_Connected_Monolith_v0.4.30-WALMI-NATIVE-WIRING.zip`

This wave extends the first FrameState cold-vs-flow result. It asks whether the measured advantage survives decomposition, repeated-use scaling, and a second independent monolith subsystem.

## 1. FrameState state decomposition

Workload: 18 deterministic 128×96 frames of the Blackline relay OBJ used in the first probe. Every mode produced the same per-frame SHA-256 output digests.

Five alternating-order trials were run for four modes:

| Mode | Retained state | Median CPU | Gain vs cold | Yield vs cold |
| --- | --- | ---: | ---: | ---: |
| cold | none; rebuild `MediaCache` and mesh each frame | 694,365,790 ns | baseline | 1.000× |
| manifest_persist | retain manifest/cache object; clear parsed mesh each frame | 686,818,247 ns | 1.087% | 1.011× |
| mesh_persist | parse mesh once; rebuild media manifest each frame | 617,470,201 ns | 11.074% | 1.125× |
| flow | retain both media/cache state and parsed mesh | 585,289,860 ns | 15.709% | 1.186× |

Interpretation: most of the measured gain in this workload comes from retaining the parsed mesh, not merely from retaining media-manifest bookkeeping. The full gain is larger than either isolated component, but these differences are not claimed to be additive causal percentages.

## 2. Reuse horizon / frame-count scaling

Cold-vs-flow was repeated at different reuse horizons. Each point used three alternating-order trials with exact output digest equality.

| Frames | Median CPU gain | Yield multiplier | All three trials flow-faster? |
| ---: | ---: | ---: | --- |
| 1 | -2.019% | 0.980× | no |
| 2 | 26.078% | 1.353× | no |
| 4 | 18.328% | 1.224× | no |
| 8 | 14.127% | 1.165× | yes |
| 18 | 15.144% | 1.178× | yes |
| 36 | 16.170% | 1.193× | yes |

The 2- and 4-frame medians are noisy and are not treated as stable effect estimates. The one-frame result is an important negative control: when there is effectively no reuse horizon, retaining state did not help and was slightly slower. From 8 frames onward, every measured trial favored persistent state in this run.

## 3. Independent subsystem: Execution Fabric status state

The monolith's `EXECUTION_FABRIC.json` is 39,055,991 bytes. The current `AXM_EXECUTION_FABRIC.status()` path parses that complete registry for each status request even though the returned status is a small summary.

A second experiment compared four identical status requests under three designs. Canonical JSON output hashes were identical across all modes.

Two alternating-order trials:

| Mode | Description | Median CPU for 4 requests | CPU saved vs cold | Throughput/yield vs cold |
| --- | --- | ---: | ---: | ---: |
| cold | parse the 39 MB registry on every request | 3,492,977,890 ns | baseline | 1.000× |
| resident | parse once and keep the full parsed registry | 746,308,701 ns | 78.634% | 4.680× |
| compiled | parse once, retain only the derived status state, discard full parsed registry | 934,540,275 ns | 73.245% | 3.738× |

### Retained-state size / memory tradeoff

The resident design raised process RSS from roughly 102–104 MB to roughly 171 MB after setup: approximately +67–69 MB retained memory in these runs.

The compiled derived status state serialized to only **848 bytes**. After the full registry was discarded and garbage collected, observed process RSS returned close to the pre-setup level (about +1 MB in these coarse process measurements).

The compiled design's median measured post-setup CPU for four returned status answers was about 118,868 ns total, or about 29,717 ns per request. This number is only meaningful for the pinned, unchanged snapshot used here; it is not a general latency claim.

## What wave 2 establishes

On this copied monolith and this host:

1. the FrameState result is tied to concrete reusable structure rather than a universal loop advantage;
2. no-reuse work can be neutral or slower under a persistent-state design;
3. the FrameState advantage becomes repeatable once a meaningful reuse horizon exists;
4. a separate 39 MB Execution Fabric structure can be converted once into a tiny derived state that answers the same repeated status question with much less repeated CPU work;
5. retaining the whole body and retaining only a compact derived state have very different memory costs.

This is evidence for **compute-yield improvement through preserved/compiled computational structure**, not evidence that software creates physical compute or energy.

## Required next truth test: freshness / invalidation

The 848-byte compiled-state result assumes an immutable or pinned source snapshot. If the 39 MB registry changes, blindly serving the old derived state would be stale and therefore wrong.

A mutable implementation must have an explicit freshness contract, for example:

- immutable content-addressed source identity; or
- source generation/version identity; or
- validated change notification; or
- bounded invalidation/recompile rules.

The cost of keeping derived state truthful must be included in later accounting. A speedup that silently serves stale state is not a valid Flowing Compute gain.

## Truth boundary

- single execution environment;
- Python process CPU time and wall time, not direct joule measurement;
- exact-output equality was checked for the measured contracts;
- small trial counts, especially for scaling points;
- OS page cache and interpreter/runtime state are part of the host conditions and were not independently controlled;
- no claim of free energy, physical over-unity, or universal AXM-wide percentage;
- no claim that current monolith code is already an optimized Flowing Compute architecture;
- independent reproduction on another host remains required.

## Reproducibility pack

`evidence/probes/axm_flowing_compute_probe_pack_v2.zip`

SHA-256: `894915625d5b4d1141c0a7727d84388de50ab1b80742be8c754bb9103f1f5af2`
