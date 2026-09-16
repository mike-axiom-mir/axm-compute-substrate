# Wave 94 independent adversarial verification — dangling authority-state chains

Date: 2026-09-16  
Verifier lane: `chatgpt/verifier-wave94-dangling-state-key-state`  
Builder head tested: `340fd44141b40493b0ddd7a51fd653ada9ddf9b8`  
Status: verifier-only evidence; draft/unmerged; no canon or automatic-merge authority.

## Verdict

**FAIL_ATTESTATION_AND_KEY_STATE_PREDECESSOR_BODIES_CAN_DANGLE_AND_HISTORY_CAN_EXTEND**

Wave 94 materially closes the specific Wave 93 gap for retained history bodies, active attestation chains, and signer-key lineage bodies. The independent control in this lane confirms that deleting the predecessor **history** body makes current authority `HOLD`.

A separate closure gap remains in the other two explicit predecessor chains inside the live authority tuple. `att-state/v1` and `key-state/v1` both carry `predecessor` object identities, and transition validation requires a newly constructed target's predecessor fields to equal the current tuple. However, restart/current `tuple_closure()` resolves only the current attestation-state and key-state bodies. It does not follow either object's `predecessor` field.

## Exact-API counterexample

The executable reproducer imports the committed Wave 94 module directly and uses only its public/reusable data structures and helpers.

1. Start from the normal Wave 94 fixture and verify `AUTHORITATIVE`.
2. Commit one ordinary successor. The current attestation-state and signer-key-state bodies now each contain a real predecessor SHA pointing to their genesis state body.
3. As a control, delete the current history body's predecessor history object. Authority correctly becomes `HOLD`; restore it and authority returns to `AUTHORITATIVE`.
4. Delete the predecessor **attestation-state** body and predecessor **signer-key-state** body, leaving the current bodies, history bodies, attestation bodies, key bodies, and all three witness tuples unchanged.
5. The current state bodies still explicitly name those now-missing predecessor SHAs, but `authority()` returns `AUTHORITATIVE`.
6. Build a second normal successor through `bundle()`. It succeeds because predecessor authority closure still passes.
7. `validate()` accepts the new target, `apply()` returns `COMMITTED`, and final `authority()` again returns `AUTHORITATIVE` while both older state bodies remain absent.

No SHA-256 collision, missing attestation body, missing signer-key body, whole-runtime rollback, or stolen key is required.

## What survives

Wave 94 does close the exact Wave 93 dangling-history / dangling-attestation problem on the tested retained horizon. `hclosure()` requires the full history chain to genesis; `aclosure()` requires each active root's attestation chain to sequence 1; `kclosure()` requires signer-key lineage to genesis; exact content-address key/body identity is enforced by `get()`; partial three-witness fan-out remains non-authoritative; and the report keeps the HMAC mechanism correctly scoped as a symmetric test model rather than production identity or root correctness.

The failure is narrower: the system currently has five visible historical chains — history, attestation-state, signer-key-state, per-root attestation, and per-root key lineage — but retained closure is enforced only for history + per-root attestation + per-root key lineage. The two state-snapshot predecessor chains can contain dangling historical references and still be extended.

If those state predecessor fields are intentionally non-retained/redundant breadcrumbs, that should be an explicit contract and Wave 95 checkpoint/compaction semantics should say they may legally dangle. If they are intended as auditable authority-tuple history, they need the same closure or an explicit checkpoint cut.

## Secondary hidden cost — symmetric key rotation retains old private secrets

The reproducer also performs a normal truth-root key rotation, then deletes only the retired predecessor key's secret from the in-memory secret store while keeping the key record and all evidence bodies. Current authority becomes `HOLD` until the old secret is restored.

That is inherent to the present HMAC verification model: historical MACs and `kclosure()` require historical symmetric secret material to remain available. This is not counted as a cryptographic break because Wave 94 already says the HMAC mechanism is test-only and not production key management. It is nevertheless an important retention/security cost for Wave 95: "key rotation" here does not yet permit secure destruction of retired private signing material.

## Benchmark / fairness boundary

This verifier does not reinterpret Wave 94's ~10–12 ms synthetic process-CPU measurement as a compute-efficiency result. The builder explicitly makes no retained/incremental/dormant-state efficiency, energy, scaling, network/storage-latency, distributed-consensus, or fresh monolith claim. Full retained closure is structurally history-depth dependent, so a future scaling benchmark should vary retained depth rather than benchmark only the short fixture.

## Next adversarial gate

Before Wave 95 compaction is trusted, define the retention semantics for **all** predecessor-bearing authority objects. Either:

- require attestation-state and signer-key-state predecessor closure back to genesis, or
- explicitly declare those snapshot predecessor links non-retained and replace them with checkpoint-bound provenance that intentionally cuts the chain.

Then make the checkpoint bind the exact live history/state/key-state tuple, active attestation heads, current key heads, and the retained cut. For symmetric-key experiments, also decide whether historical secret retention is intentionally required; if retired secrets should be destroyable, use a verification design that does not require keeping old private key material.

Next attacks: missing immediate/older state snapshots, stale checkpoint reuse, omitted state snapshot at the cut, key rotation across a cut, retired-secret destruction, checkpoint rollback with live state, and forged checkpoint continuity.

Executable reproducer: `verification/wave94_dangling_state_key_state_repro.py`.
