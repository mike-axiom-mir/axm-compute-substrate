# Wave 112 independent adversarial verification — recovery atomicity

Date: 2026-09-17
Lane: `chatgpt/verifier-wave112-recovery-atomicity`
Status: verifier-only; draft/unmerged/non-CANON

## Exact builder state

- newest builder head inspected and rechecked before completion: `a1cf4ccb535142a63a328c4a0dadc86984deaa3b`
- exact Wave-112 source that builder CI tested: `1be9303bba0712869d40444f5cf1b0e878948ab7`
- Wave-112 implementation blob: `41e73e8f042df974b161fa9b85b128c99b1bb819`
- Wave-112 original self-test blob: `7a48968a851c23129b6ae31ef017483407e70e8f`
- builder CI run: `35218596920`, job `105192939604`
- builder result: Wave-111 regression 27/27 PASS; Wave-112 22/22 PASS in normal Python and `python -O`

The direct Wave-112 repair is material: when the retained provenance prefix is sound and exactly one trailing provenance row is missing after a lower Wave-110 commit, the exact retry can append that missing row and restore a VALID history. The builder also keeps the truth boundary narrow: same modeled Python failure domain, no energy/process/provider/retained-compute claim.

## Adversarial case

Reproduced verdict:

`FAIL_FAILED_RECOVERY_MUTATES_LEDGER_AND_THEN_MISREPORTS_ALREADY_COMMITTED`

The public recovery path validates the lower Wave-110 committed history, checks only the existing provenance rows' structural chain plus authority-prefix identity, and then calls Wave-111 `_append_provenance(...)`. Full Wave-112 provenance semantics are checked only **after** that append has already mutated the retained provenance store.

The reproducer:

1. accepts epoch 1 normally, including genuine provenance;
2. commits epoch 2 through the lower Wave-110 layer and simulates the documented crash before its provenance append;
3. replaces only epoch-1's provenance row with a new content-addressed row that preserves schema/sequence/epoch/authority/chain structure but corrupts one semantic field (`target_state_sha`);
4. confirms Wave 112 is already `INCOMPLETE_OR_CORRUPT` / authority `HOLD_COMMITTED_HISTORY_INCOMPLETE` before retry;
5. retries the exact epoch-2 authority/transition through the public Wave-112 `commit(...)`;
6. observes Wave 112 append the epoch-2 provenance row first, then reject the overall history during its post-write validation with `transition-provenance-target-state-mismatch`;
7. confirms the failed retry left the epoch-2 provenance row durably present;
8. retries the exact same commit again and observes `ALREADY_COMMITTED` even though full Wave-112 status remains `INCOMPLETE_OR_CORRUPT` and authority remains HOLD.

This is not stale-authority acceptance. It is an evidence-integrity/recovery atomicity and liveness failure: a retry attempted while the history is already known incomplete can make durable verifier evidence *more mutated*, then report idempotent success on the next retry without returning the history to validity.

## Why this differs from the builder controls

Wave 112 tests a sound existing prefix plus one missing trailing row, an arbitrary wrong transition SHA rejected before the append, and multiple missing provenance rows rejected before the append. It does not test a structurally valid but semantically damaged existing provenance prefix. `_recover_missing_trailing_provenance(...)` does not run Wave-112's full `_validated_provenance_state(...)` over that prefix before `_append_provenance(...)` mutates the store.

The second-retry issue is separate but related: once the failed first attempt has inserted the trailing row, `_recover_missing_trailing_provenance(...)` sees the requested authority already present and returns `ALREADY_COMMITTED` after checking only its transition SHA, without first requiring the complete Wave-112 history to be VALID.

## Severity boundary

- demonstrated: failed recovery can mutate retained provenance while still ending in HOLD;
- demonstrated: subsequent exact retry can return `ALREADY_COMMITTED` while full history remains incomplete and authority remains HOLD;
- not demonstrated: stale authority acceptance;
- not demonstrated: credential/hash forgery;
- not a performance, energy, retained/incremental/dormant-compute, process, device, network, or provider-independence result.

## Independent CI

Read-only verifier workflow: `.github/workflows/verifier-wave112-recovery-atomicity.yml`

Exact reproducer: `verification/wave112_recovery_atomicity_repro.py`

Final successful independent execution:

- run `35220649306`, branch head `3977ad3f1e13aee238796976276965f6d454c7aa`;
- normal job `105199664783`: adversarial reproducer PASS and unchanged exact Wave-112 CI wrapper PASS;
- optimized job `105199664406`: adversarial reproducer PASS and unchanged exact Wave-112 CI wrapper PASS under `python -O`;
- normal artifact `10497430466`, ZIP SHA-256 `d13d63faa70629ce829bceecba6e770f591cf665cbb677bf31594fc6bac6f18e`;
- optimized artifact `10497590342`, ZIP SHA-256 `e89c630f6e0e4c2205aad778b54b934daa2b9b650a748915f0074d698fb45ffc`.

The exact reproduced output records `mutated_store: true`, `appended_epoch2_provenance: true`, a failed first exact retry caused by the pre-existing semantic mismatch, then a second exact retry result of `ALREADY_COMMITTED` while history remains `INCOMPLETE_OR_CORRUPT` and authority remains `HOLD_COMMITTED_HISTORY_INCOMPLETE`.

Two earlier verifier-harness attempts are intentionally not hidden: one invoked the original Wave-112 scaling self-test rather than the builder's exact CI wrapper and hit the already-disclosed monkeypatch-signature issue; another omitted `tools/` from the standalone verifier import path. Both were verifier harness mistakes, not builder failures, and were corrected before the successful reproduction above.

No builder files are rewritten and nothing is auto-merged or promoted to CANON.

## Next adversarial gate

Before any recovery write:

1. validate the complete existing provenance prefix semantically against committed markers, transitions, checkpoint state, and registry continuity;
2. stage the missing provenance append transactionally or roll it back if final validation fails;
3. return `ALREADY_COMMITTED` only after full Wave-112 status is `VALID`;
4. then crash/fault-inject before append, during append, after append-before-validation, and after validation, including restart and repeated retry;
5. only after recovery is atomic should the commit-decision witness move into a separate OS process.
