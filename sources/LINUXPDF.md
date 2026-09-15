# LinuxPDF — external compute-substrate source

Status: **EXTERNAL RESEARCH SOURCE — NOT VENDORED**

## Primary source

- Project: `ading2210/linuxpdf`
- Repository: https://github.com/ading2210/linuxpdf
- Author/maintainer credit: ading2210 / Allen
- Upstream license: GNU GPL v3
- First published: 2025

## Contemporary coverage

- Hackaday, 2025-02-10: `Nice PDF, But Can It Run Linux? Yikes!`
  - https://hackaday.com/2025/02/10/nice-pdf-but-can-it-run-linux-yikes/
- OSNews, 2025-02-03: `Run Linux inside a PDF file via a RISC-V emulator`
  - https://www.osnews.com/story/141668/run-linux-inside-a-pdf-file-via-a-risc-v-emulator/

The upstream repository is the primary technical source. Articles are secondary context only.

## What the project demonstrates

LinuxPDF packages a Linux environment into a PDF by using a compatible PDF viewer as an execution substrate:

```text
host machine
  -> browser / PDF viewer
    -> PDF JavaScript runtime
      -> asm.js-compiled TinyEMU
        -> emulated RISC-V machine
          -> Linux environment
```

The upstream explanation states that PDF JavaScript can perform general computation with limited I/O. A modified TinyEMU RISC-V emulator is compiled from C using an older Emscripten target (`asm.js`) rather than WebAssembly, then executed by the PDF JavaScript environment.

Input/output is also expressed through PDF primitives: text fields are used for terminal display rows, while buttons and a text field provide keyboard input.

The upstream README reports roughly 30–60 seconds for Linux kernel boot in the PDF and describes the emulator as more than 100x slower than normal execution because the relevant PDF-engine V8 environment has JIT disabled.

## Why AXM Compute Substrate keeps this source

This project is evidence for a useful substrate distinction:

> A file format can carry executable computational structure while a separate compatible host/viewer supplies the physical compute and runtime.

The PDF does **not** create physical CPU cycles or energy. The important observation is architectural: an object normally treated as a passive document can become a portable computational container when interpreted by a capable runtime.

That makes LinuxPDF relevant to research on:

- software as computational infrastructure rather than one-shot execution;
- portable compute-bearing artifacts;
- runtime hidden behind a capability or document boundary;
- small persistent structures that unfold larger computation on compatible hosts;
- compute movement between representation, container, runtime, emulator and machine substrate;
- the distinction between stored computational potential and physical compute supplied at execution time.

## Relation to the current flowing-compute hypothesis

Current research question, **not an established result**:

> Can a bounded amount of setup computation construct a persistent software structure that subsequently harvests, redirects, composes, or activates continuing computational resources so that cumulative useful computational flow exceeds the computation spent to construct the structure?

LinuxPDF does not prove that hypothesis. It is a concrete example showing that the place where computational structure is stored and the place where physical computation is supplied can be radically different.

## Provenance / reuse boundary

No LinuxPDF source code is copied into this repository by this record. This file cites and summarizes the external project. If source is ever vendored or modified later, preserve its GPL-3.0 obligations and upstream attribution separately from AXM's own Apache-2.0 material.
