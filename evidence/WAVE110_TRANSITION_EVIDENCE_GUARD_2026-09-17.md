# Wave 110 — Transition-store evidence guard

Date: 2026-09-17
Lane: `chatgpt/lane-001-platform-extract` / PR #2
Status: experimental, unmerged, not CANON

## Trigger

Independent verifier PR #34 tested Wave 109 builder head `84c5f53f4a6e9ffafc013db634adba485cd44479` and exact tested source commit `1747e087d3ab07312484980da987b88f8e8f56cd`.

Verifier source/provenance identity:

- verifier PR: #34
- verifier head: `5bb440a9e7428ba0dbd4eb40f97f561e4215d471`
- verifier evidence blob: `b1af4cd5608171191e6974d4e322a399c04544dd`
- verifier reproducer blob: `dc870b6f63dae94e243d152a033c1b1565c5f3db`
- verifier CI run: `35204202093`
- verifier job: `105145889080`
- preserved verdict: `FAIL_SURVIVING_TRANSITION_RECORD_IGNORED_BY_COMMIT_STATUS_GUARD`

The finding is semantic, not a hash or credential forgery. Wave 109 correctly HOLDs when it sees unmanifested authority-link/checkpoint/signer-use/root-binding evidence, but it did not inspect the normal Wave-100 `transition_store`. The verifier removed epoch-2 commit markers plus epoch-2 L/C/U/root-binding rows while deliberately retaining the sealed epoch-2 transition. That transition still named the exact newer authority SHA, checkpoint SHA, and root-binding SHA. Under unchanged Wave 109, the damaged local prefix was classified `VALID` and the partial stale quorum returned `AUTHORITATIVE_QUORUM_2_OF_3_MODELED`.

## Wave 110 change

Wave 110 adds the transition store as a first-class commit-status evidence family without changing or rewriting Wave 109.

For every committed authority named by the Wave-108 paired marker lineage, Wave 110 now requires exactly one valid sealed transition whose:

1. target authority is the exact committed authority;
2. target checkpoint is the exact checkpoint resolved from that authority link;
3. predecessor authority matches the prior committed authority in sequence;
4. target state binding still verifies from its target app-state/root-binding identity and registry identity.

A committed authority missing its exact transition, a duplicate match, malformed body, tampered seal, or broken predecessor relation is `INCOMPLETE_OR_CORRUPT`.

Any valid retained transition that is not accounted for by the committed marker lineage is `UNRESOLVED_COMMIT_STATUS`. Wave 110 does **not** infer whether that transaction was merely prepared or had once committed and then lost its marker/local-body evidence. Authority fails closed with `HOLD_COMMIT_STATUS_UNRESOLVED`.

## Positive cases

The exact self-test covers:

- clean genesis with an empty transition store;
- normal accepted epoch 1;
- normal accepted epoch 2;
- exact transition-lineage count matching committed history;
- legitimate prepare entering unresolved status;
- local commit clearing that ambiguity;
- normal authority after the accepted transition lineage;
- retained depth 6 as **synthetic correctness-only scaling**, with no timing claim.

## Negative / adversarial cases

The exact self-test covers:

- verifier PR #34's retained-transition stale-prefix attack;
- reproduction of the unchanged Wave-109 failure before applying the Wave-110 decision rule;
- removal of a transition required by a committed authority;
- tampering with a retained transition body without resealing it.

For the exact PR #34 attack, unchanged Wave 109 returned:

- commit-status state: `VALID`
- authority: `AUTHORITATIVE_QUORUM_2_OF_3_MODELED`

Wave 110 over the same attacked world returned:

- commit-status state: `UNRESOLVED_COMMIT_STATUS`
- reason: `retained-unmanifested-transition-evidence`
- authority: `HOLD_COMMIT_STATUS_UNRESOLVED`

## Exact-source CI

CI-tested source commit: `dfe22164f853cf1f04f0ae93103e33478ed074fd`

Exact source blobs at that commit:

- tool `tools/AXM_FLOWING_COMPUTE_TRANSITION_EVIDENCE_GUARD.py`: `abc96489922bcf7af64412a8e85cf447796321b1`
- self-test `tools/AXM_FLOWING_COMPUTE_TRANSITION_EVIDENCE_GUARD_SELFTEST.py`: `00b0eccac36cf479c81004ceac811a6af1293b85`
- workflow `.github/workflows/wave110-transition-evidence-guard.yml`: `eaf21f0aefa0576dbdc06f77c68fba9abfbd427e`

GitHub Actions run `35206504427`, job `105153493003`, completed successfully.

- unchanged Wave 109 regression: **18/18**
- Wave 110 normal Python: **20/20**
- Wave 110 `python -O`: **20/20**
- artifact: `wave110-transition-evidence-reports`
- artifact id: `10490167911`
- artifact digest: `sha256:4e536132a20f62976fe6807067a8565b97d54fa3540a024062624cd1c30d73bd`

The evidence/report commit is appended only after this exact-source run; it does not alter the tested tool, self-test, or workflow blobs.

## Preserved failures / counterexamples

Wave 110 still cannot recover a fact after every newer fact in the same modeled domain is gone. If a failure/attacker restores the commit markers to an older prefix **and** erases all newer L/C/U/root-binding rows **and** erases the newer transition row, the local evidence becomes a genuine older prefix again. With the same partial stale-quorum conditions and the only newer certificate witness unavailable, this one-process model can still accept the stale prefix.

A legitimate prepare also remains intentionally unavailable for authoritative reads until commit resolves its ambiguity. That is a conscious safety-over-availability cost, not a hidden success.

All authority, certificate, marker, binding, transition, witness, and credential stores remain modeled Python objects in one process. No OS-process durability, physically monotonic storage, device independence, provider independence, or crash-atomic commit publication has been demonstrated.

## Truth boundary

Wave 110 makes **no** fresh claim about:

- AXM/monolith workload speed;
- retained-compute advantage;
- incremental-compute advantage;
- dormant-compute advantage;
- energy or joules;
- networking;
- physical independence;
- provider independence;
- process-level persistence.

No synthetic timing benchmark was used. The depth-6 case is correctness-only synthetic scaling.

No merge, auto-merge, or CANON promotion is performed.

## Next gate

Wave 111 should introduce an **independently durable commit-decision witness/receipt** outside the local transaction+marker failure domain, then move that boundary into a real OS process with its own durable store and credential. The first target is not “three processes means safe”; it is proving that a committed transaction cannot become an innocent old prefix after local rollback while the independent decision witness survives.

Attack matrix for the next gate:

- crash before prepare;
- crash after prepare but before lower commit;
- crash after lower commit but before independent decision publication;
- crash after independent decision publication but before local marker persistence;
- local marker-tail rollback plus complete newer L/C/U/binding/transition erasure;
- independent decision witness unavailable;
- stale independent witness plus another authority witness unavailable;
- stale/cloned local process disk;
- certificate-tail rollback independently of commit-decision storage;
- partition/reconnect and simultaneous old/new process views;
- whole local process rollback while the independent witness retains the newer decision.

Success would be evidence for a process-separated durable decision boundary only. It would still not establish physical or provider independence.
