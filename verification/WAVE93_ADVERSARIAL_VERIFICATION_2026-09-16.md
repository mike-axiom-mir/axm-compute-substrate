# Wave 93 independent adversarial verification — dangling committed evidence

Date: 2026-09-16
Verifier lane: `chatgpt/verifier-wave93-dangling-attestation-history`
Builder lane/head tested: `chatgpt/lane-001-platform-extract` @ `24c3597089097d67b5f2972beb11d51a764bee12`
Status: verifier-only evidence; draft/unmerged; no canon or automatic-merge authority.

## Verdict

**FAIL_COMMITTED_HISTORY_CAN_EXTEND_OVER_MISSING_PREDECESSOR_BODIES**

Wave 93 closes the Wave 92 remove/re-add evaluator-ID resurrection counterexample on the tested normal path: its cumulative evaluator-ID history tombstones removed IDs and rejects later ADD of an already-seen ID. The new transition-specific attestation binding also rejects the directly tested stale/cross-root/tool-substitution cases.

A separate historical-evidence continuity gap remains. Once a transition is committed, `authority()` validates only the current registry/history/state bodies and the three current witness tuples. It does not resolve the predecessor history body named by the current history, nor any attestation body named by the current attestation-state heads. `derive_state()` extends an evaluator sequence from the stored head hash without resolving that predecessor attestation body. `hist_step()` similarly extends the cumulative history without resolving the predecessor-history body named by the current history object.

## Exact-API counterexample

The executable reproducer uses only the committed Wave 93 public module state structures/functions.

1. Start from the normal Wave 93 genesis fixture and verify `AUTHORITATIVE`.
2. Perform a normal same-ID truth evaluator replacement and commit it with all four exact attestations. Verify the resulting tuple is `AUTHORITATIVE`.
3. Delete the **already-committed prior continuity attestation body** while leaving the committed attestation-state head unchanged. The continuity evaluator remains active and the head still names the deleted attestation SHA.
4. Delete the **genesis evaluator-history body** while leaving the current generation-1 history body unchanged. The current history still names the deleted predecessor-history SHA.
5. `authority()` still returns `AUTHORITATIVE`.
6. Prepare a second normal truth evaluator replacement. The new continuity attestation is accepted with `previous_attestation_sha256` equal to the missing prior attestation body. The new history is accepted even though its current predecessor history already contains a dangling predecessor link.
7. `apply()` returns `COMMITTED`, and final `authority()` again returns `AUTHORITATIVE`.

No hash collision, store-key/body substitution, whole-current-tuple rollback, or target self-authorization is required.

## Independent execution evidence

Read-only GitHub Actions workflow `verifier-wave93-dangling-history`, run `35127370580`, completed successfully against the PR merge of verifier head `5de3c5d6f3972574f5be8a6864ad244bc2a4b3ab` over exact builder base `24c3597089097d67b5f2972beb11d51a764bee12`.

The executable output recorded:

- `control_generation1_commit = COMMITTED`
- `missing_active_evaluator_prior_attestation_body = true`
- `missing_predecessor_history_body = true`
- `authority_after_committed_evidence_loss = AUTHORITATIVE`
- `next_attestation_chains_to_missing_body = true`
- `generation2_commit = COMMITTED`
- `final_authority = AUTHORITATIVE`
- verdict `FAIL_COMMITTED_HISTORY_CAN_EXTEND_OVER_MISSING_PREDECESSOR_BODIES`

## What survives

The specific Wave 92 evaluator-ID resurrection finding is closed on this path because the **current cumulative history body** preserves the seen/tombstoned sets. Current-transition attestations still require exact transition/root/evaluator/tool/source/sequence/predecessor-hash binding and PASS. Partial witness fan-out remains non-authoritative in the builder controls.

## What fails / bounded interpretation

Wave 93 currently proves continuity of **hash references and cumulative current state**, not durable availability or re-validation of the historical evidence bodies those hashes name. Therefore the phrase “append-only evaluator-ID history” is safe only as a logical current-state construction, not yet as an independently replayable/auditable append-only evidence log. Likewise, the report's missing-attestation negative case is bounded to attestation bodies needed by the transition being validated; a missing previously committed predecessor attestation does not fail closed.

This finding does not claim the tombstone security property is bypassed, does not claim a compute-efficiency regression, and does not alter the builder's explicit single-host/synthetic benchmark boundary.

## Next adversarial gate

Before key/signature provenance is treated as a durable chain, require current authority and/or transition validation to prove the reachable predecessor evidence closure needed by the claimed retention horizon. At minimum: resolve each active evaluator head's last attestation body and exact key/body identity; validate its sequence/evaluator/registry linkage; define whether all history ancestors must remain available or whether signed checkpoints/compaction receipts intentionally cut the chain; and make garbage collection produce explicit, authority-bound compaction evidence rather than silent dangling hashes.

Then attack: missing immediate predecessor attestation, missing older attestation two+ generations back, missing predecessor history objects, malicious history compaction, stale checkpoint reuse, key rotation over a dangling attestation predecessor, and whole-store rollback.

Executable reproducer: `verification/wave93_dangling_history_repro.py`
Workflow: `.github/workflows/verifier-wave93-dangling-history.yml`
