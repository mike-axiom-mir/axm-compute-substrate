# Independent adversarial verification — Wave 110

Date: 2026-09-17
Verifier lane: `chatgpt/verifier-wave110-transition-provenance`
Draft PR: #35
Builder base: `0d97d0dde7f3b72ff1da6ae68315c0e163330f75`
Exact builder-tested source: `dfe22164f853cf1f04f0ae93103e33478ed074fd`
Wave-110 tool blob: `abc96489922bcf7af64412a8e85cf447796321b1`
Wave-110 self-test blob: `00b0eccac36cf479c81004ceac811a6af1293b85`
Status: verifier-only, unmerged, not CANON

## What survived

Wave 110's direct repair for verifier PR #34 survives its intended case. The builder receipt records
Wave 110 as 20/20 in normal Python and 20/20 under `python -O`, and verifier CI reran the unchanged
Wave-110 self-test successfully in both modes before running this adversarial reproducer.

The semantic rule "a retained extra transition makes commit status unresolved" also works while the
lower Wave-109 history state is already VALID/UNRESOLVED and the genuine transition is retained.

## Primary failure — committed transition identity is substitutable

Preserved verdict:

`FAIL_COMMITTED_TRANSITION_IDENTITY_IS_SUBSTITUTABLE`

A real epoch 1 was committed, published, certified, and authoritative. Its genuine transition SHA was
then deleted from `transition_store`. No committed marker, authority link, checkpoint, binding,
certificate, remote witness, or certificate witness was changed.

The verifier inserted a *different* newly content-addressed transition body. It retained only the
committed authority SHA, committed checkpoint SHA, and predecessor relation. It deliberately changed:

- target app-state identity;
- target registry SHA to a SHA absent from the registry store;
- target state SHA accordingly;
- current registry SHA;
- current and target registry generations;
- transition kind;
- changed slot and changed-field semantics.

Wave 110 still returned commit status `VALID` with reason
`markers-retained-transaction-and-transition-evidence-agree`, treated the substitute transition SHA as
its `expected_transition_shas`, and returned `AUTHORITATIVE_QUORUM_3_OF_3_MODELED`.

This used no credential forgery, no hash collision, and no in-place modification of the original
transition body. The replacement was simply a new correctly content-addressed body. The root cause is
that no committed object retains the expected transition SHA, and Wave 110 does not re-check the
transition target-state against the committed checkpoint state or validate the transition's registry
step against `registry_store` while reconstructing commit status.

Therefore Wave 110 currently proves "one self-consistent transition-like body names the same
committed authority/checkpoint/predecessor", not "this is the exact transition that was prepared and
committed for that authority".

## Secondary failure — HISTORY_NONE bypasses surviving transition evidence

Preserved verdict:

`FAIL_TRANSITION_ONLY_EVIDENCE_IS_IGNORED_WHEN_WAVE109_REPORTS_NONE`

A real epoch 1 became authoritative and its genuine transition remained intact. The lower authority
world was then restored to the already-adopted saved-genesis image and the two Wave-108 marker-store
keys were removed, while `transition_store` was deliberately *not* rolled back.

Wave 109/Wave 108 reported `NONE`. Wave 110 returns immediately for that status before validating the
transition store, so the surviving accepted-epoch transition was ignored. Unchanged Wave 110 returned:

- commit-status state: `NONE`;
- reason: `wave109-base-wave108-base-pre-wave108-fresh-state-no-authority-history`;
- authority: `AUTHORITATIVE_GENESIS_MODELED`.

This is broader rollback than the primary provenance failure, so it is recorded as a secondary gate.
It is still materially narrower than Wave 110's published preserved counterexample because the newer
transition record survives. The Wave-110 report currently says stale-prefix acceptance requires the
newer transition row to be erased together with the other newer local evidence.

## CI evidence

Verifier workflow run: `35209627758`

Normal Python job: `105163740894` — success.
Optimized Python job: `105163741071` — success.

Both jobs reran the unchanged Wave-110 builder self-test first, then reproduced the verifier result.
The normal builder rerun remained 20/20 PASS.

Artifacts:

- `10491453206` — `wave110-transition-provenance-false`, digest `sha256:d21a7a6507dede1d0ef6490451763636b3ff974987499b688b93a9f029e480bd`
- `10491167895` — `wave110-transition-provenance-true`, digest `sha256:4333c815799f70c22b0ad1e66b2a6aba602d416badb9937cc6e21eab1689e2f8`

## Benchmark / truth boundary check

No performance, energy, retained-compute, incremental-compute, dormant-compute, network, OS-process,
device, physical-independence, or provider-independence claim was made by Wave 110. Its depth-6 case
is explicitly correctness-only. I found no benchmark-fairness overclaim to falsify in this wave.

The primary finding is provenance/equivalence semantics, not a Flowing Compute performance result.

## Next adversarial gate

Before treating transition evidence as exact commit provenance:

1. bind the exact `transition_sha` into an independently committed decision/marker (or another object
   already rooted in the committed authority lineage);
2. on read, re-run the transition's registry-step validation against the retained registry store and
   require its target state to equal the committed checkpoint state;
3. inspect `transition_store` even when lower history says `NONE`; surviving transition evidence must
   produce HOLD/UNRESOLVED rather than silently reopen genesis;
4. test missing genuine transition + substitute body, duplicate candidates, nonexistent/sibling
   registry targets, wrong generation/delta, transition-only survival, and saved-genesis restart;
5. then move the commit-decision witness into the proposed separate OS-process failure domain and
   attack crash/rollback boundaries there.

No merge, auto-merge, builder rewrite, or CANON promotion was performed.
