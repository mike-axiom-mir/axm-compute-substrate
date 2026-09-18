# Independent adversarial verification — Wave 109

Date: 2026-09-17  
Lane: verifier-only, draft/unmerged, not CANON  
Builder branch: `chatgpt/lane-001-platform-extract`  
Builder head inspected: `84c5f53f4a6e9ffafc013db634adba485cd44479`  
Exact Wave-109 tested source commit: `1747e087d3ab07312484980da987b88f8e8f56cd`

## Builder result that survives

Wave 109 materially closes verifier PR #33 while any of its four inspected newer evidence families survive. Its new read-side rule refuses to guess that unmanifested `L/C/U/root-binding` evidence was merely prepared; it returns `HOLD_COMMIT_STATUS_UNRESOLVED` instead. The builder's exact-source receipt reports Wave-108 regression `27/27` and Wave-109 `18/18` in normal Python and `python -O`, and the referenced GitHub Actions run `35201878046` completed successfully at the exact tested source commit.

No fresh performance, energy, network, retained/incremental/dormant-compute, OS-process, device, or provider-independence claim is made by Wave 109.

## New finding

**Verdict:** `FAIL_SURVIVING_TRANSITION_RECORD_IGNORED_BY_COMMIT_STATUS_GUARD`

Wave 109 describes its preserved stale-prefix case as requiring erasure of both marker tails plus **every newer local transaction evidence body** (`L/C/U/root-binding`). That boundary is too strong.

The normal prepare path also writes a sealed Wave-100 transition record into `transition_store`. That record survives normal commit and contains the exact target:

- authority SHA;
- checkpoint SHA;
- app-state slot, which under Wave 105 is the exact root-binding SHA;
- predecessor authority and registry transition identities.

Wave 109's `commit_status_state()` and `authority()` do not accept `transition_store` and therefore cannot see this retained transaction artifact.

The verifier reproducer advances normally through accepted epochs 1 and 2, verifies the epoch-2 transition through the unchanged `AXM_FLOWING_COMPUTE_REMOTE_REGISTRY_MONOTONICITY.get_transition()` path, then recreates Wave 109's own preserved stale-prefix attack:

1. truncate Wave-108 commit/high-water marker seq2;
2. restore the mutable runtime pointer to epoch 1;
3. restore remote B+C to legitimate epoch-1 snapshots while remote A remains newer;
4. restore the local quorum-certificate tail to certificate 1;
5. restore certificate witnesses B+C to epoch 1 while the genuine cert-A disk retains epoch 2 but cert-A is unavailable;
6. remove epoch-2 `L/C/U` and the epoch-2 root-binding body;
7. **do not remove the epoch-2 transition record**.

The transition remains sealed and still names the exact erased epoch-2 authority/checkpoint/root-binding identities. Unchanged Wave 109 nevertheless classifies the remaining local committed history as the valid epoch-1 prefix and returns stale epoch-1 authority in the partial stale-quorum configuration.

## Why this matters

The surviving transition does **not** itself prove that epoch 2 committed; a transition exists from prepare time. But that is exactly the ambiguity class Wave 109 says it now treats conservatively. Wave 109 deliberately HOLDs when retained evidence cannot distinguish `prepared-only` from `committed-then-damaged`.

A surviving sealed transition is another retained prepare/transaction artifact with that same ambiguity. Ignoring it creates an inconsistent evidence boundary: losing `L/C/U/binding` is enough to turn the world into a supposedly clean old prefix even though another exact newer transaction record remains in the modeled local state.

This is therefore narrower than the builder's stated preserved counterexample. It does **not** require complete newer local transaction-artifact erasure.

## Scope / severity boundary

This reproducer does not forge hashes, credentials, witness identities, or transition contents. It retains remote A's newer state and the genuine cert-A newer disk but makes cert-A unavailable, matching the builder's disclosed partial stale-quorum limitation. It does not claim that the transition record proves finality; the failure is that Wave 109's own safety-over-availability ambiguity policy omits one of its normal retained transaction stores.

## Next adversarial gate

Before moving the result into separate OS processes, commit-status completeness should include **all retained transaction families**, not only `L/C/U/root-binding`:

- bind each transition record to the committed marker/authority identity it belongs to, or explicitly garbage-collect it under a proven rule;
- treat an orphaned/unmanifested transition as unresolved rather than clean absence;
- distinguish committed transitions from genuinely abandoned prepares with an independently durable commit-decision receipt;
- test transition-only survival, L-only loss, binding-only loss, marker loss, transition-store truncation, and crash/restart before and after each durable write.

Verifier files are additive only. No builder file is rewritten, no merge is requested, and nothing is promoted to CANON.
