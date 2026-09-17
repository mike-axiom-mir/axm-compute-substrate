# Independent adversarial verification — Wave 120

Status: verifier lane only; **non-CANON, unmerged, no builder rewrite**.

Builder base inspected: `f0d171e65fcc3d0618915bd7d9d79a4deabda7cb` (`test: bound Wave 120 scaling cost with prevalidated predecessor`).
Wave 120 tool blob: `cdf87ee52abb1c9381af38807cea73509ce9cd40`.
Wave 120 self-test blob: `b763c7123494d777d969475e58b5640009f526c6`.

## Builder result being challenged

Wave 120 repairs verifier PR #44's retained-state leak by deleting only newly created candidate root/envelope objects after an exception when they remain unreferenced. Its own self-test covers faults after root creation, after envelope creation, partial lower references, and a fault **after successful lower prepare but before `_sync_prepared_transition`**.

The bounded cleanup claim for pre-lower failures is sensible. The adversarial question here is whether the post-lower/pre-sync boundary leaves a recoverable transaction or a stranded partial prepare.

## Source-level counterexample

`prepare_rotation()` constructs `effective = _effective_transition_store(...)`, calls `w114.prepare(..., effective, ..., binding_store, envelope_sha, ...)`, then only afterward copies the prepared transition back to the caller-visible/original `transition_store` through `_sync_prepared_transition(...)`.

The built-in `fault_after_lower_prepare_before_sync=True` raises exactly between those two steps. Lower prepare has already created durable/shared prepare evidence including a binding that references the new envelope, so Wave 120's rollback correctly refuses to delete that envelope/root. But the newly prepared transition exists only in the temporary `effective` dictionary and is discarded when the exception unwinds. The original transition store never receives it.

That means the exception can leave:

- new retained root: present;
- new retained envelope: present;
- new lower binding referencing that envelope: present;
- matching newly prepared transition in the public/original transition store: **missing**.

Because the verifier/history rules treat unmatched prepare evidence conservatively, authority is expected to HOLD. The exact public retry then begins by requiring an authoritative predecessor, so it cannot recreate/sync the missing transition.

## Verifier executable

`verification/wave120_post_lower_prepare_pre_sync_transition_loss_repro.py`

It uses the builder's own exposed fault boundary; it does not monkeypatch the lower prepare and does not forge hashes or credentials. It requires all of the following to call the issue reproduced:

1. settled authoritative predecessor;
2. exact builder fault `injected-wave120-fault-after-lower-prepare-before-sync`;
3. one new root and one new envelope survive because lower state references them;
4. at least one new binding references the new envelope;
5. zero new transition rows reach the original/public transition store;
6. authority is no longer authoritative;
7. the exact same public rotation retry fails and authority remains non-authoritative.

Expected verifier verdict:

`FAIL_LOWER_PREPARE_SUCCEEDS_BUT_TRANSITION_IS_LOST_BEFORE_SYNC_AND_PUBLIC_RETRY_HOLDS`

## Truth boundary

This is **not** a stale-authority takeover, hash collision, credential forgery, power-loss experiment, process-isolation result, timing benchmark, energy result, or general retained/incremental/dormant-compute claim. It is a same-process prepare-atomicity/liveness and evidence-synchronization counterexample at a fault boundary Wave 120 itself exposes.

## Next adversarial gate

Make the lower prepared transition and its binding visible atomically to the caller-visible evidence domain, or add an exact recovery path that can reconstruct/sync the lower transition before predecessor authority is required. Then crash/fault after every lower-prepare write and before/after transition sync; exact retry must either resume the same prepare or roll it back without deleting referenced evidence. Wrong successor, wrong target state, and stale/replayed transition recovery must still HOLD.

CI/runtime evidence will be bound here after the verifier workflow completes; until then, this file records the source-level counterexample only.
