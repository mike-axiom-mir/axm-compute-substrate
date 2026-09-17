# Flowing Compute Wave 115 — Prevalidated Commit Decision

Date: 2026-09-17
Lane: `chatgpt/lane-001-platform-extract`
Status: experimental evidence only; no merge, auto-merge, or CANON promotion.

## Why this wave happened

Independent verifier PR #39 challenged exact Wave 114. Wave 114 could seal a durable `COMMIT` decision for a strict-field, correctly content-addressed transition **before** the lower transition semantic contract had accepted it. The verifier changed only the declared registry transition kind, resealed the body, and reproduced this sequence:

- the adversarial transition became the durable decision identity;
- the lower layer returned `TRANSITION_DELTA_HOLD`;
- the genuine transition remained retained and semantically valid;
- retrying that genuine transition failed with `ValueError:decision-authority-bound-to-different-transition`;
- commit status remained unresolved and authority remained HOLD.

This was therefore a liveness / evidence-integrity / decision-semantics defect, not a demonstrated stale-authority takeover.

Verifier identity at Wave-115 start:

- verifier PR: `#39`
- verifier head: `8bf3003ed765210cbbfbfc5cd0bc3ef044777987`
- verifier tested source/workflow head: `1769f6fc1b17ea0f3cd749c581473806528882d8`
- verifier CI run/job: `35232714178` / `105240688233`
- verifier artifact: `10501523595`
- verifier artifact SHA-256: `3a9122f3e759319dcbcea1faa1d22bcbb6e3579dc5628a4b79c7c185a310ab69`

## Preserved failed first repair

The first Wave-115 attempt prevalidated before writing the real COMMIT decision, but simply left the rejected transition in the raw transition store. That did **not** solve the whole contract: after the genuine transition committed, retained-history validation found both the rejected and genuine transition matching the same authority and failed with:

`committed-authority-transition-match-not-unique`

That attempt is not credited as successful. Its failed CI evidence is retained:

- run/job: `35236136821` / `105252409348`
- artifact: `10503004371`
- artifact SHA-256: `c381e9bafc4c895676b7395466db1dd3613b4171c34a365bfc39b3008d661be9`

The repair did **not** delete the rejected transition to make the tests green.

## Final Wave-115 contract

Wave 115 keeps the raw rejected transition body and adds an append-only sealed rejection ledger. The commit path now:

1. runs the exact lower Wave-110 commit semantics on deep-copied state with the exact Wave-114 decision that would exist during the real commit;
2. if prevalidation returns a stable semantic rejection, records an exact sealed rejection receipt and leaves the real COMMIT decision, provenance, and runtime untouched;
3. filters only transition identities backed by valid rejection receipts from later ambiguity scans, while preserving their raw bodies as counterevidence;
4. writes the real exact COMMIT decision only after successful semantic prevalidation, then runs the real lower commit and provenance path.

The rejection receipt binds `authority_sha`, exact `transition_sha`, checkpoint, exact lower result, sequence, predecessor rejection SHA, schema, and its own content-addressed seal.

Only stable semantic outcomes are tombstoned. Broad/state-dependent failure such as `TRANSITION_VALIDATION_HOLD` from missing registry evidence is deliberately **not** converted into a permanent rejection; it remains unresolved/incomplete so later evidence is not silently pre-judged.

Tampered rejection evidence fails closed. If isolated prevalidation says COMMITTED but the real lower call later differs, the decision is kept visible and the path returns `HOLD_LOWER_CHANGED_AFTER_PREVALIDATION:<result>` rather than deleting append-only evidence.

## Exact tested source and provenance

Final exact tested source commit:

`ad03fc8582a8ac6d8b294c494fa8b2fabb142dc6`

Blobs at that commit:

- Wave-115 tool: `7279d1aa84df3efec5848ea98fe601a590ffc2a9`
- broad self-test: `f31881af1fa976fa1c125f4d84f613b1af1cd680`
- focused exact rejection-identity self-test: `9f85264227a9061c406469720f88ac90378d015d`
- workflow: `13f5e7cdb9eba3f071526d7315fb967132c5dd86`

Final CI:

- run: `35237020219`
- job: `105255433344`
- exact checkout: `ad03fc8582a8ac6d8b294c494fa8b2fabb142dc6`
- result: success
- artifact: `10503696423`, `wave115-prevalidated-commit-decision-reports`
- artifact size: 8803 bytes
- artifact ZIP SHA-256: `a92d7ac96fe0879f75ed314b48b25708428433cf57e7503f632df2350632ffbb`

Exact CI results:

- unchanged Wave 114 regression: **20/20 PASS**
- Wave 115 broad self-test: **42/42 PASS**
- Wave 115 broad self-test under `python -O`: **42/42 PASS**
- focused exact rejection-identity test: **9/9 PASS**
- focused exact rejection-identity test under `python -O`: **9/9 PASS**

The focused identity test exists because the broad test's named identity control was weaker than its name implied; the focused test performs the actual SHA equality checks. In the normal focused run, the rejected transition SHA and rejection receipt both equal `dc5ce5df422374e01c73bc32f69ee408f0f019df2748e9f1a30a53c2b49f359d`, while the genuine transition and COMMIT decision both equal `699b4c3786f8fdbf16ecbf7778057d7347caf0d9bb90934a8d2f0cc0d9b94a41`. The optimized run independently passed the same exact-identity checks.

## Positive and negative evidence

Positive:

- genuine retry after a rejected semantic sibling commits successfully;
- final history returns `VALID` and authority returns `AUTHORITATIVE_QUORUM_3_OF_3_MODELED`;
- a subsequent prepare succeeds, so the rejected sibling no longer permanently poisons forward progress;
- two normal epochs remain VALID with exact decision transition SHAs equal to the committed transition SHAs and zero rejection receipts.

Negative/adversarial:

- verifier-39 Wave-114 poisoning is reproduced unchanged before crediting the repair;
- generation mismatch returns `TRANSITION_GENERATION_HOLD` and gets an exact rejection receipt;
- state-binding mismatch returns `TRANSITION_STATE_BINDING_HOLD` and gets an exact rejection receipt;
- missing registry evidence returns `TRANSITION_VALIDATION_HOLD` but is **not** permanently rejected;
- tampering a rejection receipt causes `INCOMPLETE_OR_CORRUPT` and `HOLD_COMMITTED_HISTORY_INCOMPLETE`;
- crash after real decision but before lower commit leaves history unresolved, lower runtime/provenance unchanged, retains the exact decision, and exact retry can commit;
- crash after lower commit but before provenance leaves history incomplete until exact recovery returns `COMMITTED_RECOVERED_EXACT_DECISION`.

## Counterexample retained

The whole-modeled-domain rollback counterexample still survives. If the entire modeled world is rolled back together, including newer commit decisions **and** rejection evidence, the genuine older snapshot can still return:

`AUTHORITATIVE_QUORUM_3_OF_3_MODELED`

Wave 115 therefore does not claim independent durability or finality.

## Truth boundary / non-claims

Wave 115 is still one modeled Python failure domain. Deep-copy prevalidation is not process independence, concurrent-mutation proof, power-loss atomicity, durable-device proof, network proof, physical independence, or provider independence.

No real AXM/monolith workload and no synthetic scaling workload were run in this wave because the correctness/evidence-integrity gate took priority. No performance, energy, retained-compute, incremental-compute, dormant-state, or Flowing-Compute efficiency win is claimed.

## Next gate — Wave 116

Move the exact outcome witness into a genuinely separate OS process with its own durable store and credential. The external witness must distinguish at least **COMMIT**, stable terminal **REJECT**, and retriable **HOLD**; it must not silently turn uncertain/state-dependent HOLD into permanent rejection.

Attack: crash before/after witness publication, local rollback while witness remains newer, rejected-body substitution, stale/cloned disks, witness outage/restart/staleness, witness-store loss/truncation/tamper, credential substitution, partitions/reconnects, simultaneous old/new process views, and misclassification of state-dependent HOLD. A pre-Wave-115 migration policy remains a separate explicit gate; no rejection history should be invented retroactively.
