# Third independent consumer — Universal Creation

Date: 2026-09-20  
Status: **CROSS-REPOSITORY EXPERIMENTAL EVIDENCE / NON-CANON**

Neutral Compute v0.1 now has a third materially different implementation/consumer:

1. Neutral Compute reference runtime — JavaScript.
2. MorphTile native Flow runtime — JavaScript but independently shaped around MorphTile cold/sleep matter.
3. Universal Creation native runtime — **Python**, integrated with real UC shape-recipe/material state.

## UC source identity

Repository: `mike-axiom-mir/axm-universal-creation`  
PR: **#223**  
Exact tested head: `29982c61f2d467ac144763459ef03b4605560016`

UC pins only the vector data:

- neutral source commit: `0ec916cd6ab895a9a2118e5b63a6d3c8c1e34eb4`
- vector path: `conformance/vectors.json`
- vector Git blob: `ec5366ede678b621c43690292eff5b5e47503e47`

UC does **not** import the Neutral Compute JavaScript runtime.

## Focused cross-language result

Workflow: `35483964044`

Python 3.11 and Python 3.13 both passed the focused suite:

- canonical JSON hash primitive;
- exact byte hash primitive;
- all pinned Neutral Compute v0.1 behavior vectors;
- real UC shape-recipe dependency/reuse proof;
- unknown UC source HOLD control.

Focused result: **4/4 PASS** on both Python versions.

## Full UC regression

The same PR head passed:

- the focused workflow's full Python 3.11 suite: **1201 tests PASS**;
- repository-wide `Tests` workflow run `35483963996`: **SUCCESS**.

So the neutral state layer did not require weakening or replacing UC's existing test surface.

## Real UC contract proof

The integration test uses existing UC machinery, not generic toy objects:

- `compile_shape_recipe()` produces deterministic source-first derived geometry;
- `material_response_catalog()` provides an unrelated installed material-response body.

Registered contracts:

```text
creator-source
  depends on uc:shape-recipe/**

compiled-realization
  depends on uc:shape-recipe/**
  and uc:material-response/**

material-response-catalog
  depends on uc:material-response/**
```

Changing one retained shape recipe yields:

```text
creator-source             UPDATE
compiled-realization       UPDATE
material-response-catalog  REUSE_EXACT
```

The test verifies:

- source and compiled recipe identities actually change;
- the unrelated material catalog keeps the exact prior artifact hash;
- staging does not advance current generation;
- one commit advances the complete state;
- an unknown future UC source selector HOLDs instead of declaring all known contracts unaffected.

## Why this matters

MorphTile passing the vectors could still have meant the contract was accidentally tailored to one JavaScript/state style.

UC provides a materially different language, package structure and application domain while preserving the same observable rules.

That is stronger evidence that Neutral Compute v0.1 is a reusable substrate contract rather than a renamed MorphTile runtime.

## Truth boundary

Three implementations/consumers are still a bounded sample.

This result does not prove:

- all future AXM systems fit the contract;
- UC should replace candidate/adoption authority with Neutral Compute;
- dependency maps are automatically complete;
- state reuse improves UC performance;
- durable filesystem semantics are provided by the UC-native in-memory layer;
- passing conformance grants merge/CANON authority.
