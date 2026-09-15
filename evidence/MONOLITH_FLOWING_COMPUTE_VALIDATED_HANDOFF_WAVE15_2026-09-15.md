# Flowing Compute Wave 15 — Validated-State Handoff

Date: 2026-09-15  
Status: `EXPERIMENTAL RUNTIME INTERFACE EVIDENCE`

## Problem

Wave 14 showed that the packed AXDS dormant state could be much smaller than canonical JSON, but the first integration paid two semantic-validation boundaries: once during unpack and again inside the transition runtime.

A boolean such as `skip_validation=true` would be fast but would create an unsafe/ambiguous API.

## Handoff contract

Wave 15 adds a process-local `ValidatedStateHandle` minted only by registered validator functions.

Current validators:

- `canonical-json-state/v0.1`
- `axds-packed-state/v0.1`

The handoff receipt records validator identity, artifact SHA-256, semantic state SHA-256, source SHA-256, and validation success.

The handle is **one-use**. Once consumed by a transition, reuse rejects.

The ordinary dictionary transition API is unchanged and still validates state itself. Only the separate validated-handoff path avoids duplicate validation.

This is a cooperative runtime correctness boundary, not a malicious in-process Python sandbox.

## Self-test

**5 checks PASS** in the local Wave-15 fixture:

- JSON and AXDS validators resolve to the same semantic state hash;
- handle consumption works;
- second consumption rejects;
- direct handle construction without the module-private mint token rejects;
- tampered AXDS artifact rejects before handoff.

## Fresh-process transition benchmark

11 alternating fresh-process trials per format/case. Both formats are validated exactly once and then use the same dormant transition implementation.

### 58 / 127 affected components

- JSON: **15.770 ms CPU**
- AXDS: **16.022 ms CPU**
- AXDS delta: **+1.60% CPU**
- JSON validation/load: ~8.339 ms
- AXDS validation/load: ~8.401 ms
- fresh-process wall delta: **+1.14%**

### 127 / 127 affected components

- JSON: **17.665 ms CPU**
- AXDS: **17.935 ms CPU**
- AXDS delta: **+1.53% CPU**
- JSON validation/load: ~8.265 ms
- AXDS validation/load: ~8.348 ms
- fresh-process wall delta: **+0.93%**

Exact final state SHA-256 equality passed for every sample.

## Combined Wave-14/15 result

AXDS v0.1 now demonstrates, for this one dormant state body:

- storage: **261,570 bytes** vs **662,225 bytes JSON** (**60.5% smaller**);
- exact semantic state reconstruction;
- container tamper rejection;
- one-use semantic validation handoff;
- transition CPU within about **1.5–1.6%** of JSON in the measured cases;
- fresh-process wall time within about **1%**.

That is materially stronger than generic gzip in the earlier integration benchmark, where gzip was ~14–19% more CPU than JSON while also being slightly larger than AXDS.

## Truth boundary

- AXDS still reconstructs JSON-shaped Python structures; it is not a native packed update engine.
- `ValidatedStateHandle` prevents accidental double-validation/reuse in the cooperative runtime API; it is not a security boundary against malicious code already running inside the same Python process.
- These are one-host results for one state contract.
- Smaller storage is not declared universally superior.

## Next gate

Operate **directly on the packed representation** instead of reconstructing all JSON-shaped hash dictionaries. The question is whether native packed transition can make the smaller representation equal or cheaper in compute while retaining the same source/delta/topology/equivalence evidence.
