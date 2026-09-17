# Independent verification — Wave 118 rotation lower-commit → provenance crash

Status: **FAIL (bounded recovery/liveness finding; safety still fails closed)**

Verifier verdict: `FAIL_ROTATION_LOWER_COMMIT_TO_PROVENANCE_CRASH_HAS_NO_PUBLIC_RECOVERY`

## Exact source boundary

Builder branch: `chatgpt/lane-001-platform-extract`

Builder head challenged: `24d89d57ac0aaffe77febec875e1d70109f703a8`

Wave 118 tool blob: `8db646560e512a9fef3c4e57dc60012126533f6f`

Wave 118 self-test blob: `e468ed84b2b3e9e654d5723cd4ffaeb61e08e6a4`

The builder's own Wave 118 CI is green with 34/34 tests in normal Python and 34/34 under `python -O`. This verifier does not dispute the cases that suite actually covers, including recovery when the fault is injected after checkpoint/provenance persistence but before live credential activation.

## Adversarial cut

The verifier injects one earlier crash boundary inside `commit_rotation(...)`:

1. valid history exists;
2. a valid successor outcome-authority rotation is prepared;
3. the exact commit decision is durable;
4. the lower Wave 110 commit succeeds, so the committed checkpoint/root lineage advances to the successor;
5. execution crashes immediately before Wave 111 provenance append writes the missing trailing provenance row;
6. live in-memory keyring remains on the predecessor authority.

No hash collision, HMAC forgery, stale credential fabrication, builder-file rewrite, or old-evidence rewrite is used.

## Reproduced post-crash state

After the injected crash:

- accepted root generations are `[0, 1]`;
- the newest durable root identifies the successor authority;
- live `keyring.current` is still the predecessor;
- `commit_status_state(...)` is `INCOMPLETE_OR_CORRUPT`;
- `authority(...)` is `HOLD_COMMITTED_HISTORY_INCOMPLETE`.

This is good safety behavior: stale authority does **not** become authoritative.

## Public recovery failure

Three available public routes were then tried against the exact same legitimate durable state:

- exact `commit_rotation(...)` retry → `ValueError:checkpoint-anchored-current-outcome-authority-mismatch`;
- generic `commit(...)` retry → the same current-anchor mismatch before its existing trailing-provenance recovery can run;
- `recover_rotation_activation(...)` → activation is rolled back because history is still missing the provenance row (`committed-transition-provenance-count-mismatch`).

Repeated public recovery attempts therefore leave history `INCOMPLETE_OR_CORRUPT`, authority HOLDed, and the live keyring on the predecessor.

## Diagnostic control

As a diagnosis only, the verifier manually invokes the already-existing internal Wave 114 exact trailing-provenance recovery helper on the same retained durable evidence. It returns `COMMITTED_RECOVERED_EXACT_DECISION`. After that, the normal Wave 118 activation recovery returns `RECOVERED_ROTATION_ACTIVATION`, history becomes `VALID`, all remotes publish, certification succeeds, and final authority becomes `AUTHORITATIVE_QUORUM_3_OF_3_MODELED`.

This control matters: the durable evidence is sufficient. The missing piece is public/idempotent orchestration across the lower-commit → provenance → credential-activation sequence.

## Evidence

Reproducer: `verification/wave118_rotation_provenance_crash_repro.py`

Completed corrected fast diagnostic run: `35258292003`, job `105327329440`, artifact `10513519067`, artifact SHA-256 `d3349a52914f349a548431af91cee24d48a53354f2fce927e59f438f98b15d61`. The reproducer exited 0 with `public_gap_reproduced=true` and `diagnostic_internal_repair_works=true`.

An earlier verifier run is intentionally retained because it exposed a verifier-only import-path mistake (`ModuleNotFoundError`); it is not builder evidence. Corrected workflows set `PYTHONPATH=tools`.

## Truth boundary

This finding is **not** a stale-authority takeover. The system fails closed. It is a recovery/liveness and transactional-orchestration gap after a legitimate lower commit. It does not establish real power-loss behavior, OS-process isolation, hardware monotonicity, external witness durability, network/provider independence, speed, energy, or retained/incremental/dormant-compute performance.

## Next adversarial gate

Make rotation recovery idempotent across every durable boundary. A restart must be able to inspect an accepted successor root even while the live credential is still the predecessor, recover only the exact missing provenance for the durable `(authority_sha, transition_sha)` decision, and only then activate the exact successor. A different successor or transition must remain rejected.

Then fault-cut: before decision; after decision/before lower commit; after lower commit/before provenance; during provenance append; after provenance/before activation; after activation; and repeated restarts/retries. Also test wrong-successor, wrong-transition, stale-predecessor, duplicate-recovery, and abandoned/rejected rotation paths.

Separate follow-up cost gate: `prepare_rotation(...)` stores successor root/envelope material before the lower prepare completes. Repeated unique abandoned/rejected prepares should be measured for orphan retained-state growth and cleanup behavior before making storage-efficiency claims.
