# AXM Flowing Compute — Wave 114 Exact Transition Decision — 2026-09-17

## Why this wave changed direction

Wave 113 remained green on its own contract, but independent verifier PR #38 found a narrower exact-identity defect in its documented lower-commit -> missing-provenance recovery window. If the genuine unprovenanced transition body was deleted and replaced by a newly content-addressed, semantically equivalent transition carrying an ignored extra field, Wave 113 could bind the replacement SHA into provenance and later classify the history VALID.

Preserved verifier verdict: `FAIL_RECOVERY_BINDS_SUBSTITUTED_TRANSITION_IDENTITY`.

This is treated as a recovery provenance/identity defect, not as evidence of stale-authority takeover by itself.

## Wave 114 change

Wave 114 adds an append-only modeled commit-decision ledger. Before the lower Wave-110 commit is allowed to run, the ledger seals the exact `(authority_sha, transition_sha)` pair together with checkpoint, target-state, registry identities, predecessor decision and predecessor authority. Recovery may use only the transition SHA already bound by that decision record.

Wave 114 also makes the Wave-100 transition identity field set strict. A transition carrying an otherwise ignored extension field is rejected instead of being accepted as a second content identity.

The implementation remains additive over Wave 113. No earlier evidence was rewritten and no merge or CANON promotion was performed.

## Positive and negative evidence

Exact CI-tested source commit: `cd946978f2c01ce719307c5bc025beccbcb1ec4f`.

Successful CI run `35229822814`, job `105230686122`:

- unchanged Wave 113 regression: **25/25 PASS**;
- Wave 114 normal Python: **20/20 PASS**;
- Wave 114 `python -O`: **20/20 PASS**;
- artifact `10500408246` (`wave114-exact-transition-decision-reports`), SHA-256 `3afedbb0b7ca906c5cdd7f097f9849e8be9b79e61339d5d230d3ecd92b549bfd`.

The Wave-114 self-test first reproduces verifier PR #38 against unchanged Wave 113: the replacement transition becomes the bound provenance identity and the status becomes VALID. Against Wave 114, the same replacement attempt is rejected with `recovery-transition-does-not-match-durable-commit-decision`; provenance remains unchanged and authority remains `HOLD_COMMITTED_HISTORY_INCOMPLETE`.

Additional negative controls require:

- unknown transition extension fields to fail with `transition-field-set-mismatch` before creating a decision;
- a missing decision to classify history `INCOMPLETE_OR_CORRUPT` and block authority;
- a tampered decision to classify history `INCOMPLETE_OR_CORRUPT` and block authority;
- the injected lower-commit -> provenance crash to retain the exact decision identity and remain held until exact recovery;
- clean exact recovery to return `COMMITTED_RECOVERED_EXACT_DECISION`, restore VALID history and remain idempotent on retry;
- normal two-epoch progress to remain VALID and authoritative while decision transition SHAs exactly match the committed transition SHAs.

## Preserved failed run

The first Wave-114 CI attempt, run `35229354618` / job `105229070310`, is intentionally left in history. Wave 113 regression passed, then the Wave-114 test harness failed before exercising the new decision logic because the self-test referenced `w.PROVENANCE_STORE`, while the additive module kept that predecessor constant on Wave 113. The failed artifact `10500836778` has SHA-256 `a513f08a5e7643d7636780f3f1757b4670d0b7472daceb1b9087bfccc4c192c9`.

The repair did not weaken the implementation or erase the failed run. Commit `cd946978f2c01ce719307c5bc025beccbcb1ec4f` adds an explicit CI-only compatibility runner exposing that one predecessor constant to the unchanged self-test process. The Wave-114 implementation blob and original self-test blob remain unchanged from the first attempt.

## Counterexample still alive

The decision ledger is still another dictionary inside the same modeled Python failure domain. If the entire modeled world is restored to an older genuine snapshot, the newer decision disappears with everything else and the older prefix can still return `AUTHORITATIVE_QUORUM_3_OF_3_MODELED`.

Therefore Wave 114 does **not** prove process/power-loss atomicity, independent durable witnessing, device independence, network independence, physical monotonicity or provider independence.

No real AXM/monolith workload and no synthetic scaling benchmark was run in this correctness wave. No new performance, energy, retained/incremental/dormant-compute result is claimed.

## Next gate

Wave 115 should move the exact commit-decision witness into a genuinely separate OS process and durable store with its own credential. Attack at least: crash before decision publication; crash after durable decision publication but before lower/local provenance completion; full local rollback while the witness remains newer; transition-body deletion/replacement across restart; stale/cloned local disks; decision-witness outage/staleness; witness-store truncation/corruption; credential substitution; partitions/reconnects; and simultaneous old/new process views.

A positive Wave 115 result would establish only process/store separation under the tested fault model. It must not be promoted to physical, provider-independent or universally monotonic finality without separate evidence.
