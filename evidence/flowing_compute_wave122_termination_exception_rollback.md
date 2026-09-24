# AXM Flowing Compute — Wave 122 evidence

Status: experimental lane only. No merge, auto-merge, or CANON promotion.

## Trigger / preserved counterexample

Independent verifier PR #46 (`4fe827550c160e9155f5825eb5331cbfcca6f2f3`) found a narrower same-process truth defect in Wave 121. The unchanged Wave 121 self-test still passed 8/8 normally and 8/8 under `python -O`, but Wave 121's publication rollback handler caught `Exception` rather than `BaseException`.

The verifier injected `KeyboardInterrupt` immediately after the first caller-visible publication write. Because `KeyboardInterrupt` is a `BaseException`, the rollback handler did not run. The transition store advanced while retained state, the binding store, and private signer state stayed at the predecessor view. Commit status became `UNRESOLVED_COMMIT_STATUS` with `retained-unmanifested-transition-evidence`; authority failed closed at `HOLD_COMMIT_STATUS_UNRESOLVED`; and the exact legitimate retry failed at the predecessor-authority gate.

This is a liveness/evidence-atomicity failure, not stale-authority acceptance. No hash/signature forgery, hard process kill, power loss, timing/energy result, or retained/incremental/dormant-compute result is inferred.

Verifier evidence: PR #46; workflow run `35275924241`; job `105386418339`; artifact `10520647551`; artifact ZIP SHA-256 `53da634a88895bf91c242c61f74f7e3b2f74532987be7a093fa39a85b325d342`.

## Wave 122 change

Wave 122 keeps Wave 121's existing off-public-state staging and exact source/transition/binding/root/signer validation. It changes only the publication rollback boundary:

- caller-visible publication writes go through a dedicated publication helper;
- after publication starts, one same-process `BaseException` is caught;
- the transition store, retained state, binding store, and private signer state are restored from exact pre-call snapshots through a separate private restore path that does not reuse the instrumented publication helper;
- the original termination exception is re-raised after restoration;
- no missing transition or authority fact is reconstructed from semantic similarity.

The private restore path matters because the adversarial cut is attached to the publication helper itself. Rollback therefore does not recursively trigger the same injected publication fault.

## Exact-source verification

Tested source commit: `5ebe63488494c6767637b82407be8675d1fcca52`

Source blobs:

- `tools/AXM_FLOWING_COMPUTE_TERMINATION_EXCEPTION_ROLLBACK.py`: `78df9135f97e568e64ef37b83d743d6475a8adee`
- `tools/AXM_FLOWING_COMPUTE_TERMINATION_EXCEPTION_ROLLBACK_SELFTEST.py`: `1818037e4e017f69c98f1e269b08fc3d2de66071`
- `.github/workflows/wave122-termination-exception-rollback.yml`: `ba57c39dec1fdc9c7d38a4192382892fc0b88c79`
- Wave 121 dependency tool: `b0909097c6af1d6aa5dd522664aa9f8caaade587`
- Wave 121 dependency self-test: `c73fc1b19f517927643ebb771bc8cd17d873776f`

Exact-source workflow run `35278477192`, job `105394656067`, completed successfully. Artifact `10521633453` (`wave122-report`) has GitHub digest `sha256:1bc3634aaff202d7da051a3fcbf3841ec6a2b8a50121fd7c3e679142ef98e8d9`.

Verification results:

- unchanged Wave 121 regression: 8/8 PASS;
- unchanged Wave 121 regression under `python -O`: 8/8 PASS;
- Wave 122: 12/12 PASS;
- Wave 122 under `python -O`: 12/12 PASS.

The Wave 122 suite first reproduces PR #46 against unchanged Wave 121. It then checks that a termination exception during lower staged preparation never reaches public state; injects both `KeyboardInterrupt` and `SystemExit` after each of the four caller-visible publication writes; requires exact rollback plus successful exact retry in all eight cuts; keeps an ordinary `RuntimeError` rollback control; and verifies a clean rotation still commits as `COMMITTED_ROTATED`, reaches VALID history, settles authoritative, and activates the exact successor.

No synthetic scaling run and no real AXM/monolith performance workload were run in Wave 122. This gate was correctness/recovery only.

## Truth boundary / surviving failures

Wave 122 proves only a bounded **single same-process termination-exception rollback while the restore path itself is allowed to run**. It does not prove rollback if the process is killed with `SIGKILL`, if power disappears, if the filesystem/device fails, or if a second termination interrupts the rollback itself. Successful publication still consists of multiple writes. Coordinated whole-modeled-domain rollback remains possible because the witness, credentials, and stores are still inside one modeled Python failure domain.

Wave 122 therefore makes no OS-process independence, durable external witness, physical/provider-independent finality, performance, energy, network, retained-compute, incremental-compute, or dormant-compute claim.

## Next gate

Move the COMMIT / stable-REJECT / retriable-HOLD outcome/decision witness into a genuinely separate OS process with its own durable store and credential. Use actual process kills after every durable witness/local publication boundary, then test complete local rollback while the witness remains newer, stale/cloned local disks, witness restart/truncation/corruption, credential substitution, simultaneous old/new process views, partitions/reconnects, and outcome-authority rotation across that boundary. Success would establish only the tested process/store separation, not physical or provider-independent finality.
