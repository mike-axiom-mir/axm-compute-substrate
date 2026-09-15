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

## Flowing compute research

The first standalone research branch asks whether bounded setup computation can construct a persistent software structure that later harvests, redirects, composes, or activates continuing machine/environment resources so useful computational output accumulates beyond the original construction cost.

Current surfaces:

- `research/FLOWING_COMPUTE_HYPOTHESIS.md` — hypothesis, accounting boundaries, candidate mechanisms, and disproof cases;
- `tools/flowing-compute-accounting.js` — dependency-free deterministic accounting surface;
- `tools/flowing-compute-selftest.js` — refusal and break-even checks;
- `examples/flowing-compute-amortization.example.json` — synthetic fixture;
- `evidence/FLOWING_COMPUTE_ACCOUNTING_SELFTEST.md` — bounded 20/20 self-test receipt.

The accounting deliberately separates:

- setup/construction cost;
- continuing maintenance cost;
- continuing external/host compute input;
- reclaimed/idle capacity as a subset of real external input;
- useful output under a declared comparable unit;
- equivalent repeat-from-zero baseline cost.

A system may amortize its setup cost or beat a repeated baseline without producing compute from nothing.

## New research question

A current hypothesis to investigate is whether software can use a bounded setup computation to create a persistent computational structure that later harvests, redirects, composes, or activates continuing machine/environment resources, such that cumulative useful computational flow exceeds the computation spent constructing that structure.

This is **not** a claim of free energy or compute from nothing. The research distinction is between:

- stored computational structure;
- the runtime/substrate that supplies physical computation;
- setup cost;
- continuing resource input;
- cumulative useful computational output.

LinuxPDF is relevant because it demonstrates that computational structure can be stored in a surprising carrier while execution is supplied later by a separate compatible runtime.

## Current truth boundary

The donor snapshot is provenance, not a claim that it already runs standalone in this repository. Some copied files still reference collaboration-platform modules such as deterministic research and hardware-research components. Standalone rewiring, real workload benchmarks, and governance repair come **after** source preservation.

The Flowing Compute accounting test currently proves only that the experimental accounting model behaves as declared on a synthetic fixture. It does not prove the world-level hypothesis.
