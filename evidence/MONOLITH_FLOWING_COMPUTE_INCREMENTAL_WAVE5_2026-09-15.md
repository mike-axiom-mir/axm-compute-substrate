# Flowing Compute Wave 5 — Incremental Change / Dependency Closure

Date: 2026-09-15  
Status: `EXPERIMENTAL SINGLE-HOST RUNTIME EVIDENCE`

Source body: uploaded `AXM_Connected_Monolith_v0.4.30-WALMI-NATIVE-WIRING.zip` copy.

## Question

After useful state has already been retained, can a small source change update only the state that is actually downstream of that change, while producing exactly the same final derived state as rebuilding globally?

This wave tests the step from **reuse previous work** to **only recompute what became new**.

## Source graph

The real monolith `EXECUTION_GRAPH.json` used here is about 1.28 MB and contains 3,618 wired candidate edges. The active edge graph contains 160 endpoint nodes. Its SCC-condensed dependency graph contains 127 components.

All mutations in this wave are controlled temporary probe mutations on copies. They are not canonical changes to the monolith.

## A — topology-removal boundary control

A retained downstream-reachability state was built for the 160 active endpoint nodes. One existing real edge was then disabled per independent case.

Two strategies were compared after the mutation:

- **global rebuild:** recompute reachability for all 160 nodes;
- **incremental:** recompute only the changed edge source plus nodes that could reach that source before the mutation.

31 alternating-order trials were used per selected case. Exact reachability state equivalence was required.

### Small affected closure

Two cases affected only **1 / 160 nodes**.

- CPU saved: **98.69%** and **98.79%**.

### Near-global affected closure

Two cases conservatively required recomputation of **131 / 160 nodes**.

- CPU change: **-2.35%** and **-0.90%** versus full rebuild.

So the incremental path was slightly slower once the affected closure approached the whole graph.

This is an important negative/control result: retained-state machinery is not automatically beneficial. A substrate needs a break-even policy and should be allowed to choose a rebuild when change is broad.

## B — semantic state propagation with unchanged topology

A second experiment collapsed the real execution graph into 127 SCC components and created an experimental content signature for each component. Each signature depends on:

1. that component's local outgoing edge-contract payload; and
2. predecessor component signatures.

A one-field semantic metadata change was applied to one real execution edge per case. Topology was unchanged. Eight source components were selected whose downstream affected closures covered:

`22, 28, 29, 30, 31, 33, 41, 42` of `127` components.

15 alternating-order trials were run per case.

Three strategies were compared:

1. **full rebuild** — re-hash every local edge-contract payload and propagate every component signature;
2. **global propagation control** — retain unchanged local hashes, but recompute propagated signatures for every component;
3. **incremental closure** — re-hash only the changed local payload and propagate only through the affected downstream closure.

Every incremental result was byte-identical to the global/full result.

### Isolated closure benefit

Compared with the stronger **global propagation control**, where most retained work was already shared by both sides:

- CPU saved range: **17.33%–58.44%**;
- median CPU saved: **~39.0%**;
- median useful-yield multiplier: **~1.64×**;
- all 8 cases favored incremental propagation.

This is the cleaner evidence for dependency-closure selection itself.

### Full rebuild comparison

Compared with rebuilding all local hashes and all propagated signatures:

- CPU saved range: **70.41%–95.03%**;
- median CPU saved: **~92.89%**;
- median yield multiplier: **~14.06×**.

This larger number includes two effects and must not be described as closure selection alone:

- reuse of unchanged local computational structure;
- selective propagation through only the changed dependency closure.

## C — content-addressed generation transition

Representative mutation: `edge-02387`, affecting **31 / 127** components.

The retained graph state was wrapped in the existing content-addressed retained-state envelope contract.

Observed:

- state payload: **33,223 bytes**;
- envelope: **33,683 bytes**;
- the old envelope validated against the old source generation;
- after source mutation, the old envelope was rejected as stale;
- incremental update produced exactly the same state as a full rebuild;
- a new envelope tied to the new source generation validated successfully.

This is the first bounded probe in this research where retained state was not merely reused; it crossed a source-generation change while preserving explicit provenance and equivalence.

## Current interpretation

The useful result is not that incremental computation exists in computer science; that is established territory. The useful AXM result is that the monolith's real graph/state bodies can be instrumented under one evidence discipline and can expose a measurable policy boundary:

> retain and update locally when the affected closure is small enough; rebuild when the closure becomes broad enough that incremental bookkeeping no longer pays.

That policy is directly relevant to later node/cartridge work, but this wave does not claim the Magic Box architecture is solved.

## Truth boundary

- CPU process time is not direct energy measurement.
- This is one host and one monolith snapshot.
- The propagated signature state is experimental research state, not an existing production AXM runtime.
- Controlled probe mutations are not canonical monolith edits.
- Exact equivalence is proven only for the state contracts measured here.
- The ~92.9% full-rebuild comparison includes reuse of unchanged local hashes; the ~39.0% median versus global propagation is the cleaner closure-selection result.
- Near-global mutation showed incremental processing can lose.
- No free-compute, over-unity, or universal performance claim is made.
