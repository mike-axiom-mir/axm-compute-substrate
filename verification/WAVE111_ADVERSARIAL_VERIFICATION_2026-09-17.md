# Wave 111 independent adversarial verification — 2026-09-17

Status: **separate verifier lane; draft; unmerged; non-CANON**.

Builder base: `ea430afcade876dee771c972028a4c02761a737f`  
Exact Wave-111 tested source: `8b3c7e727fb1110259da15a9e9e62b720c520045`  
Wave-111 tool blob: `638294762fc84245e265bfad138869f83c621fd6`  
Wave-111 self-test blob: `d48f09c80900ad3a8ab1667f524832ca3a2892db`  
Verifier code/workflow tested head: `5f71aee8ecacd1565b0dc74f0e525762deacd2be`  
Independent CI run: `35214808338`.

## Bounded verification that survived

The unchanged Wave-111 builder self-test passed **27/27** in both normal Python and `python -O` inside the independent verifier workflow. Wave 111's direct security repair therefore survives these checks: exact committed transition provenance is pinned, the prior transition-substitution attack fails closed, surviving transition evidence prevents silent genesis re-entry, and the documented lower-commit -> provenance-persist crash is detected as incomplete/corrupt rather than accepted as authoritative.

This verification does **not** add a speed, energy, retained/incremental/dormant-compute, network, device, OS-process, or provider-independence claim.

## Failure: documented crash boundary has no public retry recovery

Reproducer sequence:

1. Start a fresh Wave-111 world and call the unchanged public `prepare(...)`.
2. Simulate the exact documented crash boundary by invoking unchanged Wave-110 `commit(...)`, so the lower durable commit completes but Wave-111 provenance is not appended.
3. Confirm Wave 111 reports `INCOMPLETE_OR_CORRUPT` with reason `committed-transition-provenance:ValueError:committed-transition-provenance-count-mismatch` and authority `HOLD_COMMITTED_HISTORY_INCOMPLETE`.
4. Retry the unchanged public Wave-111 `commit(...)` with the **same exact authority link and transition SHA**.

Observed in both normal Python and `python -O`:

- lower commit before simulated crash: `COMMITTED`
- public retry result: `TRANSITION_PREDECESSOR_HOLD`
- public retry exception: `null`
- state after retry: still `INCOMPLETE_OR_CORRUPT`
- recovered by public commit retry: `false`
- verifier verdict: **`FAIL_COMMIT_TO_PROVENANCE_CRASH_HAS_NO_PUBLIC_RETRY_RECOVERY`**

This is a **liveness/recovery failure, not a stale-authority acceptance**. Safety survives because authority stays HOLD. The missing property is an idempotent public recovery path that can finish the already-durable exact commit without reopening transaction semantics.

## Supporting liveness boundary: abandoned prepare

After a legitimate public `prepare(...)` without commit:

- status is `UNRESOLVED_COMMIT_STATUS`
- authority is `HOLD_COMMIT_STATUS_UNRESOLVED`
- no public `abort` API is present
- a second public prepare is blocked with `ValueError:Wave 111 predecessor HOLD`
- genesis retry is blocked with `ValueError:Wave 106 bootstrap is closed by retained authority evidence`
- deleting only the speculative transition body still leaves the lower prepared evidence unresolved

This is recorded as `LIVENESS_BOUNDARY_NOT_STALE_AUTHORITY_CLAIM`; Wave 110 already disclosed that a prepared transaction is unavailable until commit, so this is supporting evidence rather than the primary new failure.

## Hidden retained-history verification cost

For a single clean `commit_status_state(...)` verification, the verifier instrumented Wave 111's per-committed-sequence marker lookup without using wall-clock timing. All tested histories remained `VALID`.

| committed depth N | `_marker_rows_for_seq` calls | `_marker_chains` calls | `_linearize` calls | marker-store rows scanned |
|---:|---:|---:|---:|---:|
| 1 | 1 | 2 | 4 | 4 |
| 4 | 4 | 5 | 10 | 40 |
| 8 | 8 | 9 | 18 | 144 |

The observed structural row-scan count is `2*N*(N+1)` for these depths. This exposes a **quadratic retained-history verification component** because each committed sequence re-runs full Wave-108 marker-chain linearization. It is not a wall-clock, energy, or end-to-end performance result and does not contradict Wave 111's stated no-performance-claim boundary. It is a cost gate that should be addressed or explicitly benchmarked before long-lived retained-state efficiency claims.

## Exact CI evidence

Both matrix jobs in run `35214808338` completed successfully and uploaded the builder self-test plus verifier JSON from tested head `5f71aee8ecacd1565b0dc74f0e525762deacd2be`:

- normal Python artifact `10494700023`, `sha256:1cd73e9f3cb55c9784734ad565890adadd2dbabe56d48082741e899272df70c3`
- `python -O` artifact `10494019922`, `sha256:89c09541fb5b120829a15fe0033a63a8bd393ec99c066f298777f1cfea76d4d4`

The verifier source is `verification/wave111_crash_recovery_repro.py`; workflow is `.github/workflows/verifier-wave111-crash-recovery.yml`.

## Next adversarial gate

Before treating OS-process separation as stronger finality evidence, make crash recovery idempotent: if the lower durable markers prove the exact `(authority_sha, transition_sha)` already committed and the provenance row alone is missing, recovery should be able to append **only that exact provenance fact** without re-committing, changing registry semantics, or accepting a different transition. Then crash/restart at every prepare -> lower commit -> provenance -> publish/certify write boundary, retry repeatedly, prove mismatched transitions cannot recover, and add a bounded abort/cleanup path for genuinely abandoned prepares.

Separately, avoid rescanning the full marker chains once per committed sequence (for example, verify/linearize marker chains once per status check and index rows by sequence), then measure retained-depth scaling before making any efficiency claim.
