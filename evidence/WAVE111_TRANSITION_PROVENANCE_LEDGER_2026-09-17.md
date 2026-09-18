# Wave 111 — committed transition provenance ledger

Date: 2026-09-17
Lane: `chatgpt/lane-001-platform-extract`
PR: #2 (experimental, unmerged, not CANON)

## Why this wave changed direction

The planned next gate was an independently durable commit-decision witness. Before crossing that process boundary, independent verifier PR #35 found two narrower Wave-110 truth failures that had to be repaired first.

Primary verifier verdict: `FAIL_COMMITTED_TRANSITION_IDENTITY_IS_SUBSTITUTABLE`.
Wave 110 did not retain the exact transition SHA in a committed decision. Deleting the real transition and inserting a different newly content-addressed body that kept only authority/checkpoint/predecessor identities could still classify the history `VALID` and authoritative.

Secondary verifier verdict: `FAIL_TRANSITION_ONLY_EVIDENCE_IS_IGNORED_WHEN_WAVE109_REPORTS_NONE`.
If lower history was restored to saved genesis while an accepted transition record survived, Wave 110 returned early on `HISTORY_NONE` and could reopen modeled genesis authority.

Verifier identity is preserved in the Wave-111 source: verifier PR #35, head `eb8b2d21b63d280cd84f53f98769bc70c4939cf2`, evidence blob `3a035e1cb20a5e0159ca6dc9e5501f3cb669841e`, reproducer blob `62beb82f18517ee887bbc508b161db214bea477f`, CI run `35209627758`.

## What Wave 111 adds

Wave 111 adds a content-addressed append-only `W111_COMMITTED_TRANSITION_PROVENANCE` ledger in the existing modeled authority state. Each committed sequence binds:

- exact authority SHA;
- exact checkpoint SHA and signer-use SHA;
- exact transition SHA;
- transition target-state/current-registry/target-registry/kind identity;
- exact Wave-108 commit-record SHA and high-water SHA;
- predecessor provenance record SHA.

Read validation no longer accepts a transition merely because it names the same authority/checkpoint. It resolves the exact transition pinned by the provenance ledger, replays the Wave-100 registry step against the retained registry store, checks registry generations and delta semantics, and requires the transition target-state binding to equal the committed checkpoint state.

Transition evidence is now inspected even when the lower Wave-110 history result is `NONE`. A surviving transition or provenance row with no lower history becomes `UNRESOLVED_COMMIT_STATUS` rather than silently reopening genesis.

No pre-Wave-111 history is silently migrated. Fresh adoption initializes an empty provenance store only at zero committed epochs. Existing history requires a separate explicit migration/recovery procedure.

## Exact-source CI result

Tested source commit: `8b3c7e727fb1110259da15a9e9e62b720c520045`.

- unchanged Wave-110 regression: **20/20 PASS**;
- Wave-111 normal Python: **27/27 PASS**;
- Wave-111 `python -O`: **27/27 PASS**;
- workflow run: `35212162444`;
- job: `105171986067`;
- artifact: `10492447950`, `wave111-transition-provenance-reports`;
- artifact digest: `sha256:1b2938418059419e59d9278ec4055e4318b7ee2c32ae113c3e09392677295e8e`.

The exact PR #35 primary attack is reproduced against unchanged Wave 110 first: `VALID` + `AUTHORITATIVE_QUORUM_3_OF_3_MODELED`. Under Wave 111 the same attacked world becomes `INCOMPLETE_OR_CORRUPT` because the provenance ledger still pins the deleted genuine transition SHA, and authority becomes `HOLD_COMMITTED_HISTORY_INCOMPLETE`.

The exact PR #35 secondary attack is also reproduced first: unchanged Wave 110 returns `NONE` + `AUTHORITATIVE_GENESIS_MODELED`. Wave 111 sees the surviving transition and returns `UNRESOLVED_COMMIT_STATUS` with `HOLD_COMMIT_STATUS_UNRESOLVED`.

Additional negative controls cover:

- lower commit succeeding while the Wave-111 provenance append is absent (commit→provenance crash boundary): fail closed;
- provenance row loss: fail closed;
- provenance row tamper/key-body mismatch: fail closed;
- a same-domain provenance rewrite pointing at a nonsense replacement transition: semantic replay rejects it;
- a legitimate prepared-but-not-yet-committed transition: remains deliberately unresolved until commit completes.

Synthetic retained depth 6 passed only as a correctness check. It is intentionally untimed.

## Preserved counterexample / truth boundary

Wave 111 deliberately demonstrates that it is **not** the independent durability result yet. After a real epoch 2 exists, restoring the entire modeled world to the genuine epoch-1 snapshot — local state, transition store, commit/provenance ledgers, remotes, certificate store, binding store, and all three certificate-witness disks — still returns `AUTHORITATIVE_QUORUM_3_OF_3_MODELED` for the old genuine prefix.

That is expected: no independently surviving newer fact remains. The new provenance ledger is append-only and content-addressed inside the model, but it is still in the same rollback domain.

Therefore this wave makes no fresh AXM/monolith workload, performance, energy, network, retained-compute, incremental-compute, dormant-compute, OS-process independence, device independence, physical monotonicity, or provider-independence claim.

## Next gate — Wave 112

Move the commit decision/provenance receipt into a genuinely separate OS process and durable store with separately held identity/credential material. Then attack:

- crash after prepare, before lower commit;
- crash after lower commit but before independent decision publication;
- crash after independent decision publication but before local marker/provenance persistence;
- complete local-process rollback while the independent decision witness stays newer;
- stale/cloned local disks;
- witness outage and witness staleness;
- process restart/bootstrap from saved genesis;
- partitions/reconnects and simultaneous old/new views;
- whole local authority-store rollback plus certificate-tail rollback.

A successful Wave 112 would establish only bounded process-level durable separation. It would still not prove physically monotonic storage or independent-provider safety.

No merge, auto-merge, or CANON promotion was performed.
