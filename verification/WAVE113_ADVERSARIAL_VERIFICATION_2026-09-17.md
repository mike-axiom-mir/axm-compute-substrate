# Wave 113 independent adversarial verification — recovery transition identity

Date: 2026-09-17
Builder branch: `chatgpt/lane-001-platform-extract`
Exact builder head inspected: `3a2a19a9317291da82bda34d7dbe5fbc5d2a4ac7`
Exact builder CI-tested Wave-113 source: `dfedcab483ba6f798e0cd8e18a8a0c893397efd5`
Verifier lane: `verifier/wave113-recovery-transition-identity`
Status: verifier-only, draft/unmerged, non-CANON

## What survives

Wave 113 materially repairs verifier PR #37's exact mutate-then-fail problem. Its positive path requires a fully valid retained provenance prefix before the one allowed trailing recovery append, restores the provenance store on same-process append/validation exceptions, and refuses `ALREADY_COMMITTED` unless the complete Wave-112 history validates as `VALID`.

The builder's exact-source report records unchanged Wave 112 regression **22/22 PASS**, Wave 113 normal **25/25 PASS**, and Wave 113 `python -O` **25/25 PASS**. The independent verifier CI also reran the unchanged Wave-113 self-test and it remained **25/25 PASS**. Its scope statement remains bounded: no new wall-clock, energy, retained/incremental/dormant-compute, OS-process, device, network, physical-monotonicity, or provider-independence result is claimed.

## New adversarial question

After the lower Wave-110 commit is durable but before the Wave-111 provenance row is written, what durable evidence binds the *exact transition SHA* that performed that commit?

Wave 113 recovery searches the retained transition store for exactly one transition targeting the committed authority, validates its known semantics, and then writes provenance binding that surviving SHA. But the lower durable commit itself does not root the transition SHA.

The Wave-100 transition schema is sealed/content-addressed but does not reject unknown extra fields. Later Wave-110/Wave-111 semantic validation checks the known authority/checkpoint/state/registry fields and ignores additional fields. Therefore a newly content-addressed transition can preserve every checked semantic field while having a different identity.

## Reproducer

`verification/wave113_recovery_transition_identity_repro.py`

The attack:

1. Create genesis and a normal fully accepted epoch 1.
2. Prepare epoch 2 and preserve its genuine transition body/SHA.
3. Execute only the lower Wave-110 epoch-2 commit, recreating the documented missing-trailing-provenance crash window.
4. Leave the committed epoch-2 authority/checkpoint/use bodies and Wave-108 commit/high-water markers intact.
5. Delete only the genuine, still-unprovenanced epoch-2 transition body.
6. Create a semantically identical transition body with one additional ignored field, reseal it, and store it under its new content-addressed transition SHA.
7. Retry Wave-113 commit/recovery using the replacement SHA.
8. Check whether Wave 113 writes provenance binding the replacement transition, reports complete history `VALID`, and allows the recovered world to become authoritative after ordinary publication/certification.

No hash collision, credential forgery, authority/checkpoint replacement, Wave-108 marker rewrite, or whole-world rollback is used.

A duplicate-survivor control also keeps both original and replacement transitions. It correctly remains non-VALID because the committed authority has multiple matching retained transitions. This distinguishes the actual boundary: Wave 113's uniqueness rule works only while the original transition survives.

## Confirmed independent result

Preserved verdict:

`FAIL_RECOVERY_BINDS_SUBSTITUTED_TRANSITION_IDENTITY`

Independent CI run: `35225948399`
Job: `105217445642`
Conclusion: **success** (a green verifier job means the adversarial failure reproduced and the positive controls survived).

Normal Python reproduced:

- genuine one-row recovery control: `COMMITTED_RECOVERED_PROVENANCE_ATOMIC`, then `VALID`;
- replacement transition had a different SHA while preserving every checked transition semantic and differing only by one ignored extra field;
- genuine unprovenanced trailing transition removed: yes;
- pre-retry history: `INCOMPLETE_OR_CORRUPT`;
- Wave-113 retry with replacement SHA: `COMMITTED_RECOVERED_PROVENANCE_ATOMIC`;
- post-retry history: `VALID`;
- resulting provenance row bound the replacement transition SHA;
- normal publish to all three modeled remotes: `APPENDED` / `APPENDED` / `APPENDED`;
- certificate sync: `CERTIFIED`;
- final authority: `AUTHORITATIVE_QUORUM_3_OF_3_MODELED`.

`python -O` independently reproduced the same verdict and authority outcome.

Verifier artifact:

- artifact id: `10499315478`
- name: `verifier-wave113-recovery-transition-identity`
- SHA-256: `96ab2f0134cd5f567cbfb97014c27e5b2d034ce12aeed8ba6db7f3107e6cc365`

Meaning: the recovered provenance row currently proves "this is the only currently surviving semantically compatible transition" rather than "this is the exact transition that actually performed the lower durable commit."

This is a provenance/identity failure in the documented crash-recovery window. It is not, by itself, a stale-authority takeover or a performance/energy result.

## Next adversarial gate

Root the exact `transition_sha` in the durable lower commit decision itself, before the provenance append can be lost. Recovery should accept a missing provenance row only when the independent/lower durable decision says exactly `(authority_sha, transition_sha)` committed. Also make the transition schema exact/canonical enough that unknown fields cannot silently create a second content identity with identical validated semantics. Then attack:

- original transition deletion + semantically equivalent replacement;
- extra-field / schema-extension identity changes;
- two semantically equivalent retained transitions;
- transition-store truncation after commit;
- crash before and after the exact transition decision becomes durable;
- mismatched recovery transition with identical target state/checkpoint;
- process restart using a stale transition store.

Only after that exact identity is durable should OS-process separation be treated as stronger finality evidence.
