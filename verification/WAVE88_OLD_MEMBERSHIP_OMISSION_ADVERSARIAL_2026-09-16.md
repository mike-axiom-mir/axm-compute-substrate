# Independent adversarial verification — Wave 88 old-membership omission

Date: 2026-09-16  
Builder head tested: `e5271b2c7dd74a9230c3bd48dc530428e7f49356`  
Wave 88 tool blob: `efabee7b9c9724e1bd23f37cfc909cc9ed54cf1a`  
Status: **FAIL — old committed witness set is not cross-bound to reconfiguration body**

This lane is verifier-only. It does not modify builder files, merge anything, or promote a repair to canon.

## What survives

Wave 88 materially improves the previous caller-selected membership problem when callers use `prepare_reconfiguration()` exactly as intended. The control path for `A,B,C -> A,B` creates a reconfiguration whose `old_witness_ids` are exactly `A,B,C`, marks `C` as removed, writes a final `RETIRED` record for C, and only then publishes the A/B current membership. Explicit current membership also correctly makes a silently missing current witness fail steady-state validation.

The preserved Wave 88 report is appropriately bounded: it labels the benchmark as single-host orchestration, not compute-efficiency, energy, consensus, or independent physical witnessing evidence.

## Counterexample

Wave 88's reusable validator checks that the `old_witness_ids`, `target_witness_ids`, added/removed/retained sets, predecessor-head map, and epoch step are internally self-consistent. It does **not** verify that `old_witness_ids` equal the witness IDs in the predecessor membership object named by `predecessor_membership_sha256`.

The exact published APIs therefore accept this sequence:

1. Initialize committed membership `A,B,C` at epoch 0.
2. Use normal `prepare_reconfiguration()` to create the legitimate target membership `A,B` and staged target pointer.
3. Copy the legitimate reconfiguration, but change its declared old set from `A,B,C` to only `A,B`; change retained to `A,B`, removed to empty, and predecessor-head map to only A/B; recompute its content hash.
4. `validate_reconfiguration()` accepts the rehashed object.
5. **Direct path:** `commit_reconfiguration()` advances only A/B, publishes the A/B pointer, and returns `COMMITTED`. `validate_steady_state()` then returns `CONSISTENT`, while witness C is still untouched at epoch 0 with its original `GENESIS` record.
6. **Recovery path:** advance only A under the forged reconfiguration. `recovery_status()` reports `OLD_MEMBERSHIP_HANDOFF_PARTIAL_RECOVERABLE`; `repair=True` advances B and publishes A/B. It again returns `CONSISTENT` while C remains untouched at epoch 0.

No SHA collision, pointer-file corruption, witness deletion, whole-store rollback, or actor-authentication claim is needed. The predecessor membership hash still names the genuine A/B/C membership. The failure is a semantic cross-binding gap: recovery trusts the reconfiguration's declared `old_witness_ids` instead of re-deriving that set from the resolved predecessor membership.

## Why this matters

Wave 88's written handoff rule says every witness in the old committed membership must hand off before the pointer can move. The counterexample falsifies that stronger rule under the reusable API: one committed old witness can be silently omitted from the reconfiguration object, and both normal commit and crash recovery can accept the resulting membership shrink as healthy.

This is distinct from the already-admitted authorization problem for Wave 89. Even a perfectly authorized membership change still needs the protocol to prove that the exact old committed set participated in the handoff. Authorization cannot repair a reconfiguration body that lies about who the old members were.

## Reproducer

`verification/wave88_old_membership_omission_counterexample.py`

The script includes:

- a legitimate REMOVE control proving normal preparation includes and retires C;
- a direct `commit_reconfiguration()` counterexample;
- a `recovery_status(..., repair=True)` counterexample.

It asserts the failure mechanically and prints the resulting state as JSON.

## Next adversarial gate

Before or alongside Wave 89 authorization:

- resolve the exact predecessor membership object and require `r.old_witness_ids == predecessor_membership.witness_ids`;
- resolve the exact target membership object and require `r.target_witness_ids == target_membership.witness_ids`;
- re-check membership generation, predecessor membership identity, transition kind, pointer predecessor/epoch, and retention linkage inside commit/recovery rather than only at construction time;
- make normal commit and recovery share the same full semantic validator;
- then attack omitted-old-member, extra-old-member, target-set mismatch, stale reconfiguration replay, target-membership substitution, and authorization replay under a different membership generation.

The narrow Wave 88 result remains useful, but the claim should be bounded to **constructor-produced reconfigurations** until these cross-object invariants are enforced on load/commit/recovery.
