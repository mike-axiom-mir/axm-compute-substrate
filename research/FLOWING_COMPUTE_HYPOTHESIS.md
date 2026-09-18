# Flowing Compute Hypothesis

Status: **EXPERIMENTAL RESEARCH QUESTION**

## Origin

The motivating intuition is not that software creates physical energy or CPU cycles from nothing.

It is that a bounded amount of computation may construct a persistent software structure which then continues to **harvest, redirect, compose, schedule, activate, or transform** computational resources supplied by a compatible environment.

The renewable-energy analogy is useful only at the pattern level:

```text
bounded construction cost
        ↓
persistent structure
        ↓
continuing environmental input
        ↓
useful output accumulates over time
```

For software, the continuing input may be CPU/GPU time, idle capacity, memory bandwidth, networked machines, event streams, device runtimes, human actions, or another declared substrate.

## Primary hypothesis

> Can bounded setup computation construct a persistent software structure whose cumulative useful computational output eventually exceeds the computation spent constructing that structure, while every continuing physical/runtime input remains explicitly accounted for?

This is called the **setup-amortization hypothesis** in the first experiments.

It is deliberately weaker than either of these claims:

- that software produces physical compute without continuing resource input;
- that cumulative useful output exceeds *all* physical/runtime compute consumed.

Those stronger claims are not assumed.

## Why the distinction matters

A solar panel can return more lifetime energy than the energy spent manufacturing it because sunlight continues to enter the system.

Likewise, a software structure can cost `S` compute units to construct and later coordinate much more than `S` compute units of useful work **because the host environment continues supplying compute**.

The software is therefore closer to a collector, scheduler, converter, reusable machine, or infrastructure layer than to an energy source.

## Accounting model v0.1

Each experiment must name one comparable unit when it wants to compare setup cost and useful output numerically.

Example units might be:

- normalized deterministic operations;
- CPU instruction-equivalents under one fixed benchmark;
- milliseconds of one pinned workload on one pinned host;
- joules measured by one pinned device/benchmark;
- another explicitly defined experimental unit.

Do not compare quantities across incompatible units.

For one run:

- `S` = setup/construction compute;
- `M(t)` = maintenance/coordination compute consumed by the persistent structure at time or step `t`;
- `E(t)` = external/host compute entering the system at step `t`;
- `U(t)` = measured useful computational output at step `t` under the declared benchmark;
- `R(t)` = resource that was available but would otherwise have remained unused, when that can be evidenced separately.

Derived quantities:

```text
cumulative useful output      UΣ = Σ U(t)
cumulative maintenance        MΣ = Σ M(t)
cumulative external input     EΣ = Σ E(t)
construction-amortization     A  = UΣ / S
all-input efficiency          η  = UΣ / (S + MΣ + EΣ)
```

`A > 1` means only that accumulated useful output exceeded setup cost.

It does **not** mean the system created compute from nothing.

`η > 1` would require especially careful scrutiny because measured useful-output units may encode reuse, avoided baseline work, parallelism, or an invalid apples-to-oranges comparison. It must never be promoted automatically into a physical over-unity claim.

## Break-even events

The first model tracks several different break-even points instead of collapsing them:

1. **Setup break-even** — cumulative useful output exceeds setup cost.
2. **Setup + maintenance break-even** — useful output exceeds construction plus internal upkeep.
3. **Baseline break-even** — cumulative cost of the persistent approach becomes lower than a declared repeat-from-zero baseline for equivalent outputs.
4. **Physical/resource break-even** — only meaningful when energy or another physical unit is directly measured and comparable.

A run can pass one and fail another.

## Candidate mechanisms

The project should investigate mechanisms independently rather than treating them as one magic effect.

### Persistent state

Avoid recomputing information that the system can retain truthfully.

### Reusable compiled structure

Pay an expensive translation/compilation/indexing cost once and invoke the resulting structure many times.

### Dormant activation

Keep capabilities represented but inactive; materialize only the dependency closure required by current state.

### Idle-resource harvesting

Use explicitly available capacity that would otherwise remain unused. Account for its real energy and hardware cost even when its opportunity cost is low.

### Event-driven activation

Remain cheap while idle, then perform useful work only when external state changes.

### Parallel substrate activation

A small coordinator may configure many independent workers. Their computation remains external input, not generated compute.

### State/recipe composition

Represent many behaviors as compositions of shared primitives instead of separately executing or storing duplicated machinery.

### Artifactized computation

A computed artifact can carry reusable executable or state structure forward so later compatible runtimes do not need to reconstruct the same structure from scratch.

LinuxPDF is one conceptual example of a carrier whose stored structure causes a much larger machine state to unfold when a separate runtime supplies execution.

## Failure / disproof cases

The research should record negative results when:

- setup cost never amortizes;
- maintenance cost grows faster than useful output;
- indirection costs more than direct execution;
- claimed reuse merely shifts computation elsewhere;
- output and input units are not actually comparable;
- idle-resource claims ignore real electricity or hardware wear;
- the persistent structure becomes stale and expensive to repair;
- storage/memory costs erase compute savings;
- a benchmark counts cached answers as new computation without equivalent-task justification;
- output quality falls while cost appears lower.

## Initial goal

The first goal is not to prove a new law of computation.

It is to build a deterministic accounting surface capable of saying, for a bounded experiment:

- what was paid once;
- what continues to be paid;
- where continuing compute comes from;
- what useful output was actually measured;
- when each break-even boundary was crossed;
- which claims remain unknown.

Only after several real workloads can we decide whether "flowing compute" describes a useful reusable systems pattern or only an analogy.
