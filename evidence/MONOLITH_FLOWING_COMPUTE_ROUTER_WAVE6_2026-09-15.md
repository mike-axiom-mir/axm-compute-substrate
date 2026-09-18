# Flowing Compute Wave 6 — Pre-Execution Update Router

Date: 2026-09-15  
Status: `EXPERIMENTAL SINGLE-HOST RUNTIME EVIDENCE`

Source: uploaded `AXM_Connected_Monolith_v0.4.30-WALMI-NATIVE-WIRING.zip` copy.

## Question

Can the retained-state substrate decide **before doing the expensive update** whether a source-generation change should use selective incremental propagation or a global rebuild, based only on structural information already available from retained dependency state?

Wave 6 turns Wave 5's observed boundary into a measured routing policy.

## Same-state-contract control

This wave deliberately stays inside one state contract: propagated signatures over the real monolith `EXECUTION_GRAPH.json` SCC-condensed dependency graph.

Both routes receive equivalent already-resident local/signature state. Both re-hash the changed local source components. The only intended routing difference is:

- **incremental** — propagate through the affected downstream closure only;
- **global** — overwrite/recompute every component signature.

Every case must finish with exactly the same derived state.

## Broad invalidation surface

Controlled semantic mutations were combined over real source components so the affected union covered:

`22, 32, 45, 58, 70, 82, 94, 105, 114, 121, 127` of `127` components.

Each point used 9 alternating-order timing trials with 30 repeated updates per timing sample. Benchmark reset/state-copy work was prepared outside the measured update window for both routes.

## Independent measured run 1

Incremental CPU saving versus global propagation:

- 22/127: **54.89%**
- 32/127: **38.75%**
- 45/127: **29.55%**
- 58/127: **18.04%**
- 70/127: **14.28%**
- 82/127: **9.32%**
- 94/127: **5.60%**
- 105/127: **1.64%**
- 114/127: **1.32%**
- 121/127: **-0.50%** — global won
- 127/127: **-0.48%** — global won

## Independent measured run 2

- 22/127: **56.93%**
- 32/127: **37.74%**
- 45/127: **28.68%**
- 58/127: **18.87%**
- 70/127: **11.80%**
- 82/127: **8.49%**
- 94/127: **4.88%**
- 105/127: **2.62%**
- 114/127: **1.60%**
- 121/127: **1.40%** — incremental won
- 127/127: **-1.23%** — global won

The 121/127 point changed winner between independent runs. That is treated as a real noisy break-even region, not averaged away into a false crisp threshold.

## Router calibration

A deliberately small structural cost model uses only information available before execution:

- affected component count;
- number of mutated source components.

The calibration alternates increasing affected-size points into train and holdout sets. The coefficients from two independent measurement runs are averaged into the candidate calibration.

The runtime decision remains simple: choose the route with lower predicted CPU cost. An empirical **1.0% uncertainty band** labels near-crossover decisions as uncertain; it does not falsify certainty by changing the predicted winner.

Across the two independent measurement runs:

- observed route decisions: **22**;
- correct predicted winner: **21 / 22 (95.45%)** including calibration points;
- held-out decisions: **10**;
- held-out correct: **9 / 10 (90%)**;
- maximum wrong-route regret: **1.42%**;
- mean regret across all observed decisions: **0.065%**.

The only held-out miss was the 121/127 crossover point: one run favored global by ~0.5%, the other favored incremental by ~1.4%.

This is more useful than claiming perfect accuracy: the policy found the broad direction and bounded its mistake inside the empirically noisy crossover region.

## Router overhead

Using retained closure metadata plus the calibrated cost model, 10,000 repeated route decisions were benchmarked on this host.

Median decision cost, including unioning the precomputed source-component closure sets and evaluating the model, was about **7.4 microseconds CPU per decision**.

That overhead is small relative to the measured update costs in this experiment (~0.4 ms to ~4 ms), but it is not zero and remains part of future end-to-end accounting.

## Important control repair

An earlier broad-surface pass still showed a ~2% incremental advantage at 127/127. Inspection found that the global path was allocating a fresh signature dictionary while the incremental path reused an existing one. That was a retained-allocation advantage, not dependency-closure routing evidence.

The final control gives **both** strategies equivalent preallocated state bodies. After that correction, global rebuild won the 127/127 case in both independent runs.

This repair is preserved because the experiment must distinguish the mechanisms rather than collect the largest possible percentage.

## Interpretation

For this state contract, the machine can estimate the size of invalidation before performing propagation and use that estimate to route computation.

The current observed shape is:

- local / medium invalidation → incremental clearly wins;
- broad invalidation → advantage shrinks;
- near-global invalidation → winner enters measurement noise;
- complete invalidation → global rebuild wins slightly.

So the next substrate primitive is not "cache everything." It is:

> preserve useful state, estimate the invalidation closure, predict route cost, execute the cheaper route, and record whether the prediction was right.

## Truth boundary

- CPU process time is not direct energy measurement.
- This remains one host and one monolith snapshot.
- The mutation sets are controlled research mutations, not canonical product edits.
- The policy is calibrated for this state contract; it is not a universal threshold for all software.
- Held-out cases come from the same source graph, not an independent machine or repository.
- The policy can be wrong; its observed miss and regret are retained.
- Output equivalence was required for every measured incremental/global case.
- No claim of free compute, physical over-unity, or universal performance gain is made.

## Next gate

Run the same routing/receipt discipline against another AXM state contract and test whether the substrate can maintain **separate local calibration profiles** rather than forcing one global heuristic across unlike workloads.
