# Independent adversarial verification — Flowing Compute Wave 91

Date: 2026-09-16  
Builder head verified: `3b7ae7ce9751497666d8e85494ca72150c088882`  
Lane status: verifier-only, draft/unmerged, no canon authority.

## Target

Wave 91 claims that authorization is forced to the exact currently committed evaluator registry: the runtime current pointer and all three required witness views must agree on one registry identity, the body must exist and validate, and the authorization must name that exact current registry.

The builder also explicitly preserves a different known gap: evaluator-registry transitions are still unguarded, so a self-minted successor can become current if the transition primitive is allowed to finish. This verification does **not** reuse that admitted failure.

## What survived

The normal exact-key control survives:

- runtime current pointer = registry A SHA;
- all three witnesses = registry A SHA;
- store key A resolves to registry body A;
- normal Wave 91 authorization built from A returns `ALLOW`.

The missing-key control also survives: if A is absent from the store, `current_authority()` returns `HOLD`.

The report's benchmark/truth boundary remains appropriately narrow: this is synthetic single-host authority bookkeeping, not a fresh monolith workload, distributed consensus result, joule result, or retained/incremental compute-saving claim.

## Reproduced failure — current-registry key/body identity is not enforced

Wave 91 treats the registry store as content-addressed, but its reusable validators never check that the body loaded from `store[current_registry_sha256]` has `registry_sha256 == current_registry_sha256`.

Exact-API counterexample:

1. Construct valid registry A and set the runtime current pointer plus all three witness views to A's SHA.
2. Construct a second independently valid registry B with a different self-hash and different evaluator IDs.
3. Supply a store mapping whose **key is A's SHA but whose body is B**.
4. `current_authority()` loads B, validates B's own internal seal, but does not compare B's self-hash to lookup key A. It returns `AUTHORITATIVE` while reporting A as the authoritative identity.
5. Construct a normally sealed authorization whose external registry SHA is A but whose evaluator rows match B's evaluator IDs.
6. `validate_current()` -> `validate_structural()` again loads B under key A, validates B's own seal, checks row evaluator IDs against B, and returns `ALLOW`.

No registry transition, witness disagreement, hash collision, missing body, corrupt internal seal, or use of the already-disclosed self-admission transition gap is required.

The exact verifier verdict is:

`FAIL_CURRENT_REGISTRY_KEY_BODY_IDENTITY_NOT_ENFORCED`

## Why it matters

The authority claim is about an **exact registry identity**, not merely "some internally valid registry body happened to be returned under this dictionary key." Without key/body identity binding, the current pointer and witnesses can agree on A while the authorization semantics are taken from B.

In gamer terms: all three guards point at save-slot A, but the storage shelf silently puts save-file B inside slot A. The checker confirms B is a valid save file, never checks that it is actually save A, and then lets B's team make the decision while the UI still says A is current.

## Next adversarial gate

Before Wave 92 transition authorization is trusted, require every content-addressed load to prove `lookup_key == body[self_hash_field]` before the body can influence authority or authorization. Prefer one shared resolver rather than repeating dictionary access plus body-only validation.

Then attack:

- key/body substitution for evaluator bodies as well as registry bodies;
- valid-but-wrong historical registry bodies under a current key;
- missing and corrupt predecessor bodies;
- stale transition authorization replay after a registry generation change;
- competing predecessor-authorized transitions;
- target/new evaluator attempts to authorize their own admission;
- transition recovery after partial witness fan-out.

This lane does not modify builder code and should remain unmerged until the builder either closes the identity gap or explicitly narrows the Wave 91 authority claim.
