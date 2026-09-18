# Donor provenance

## Purpose

This repository is being extracted from the paused `mike-axiom-mir/axm-collaboration-platform` so compute-substrate research can continue independently.

The extraction rule is deliberately simple:

> **Preserve first. Repair, simplify, rewire, benchmark, or reinterpret later.**

Do not silently rewrite donor files during extraction merely because the platform contains historical dirt, old safety assumptions, stale dependencies, or architecture that may later change.

## Primary AXM donor

Repository:

`mike-axiom-mir/axm-collaboration-platform`

Initial donor paths:

- `shared/compute-substrate-lab/`
- `tools/compute-substrate-lab/`

The donor module describes its scope as research into how computation may be **represented, moved, combined, reclaimed, and physically implemented**, including mechanical, electromechanical, electronic, analog, optical, fluidic, biological, quantum, hybrid and e-waste candidates plus body/village/workshop/cloud architectures.

## Extraction state

The `donor/platform/` tree is intended to preserve copied platform material with its original relative structure underneath `shared/` and `tools/`.

During extraction:

- preserve text/content as copied from the donor;
- preserve original filenames and relative structure;
- do not pretend platform dependencies have become standalone dependencies;
- do not rewrite old authority/safety/governance language during the copy step;
- record unresolved external/platform dependencies instead of hiding them;
- keep later standalone AXM work outside the donor snapshot where practical.

A donor snapshot is provenance, not CANON and not proof that the extracted code currently runs standalone.

## Known donor dependencies

The current platform compute-substrate code references other platform modules, including at least:

- `shared/deterministic-research`
- `shared/hardware-research-registry`
- `tools/hardware-research-registry`

Those references are preserved during extraction. Standalone rewiring is a later task and must not be confused with the fidelity of the source copy.

## External research sources

External sources live under `sources/` and are not AXM-owned merely because they are cited here.

Current source:

- `sources/LINUXPDF.md` — `ading2210/linuxpdf`, GPL-3.0, cited as evidence that a PDF plus a compatible viewer can form an executable compute substrate.

## Current research extension

A new research question emerged after extraction began:

> Can a bounded setup computation construct a persistent software structure whose later interaction with available machine/environment resources creates a continuing useful computational flow whose cumulative useful output exceeds the computation spent constructing the structure?

This is a hypothesis to investigate, not a claim of free energy, free compute, or violated conservation laws.
