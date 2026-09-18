# AXM Flowing Compute — Wave 119 crash-recoverable rotation lineage

Date: 2026-09-17
Lane: `chatgpt/lane-001-platform-extract` / PR #2
Status: experimental evidence only; no merge, auto-merge, or CANON promotion.

## Why this wave existed

Wave 118's old-root-authorized rotation lineage is now exact-source green, but two independent verifier findings exposed fail-closed recovery/liveness gaps before a separate-process witness could honestly be credited.

- Verifier PR #42: if Wave 117 persisted the exact generation-0 outcome root, or the exact root plus app envelope, and then crashed before lower genesis adoption, the public bootstrap retry rejected the retained exact prefix with `wave117-root-anchor-state-already-present`. No stale authority was accepted; the problem was retry/recovery atomicity.
- Verifier PR #43: during Wave 118 rotation, the lower authority/checkpoint and exact commit decision could become durable and then crash before transition provenance. The accepted checkpoint already anchored the successor root, the live credential remained the predecessor, and the system safely HOLDed. The older exact trailing-provenance repair could recover the retained data, but Wave 118 exposed no public route that composed that repair with exact successor activation.

## Wave 119 change

Wave 119 adds two deliberately narrow public recovery paths.

1. Genesis adoption may resume only an exact deterministic pre-lower-genesis prefix: either the expected generation-0 outcome root alone, or that exact root plus its exact app envelope. Extra, mismatched, or ambiguous root/envelope residue fails closed. A completely adopted genesis is idempotent only after full Wave 118 validation.
2. Rotation retry inspects the already accepted checkpoint/root lineage without requiring the live credential to have switched yet. If the supplied transition resolves to the exact accepted successor root, the existing Wave 114 helper may append only one exact missing trailing provenance row already proven by the durable lower commit + exact commit decision. Only then may Wave 118's exact successor-activation recovery run. An already settled exact retry returns idempotently.

No missing root, transition, decision, outcome, or provenance chain is synthesized from ambiguous history.

## Positive and negative controls

The Wave 119 self-test first reproduces both predecessor failures. It then checks:

- exact root-only bootstrap retry succeeds without duplicate durable state;
- exact root+envelope bootstrap retry succeeds without duplicate durable state;
- completed bootstrap retry is idempotent;
- mismatched bootstrap residue fails before lower adoption and leaves the bad prefix visible;
- Wave 118's lower-commit/provenance crash still leaves `INCOMPLETE` and its public retry remains blocked;
- Wave 119's exact `commit_rotation` retry appends the one proven missing provenance row, activates the exact successor, and settles `VALID`;
- the explicit public recovery route does the same;
- a wrong successor credential fails before provenance, mutable binding, or current-keyring mutation;
- the existing crash after provenance but before activation is also recoverable through exact retry;
- a clean rotation still follows the Wave 118 path and remains authoritative after normal publish/certify settlement;
- a second retry after a settled rotation is idempotent.

## Exact-source result

Tested source commit: `c96d679d7cb03935c821bbdff4ab3e1a19c99018`

Exact blobs:

- Wave 119 tool: `28c8c85b3377289b69d742990556e5429fca487f`
- Wave 119 self-test: `5c08eb322964b60a34359ef82058b34ddf57b96a`
- Wave 119 workflow: `69c6299d3cb547d29df4801baeaf8fe42485d149`
- unchanged Wave 118 tool: `8db646560e512a9fef3c4e57dc60012126533f6f`

GitHub Actions run `35261332504`, job `105337519571`: success.

- unchanged Wave 118 regression: 34/34 normal, 34/34 under `python -O`;
- Wave 119 controls: 16/16 normal, 16/16 under `python -O`;
- artifact `10514504266` (`wave119-report`), SHA-256 `1bb51aac958737905b642246fff759841ea7c8e8924ceceea92ced95d5b85e98`.

The machine-readable reports stayed in the CI artifact rather than being committed as generated ballast.

## Truth boundary and preserved counterexamples

This is still one modeled Python failure domain. The result does not establish power-loss durability, OS-process isolation, device independence, network/provider independence, hardware monotonicity, energy savings, or a retained/incremental/dormant-compute performance win.

The whole-domain rollback counterexample remains: if every newer checkpoint/root, commit decision, provenance row, credential state, witness state and transition is rolled back together to a genuine older snapshot, the model can still lose knowledge of the newer world. Wave 119 does not claim to solve that.

The recovery rules are intentionally availability-losing at ambiguity: extra bootstrap residue, a wrong successor, a target transition not bound to the accepted successor root, or anything wider than exactly one already-proven missing trailing provenance row remains a HOLD/error rather than being reconstructed from a story.

## Next gate

Move the outcome/decision witness into a genuinely separate OS process with its own durable store and credential. Attack process death before/after witness publication, full local rollback while the witness remains newer, witness restart/truncation/corruption, stale/cloned disks, credential substitution, partitions/reconnects, simultaneous old/new views, COMMIT/REJECT/HOLD crossover, and rotation across the process boundary. Success would prove only the tested process/store separation, not physical or provider-independent finality.
