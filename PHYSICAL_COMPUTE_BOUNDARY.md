# Physical Compute Boundary

**Status:** research boundary for future compute/substrate design  
**Checked:** 2026-09-22

## Root rule

> **Software may invent architectures. It may not invent away physics.**

A future AXM system may search designs in software, simulate new architectures, generate circuits, design mechanical or optical structures, or combine multiple substrates.

Any design that is intended to become physical must eventually declare how its information is physically represented and what physical constraints apply.

This file exists because chip/IC physics is not merely an implementation detail. It is one strong example of a broader rule:

> information processing always has a physical realization.

## Fundamental versus implementation-specific constraints

Keep these categories separate.

### Fundamental physical constraints

These follow from the physical nature of information processing rather than from current CMOS design:

- thermodynamics;
- finite signal propagation;
- noise and statistical uncertainty;
- finite energy and material resources;
- causal ordering;
- entropy / information loss;
- measurement limits.

### Engineering/substrate constraints

These depend on the chosen implementation:

- wire resistance/capacitance;
- optical loss;
- mechanical backlash;
- friction;
- transistor leakage;
- memory endurance;
- fabrication tolerances;
- clock distribution;
- thermal packaging;
- material aging;
- corrosion;
- radiation sensitivity;
- biological variability.

A software design tool must not confuse a current engineering limitation with a universal law, or a universal law with a limitation unique to silicon.

## Constraint 1 — thermodynamics and information erasure

Landauer's principle connects logical irreversibility to physical dissipation. At temperature T, erasing one bit has a minimum thermodynamic cost associated with k_B T ln 2.

The practical lesson is **not** that every logic gate currently operates near that limit. Modern devices are generally far above fundamental minima.

The design lesson is:

- information destruction and state reset are physical operations;
- reversible transformations occupy a different design space from irreversible ones;
- energy models should track where information is discarded;
- "zero-cost compute" cannot be asserted without specifying what happens to state and entropy.

**Sources:**

- Nature Reviews Physics — 60 years of Landauer's principle: https://www.nature.com/articles/s42254-021-00400-8
- IBM — Rolf Landauer / physics of computing: https://www.ibm.com/history/rolf-landauer
- IBM Research — Fundamental Physical Limits of Computation: https://research.ibm.com/publications/fundamental-physical-limits-of-computation
- Nature experimental verification: https://www.nature.com/articles/nature10872

## Constraint 2 — location and communication are part of cost

A compute architecture is not only a set of operations. It is also a topology.

State must move between physical locations.

Depending on substrate, movement may cost:

- time;
- energy;
- bandwidth;
- area;
- routing resources;
- synchronization;
- reliability margin.

In modern integrated circuits, interconnect delay and power can become major performance limits rather than transistor switching alone.

**Design consequence:**

Future architecture search should score where state lives and how far/through what medium it must move.

**Source:**

- IEEE Technology Navigator — integrated circuit interconnections: https://technav.ieee.org/topic/integrated-circuit-interconnections/

## Constraint 3 — finite propagation and causal order

Signals do not arrive everywhere simultaneously.

Any physical architecture must handle propagation delay.

This matters whether the carrier is:

- electrical;
- optical;
- mechanical;
- acoustic;
- chemical;
- fluidic;
- biological.

A software simulator that assumes instantaneous global state can be useful as an abstraction, but a physical compiler must eventually introduce real timing/causal constraints.

## Constraint 4 — synchronization is constructed, not free

Digital systems often present a clean clocked abstraction. The physical signals underneath are continuous and can cross timing boundaries badly.

Metastability can occur when a signal is sampled near a transition. Synchronization machinery reduces the probability of failure; it does not make asynchronous physical reality disappear.

**Design consequence:**

A generated architecture must declare whether it is:

- synchronous;
- asynchronous;
- locally clocked;
- event-driven;
- continuous-time;
- hybrid.

**Source:**

- IEEE Design & Test — Metastability and Synchronizers: A Tutorial: https://ieeexplore.ieee.org/document/6028533/

## Constraint 5 — noise and error are architectural inputs

No physical state carrier is infinitely separated from every competing state.

Physical compute must deal with:

- thermal noise;
- manufacturing variation;
- wear;
- drift;
- interference;
- random faults;
- measurement error;
- environmental change.

Digital logic buys robustness by creating margins and restoration. Analog systems may trade exactness for efficiency or native operation. Biological/chemical systems may operate statistically.

The architecture should state its error model rather than assuming perfect bits.

## Constraint 6 — geometry is part of the machine

Layout can change behavior.

Examples:

- wire length changes delay/capacitance;
- gear dimensions determine ratios;
- optical path length changes phase/timing;
- fluid-channel geometry changes flow;
- spatial locality affects heat and communication.

Therefore a future "personal chip" or non-chip compute generator cannot stop at a graph of logical blocks.

It eventually needs a physical placement/routing/geometry stage.

## Constraint 7 — heat removal can become the bottleneck

Useful compute density is limited not only by whether operations can occur, but by whether generated heat can be removed while the substrate stays within valid operating conditions.

A design can be logically valid and physically useless because:

- local hotspots exceed limits;
- cooling consumes too much energy/volume;
- material properties shift with temperature;
- neighboring elements interfere thermally.

Thermal behavior belongs in architecture evaluation, not only final packaging.

## Constraint 8 — state retention has a mechanism

"Memory" is not one thing.

A physical state may be:

- volatile;
- nonvolatile;
- refresh-dependent;
- mechanically latched;
- magnetic;
- charge-based;
- phase-based;
- optical;
- chemical;
- biological.

For each state carrier ask:

- how is state written?
- how is it read?
- how is it retained?
- how is it erased?
- how many times can it change?
- what happens on power loss?
- what errors accumulate?

## Constraint 9 — fabrication, tolerance and yield matter

A theoretically valid architecture is not deployable if it requires impossible precision or has terrible yield.

Future substrate search must track:

- minimum feature/tolerance;
- alignment needs;
- material purity;
- manufacturing steps;
- calibration;
- testability;
- repair;
- expected variation;
- yield sensitivity.

This is especially important when software search discovers exotic geometries that are mathematically attractive but physically fragile.

## Constraint 10 — reversibility is a real design axis

Conventional Boolean/electronic architectures often discard information as they compute.

That is not a universal requirement.

Reversible computation demonstrates that logical transformations can be structured differently, with different thermodynamic implications.

This does **not** mean reversible machines are automatically practical or free. It means irreversibility should be an explicit architecture choice rather than an invisible assumption.

**Sources:**

- Nature: https://www.nature.com/articles/335779a0
- IBM Research: https://research.ibm.com/publications/the-thermodynamics-of-computation-a-review

## Constraint 11 — substrate and algorithm can be co-designed

Historical devices already show this.

Examples:

- logarithmic scales make multiplication a geometric addition problem;
- gear ratios make cyclic astronomical relationships physical;
- punched media externalizes control;
- modern accelerators make selected mathematical operations native.

Future AXM compute design should therefore search both directions:

~~~text
algorithm -> find substrate that makes it cheap/native
substrate -> find algorithms that exploit its natural dynamics
~~~

Do not assume the architecture must first imitate a CPU and only then run software.

## Minimal physical contract for generated compute

Any design proposed for eventual physical realization should be able to fill this structure before promotion:

~~~yaml
physical_compute_contract:
  information_carrier: unknown
  state_encoding: unknown
  transform_mechanism: unknown
  memory_mechanism: unknown

  topology:
    geometry: unknown
    communication_medium: unknown
    maximum_relevant_distance: unknown

  timing:
    model: unknown
    propagation_model: unknown
    synchronization_model: unknown

  energy:
    source: unknown
    dissipation_model: unknown
    reset_erasure_model: unknown
    thermal_path: unknown

  reliability:
    noise_model: unknown
    error_model: unknown
    correction_or_margin: unknown
    aging_model: unknown

  fabrication:
    process: unknown
    critical_tolerances: unknown
    calibration: unknown
    testability: unknown
    repairability: unknown

  lifecycle:
    power_loss_behavior: unknown
    state_retention: unknown
    endurance: unknown
    recovery: unknown

  evidence:
    simulated: false
    physically_tested: false
    assumptions: []
    unresolved_constraints: []
~~~

Unknown is valid. Hidden assumptions are not.

## Software-side rule

The software layer may temporarily abstract these constraints away while exploring ideas.

Before a candidate is promoted from "interesting computation" to "physical compute design," the system should require a physicalization pass:

~~~text
logical candidate
-> identify state carrier
-> identify physical transformations
-> add geometry/topology
-> add timing/propagation
-> add energy/thermal model
-> add noise/error model
-> add fabrication constraints
-> simulate
-> prototype
-> measure
-> compare simulation with reality
-> revise
~~~

A failed physicalization is useful evidence. Preserve why it failed.

## Why chip physics still belongs in this repo

Silicon is not the definition of computation, but semiconductor design is one of the best-developed examples of repeatedly translating abstract logic into physical geometry under hard constraints.

Useful lessons to extract from IC design include:

- standard cells / reusable primitives;
- placement and routing;
- timing closure;
- power distribution;
- clocking;
- design-rule checking;
- parasitic extraction;
- thermal analysis;
- verification before fabrication;
- post-silicon measurement and iteration.

Those are transferable workflow patterns even when a future substrate is not silicon.

## Connection to the Compute Lineage Atlas

The history file and this physics boundary answer different questions:

- COMPUTE_LINEAGE.md asks: **what computational ideas existed before modern chips?**
- PHYSICAL_COMPUTE_BOUNDARY.md asks: **what must any future physical computation obey or explicitly model?**

Together they form the research base for later work on personal compute structures, custom chips, hybrid substrates and machine-designed compute.

## Truth boundary

This file is a research contract, not a claim that all listed engineering constraints are fundamental laws.

The system must preserve the difference between:

- fundamental physical limits;
- current technology limits;
- substrate-specific constraints;
- design conventions;
- unresolved assumptions.

That distinction is essential if AXM later searches beyond silicon instead of accidentally rebuilding silicon's assumptions in a different material.
