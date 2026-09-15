# axm-compute-substrate

Standalone home for AXM compute-substrate research.

The first step is **extraction, not cleanup**: preserve the existing Compute Substrate Lab from the paused `mike-axiom-mir/axm-collaboration-platform` before changing its assumptions, dependencies, governance language, or safety structure.

## Donor snapshot

Exact copied platform material lives under:

- `donor/platform/shared/compute-substrate-lab/`
- `donor/platform/tools/compute-substrate-lab/`

See `DONOR_PROVENANCE.md` for source identity, boundaries, and known unresolved platform dependencies.

The extracted lab studies how computation may be represented, moved, combined, reclaimed, and physically implemented across mechanical, electromechanical, electronic, analog, optical, fluidic, biological, quantum, hybrid, e-waste, body, village, workshop, and cloud candidates.

## External sources

- `sources/LINUXPDF.md` — source-grounded note on `ading2210/linuxpdf`, where PDF JavaScript hosts an asm.js-compiled TinyEMU RISC-V emulator which boots Linux. The upstream code is GPL-3.0 and is cited here rather than vendored.

## Flowing Compute hypothesis

A current hypothesis to investigate is whether software can use a bounded setup computation to create a persistent computational structure that later harvests, redirects, composes, or activates continuing machine/environment resources, such that cumulative useful computational flow exceeds the computation spent constructing that structure.

This is **not** a claim of free energy or compute from nothing. The research distinction is between:

- stored computational structure;
- the runtime/substrate that supplies physical computation;
- setup cost;
- continuing resource input;
- cumulative useful computational output.

LinuxPDF is relevant because it demonstrates that computational structure can be stored in a surprising carrier while execution is supplied later by a separate compatible runtime.

## First measured AXM result

The first real runtime probe used FrameState code already present inside the uploaded `AXM_Connected_Monolith_v0.4.30-WALMI-NATIVE-WIRING` body.

A deterministic 18-frame 3D relay-mesh render was executed in two modes:

- **cold/rebuild:** reconstruct media/cache/mesh state for every frame;
- **flowing/persistent:** initialize once and retain the reusable state across all frames.

All output frame hashes matched exactly.

Two independent seven-trial runs measured approximately **16.50%** and **16.01%** median CPU reduction for the persistent path, corresponding to about **1.198×** and **1.191×** equivalent useful-yield multipliers.

A procedural-cube control with little reusable external state measured only about **0.65%** median CPU reduction, providing an initial indication that the larger mesh result is tied to real reusable state rather than a generic loop artifact.

See `evidence/MONOLITH_FRAMESTATE_FLOWING_COMPUTE_2026-09-15.md` for the bounded evidence and truth limits.

## Current truth boundary

The donor snapshot is provenance, not a claim that it already runs standalone in this repository. Some copied files still reference collaboration-platform modules such as deterministic research and hardware-research components.

The flowing-compute measurements are runtime evidence for one host and two FrameState workload shapes, not a claim of general scaling or physical over-unity. Standalone rewiring, broader benchmarks, mechanism isolation, and governance repair remain future work.
