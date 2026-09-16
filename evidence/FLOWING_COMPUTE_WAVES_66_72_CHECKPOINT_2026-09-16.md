# Flowing Compute Waves 66–72 — Composite Lineage, Routing, Planning, and Plan-Bound Generations

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST EVIDENCE CHECKPOINT`

This checkpoint preserves the transition from two-contract atomic state into a four-contract planned generation model. It does not replace the underlying per-wave raw reports.

## Wave 66 — exact-ancestry rollback

Composite rollback is proven by exact `parent_pointer_sha256` lineage, not by sequence number.

- current G3 rolled back explicitly to ancestor G1;
- preserved G2/G3 remained valid and were not auto-reactivated;
- a valid unrelated sibling/lower-sequence branch returned `HOLD_TARGET_NOT_ANCESTOR`.

## Wave 67 — exact-descendant reactivation

After rollback to G1, preserved G3 could be explicitly reactivated without recomputing G2/G3.

- unrelated sibling branch -> `HOLD_TARGET_NOT_DESCENDANT`;
- an ancestor passed to the forward/reactivation API -> `HOLD_TARGET_NOT_DESCENDANT`;
- fresh-process graph logical hash and snapshot root matched the preserved G3 state exactly.

## Wave 68 — sibling merge candidate

Two disjoint real-format sibling mutations were combined into a **proven non-current** merge candidate.

- branch A: 13 changes;
- branch B: 7 changes;
- merged: 20 changes;
- exact cold graph oracle and full snapshot audit matched;
- candidate remained `PROVEN_NOT_CURRENT`.

A conflicting sibling that changed the same edge differently returned `HOLD_MERGE_CONFLICT`; no last-writer-wins rule is used.

## Wave 69 — four-contract selective generation

One G0→G1 generation referenced four real state contracts.

Changed:
- Execution Graph runtime state;
- whole-monolith snapshot identity.

Reused by exact content identity:
- FrameState dormant mesh;
- Execution-Fabric capability truth index.

Observed:
- new changed-contract artifacts: **10,083 bytes**;
- reused unchanged dormant artifacts: **11,270,945 bytes**;
- corrupting an unchanged reused artifact invalidated the whole composite generation.

A generation number therefore does not force every state contract to rewrite.

## Wave 70 — contract dependency invalidation router

A registry-backed router maps source mutations to affected contracts before any execution-policy decision.

Examples:
- `monolith:EXECUTION_GRAPH.json` -> graph + snapshot affected;
- `monolith:EXECUTION_FABRIC.json` -> capability index + snapshot affected;
- `asset:relay_offline.obj` -> dormant mesh affected;
- unknown source namespace -> `HOLD_UNKNOWN_SOURCE_NAMESPACE`.

Self-test: **7 checks passed**.

The registry is explicitly scoped only to the four experimental contracts. Absence of a selector is not claimed as universal software knowledge.

## Wave 71 — local-policy planner

Planning is split into two independent questions:

1. which contracts are affected?;
2. what measured local policy should each affected contract use?

For the real G0→G1 graph mutation:
- graph -> `incremental`;
- snapshot -> `fixed_dense_merkle`;
- dormant mesh -> `reuse_exact_current_artifact`;
- capability index -> `reuse_exact_current_artifact`.

Controls:
- affected capability index with missing future-use context -> `HOLD_MISSING_POLICY_CONTEXT`;
- fake graph feature combination outside the measured Wave-6 surface -> `HOLD_POLICY_DECISION`;
- FrameState one expected fresh worker -> cold parse; two -> compile dormant.

The dependency layer does not invent policy features that the local policy needs.

## Wave 72 — plan-bound generation evidence

The generation carries a content-addressed plan receipt explaining why every contract updated or reused.

Plan receipt SHA-256:

`d4334385512128e63fbff40dcc4f6bf70618558c30e0ae68e08349c114a78e14`

Controls passed:
- plan receipt tamper rejected;
- changing a contract whose plan action is exact reuse rejected;
- all four referenced artifacts validated independently;
- affected graph/snapshot refs differ from baseline exactly as planned.

The plan is explanatory evidence, not commit authority and not a substitute for artifact validation.

## Reusable primitives added

- `tools/AXM_FLOWING_COMPUTE_COMPOSITE_LINEAGE.py`
- `tools/AXM_FLOWING_COMPUTE_CONTRACT_DEPENDENCY_ROUTER.py`
- `tools/AXM_FLOWING_COMPUTE_SNAPSHOT_IDENTITY_POLICY.py`
- `tools/AXM_FLOWING_COMPUTE_MULTI_CONTRACT_PLANNER.py`
- `calibration/contract-dependencies.v0.1.json`

## Truth boundary

- one host/runtime;
- content hashes establish byte identity/integrity, not external authorization or semantic truth;
- HOLD/refusal paths are part of the evidence and are not implicit fallbacks;
- merge candidates do not gain current-state authority automatically;
- the dependency registry covers only the explicitly registered experimental contracts;
- no claim of compute or energy from nothing.

## Next gate

Execute a real plan through named contract executors and emit a plan-execution receipt. The generation should validate not only that its final artifacts agree with the plan, but that the measured execution path reports the same contract actions and output identities. A mismatch between plan and execution must HOLD before commit.
