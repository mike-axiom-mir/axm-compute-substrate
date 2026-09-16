# Independent verifier — Wave 79 audit-work receipt boundary

Date: 2026-09-16  
Builder head verified: `dbf4acdc9c13d15d56dcc6d596e1b5aac3df8acc`  
Status: `DRAFT VERIFIER EVIDENCE — NOT CANON / NOT MERGED`

## Scope

This run challenged the newest Wave 79 claim that an `audited_reuse` freshness reset now requires evidence that the exact artifact bytes were actually read and matched the expected identity.

The verifier did **not** modify builder code. It revalidated the committed Wave 79 receipt contract and then attacked the time boundary between audit and freshness commit plus the semantic validity of measurement metadata.

## What survived

The committed Wave 79 receipt revalidates against the exact predecessor freshness state reconstructed from its public identity fields. Its predecessor state SHA is exactly:

`58959e3053fe81c2686894296e542859a3a6d86a5591dfddde19110786bc7a01`

So the Wave 79 positive receipt is internally consistent with the current validator. The earlier bare-label-only path is also materially improved: `audited_reuse` without a receipt is held by the wrapper.

This verifier run did **not** independently reread the real 11,255,808-byte capability-index artifact, so it does not independently reproduce the builder's ~8.54 ms real-artifact timing.

## Counterexample 1 — audit/commit TOCTOU

A deterministic small-artifact reproduction used the real Wave 79 `perform()` + `advance_with_receipts()` contracts:

1. Create a 7,681-byte artifact.
2. Build freshness state for its exact SHA-256.
3. Run the real audit-work receipt tool: `AUDIT_PASS`, 7,681 bytes read in 8 chunks.
4. After the receipt exists, flip the artifact's final byte.
5. Confirm the current artifact SHA no longer matches the audited identity.
6. Submit the still-valid audit receipt to `advance_with_receipts()`.

Observed identities:

- audited artifact SHA-256: `7fec16a715f90ae74ea363f7cc8095627165474e3bfdfa4648b237bf3728c18e`
- current post-audit artifact SHA-256: `f275fbe744ac3fe864dc21b73273e69a0ffc2959f73b2eb21d3db6318d0fba78`

Observed transition result after mutation:

- transition: `ADVANCED`
- `last_strong_audit_sequence`: `1`
- `carried_generations_since_audit`: `0`

Therefore Wave 79 currently proves **"these bytes matched when the audit receipt was created"**, not **"the artifact still matches at freshness/generation commit time"**.

This is not the earlier forged-actor objection. No receipt fields were forged for this counterexample. The artifact simply changed after a legitimate successful audit and before the freshness transition consumed the receipt.

## Counterexample 2 — measurement metadata is not semantically validated

Starting from the committed Wave 79 receipt, the verifier changed only measurement metadata, recomputed the ordinary receipt digest, and called the current validator:

- `chunk_bytes = 1`
- `chunks_read = 1`
- `bytes_read = 11,255,808`
- `audit_cpu_ns = -1`
- `audit_wall_ns = -1`

That receipt is impossible as an output of the current `perform()` loop, but `validate()` accepts it because it checks the receipt hash and the freshness-critical identity fields while not checking timing/chunk consistency.

This does **not** by itself break artifact/freshness identity. It does mean a receipt that passed the current validator should not automatically be treated as trustworthy benchmark evidence. Timing/chunk fields need either semantic validation or a separate evidence class.

## Bounded conclusion

Wave 79 **partially survives**:

- real receipt requirement: survives;
- predecessor/artifact/proof/sequence binding: survives;
- bare `audited_reuse` label reset: closed inside this wrapper;
- actor authenticity: correctly remains outside the stated boundary;
- commit-time current-artifact guarantee: **not established** due to the reproduced TOCTOU gap;
- receipt timing/chunk metadata as validated benchmark evidence: **not established**.

## Next adversarial gate

Before calling an age-zero state a commit-time fresh audit, bind audit evidence to the atomic generation commit so the current artifact identity cannot drift between check and commit. Safe options include a content-addressed immutable artifact object selected by hash, or a commit transaction that pins/rehashes the exact artifact object at pointer move.

Then test at least these cases:

- mutate/replace artifact after `AUDIT_PASS` but before pointer move -> commit must HOLD or still resolve the exact immutable audited object;
- replay a receipt after rollback/branch switch -> must only apply to the exact predecessor + exact committed object;
- receipt references correct SHA but storage path/object has drifted -> no age-zero claim unless the committed object identity is exact;
- timing/chunk metadata contradictions -> reject them or explicitly mark those fields non-authoritative.

Reproducer: `verification/WAVE79_RECEIPT_BOUNDARY_REPRO.py`  
Machine-readable result: `verification/WAVE79_RECEIPT_BOUNDARY_REPORT.json`
