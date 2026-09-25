# Neutral Compute v0.1 — Universal Creation third-consumer receipt

Date: 2026-09-20  
Status: **MERGED CONSUMER EVIDENCE / neutral core still experimental**

## Consumer

Repository: `mike-axiom-mir/axm-universal-creation`

Merged PR: **#223** — `Prove Neutral Compute v0.1 with UC-native Python state`

- PR head: `29982c61f2d467ac144763459ef03b4605560016`
- merge commit: `35ac0ac2f5cd3910ce129536b9b0946b8cc9ea85`
- merged at: 2026-09-20T02:49:23Z
- changed files: 5
- additions: 1467
- deletions: 0

UC pins the neutral vector file as data and implements the runtime independently in Python. It does not import the neutral JavaScript runtime.

## Dedicated conformance verification

Workflow run: `35483964044` — **SUCCESS**

Python 3.11 job `106006748714`:

- compile native neutral runtime + focused proof: PASS
- pinned neutral vectors + real UC proof: PASS
- full UC unittest suite: PASS

Python 3.13 job `106006748858`:

- compile native neutral runtime + focused proof: PASS
- pinned neutral vectors + real UC proof: PASS

The Python 3.11 full-suite log reports **1,201 tests passed**.

The repository's ordinary PR Tests workflow also passed on the same PR state: run `35483963996`.

## Real UC-shaped proof

The consumer test does more than replay generic vectors.

It uses UC's existing:

- `compile_shape_recipe()`
- `material_response_catalog()`

A retained shape-recipe mutation is planned against three contracts:

1. creator source
2. compiled realization
3. material-response catalog

Changing only the shape recipe requires:

- creator source → **UPDATE_REQUIRED**
- compiled realization → **UPDATE_REQUIRED**
- material-response catalog → **REUSE_EXACT**

Staging does not move current authority. One commit advances the complete generation. An unknown UC source selector returns HOLD instead of declaring all existing contracts reusable.

## Why this matters

Neutral Compute v0.1 now has three materially different implementations/evidence surfaces:

1. neutral zero-dependency JavaScript reference runtime;
2. MorphTile native JavaScript Flow runtime;
3. Universal Creation native Python runtime.

UC is a different language and a different application architecture. This reduces the risk that the neutral contract is merely MorphTile-shaped behavior with generic names.

## Truth boundary

This third consumer proves agreement only on the committed vectors and the bounded real UC recipe/material case.

It does not prove:

- every UC dependency is mapped;
- performance gains;
- crash durability;
- automatic caching policy;
- distributed authority;
- semantic or visual quality;
- CANON authority.
