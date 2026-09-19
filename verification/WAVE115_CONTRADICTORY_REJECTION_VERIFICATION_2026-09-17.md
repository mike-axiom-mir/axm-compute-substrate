# Independent adversarial verification — Wave 115 contradictory rejection outcomes

Date: 2026-09-17

## Lane and provenance

- Repository: `mike-axiom-mir/axm-compute-substrate`
- Builder working branch observed at verification start: `chatgpt/lane-001-platform-extract`
- Builder head observed at verification start: `8f183d61e9874fd821ec2c03c222f13711d7b8ff`
- Builder exact tested Wave 115 source: `ad03fc8582a8ac6d8b294c494fa8b2fabb142dc6`
- Separate verifier branch: `chatgpt/verifier-wave115-conflicting-rejections`
- Verifier workflow source head: `f98db5b397c075e02713ef9cddc8bb7bec95efd9`
- Verifier Actions run: `35239141257`
- Verifier job: `105262730665`
- Verifier artifact: `10504223866`
- Artifact SHA-256: `7f30c813632c66db33069595c62fd2673b7dd07c8111b74aa5f864a1e0b0d816`
- Artifact size: 8264 bytes

This verifier lane does not modify builder files, delete or rewrite prior evidence, merge itself, or promote CANON.

## Builder result that survived

The unchanged Wave 115 broad self-test passed independently in both ordinary Python and `python -O`: 42/42 PASS in each mode. The unchanged focused rejection-identity self-test also passed 9/9. The intended Wave 114 repair therefore survives its published controls: a semantically rejected transition is prevalidated before the real commit decision, its raw transition body is retained, the rejection receipt binds the exact rejected transition SHA and the observed stable lower result, and the genuine sibling can subsequently commit.

The builder's own truth boundary also remains in force: this is still one modeled Python failure domain; deepcopy preflight is not process independence; there is no wall-clock performance, energy, retained/incremental/dormant-compute, physical/provider-independence, concurrent mutation, process/power-loss atomicity, real AXM workload, or scaling claim in this wave.

## New counterexample

Verdict: `FAIL_CONTRADICTORY_REJECTION_OUTCOMES_ACCEPTED_AS_VALID_HISTORY`

The Wave 115 writer path refuses to append a second conflicting rejection for one transition, but the retained-history verifier does not enforce the same invariant. It validates each self-sealed rejection body plus sequence/predecessor continuity, yet does not require a unique terminal `lower_result` for each exact `transition_sha`.

Reproduction:

1. Start a clean Wave 115 world and prepare a genuine transition.
2. Create a correctly content-addressed sibling whose `transition_kind` is wrong while its authority/checkpoint identity remains the same.
3. Submit that bad transition through the public Wave 115 commit path. It returns `TRANSITION_DELTA_HOLD` and appends one legitimate rejection receipt.
4. Re-run the exact lower semantic prevalidation on that same transition before adding the adversarial row. It again returns `TRANSITION_DELTA_HOLD`.
5. Without deleting or rewriting anything, append a second correctly self-sealed, next-sequence, correct-predecessor rejection body for the exact same transition SHA, but claim `TRANSITION_GENERATION_HOLD`.
6. Wave 115's retained rejection verifier accepts both rows without error.
7. Commit the genuine sibling, publish, certify, and evaluate retained history and authority.

Normal Python reproduced:

- accepted rejection rows: 2
- actual first public result: `TRANSITION_DELTA_HOLD`
- repeated actual lower result: `TRANSITION_DELTA_HOLD`
- accepted claimed results for the same transition: `TRANSITION_DELTA_HOLD`, `TRANSITION_GENERATION_HOLD`
- genuine sibling commit: `COMMITTED`
- final history: `VALID`
- final authority: `AUTHORITATIVE_QUORUM_3_OF_3_MODELED`

`python -O` reproduced the same verdict and the same semantic outcome pattern.

## Severity boundary

This is a rejection-ledger provenance/integrity failure, not a stale-authority takeover. No hash collision or hash forgery was used. No existing evidence was rewritten or deleted. Builder files were not modified. The attack demonstrates that the append-only evidence layer can simultaneously treat two mutually incompatible terminal outcomes as valid facts about one exact transition identity.

Because the current rejection receipt is content-addressed but not independently authenticated as an observation from a uniquely authorized semantic outcome witness, self-sealing proves only internal body integrity. It does not by itself prove that a newly appended contradictory terminal outcome was the lower validator's result.

## Next adversarial gate

Before treating a separate OS-process outcome witness as stronger finality evidence:

- require at most one terminal rejection outcome per exact `transition_sha`, enforced by the verifier as well as the writer;
- reject duplicate/conflicting terminal rows fail-closed even when each row is individually well sealed and the sequence chain is intact;
- bind outcome authority/authentication so an arbitrary same-domain writer cannot manufacture a new terminal result merely by recomputing the content hash;
- attack duplicate same-result rows, conflicting-result rows, a forged rejection for an actually valid transition, rejection-chain truncation/replay, witness restart, and retained-history reconstruction.

Until those survive, Wave 115 is boundedly successful at prevalidating before COMMIT, but its new rejection evidence is not yet a single-valued authoritative record of the lower semantic outcome.
