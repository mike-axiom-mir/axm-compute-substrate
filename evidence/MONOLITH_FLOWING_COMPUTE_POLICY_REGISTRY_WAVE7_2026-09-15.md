# Flowing Compute Wave 7 — Contract-Specific Policy Registry

Date: 2026-09-15  
Status: `EXPERIMENTAL SINGLE-HOST RUNTIME EVIDENCE`

## Question

Can Flowing Compute route different retained-state bodies with **different local policies** instead of forcing one global invalidation threshold across unlike workloads?

Wave 7 uses FrameState frame invalidation as a second state contract, then registers it beside the Wave-6 Execution Graph policy.

## FrameState state contract

The retained state is the complete ordered frame-digest manifest. A controlled layer-property mutation invalidates only frames where that layer is active.

Both routes receive the same normalized mutated project, the same FrameState renderer/cache state, and an equivalent preallocated baseline frame manifest:

- **incremental** rerenders only invalidated frames and preserves the remaining manifest entries;
- **global** rerenders every frame;
- the final complete digest manifest must be byte-for-byte identical.

Project: 48 frames at 80×60 with ten deterministic rect/circle layers using varied active windows. 15 mutation cases were measured twice, each with 7 alternating-order trials and 3 repeated updates per timing sample.

## Independent 2D routing runs

- `layer-0` — 2/48 frames affected: run1 **96.05%**, run2 **96.10%** incremental CPU saving
- `layer-2` — 12/48 frames affected: run1 **74.75%**, run2 **74.50%** incremental CPU saving
- `layer-4` — 24/48 frames affected: run1 **48.85%**, run2 **48.89%** incremental CPU saving
- `layer-6` — 40/48 frames affected: run1 **15.04%**, run2 **14.68%** incremental CPU saving
- `layer-7` — 44/48 frames affected: run1 **5.79%**, run2 **6.67%** incremental CPU saving
- `layer-8` — 46/48 frames affected: run1 **4.82%**, run2 **3.62%** incremental CPU saving
- `combo-near-global` — 47/48 frames affected: run1 **2.17%**, run2 **0.79%** incremental CPU saving
- `layer-9` — 48/48 frames affected: run1 **0.04%**, run2 **-1.82%** incremental CPU saving
- `combo-all` — 48/48 frames affected: run1 **0.13%**, run2 **-1.70%** incremental CPU saving

At complete 48/48 invalidation, the winner is timing-noise sized: run 1 was essentially tied/slightly incremental, while run 2 favored global by about 1.7–1.8%. This is preserved rather than averaged into a fake sharp advantage.

## Structural FrameState policy

FrameState does not use the Execution Graph’s learned component-count crossover. Its current candidate policy uses retained frame-work metadata already known before execution:

`affected_work_units = Σ (1 + active_layer_count(frame)) over invalidated frames`

`total_work_units = the same quantity over the whole retained frame body`

Routing rule:

- if affected work is less than total retained work → **incremental**;
- if the whole retained body is invalid → **global rebuild**;
- predicted avoidable work ≤ 1% is labeled **uncertain**, but the decision remains explicit.

Across the two 2D runs this deliberately simple rule produced:

- **28 / 30** observed route winners correct (93.33%);
- **13 / 14** deterministic held-out points correct (92.86%);
- maximum wrong-route regret: **0.129%**;
- mean regret across all observations: **0.0056%**.

Both misses were full-invalidation cases from the first run where incremental happened to win by only ~0.04–0.13%, i.e. inside the practical tie region.

## 3D holdout outside the 2D calibration body

A separate 24-frame FrameState project used the real Blackline relay OBJ mesh. Three mesh layers had different active windows. The 2D-derived structural policy was used without retraining.

- `mesh-0` — 12/24 frames invalidated: predicted **incremental**, observed **incremental**, incremental saving **39.56%**, exact full-manifest equivalence **PASS**
- `mesh-1` — 20/24 frames invalidated: predicted **incremental**, observed **incremental**, incremental saving **11.74%**, exact full-manifest equivalence **PASS**
- `mesh-2` — 24/24 frames invalidated: predicted **global**, observed **global**, incremental saving **-1.11%**, exact full-manifest equivalence **PASS**

Result: **3 / 3** 3D holdout routes correct on this host.

## Why this matters

The Execution Graph profile and FrameState profile have visibly different break-even behavior:

- Execution Graph signature propagation entered a noisy crossover around ~90–95% invalidation and global won at 100%.
- FrameState retained-frame routing remained clearly useful through ~96–98% frame invalidation and only became a practical tie at 100%.

Therefore a universal “rebuild when X% changes” threshold is already contradicted by the measured AXM workloads. The substrate should select a policy by **state contract**, not by one global rule.

## Policy registry

Wave 7 adds a small registry with two independent profiles:

- `execution-graph-signature-propagation` → Wave-6 linear component-cost calibration;
- `framestate-frame-manifest` → retained-work-fraction policy.

Unknown state contracts fail closed instead of silently borrowing another contract’s policy. The registry self-test passes **7 checks**.

## Truth boundary

- these remain single-host CPU-time measurements, not joule measurements;
- the 2D calibration workload is synthetic deterministic FrameState content, though it uses the real monolith renderer;
- the 3D holdout uses the real relay mesh but is still the same host/runtime;
- frame-window invalidation is exact for the controlled color-property mutations tested here; other mutation types may have broader dependencies;
- the FrameState structural rule is a candidate profile, not a universal FrameState theorem;
- policy misses and tie/noise regions remain visible;
- no claim of free compute or physical over-unity is made.

## Next gate

Give the policy registry a third state contract and begin recording **policy identity + route decision + actual regret** inside the generic Flowing Compute receipt. That lets the substrate accumulate evidence about which policy works where, without silently turning observations into canon.
