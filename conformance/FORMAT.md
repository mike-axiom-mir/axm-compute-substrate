# Neutral Compute Conformance v0.1

This directory defines the **observable behavior contract** for AXM Neutral Compute Substrate v0.1.

An implementation may use completely different internal data structures, languages, storage engines or scheduling strategies. Conformance asks only whether the same inputs produce the same externally relevant state/reuse decisions and refusal boundaries.

## Why plain JSON vectors

The vectors are data, not privileged executable tests. A Python, Rust, JavaScript, C, MorphTile-native or future Magic Box implementation can consume the same cases.

The vector style is adapted from MorphTile's cross-implementation conformance file. The refusal/HOLD treatment is additionally informed by AXM Protocol Evolution and Invariant Lab.

## Required behavioral surface

A conforming implementation must be able to demonstrate equivalents of:

- register contracts and source selectors;
- plan a mutation into `UPDATE_REQUIRED` or `REUSE_EXACT`;
- HOLD when a mutation selector is unknown;
- require an affected contract to use a contract-allowed route;
- stage a complete generation without making it current;
- commit one logical current generation;
- keep hot/session state non-canonical across restart;
- reject stale plans/stages;
- rollback only to real ancestors;
- reactivate only real descendants;
- refuse sibling lineage as ancestor/descendant;
- distinguish real recomputation with identical output bytes from exact reuse;
- reject tampered persisted runtime evidence.

## Vector format

Top level:

```json
{
  "format": "axm-neutral-compute-conformance",
  "version": "0.1",
  "hash_primitives": {},
  "default_setup": {},
  "cases": []
}
```

### Setup

A setup declares contracts and initial artifacts.

```json
{
  "contracts": [
    {
      "id": "graph",
      "depends_on": ["source:graph/**"],
      "allowed_routes": ["incremental", "rebuild"]
    }
  ],
  "artifacts": {
    "graph": {
      "kind": "json",
      "value": {"graph": 0}
    }
  }
}
```

Bodies use either:

- `{"kind":"json","value":...}`
- `{"kind":"bytes-base64","value":"..."}`

The conformance runner converts them into the implementation's own artifact identity form.

### Steps

Each case is an ordered sequence. The v0.1 operation vocabulary is:

- `remember_current`
- `plan`
- `stage`
- `stage_from_current`
- `commit`
- `rollback`
- `reactivate`
- `wake`
- `sleep`
- `restart`
- `tamper_import`

`save_as` stores a plan/stage for a later step. `save_generation` stores the current generation identity as an opaque alias.

Expected output is a **partial structural match**. Implementations may expose additional diagnostic information. They must not contradict the expected fields.

Example:

```json
{
  "op": "plan",
  "selectors": ["source:graph/node-7"],
  "expect": {
    "status": "PLANNED",
    "actions": {
      "graph": "UPDATE_REQUIRED",
      "snapshot": "UPDATE_REQUIRED",
      "mesh": "REUSE_EXACT"
    },
    "current_sequence": 0
  }
}
```

## HOLD / refusal semantics

A named HOLD/refusal in a vector is a **successful conformance result**.

Examples:

- `HOLD_UNKNOWN_SELECTOR`
- `HOLD_ROUTE_REQUIRED`
- `HOLD_ROUTE_NOT_ALLOWED`
- `HOLD_STALE_BASE`
- `HOLD_TARGET_NOT_ANCESTOR`
- `HOLD_TARGET_NOT_DESCENDANT`
- `HOLD_ARTIFACT_HASH_MISMATCH`
- `REFUSED_TAMPERED_RUNTIME`

The test does not reward an implementation for "making progress" by guessing.

## Canonical identity primitives

v0.1 includes two portable identity checks:

1. canonical JSON: recursively sort object keys, preserve array order, encode as UTF-8 JSON, then SHA-256;
2. raw bytes: SHA-256 over the exact bytes.

The committed vector avoids floating-point and exotic Unicode edge cases. Those remain future versioning work rather than hidden assumptions.

## Conformance is not implementation identity

A native implementation does **not** need the same generation object layout or internal hash as the JavaScript reference runtime.

The vectors test behavior. If two systems later need to exchange persistent generation objects directly, that requires a separate wire/storage format contract.

## Status boundary

Passing these vectors means only:

> the implementation matched Neutral Compute Substrate v0.1 on the committed observable cases.

It does not prove:

- durable filesystem/database crash atomicity;
- performance improvement;
- energy reduction;
- correct dependency maps for an arbitrary product;
- availability of historical artifact bytes;
- distributed uniqueness/consensus;
- hostile-host security;
- semantic quality of an artifact;
- CANON or merge authority.
