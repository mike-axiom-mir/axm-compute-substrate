# Flowing Compute Wave 92 — predecessor-authorized evaluator-registry transition

Date: 2026-09-16  
Lane: `chatgpt/lane-001-platform-extract` / PR #2  
Status: experimental evidence only; open/unmerged; no canon or automatic-merge authority.

## Scope

Wave 92 continues directly from Wave 91 and also consumes the newest independent verifier findings instead of ignoring them.

Exact predecessor source:

- Wave 91 tool commit: `0e275b6ea43c6a8cfbd66266e210bcf93a9ecddb`
- Wave 91 tool blob: `f378627bc2f8752fc8e20f73f0737c15f9e2ddff`
- Wave 91 tool SHA-256: `28b7da0d40b53f2ba9ec58161c0531530c2bfaa7e63eada4c5e7cd7eb27ad4f5`
- Wave 91 builder head: `3b7ae7ce9751497666d8e85494ca72150c088882`
- Wave 91 verifier PR #16 head: `83c5a84d0286b8eadf4f5966e044606a23532fd5`, evidence blob `8c0bd605c8f2be99c1d6c0b3f7b09ad988929ea6`
- Wave 90 verifier PR #15 head: `5173a1d98a851f53b87b0012e43e43cd917a2006`, evidence blob `882141599c09380d264578b643de027281165e7d`

Reusable Wave 92 tool:

- `tools/AXM_FLOWING_COMPUTE_PREDECESSOR_AUTHORIZED_REGISTRY_TRANSITION.py`
- commit `d06988d200315ec8824e18aa31baadf8c1bf7114`
- blob `82904139cb532245f241f0bdafaf2ea89cac529c`
- file SHA-256 `4d0e73f86086bda5341f9153e2713ac6d65ba82dc2f163e8ba1f8507539bd320`

## What changed

Every registry/evaluator/transition/authorization lookup now resolves a content-addressed body and proves that the lookup key equals that body's self-hash before the body can influence authority. This closes the Wave 91 verifier's key/body substitution counterexample for both registry and evaluator objects.

Evaluator replacement lineage is also semantic rather than constructor-conventional: each replaced evaluator must name the exact evaluator SHA it replaces as `predecessor_evaluator_sha256`. Missing or unrelated historical predecessors are rejected, closing the Wave 90 verifier finding for this Wave 92 path.

A registry ADD/REMOVE/REPLACE/MIXED transition now carries one exact authorization from the currently authoritative predecessor registry. The authorization binds the exact transition SHA, predecessor and target registry identities, transition kind, complete added/removed/replaced/retained evaluator sets, and four root rows resolved from predecessor evaluator/tool/source identities. The target registry and newly admitted evaluators get no vote before admission.

Partial witness fan-out is recoverable only with the exact transition plus exact predecessor authorization. A competing transition cannot take over the half-written state, and a missing authorization freezes recovery. Intentional rollback remains possible by producing a new forward-lineage registry/evaluator identity rather than resurrecting old authority identity.

## Result

Two independent exact-tool runs passed **25/25 controls each**. Positive controls covered predecessor authorization, full commit, partial recovery, and forward-lineage rollback. Negative controls covered registry/evaluator key-body substitution, missing evaluator bodies, missing/wrong replacement predecessors, HOLD root verdicts, missing authorization, target self-admission, competing partial transitions, and stale authorization reuse.

Synthetic single-host process-CPU medians for current-authority plus transition-authorization bookkeeping were **1170.584 us** and **1095.743 us** over 120 rounds per run. This is infrastructure timing only: it is not wall-clock storage/network latency, joules, a retained/incremental/dormant-state win, or a new compute-efficiency result. No monolith was reread for this wave.

## Preserved counterexample / truth boundary

Wave 92 proves mechanical predecessor provenance, not moral or canonical evaluator legitimacy. A currently authoritative predecessor registry can still construct four structurally valid PASS rows and mechanically admit an arbitrary entirely new evaluator set. That counterexample is an explicit passing control so it cannot disappear behind the successful transition tests.

The committed tool also contains a spelling-only provenance label typo (`...NOT_ENFORED`) for the Wave 91 verifier finding. Exact PR/head/blob/path provenance is correct, and the machine-readable Wave 92 report records the canonical verifier name `FAIL_CURRENT_REGISTRY_KEY_BODY_IDENTITY_NOT_ENFORCED`. No result depends on the misspelled descriptive label.

## Next gate — Wave 93

Make the four root decisions themselves explicit transition-specific attestation events rather than constructor-minted rows. Each evaluator attestation should bind evaluator identity, exact tool/source identity, transition identity, predecessor registry generation, and an append-only evaluator sequence/nonce; replaying an old PASS into a new transition must HOLD. The aggregate authorization should reference those exact attestation objects, and crash/recovery should preserve issuance and consumption evidence without silently granting the target registry authority.

Then attack copied PASS rows, stale attestation replay, competing attestations from the same evaluator sequence, missing attestation bodies, tool/source substitution, and signer/identity rotation. Cryptographic signer identity, if introduced, must be described only as proof of key/control provenance—not proof that a root judgment is morally or canonically correct.
