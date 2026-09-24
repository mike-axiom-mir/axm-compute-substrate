# Flowing Compute Wave 20 — Resolved Overlay Head Index

Date: 2026-09-15  
Status: `EXPERIMENTAL SINGLE-HOST RUNTIME EVIDENCE`

## Question

Can AXM preserve the full append-only overlay history for provenance/rollback while maintaining a small derived **current-state head index** so runtime wake does not replay the entire history?

The head is not a replacement for history. It contains only the newest changed digest values over the immutable base plus content-addressed history-tip/root and carried proven target identity.

## Head size

Built over the Wave-17/19 64-generation chain:

- depth 1: **3,494 bytes**;
- depth 6: **10,671 bytes**;
- depth 24: **10,676 bytes**;
- depth 64: **10,673 bytes**.

The current-state override body saturates while append-only history continues to grow. This separates **history size** from **current working-state delta size**.

## In-process proven wake

31-trial medians. All three modes reuse previously earned immutable proof:

- `compact`: one full packed checkpoint + checkpoint proof;
- `replay`: base + ordered proven overlay replay;
- `head`: base + resolved head index, no history replay.

| depth | proven compact | proven replay | proven head | head vs compact | head saved vs replay |
|---:|---:|---:|---:|---:|---:|
| 1 | 1.745 ms | 1.837 ms | 1.819 ms | +4.3% | 1.0% |
| 6 | 1.724 ms | 2.168 ms | 1.928 ms | +11.8% | 11.1% |
| 24 | 1.802 ms | 2.627 ms | 1.994 ms | +10.6% | 24.1% |
| 64 | 1.935 ms | 3.991 ms | 2.100 ms | +8.5% | 47.4% |

At depth 64, the ~10.7 KB head wakes within ~8.5% of a full compact snapshot while preserving the complete history separately and avoiding replay.

## Fresh-process control

A first control accidentally minted a new compact-checkpoint proof on every restart, unfairly penalizing compact. That run was discarded.

After correcting the control so all three routes reuse existing proof:

### depth 6
- proven compact: **2.449 ms CPU**;
- proven replay: **2.989 ms**;
- proven head: **2.475 ms**;
- head is ~**1.1%** slower than compact and ~**17.2%** faster than replay.

### depth 64
- proven compact: **2.512 ms CPU**;
- proven replay: **5.562 ms**;
- proven head: **2.533 ms**;
- head is ~**0.9%** slower than compact and ~**54.5%** faster than replay.

The advantage therefore survives process death.

## Head maintenance cost

31-trial update medians, using the next proven overlay + proof-manifest generation:

- depth 2 head update: **0.380 ms**;
- depth 3: **0.418 ms**;
- depth 4: **0.409 ms**;
- depth 5: **0.407 ms**;
- depth 6: **0.408 ms**;
- depth 24: **0.479 ms**;
- depth 64: **0.533 ms**.

Combined with Wave-17 overlay emit (~0.38 ms) and Wave-19 semantic attestation (~0.87 ms), a proof-carrying overlay + maintained head is roughly **1.65–1.78 ms CPU/generation** in this prototype, still below the ~3.09 ms full packed-snapshot emit.

The head rewrites ~10.7 KB once saturated, while a full packed snapshot rewrites ~261.6 KB. Full history remains available through the overlay chain.

## Reusable primitive

- `tools/AXM_FLOWING_COMPUTE_OVERLAY_HEAD.py`

The binary head carries:

- immutable base artifact/source/semantic identity;
- overlay count and current chain tip;
- rolling history-chain root;
- proof-manifest identity used when head was created/updated;
- final source + semantic identity;
- newest edge/local/signature override values only.

Fast wake validates the base proof and head artifact integrity but deliberately does **not** replay/re-audit omitted history. Full audit and self-verification remain separate modes.

## Truth boundary

- this is a derived runtime index, not deletion or replacement of append-only history;
- fast head wake reuses creation-time semantic evidence and does not recompute the full effective-state proof;
- SHA/content addressing supplies integrity but not external authentication;
- head creation/update depends on the proof-manifest path having already admitted verified overlays;
- full history audit can still detect issues not rediscovered by fast wake;
- one host / one state contract;
- CPU time is not joules;
- no claim of compute/energy from nothing.

## Interpretation

Wave 20 produces a useful three-layer shape:

```text
immutable base checkpoint
        +
append-only overlay history   <- provenance / rollback / audit
        +
small resolved head index     <- current runtime state
```

The historical chain can grow without forcing current runtime wake to scale linearly with history depth.

## Next gate

Separate the head's **current-state overrides** from its **history/proof pointer** so unchanged override blocks can themselves be content-addressed/shared between head generations. Measure whether head updates can fall below the current ~0.4–0.5 ms without sacrificing exact history linkage or fast wake.
