# Independent adversarial verification — Wave 120

Status: verifier lane only; **non-CANON, unmerged, no builder rewrite**.

Builder source base tested: `f0d171e65fcc3d0618915bd7d9d79a4deabda7cb` (`test: bound Wave 120 scaling cost with prevalidated predecessor`).
Newest builder head checked afterward: `d8d466181ffc80554549899c1dcafa115a27e7ec` (`test: fix Wave 120 clean rotation result expectation`). That newest commit changes only the self-test's expected clean-rotation return string from `COMMITTED` to `COMMITTED_ROTATED`; the Wave 120 implementation file is unchanged.
Wave 120 tool blob at both heads: `cdf87ee52abb1c9381af38807cea73509ce9cd40`.
Original tested Wave 120 self-test blob: `b763c7123494d777d969475e58b5640009f526c6`.
Newest self-test blob: `51ee96c8a629ef696ce0abcc84f01e80b0a9b20d`.

## Direct repair control

Wave 120 repairs verifier PR #44's retained-state leak by deleting only newly created candidate root/envelope objects after an exception when they remain unreferenced.

Independent focused control ran 16 full-public-authority-path failed prepares. In both normal Python and `python -O` it observed:

- exact injected failures;
- root growth `0`;
- envelope growth `0`;
- transition growth `0`;
- binding growth `0`;
- compact orphan JSON bytes `0`;
- final authority `AUTHORITATIVE_QUORUM_3_OF_3_MODELED`.

Bounded verdict: `BOUNDED_REPAIR_SURVIVES`.

## New failure reproduced

Wave 120's own self-test exposes a fault **after successful lower prepare but before `_sync_prepared_transition`**. The adversarial question is whether that boundary leaves a recoverable transaction or a stranded partial prepare.

`prepare_rotation()` constructs `effective = _effective_transition_store(...)`, calls `w114.prepare(..., effective, ..., binding_store, envelope_sha, ...)`, then only afterward copies the prepared transition back to the caller-visible/original `transition_store` through `_sync_prepared_transition(...)`.

The built-in `fault_after_lower_prepare_before_sync=True` raises exactly between those two steps. Lower prepare has already created shared prepare evidence including a binding that references the new envelope, so Wave 120's rollback correctly refuses to delete that envelope/root. But the newly prepared transition exists only in the temporary `effective` dictionary and is discarded when the exception unwinds. The original transition store never receives it.

Independent runtime reproduction in both normal Python and `python -O` observed:

- baseline authority: `AUTHORITATIVE_QUORUM_3_OF_3_MODELED`;
- exact fault: `RuntimeError:injected-wave120-fault-after-lower-prepare-before-sync`;
- new retained root count: `1`;
- new retained envelope count: `1`;
- new binding count: `1`, referencing that new envelope;
- new transition count in the original/public transition store: **`0`**;
- post-fault commit status: `UNRESOLVED_COMMIT_STATUS`, reason `retained-unmanifested-transaction-evidence`;
- post-fault authority: `HOLD_COMMIT_STATUS_UNRESOLVED`;
- exact public retry: `ValueError:Wave 120 rotation predecessor HOLD`;
- post-retry authority: still `HOLD_COMMIT_STATUS_UNRESOLVED`.

Verifier verdict:

`FAIL_LOWER_PREPARE_SUCCEEDS_BUT_TRANSITION_IS_LOST_BEFORE_SYNC_AND_PUBLIC_RETRY_HOLDS`

## Preserved runtime evidence

Verifier workflow run: `35269713222`.
Job: `105365655523`.
Conclusion: `success`.
Artifact: `verifier-wave120-post-lower-pre-sync-report`, artifact ID `10517938412`.
Artifact ZIP SHA-256: `c3cb43b205a442f124d7578414ba50f61a53a6300582467931a29e37439f7b44`.
The artifact contains both normal and optimized focused-repair reports, both normal and optimized adversarial reports, and exact source identity.

## Truth boundary

This is **not** a stale-authority takeover, hash collision, credential forgery, power-loss experiment, process-isolation result, timing benchmark, energy result, or general retained/incremental/dormant-compute claim. The system fails closed. The reproduced failure is a same-process prepare-atomicity/liveness and evidence-synchronization counterexample at a fault boundary Wave 120 itself exposes.

The newest builder head's full CI was still in progress when this verifier note was finalized; it is not represented here as green or failed. The newest production Wave 120 implementation is byte-identical to the implementation independently reproduced above.

## Next adversarial gate

Make the lower prepared transition and its binding visible atomically to the caller-visible evidence domain, or add an exact recovery path that can reconstruct/sync the exact lower transition **before** predecessor authority is required. Then fault after every lower-prepare write and immediately before/after transition sync. Exact retry must either resume the same prepare or safely roll it back without deleting referenced evidence. Wrong successor, wrong target state, altered transition identity, stale/replayed transition recovery, and recovery against a different predecessor must still HOLD.
