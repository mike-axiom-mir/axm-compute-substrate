# Flowing Compute Wave 93 — evaluator history + transition-specific attestations

Date: 2026-09-16  
Lane: `chatgpt/lane-001-platform-extract` / PR #2  
Status: experimental evidence only; open/unmerged; no canon or automatic-merge authority.

## Exact predecessor / verifier provenance

Wave 93 continues from the exact Wave 92 builder path and consumes the newest independent Wave 92 verifier finding before adding new semantics.

- Wave 92 builder head: `f94d563fe5339316e3362bccf988e83c950f161d`
- Wave 92 tool: `tools/AXM_FLOWING_COMPUTE_PREDECESSOR_AUTHORIZED_REGISTRY_TRANSITION.py`
- Wave 92 tool commit: `d06988d200315ec8824e18aa31baadf8c1bf7114`
- Wave 92 tool blob: `82904139cb532245f241f0bdafaf2ea89cac529c`
- Wave 92 tool SHA-256: `4d0e73f86086bda5341f9153e2713ac6d65ba82dc2f163e8ba1f8507539bd320`
- Independent verifier PR #17 head: `b59bd5e9d58250f204d81a4ae93a74d1aa597a9d`
- Verifier evidence blob: `d06a64dced1c30a7278491a1e0f7847248a8300a`
- Verifier finding: `FAIL_REMOVED_EVALUATOR_IDENTITY_CAN_BE_RESURRECTED_AS_ADD`
- Verifier workflow run: `35120821858`

Wave 93 reusable tool:

- `tools/AXM_FLOWING_COMPUTE_TRANSITION_ATTESTATION_HISTORY.py`
- commit `e85cafebd8845f88707e96c9e84bcc97095a169c`
- blob `bd34149b4370973b56a2ab213ae9e1f1adc2ae0e`
- file SHA-256 `4ab6553768a23dcbff16255763f92f89f00179eff1fde6915692fc17301522a3`
- machine-readable report: `evidence/FLOWING_COMPUTE_TRANSITION_ATTESTATION_HISTORY_WAVE93_REPORT.json`
- report commit: `7f23cdd2cb78eecb746790a29aceb0d7cae1e910`

## What changed

The Wave 92 verifier showed that immediate-predecessor lineage was not enough: remove evaluator ID `X` for one generation, then add exact old `X` again, and Wave 92 classified it as a fresh ADD. Wave 93 adds a content-addressed, append-only evaluator-ID history. IDs that have appeared are remembered and removed IDs are tombstoned. An ADD is accepted only for an evaluator ID never seen before. Therefore both exact historical-body resurrection and a fresh predecessor-less body reusing the old ID are rejected.

This is intentionally conservative. Wave 93 does **not** invent a same-ID reactivation mechanism; a retired evaluator ID stays retired for this experiment.

The four root decisions are also no longer anonymous rows embedded directly in an authorization. They are separate content-addressed attestation objects. Each attestation binds the exact transition, predecessor registry identity and generation, root, evaluator ID/body, evaluation tool/source identities, evaluator-local sequence number, previous attestation identity, and verdict. The transition authorization references the exact four attestation objects.

Evaluator history state and attestation-head state are themselves bound to the exact registry identity, not merely its generation. The three modeled witnesses advance one authority tuple: `(registry, evaluator-ID history, attestation state)`. A partial fan-out has no current authority; exact evidence can resume it.

## Result

Two exact-source runs passed **24/24 controls each**.

Positive controls covered genesis authority, transition-specific attestation validation, an authorized REMOVE+ADD bridge transition, continuous same-ID replacement, and exact partial-fanout recovery.

Negative/adversarial controls covered history/registry cross-binding, exact-old evaluator resurrection, fresh same-ID resurrection, stale attestation replay, copied cross-root PASS, tool-identity substitution, HOLD verdicts, missing attestation bodies, and visible same-sequence competing attestations.

The Wave 92 resurrection counterexample is closed on this Wave 93 path: the removed `eval-truth` ID remains tombstoned and cannot regain authority as an ADD.

## Preserved failure / truth boundary

Mechanical provenance is still not moral or canonical legitimacy. A mechanically current predecessor evaluator can still create structurally valid PASS attestations and authorize an entirely new, never-before-seen evaluator ID. That counterexample remains an explicit passing control.

Same-sequence equivocation is detected only when both competing attestation objects are visible in the modeled attestation store. There is not yet signer/key authentication, so evaluator/tool/source hashes prove named object provenance, not who controlled an actor or whether a root judgment was correct. Rolling back the entire registry + history + attestation failure domain together is also not proven detectable here.

Because tombstones are conservative, legitimate reuse of a retired evaluator ID is currently unavailable rather than silently guessed safe.

No fresh AXM/monolith workload was reread in Wave 93 and no compute-efficiency, retained-state, incremental-state, dormant-state, energy, distributed-consensus, or scaling claim is made. The measured **1935.714 us** and **1825.295 us** medians are synthetic single-host process-CPU validation/bookkeeping over 120 rounds per run; they are not wall-clock storage/network latency or joules.

## Next gate — Wave 94

Add explicit signer/key provenance to root-attestation issuance plus predecessor-bound key-rotation lineage. Then attack stolen/rotated keys, replay across key rotation, hidden same-sequence equivocation, and whole-store rollback. A valid signature/key chain must be described only as evidence of key control and provenance — never as proof that the signed root judgment is morally or canonically correct.

Only after that gate should the experiment reconsider an explicit, separately authorized same-ID evaluator reactivation path; until then retired IDs remain tombstoned.
