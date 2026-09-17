# Wave 114 Independent Adversarial Verification — 2026-09-17

## Scope

Independent verifier lane only. No builder rewrite, merge, auto-merge, or CANON promotion.

- Newest builder head inspected: `e9b48d8e6b090ad73fe6f9d4443e741c308a70e6`
- Exact Wave-114 CI-tested builder source: `cd946978f2c01ce719307c5bc025beccbcb1ec4f`
- Exact verifier source/workflow CI-tested head: `1769f6fc1b17ea0f3cd749c581473806528882d8`
- Draft verifier PR: #39

## What survived

The intended Wave-114 repair for verifier PR #38 survives. The unchanged Wave-114 builder self-test was rerun in the independent verifier workflow and remained **20/20 PASS**. In particular, recovery remains bound to the exact transition SHA stored by the new decision ledger, extension-field transition identities are rejected, decision loss/tamper fail closed, and the documented clean exact recovery remains valid.

No new performance, energy, retained/incremental/dormant-compute, OS-process, device, network, physical-monotonicity, or provider-independence claim was made or inferred.

## New reproduced failure

Verdict:

`FAIL_SEMANTICALLY_INVALID_TRANSITION_IS_DURABLY_COMMIT_DECIDED_BEFORE_LOWER_VALIDATION`

Wave 114's public `commit(...)` performs these operations in this order:

1. strict transition field/schema/content-address check;
2. `_ensure_commit_decision(...)` appends a sealed `decision="COMMIT"` record binding the exact `(authority_sha, transition_sha)`;
3. only then call the lower Wave-110/Wave-100 commit path that validates registry-transition semantics.

The verifier starts from an ordinary Wave-114 genesis and performs a normal `prepare(...)`. It retains the genuine prepared transition. It then creates a second transition using the exact Wave-114 field set and preserving the prepared authority, checkpoint, state, registry identities, generations, and predecessor. Only the declared registry transition kind is changed (`SAME` -> `CREDENTIAL_ROTATION`) and the body is legitimately resealed/content-addressed through the unchanged Wave-100 helper.

Wave 114 accepts the strict identity and first appends a durable modeled `COMMIT` decision for that adversarial transition SHA. The lower semantic validator then rejects the same transition as:

`TRANSITION_DELTA_HOLD`

The rejected transition has therefore obtained an append-only Wave-114 COMMIT decision even though the lower transaction never committed.

The genuine original transition remains retained and semantically valid, but an exact retry with it is then rejected as:

`ValueError:decision-authority-bound-to-different-transition`

Retrying the already-bound adversarial transition still returns `TRANSITION_DELTA_HOLD`.

The world stays fail-closed:

- commit status: `UNRESOLVED_COMMIT_STATUS`
- authority: `HOLD_COMMIT_STATUS_UNRESOLVED`

So this is a liveness / evidence-integrity / decision-semantics failure, **not** stale-authority acceptance. No hash collision, credential forgery, body-key mismatch, builder-file rewrite, or whole-domain rollback is used.

## Independent CI evidence

GitHub Actions run: `35232714178`

Job: `105240688233`

Result: **success**

The workflow completed all of these successfully:

- unchanged Wave-114 builder self-test: **20/20 PASS**;
- adversarial reproducer under normal Python: reproduced the exact failure verdict;
- adversarial reproducer under `python -O`: reproduced the same exact failure verdict.

Artifact:

- ID: `10501523595`
- Name: `verifier-wave114-prevalidation-decision-poison`
- SHA-256: `3a9122f3e759319dcbcea1faa1d22bcbb6e3579dc5628a4b79c7c185a310ab69`

Representative normal-Python observations:

- genuine transition kind: `SAME`
- adversarial transition kind: `CREDENTIAL_ROTATION`
- first commit result: `TRANSITION_DELTA_HOLD`
- decision count after rejected lower commit: `1`
- decision transition SHA: adversarial SHA
- genuine retry: `ValueError:decision-authority-bound-to-different-transition`
- rejected-identity retry: `TRANSITION_DELTA_HOLD`
- status after rejection: `UNRESOLVED_COMMIT_STATUS`
- authority after rejection: `HOLD_COMMIT_STATUS_UNRESOLVED`

## Why it matters before Wave 115

Moving this decision ledger into a separate OS process before repairing the decision semantics would make the wrong fact harder to erase: a transition can currently be durably labeled `COMMIT` before the layer that actually knows the transition semantics has accepted it.

The next gate should therefore separate **intent** from **commit outcome**, or fully prevalidate the lower semantic contract before publishing a durable COMMIT decision.

Minimum next adversarial cases:

- invalid transition kind/delta;
- wrong current registry or generation;
- wrong target state binding;
- wrong predecessor;
- every lower-layer HOLD after decision publication;
- crash after intent/decision publication but before lower commit;
- exact retry and genuine-alternative retry;
- append-only ABORT/REJECT recovery for failed attempts;
- prove a rejected attempt cannot permanently poison the next legitimate commit.

Only after this survives should the exact decision witness move into a separate OS process/store and be challenged for process/store independence.