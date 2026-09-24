# Real Monolith FrameState Flowing-Compute Probe — 2026-09-15

Status: `EXPERIMENTAL RUNTIME EVIDENCE`

Subject: uploaded `AXM_Connected_Monolith_v0.4.30-WALMI-NATIVE-WIRING.zip`

## Question

Does preserving reusable runtime state inside a real AXM deterministic workload reduce the physical/runtime compute needed to produce the same outputs compared with rebuilding that state for every step?

This is a bounded experiment on one host. It is not proof of free compute, physical over-unity, universal scaling, or a general AXM performance claim.

## Workload A — 3D relay mesh

Renderer: monolith FrameState deterministic software renderer.

Mesh: `examples/blackline-relay-3d-kit-v0.3/assets/relay_offline/source/relay_offline.obj`

Observed mesh identity in the uploaded monolith copy:

- bytes: `63,280`
- vertices: `1,224`
- faces: `1,216`
- SHA-256: `301839b38bf9191b3bacacec638db2f8323c768cec56109a7f3bd69cdf8c37ba`

Render contract:

- 18 frames
- 128 × 96 output
- same project state and renderer
- frame output compared by SHA-256
- all cold and flowing outputs matched exactly

### Cold path

For every frame:

1. create a new `MediaCache`;
2. rebuild the media manifest/state;
3. parse/load mesh state again when rendering;
4. render one frame.

### Flowing/persistent path

1. create one `MediaCache` once;
2. preserve parsed mesh/media state;
3. render all 18 frames through the same retained state.

### Independent measured run 1

Seven alternating-order trials.

Median CPU:

- cold: `686,222,438 ns`
- flowing: `573,007,636 ns`
- saved: `113,214,802 ns`
- CPU reduction: **16.4983%**
- equivalent useful-yield multiplier: **1.19758×**

Per-trial CPU reductions were all positive, ranging from about **8.19% to 18.43%**.

### Independent measured run 2

The complete seven-trial probe was run again after the first report had been preserved.

Median CPU:

- cold: `677,001,234 ns`
- flowing: `568,638,380 ns`
- saved: `108,362,854 ns`
- CPU reduction: **16.0063%**
- equivalent useful-yield multiplier: **1.19057×**

Per-trial CPU reductions were all positive, ranging from about **14.25% to 17.44%**.

## Control workload B — procedural cube

A second FrameState workload rendered a procedural 3D cube with no external image or mesh payload requiring repeat parsing.

Measured contract:

- 12 frames
- 128 × 96 output
- five alternating-order trials
- identical output hashes

Median CPU:

- cold: `751,120,100 ns`
- flowing: `746,203,235 ns`
- CPU reduction: **0.6546%**
- equivalent useful-yield multiplier: **1.00659×**

This small control result matters because it suggests the ~16% mesh result is not merely a generic advantage caused by placing one Python loop around another. The larger effect appears tied to reusable state that the cold path repeatedly reconstructs, especially media initialization, manifest/digest work, and mesh parsing/loading.

## What this establishes

For this specific monolith workload on this specific host:

> preserving reusable deterministic runtime state produced identical rendered outputs with materially less measured CPU time than reconstructing the same state for every frame.

The effect reproduced in two independent seven-trial mesh runs at approximately 16% median CPU reduction.

This clears a useful research threshold for the Flowing Compute hypothesis: a real AXM workload can show a positive same-output compute-yield advantage from persistent structure/state.

## What this does not establish

This does **not** establish that:

- software creates CPU cycles or energy from nothing;
- total physical output exceeds all physical input;
- the observed ~16% transfers to unrelated workloads;
- state retention always helps;
- caching alone is the intended final Flowing Compute mechanism;
- the effect will survive different machines, runtimes, meshes, resolutions, or longer horizons;
- the current monolith is already an optimized flowing-compute substrate.

## Why this is useful

The result gives the research a real measurable foothold instead of only a conceptual analogy.

The next experiments should decompose the gain into separate mechanisms:

1. media-manifest/digest reuse;
2. mesh parse reuse;
3. decoded media reuse;
4. dependency/state graph reuse;
5. intermediate-result reuse;
6. incremental state transitions;
7. dormant-node activation versus full-body activation;
8. multi-process and multi-machine equivalents.

Each experiment should preserve identical-output or equivalent-output evidence and measure CPU, wall time, memory, storage, and continuing external resource input separately.

## Truth boundary

- exact pixel equality was checked by per-frame SHA-256 comparison;
- CPU timing used process CPU time in one execution environment;
- wall time was also recorded and tracked the same direction;
- the probe is runtime evidence, not a general scientific conclusion;
- independent reproduction on another host is still required.
