# Independent verifier — Wave 122 mid-write termination boundary

Status: **verification lane only**. Draft PR #47. Unmerged, non-CANON. Builder evidence was not rewritten.

## Source identity

- newest builder lane head checked: `41f1719b48aace2c5db5ae68cadb9ccbce14970d`
- Wave 122 tested source: `5ebe63488494c6767637b82407be8675d1fcca52`
- Wave 122 tool blob: `78df9135f97e568e64ef37b83d743d6475a8adee`
- verifier branch before this evidence note: `4b16de9bb89cb074ea671298209fde7f438e2fd1`

## What was independently rerun

The unchanged Wave 122 builder self-test was rerun from the verifier lane in both modes:

- normal Python: **12/12 PASS**
- `python -O`: **12/12 PASS**

This independently preserves the builder's bounded result: a single same-process `BaseException` after caller-visible publication begins is rolled back when the restore path itself is allowed to finish.

## Stronger single-exception cut

The builder suite faults after each complete publication helper call. The verifier moved the cut *inside* each publication write: the destination dictionary was first cleared, then the termination exception was raised before the replacement body could be installed.

The matrix covered:

- `KeyboardInterrupt` after publication write 1, 2, 3, and 4;
- `SystemExit` after publication write 1, 2, 3, and 4;
- `GeneratorExit` after publication write 1, 2, 3, and 4.

All **12/12 cases survived in normal Python and 12/12 under `python -O`**. Every case restored the exact pre-call values of retained state, private signer state, transition store, and binding store; authority returned to `AUTHORITATIVE_QUORUM_3_OF_3_MODELED`; and the exact legitimate retry succeeded.

Result: **the Wave 122 single-exception rollback claim survives this stronger mid-write adversarial cut.**

## Explicit boundary probe: second termination during rollback

Wave 122 explicitly says repeated termination during rollback is unproved. The verifier exercised that boundary rather than silently extending the claim.

Procedure:

1. allow all four publication writes to complete;
2. raise `KeyboardInterrupt` after the fourth publication write;
3. let rollback begin;
4. after the first `_restore_exact` finishes, raise `SystemExit` during rollback.

Observed identically in normal Python and `python -O`:

- caught terminal exception: `SystemExit:verifier-second-termination-during-rollback`;
- transition store restored: **true**;
- retained state restored: **false**;
- binding store restored: **false**;
- private signer state restored: **false**;
- commit status: `UNRESOLVED_COMMIT_STATUS`;
- reason: `retained-unmanifested-transaction-evidence`;
- authority: `HOLD_COMMIT_STATUS_UNRESOLVED`;
- exact legitimate retry: **blocked** with `ValueError:Wave 122 rotation predecessor HOLD`.

This is **not a falsification of Wave 122's stated claim**, because the builder explicitly excludes a second termination while rollback is running. It is a preserved boundary counterexample: safety fails closed, stale authority is not accepted, but mixed public state and liveness failure remain if cleanup itself is interrupted.

## CI evidence

Independent verifier workflow:

- run: `35281282217`
- job: `105403557568`
- conclusion: **success**
- artifact: `10522823905` (`verifier-wave122-midwrite-report`)
- artifact ZIP SHA-256: `392f9eb253884ebb591174884ace2e7f5a461c715eb6de24220e402580f87d12`
- artifact size: `14029` bytes

The workflow reran the unchanged Wave 122 builder self-test in normal and optimized Python, ran the independent stronger probe in both modes, recorded exact source identities, and uploaded the reports.

## Truth boundary

No stale authority acceptance was observed. No hash/signature forgery was used. No hard process kill, power loss, filesystem/device failure, separate OS-process witness, separate durable store, provider independence, timing, energy, network, retained-compute, incremental-compute, dormant-compute, or scaling result is established by this verification.

## Next adversarial gate

Do **not** keep widening Python exception handling as a substitute for durability. Move the decision/outcome witness across a real OS-process and durable-store boundary, or introduce a durable/versioned publication transaction that restart recovery can reconcile from exact evidence. Then use actual process kills after every durable witness/local publication boundary and during local cleanup. Require restart to recover or HOLD safely from the exact witness decision, while attacking whole-local-state rollback, stale/cloned disks, witness restart/truncation/corruption, credential substitution, simultaneous old/new process views, partitions/reconnects, and outcome-authority rotation across that boundary.
