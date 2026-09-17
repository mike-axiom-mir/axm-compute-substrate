# Wave 116 independent adversarial verification — outcome-authority root substitution

Date: 2026-09-17

Lane: `chatgpt/verifier-wave116-outcome-root-substitution`

Status: **draft / unmerged / non-CANON**. No builder files are modified by this verification lane.

## Exact builder state

- Newest observed builder evidence head: `fc9d6b0f88d9acbfb1ff5b5fcbb2a4a50de5224b`
- Exact Wave-116 tested source: `b47136f228679ef72130d5e043e56743d00257f8`
- Wave-116 tool blob: `9b3459d84766cea56e293d4cdf573d8457c51b8f`
- Builder receipt CI: run `35242671779`, job `105274825571`, artifact `10506615108`, artifact SHA-256 `9595b9322fe618606e813ed78f44edbe1942a1ab8e1438d04d50ef576c3df8f5`
- Builder receipt reports: Wave-115 regression 42/42, focused identity regression 9/9, Wave-116 normal 28/28, Wave-116 `python -O` 28/28.

Independent verifier CI reran the unchanged Wave-116 self-test in both modes and both passed 28/28.

## What survives

Wave 116 materially repairs verifier PR #40 for the direct case it tests. With the original retained binding intact:

- a caller-supplied different outcome credential is rejected;
- a forged outcome HMAC is rejected;
- unauthenticated or multiply authenticated contradictory rejection rows fail closed;
- one exact transition cannot retain both COMMIT and authenticated REJECT terminal outcomes;
- the normal rejected bad sibling -> genuine sibling commit path remains VALID/AUTHORITATIVE.

The Wave-116 truth boundary also remains appropriately narrow: same-process HMAC is not OS-process isolation, hardware-key security, power-loss atomicity, physical monotonicity, provider independence, performance, energy, or retained/incremental/dormant-compute evidence.

## New reproduced failure

**`FAIL_OUTCOME_AUTHORITY_ROOT_SUBSTITUTION_ACCEPTS_RESEALED_CONTRADICTORY_HISTORY`**

The direct credential-substitution control protects the credential *after the retained binding is assumed trustworthy*. The verifier tested whether that binding is itself rooted outside the mutable retained state.

Sequence:

1. Create a normal Wave-116 world and prepare a genuine transition plus a semantically invalid sibling.
2. Commit the bad sibling normally. The actual lower semantic checker returns `TRANSITION_DELTA_HOLD`, and a repeated exact prevalidation returns `TRANSITION_DELTA_HOLD` again.
3. Confirm that merely supplying a fresh outcome credential while retaining the original Wave-116 binding fails closed with credential substitution.
4. Do **not** forge or learn the original HMAC secret.
5. Replace only these three Wave-115/116 evidence objects:
   - the Wave-116 outcome-authority binding, with a correctly self-sealed binding naming a fresh credential;
   - the single Wave-115 raw rejection row, with a correctly content-addressed row for the same transition/authority/checkpoint but claiming `TRANSITION_GENERATION_HOLD`;
   - the single Wave-116 authenticated outcome row, correctly HMAC-signed by the fresh credential and matching that replacement raw row.
6. Leave the lower runtime, transition store, certificate store, and certificate-witness domain unchanged.
7. With the old credential, Wave 116 correctly fails closed. With the fresh credential matching the replacement binding, the Wave-116 authentication layer accepts the replacement root/history. At this point the lower layer still reports `UNRESOLVED_COMMIT_STATUS` solely because the genuine prepared sibling remains unmanifested.
8. Commit that genuine sibling normally using the accepted replacement root, publish, and certify.
9. Final retained history becomes `VALID` and authority becomes `AUTHORITATIVE_QUORUM_3_OF_3_MODELED`, while the retained authenticated rejection says `TRANSITION_GENERATION_HOLD` even though the exact semantic checker actually returned `TRANSITION_DELTA_HOLD` twice.

Thus Wave 116 authenticates rejection outcomes relative to a credential identity whose binding is itself replaceable inside the same mutable retained state/caller-selected domain. The HMAC prevents forging the *old* signer, but it does not yet prove that the supplied signer is the historically authorized signer.

## Boundary / severity

This verifier does **not** claim:

- a stale-authority takeover;
- a hash collision;
- compromise or forgery of the original outcome HMAC;
- replacement of the lower runtime;
- replacement of the certificate store/domain;
- replacement of the transition store;
- speed, energy, retained/incremental/dormant-compute, network, device, OS-process, or provider results.

The attack does replace the Wave-116 binding plus one raw rejection row and one authenticated outcome row. It is therefore an outcome-trust-root / provenance-authenticity failure, not proof that all retained lower authority state can be rolled back.

## Independent CI evidence

Exact CI-tested verifier head: `109071ef87ead838148a96395d8ed0d3cc6681ea`

Successful final run:

- run: `35245832410`
- job: `105285669536`
- unchanged Wave-116 self-test: success, 28/28
- unchanged Wave-116 self-test under `python -O`: success, 28/28
- adversarial reproducer: success / failure reproduced
- adversarial reproducer under `python -O`: success / failure reproduced
- artifact: `10507127398`
- artifact SHA-256: `28d232805a8c3159966947cd3560dd442e8b775c5d253a6fa6ffcaeb3cda9634`

Both adversarial reports preserve:

- actual semantic result: `TRANSITION_DELTA_HOLD`
- replacement authenticated claim: `TRANSITION_GENERATION_HOLD`
- genuine sibling commit: `COMMITTED`
- certificate result: `CERTIFIED`
- final status: `VALID`
- final authority: `AUTHORITATIVE_QUORUM_3_OF_3_MODELED`

An earlier run `35245623173` is intentionally preserved as verifier evidence too. The unchanged builder self-tests passed, but the first adversarial harness used an overly strict intermediate assertion that expected the prepared world to be immediately AUTHORITATIVE after the signer swap. The actual intermediate result was the legitimate lower `HOLD_COMMIT_STATUS_UNRESOLVED` caused by the still-unmanifested genuine sibling. The verifier was corrected to distinguish that lower transaction hold from rejection of the substituted outcome root; no builder code was changed between those attempts.

## Next adversarial gate

Root the exact outcome-authority identity outside the mutable Wave-116 binding itself. A viable next contract should make the initial signer part of an already monotonic trust anchor (for example genesis/boot/commit-decision/certificate-witness state) and require any signer rotation to be explicitly authorized by the previously trusted root with monotonic lineage.

Then test, separately:

- binding-only signer substitution;
- binding + full authenticated outcome-chain substitution;
- tail truncation and replay;
- signer rotation with correct old-root authorization;
- signer rotation without old-root authorization;
- crash boundaries during rotation;
- restart with stale signer configuration;
- finally a genuinely separate OS-process witness, while preserving the anchored signer identity contract.
