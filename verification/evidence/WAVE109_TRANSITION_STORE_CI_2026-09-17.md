# Wave 109 transition-store verifier CI receipt

Date: 2026-09-17  
Verifier PR: #34  
Verifier branch: `chatgpt/verifier-wave109-transition-store`  
Verifier tested head: `f86db24e249fba560018ffce1049b7538ccd3837`  
Builder base head: `84c5f53f4a6e9ffafc013db634adba485cd44479`  
Exact Wave-109 tested source commit: `1747e087d3ab07312484980da987b88f8e8f56cd`

## Successful independent run

GitHub Actions run: `35204202093`  
Job: `105145889080`  
Conclusion: `success`

Steps:

- unchanged Wave-109 builder self-test: `success` (`18/18` controls);
- adversarial transition-store reproducer, normal Python: `success`;
- adversarial transition-store reproducer, `python -O`: `success`.

Both adversarial invocations emitted:

`FAIL_SURVIVING_TRANSITION_RECORD_IGNORED_BY_COMMIT_STATUS_GUARD`

Both also showed:

- `transition_store.retained = true`;
- `transition_store.exact_epoch2_identity_match = true`;
- epoch-2 authority-link/checkpoint/signer-use/root-binding bodies erased;
- epoch-2 transition record **not** erased;
- Wave-109 commit-status classification: `VALID` with `committed_count = 1`;
- Wave-109 authority: `AUTHORITATIVE_QUORUM_2_OF_3_MODELED`.

The normal-Python run retained a sealed transition naming exact epoch-2 authority, checkpoint and app-state/root-binding identities. The optimized run reproduced the same semantic result with independently generated identities.

## Harness correction retained in history

The first verifier CI attempt, run `35204023529` / job `105145314679`, failed before the reproducer executed because the verifier script did not put repository `tools/` on Python's import path. The unchanged Wave-109 builder self-test passed in that failed harness run. Commit `f86db24e249fba560018ffce1049b7538ccd3837` corrected only the verifier import path; the builder source was untouched. The successful run above is the evidentiary run.

## Bounded interpretation

The surviving transition record is a prepare-time transaction artifact, not by itself proof that epoch 2 committed. The failure is narrower: Wave 109's own safety-over-availability rule treats retained unmanifested transaction evidence as commit-status ambiguity and HOLDs, but `transition_store` is omitted from that evidence boundary. Therefore the builder's wording that stale-prefix authority requires erasing **all** newer local transaction evidence is false under the modeled state actually retained by the normal prepare/commit path.

No hash, credential, witness identity, or transition body was forged. This verifier does not promote the result to CANON and does not merge builder code.
