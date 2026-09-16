# Independent adversarial verification — Flowing Compute Wave 92

Date: 2026-09-16  
Verifier lane: `chatgpt/verifier-wave92-evaluator-resurrection`  
Builder base: `f94d563fe5339316e3362bccf988e83c950f161d`  
Status: verifier-only evidence; keep draft/unmerged; no canon or merge authority.

## Target claim

Wave 92 materially improves the predecessor-authorized registry-transition path: content-addressed lookup key/body identity is checked before registry/evaluator bodies influence authority, replacement evaluators must descend from the exact evaluator body they replace, target/new registries do not authorize their own admission, and exact predecessor authorization is required for partial recovery.

The Wave 92 evidence also says intentional rollback remains forward-lineage by producing a new registry/evaluator identity rather than resurrecting an old authority identity.

## What survived

Static inspection of the reusable Wave 92 path confirms the previously reported key/body substitution hole is closed by `get()`: a loaded object must have a valid self-seal and its self-hash must equal the lookup key. `rreg()` applies this to registry and evaluator bodies.

For an evaluator ID that exists in both predecessor and target registries with a changed body, `rtrans()` also checks that the target evaluator's `predecessor_evaluator_sha256` equals the exact predecessor-registry evaluator SHA. This closes the direct same-ID REPLACE lineage gap found in Wave 90.

The builder truth boundary remains appropriately narrow: the Wave 92 timing is single-host synthetic authorization bookkeeping, not a compute-efficiency, retained-state, energy, wall-clock storage/network, or distributed-consensus result.

## Reproduced failure — REMOVE then ADD resurrects exact historical evaluator identity

The lineage rule is only checked against the immediately preceding registry's entry set. `parts()` classifies evaluator changes using predecessor-vs-target evaluator IDs. `rtrans()` enforces exact predecessor lineage only for IDs classified as `REPLACE`; IDs classified as `ADD` are instead required to have `predecessor_evaluator_sha256 is None`.

That permits a removed evaluator identity to return later as an ADD with no historical-lineage check.

Exact public/reusable API sequence in the reproducer:

1. Start from the normal Wave 92 genesis fixture, where `eval-truth` has evaluator SHA `truth0` and `predecessor_evaluator_sha256=None`.
2. Make an authorized generation-1 MIXED transition that removes `eval-truth`, adds a different `eval-truth-bridge`, and assigns the truth root to the bridge. Commit succeeds and generation 1 becomes authoritative.
3. Build generation 2 by removing the bridge and adding `eval-truth` back using the **exact generation-0 evaluator body/SHA**.
4. Because `eval-truth` is absent from generation 1, Wave 92 classifies it as `ADD`, not `REPLACE`.
5. The exact old generation-0 object already has `predecessor_evaluator_sha256=None`, so the ADD lineage check passes.
6. `rtrans()` accepts the transition, normal predecessor authorization is created from generation 1, `apply()` returns `COMMITTED`, and the final authoritative registry points to the exact generation-0 evaluator SHA again.

No hash collision, content-address key/body substitution, target self-authorization, missing witness, direct current-pointer rewrite, or malformed authorization is required.

Expected verifier verdict:

`FAIL_REMOVED_EVALUATOR_IDENTITY_CAN_BE_RESURRECTED_AS_ADD`

## Why it matters

Wave 92 proves direct replacement ancestry for an evaluator that remains continuously present, but it does not preserve evaluator identity history across absence. A one-generation remove/add cycle acts as a lineage reset. This means an old evaluator body can regain live authority under its exact old identity despite the stated forward-lineage rollback direction.

The same shape also allows a previously used evaluator ID to be reintroduced with a fresh predecessor-less body after an absence, because there is no append-only evaluator-ID history/tombstone/sequence binding in the registry transition semantics.

## Next adversarial gate

Before relying on Wave 93 attestation sequence/nonce semantics, bind evaluator-ID history across registry generations. For every ADD, distinguish genuinely never-before-seen evaluator IDs from historically removed IDs. A historically known ID should either be forbidden from reappearing or must carry explicit reactivation lineage to its last historical evaluator identity through a separately authorized transition.

Then attack:

- exact historical evaluator-body resurrection after one or many absent generations;
- same evaluator ID reintroduced with a fresh predecessor-less body;
- remove/re-add around attestation sequence resets;
- replay of old attestations after evaluator resurrection;
- competing branches that each reactivate the same historical evaluator ID;
- garbage-collected history that makes a reactivation look like a first-ever ADD.

Wave 93's planned transition-specific attestations remain useful, but their evaluator sequence/nonce must be anchored to durable evaluator identity history or this remove/add reset can also reset the attestation namespace.
