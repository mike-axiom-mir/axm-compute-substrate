# Neutral Compute Conformance v0.1 — cross-repository receipt

Date: 2026-09-20  
Status: **EXPERIMENTAL / NON-CANON / PR #64**

## Neutral reference result

Exact Neutral Compute source head carrying the conformance kit before this receipt:
`997aee5706ee2d4335c6059b16db1a1fe844bb6d`

GitHub Actions:

- run: `35483335983`
- job: `106004994515`
- conclusion: **SUCCESS**
- `npm test`: **14/14 PASS**
- `npm run conformance`: **8/8 behavioral cases PASS**
- canonical-JSON SHA-256 primitive: **PASS**
- raw-byte SHA-256 primitive: **PASS**

Committed vector file:

- `conformance/vectors.json`
- Git blob: `ec5366ede678b621c43690292eff5b5e47503e47`

## Pattern provenance

The kit deliberately reuses established AXM testing patterns rather than inventing a new meta-framework:

- MorphTile `tools/conformance.js`: plain JSON cross-implementation vectors.
- AXM Invariant Lab: fail-closed bounded checks and counterexample/HOLD discipline.
- AXM Protocol Evolution: REFUSE/AMBIGUOUS/UNSUPPORTED are truthful compatibility outcomes, not lower-quality PASS substitutes.

Exact inspected pins and boundaries are recorded in `conformance/PROVENANCE.md`.

No donor domain implementation was copied into Neutral Compute.

## First independent implementation

MorphTile PR #5 consumes the exact vector bytes above as a pinned fixture while keeping its own native runtime.

Source:

- repository: `mike-axiom-mir/axm-morphtile`
- final tested head: `9a5a3f21728c36470b0607066bc2a08e0ac4473b`
- test workflow run: `35483544928`
- job: `106005571928`

Final result:

- MorphTile `npm test`: **132/132 PASS**
- Neutral Compute hash primitives: **PASS**
- Neutral Compute pinned vector suite: **PASS**
- MorphTile build: **PASS**
- MorphTile's own native conformance: **PASS**, 7 cases

MorphTile does not import this repository's runtime code.

## Independent failures that improved the contract boundary

The first MorphTile vector run was intentionally preserved:

- head: `4cd773e93aeeebb170f07587e66e10bbc28bf6ee`
- run: `35483448589`
- result: **130 PASS / 2 FAIL**

It exposed:

- missing raw-byte artifact identity;
- missing general trailing-`**` namespace recursion;
- resulting incorrect reuse classifications and wake verification.

After the first repair:

- head: `92425cc4c7967f2da639b3693016d03377761de1`
- run: `35483506430`
- result: **131 PASS / 1 FAIL**

The sole remaining failure was an integration mistake: descendant reactivation existed but was not exported.

Final head `9a5a3f21728c36470b0607066bc2a08e0ac4473b` then passed unchanged vectors.

The vectors were never modified to accommodate MorphTile.

## What v0.1 conformance means

A PASS means the implementation matches the committed observable cases for:

- dependency closure;
- update versus exact reuse;
- fail-closed unknown changes;
- contract-local route enforcement;
- staging versus current authority;
- logical generation commit;
- hot/dormant restart behavior;
- lineage rollback/reactivation;
- same-output recomputation accounting;
- tamper refusal;
- canonical JSON and exact-byte identity.

It does **not** mean implementations share internal object layouts or persistent generation wire formats.

## Truth boundary

Cross-repository agreement on eight cases is stronger than a single implementation's unit tests, but it still does not prove:

- universal dependency-map correctness;
- crash-durable storage transactions;
- performance or energy gains;
- artifact retention/availability;
- distributed consensus or uniqueness;
- hostile-host security;
- semantic quality of retained artifacts;
- merge/CANON authority.

The next useful conformance expansion should come from a genuinely different runtime/storage consumer or from a concrete failure found while integrating one, not from adding vectors for coverage count alone.
