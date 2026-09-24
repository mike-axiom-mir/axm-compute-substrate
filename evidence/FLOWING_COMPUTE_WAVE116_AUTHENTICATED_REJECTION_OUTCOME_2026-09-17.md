# Flowing Compute Wave 116 — Authenticated Single-Valued Rejection Outcomes

Date: 2026-09-17
Lane: `chatgpt/lane-001-platform-extract` / PR #2
Status: experimental evidence only; no merge, auto-merge, or CANON promotion

## Why this wave happened

Independent verifier PR #40 (`chatgpt/verifier-wave115-conflicting-rejections`, head at Wave-116 start `fb478e4b5bdf040250ac1ad950bbd1fc81123e8e`) found a real Wave-115 truth-boundary defect. Wave 115 verified each rejection row's content identity and predecessor chain, but did not make the terminal rejection outcome single-valued for one exact transition SHA. A second correctly self-sealed rejection row could name the same exact transition while claiming a different stable `lower_result`; the retained history could still become `VALID`, a genuine sibling could commit, and authority could still become `AUTHORITATIVE_QUORUM_3_OF_3_MODELED`.

This is primarily a terminal-outcome/provenance integrity defect. The verifier did not demonstrate a stale-authority takeover from the contradiction alone.

## Gamer / beginner model

Imagine one exact save ticket. Wave 115 could keep two individually valid-looking cards saying:

- "this exact ticket was permanently rejected because X", and
- "this exact same ticket was permanently rejected because Y".

The cards were chained and self-sealed, but nobody authoritative had to sign which terminal outcome was the real one. Wave 116 adds a bound referee credential and a second append-only authenticated outcome ledger. A raw rejection is not trusted as terminal history unless exactly one authenticated outcome names that exact raw rejection, transition, checkpoint, authority and lower result.

## Repair

Reusable tool:
`tools/AXM_FLOWING_COMPUTE_AUTHENTICATED_REJECTION_OUTCOME.py`

Adversarial self-test:
`tools/AXM_FLOWING_COMPUTE_AUTHENTICATED_REJECTION_OUTCOME_SELFTEST.py`

Exact-source workflow:
`.github/workflows/wave116-authenticated-rejection-outcome.yml`

Wave 116 is additive over Wave 115 and preserves the raw Wave-115 rejection ledger. It adds:

1. a sealed binding to one outcome-authority identity;
2. an HMAC-authenticated append-only rejection-outcome chain;
3. exact one-to-one raw-rejection ↔ authenticated-outcome cardinality;
4. exactly one terminal REJECT per exact transition SHA;
5. fail-closed detection if one transition appears in both COMMIT and REJECT terminal evidence;
6. no permanent outcome record for retriable/uncertain HOLD results.

The HMAC secret is deliberately outside retained state, but it is still in the same Python process. This is an explicit credential boundary for the next experiment, not a claim of OS-process, hardware-key, device, network, or provider independence.

## Positive and negative evidence

The self-test first reproduces verifier PR #40 against unchanged Wave 115: two contradictory rejection rows for one exact transition are accepted, a genuine sibling commits, final status is `VALID`, and authority is `AUTHORITATIVE_QUORUM_3_OF_3_MODELED`.

Under Wave 116:

- one stable bad transition produces exactly one raw rejection and one authenticated outcome;
- retrying the exact rejected transition is idempotent and does not duplicate either ledger;
- the genuine sibling still commits and final history is `VALID` / authoritative;
- an unauthenticated contradictory raw rejection makes history `INCOMPLETE_OR_CORRUPT` and authority `HOLD_COMMITTED_HISTORY_INCOMPLETE`;
- even a second correctly authenticated but contradictory terminal outcome for the same exact transition fails with `rejection-transition-terminal-outcome-not-unique`;
- a forged outcome authentication tag fails closed;
- substituting another outcome credential fails closed;
- simultaneous COMMIT + REJECT terminal evidence for one exact transition fails closed;
- a retriable `TRANSITION_VALIDATION_HOLD` creates no raw rejection and no authenticated terminal outcome.

## Preserved counterexample / failure boundary

Wave 116 deliberately injects a crash after the raw rejection is appended but before the authenticated outcome is published. The raw evidence survives, the authenticated outcome is absent, history becomes `INCOMPLETE_OR_CORRUPT`, and authority HOLDs. Wave 116 does not invent or reconstruct the missing authenticated fact.

This is safe but not live recovery. The raw-rejection → authenticated-outcome publication boundary is the next durability/process-separation problem.

The older whole-modeled-domain rollback counterexample is also inherited: if every newer modeled fact and credential-bearing state is rolled back together to a genuine older snapshot, the model still lacks an independent surviving fact that proves a newer outcome existed.

## Exact tested source and CI

Exact tested source commit:
`b47136f228679ef72130d5e043e56743d00257f8`

Exact tested blobs at that commit:

- Wave-116 tool: `9b3459d84766cea56e293d4cdf573d8457c51b8f`
- Wave-116 self-test: `dd3b4d987d78b08ae1136771dcff2d3d4d4c427e`
- Wave-116 workflow: `d5a2caca6918fae7558bb919f3d768ad313fe82c`
- unchanged Wave-115 tool: `7279d1aa84df3efec5848ea98fe601a590ffc2a9`
- unchanged Wave-115 self-test: `f31881af1fa976fa1c125f4d84f613b1af1cd680`
- Wave-115 rejection-identity self-test: `9f85264227a9061c406469720f88ac90378d015d`

GitHub Actions run `35242671779`, job `105274825571`, completed successfully on the exact tested commit.

Observed reports from the uploaded CI artifact:

- unchanged Wave-115 regression: 42 / 42 passed;
- unchanged Wave-115 rejection-identity regression: 9 / 9 passed;
- Wave 116 normal Python: 28 / 28 passed;
- Wave 116 `python -O`: 28 / 28 passed.

Artifact:

- id: `10506615108`
- name: `wave116-authenticated-rejection-outcome-reports`
- SHA-256: `9595b9322fe618606e813ed78f44edbe1942a1ab8e1438d04d50ef576c3df8f5`

The artifact ZIP was downloaded and independently SHA-256 checked against the GitHub-reported digest before this evidence note was written.

## Truth boundary

No real AXM/monolith workload benchmark was run in this wave because the verifier correctness defect took priority. No synthetic scaling run was used either. Therefore this wave makes no new performance, energy, retained-state, incremental-compute, dormant-compute, monolith-speed, network, device, process-independence, physical-finality, or provider-independence claim.

Everything in the new outcome-authority implementation is still one modeled Python failure domain. Python introspection is not treated as a security boundary.

## Next gate — Wave 117

Move the outcome witness into a genuinely separate OS process with its own durable store and credential, then attack the publication and rollback boundaries rather than merely adding another in-memory ledger. Required cases include:

- crash before raw local rejection persistence;
- crash after raw rejection but before witness publication (the preserved Wave-116 HOLD case);
- witness publication durable before local observation;
- full local rollback while the independent witness remains newer;
- witness restart, loss, truncation and corruption;
- credential substitution;
- stale/cloned local disks;
- partition/reconnect and simultaneous old/new process views;
- conflicting COMMIT/REJECT and double-REJECT/different-result proposals;
- proving retriable HOLD cannot silently become a permanent REJECT.

Even a successful Wave 117 would prove only the tested process/store separation contract, not physical monotonic storage or provider-independent finality.
