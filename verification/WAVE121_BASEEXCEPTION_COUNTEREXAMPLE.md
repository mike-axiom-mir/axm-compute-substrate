# Independent verifier — Wave 121 same-process termination-exception counterexample

Status: verifier lane only. Draft/unmerged. Not CANON. Builder files/evidence are not rewritten.

## Builder state challenged

Latest builder lane head observed before and after the attack: `85ca87b7eec6699957343f00203e6d25f2309c39` (`evidence: add Wave 121 exact-source receipt`).

Wave 121 exact tested source recorded by the builder: `a3c763a106bc5aea6245816de67f220f2b8695bc`.

Wave 121 implementation blob: `b0909097c6af1d6aa5dd522664aa9f8caaade587`.

The unchanged builder suite passed 8/8 normally and 8/8 under `python -O` in this independent verifier workflow. Its five publication fault controls use ordinary `RuntimeError` exceptions.

## Adversarial question

Wave 121 describes same-process exception rollback, but its publication handler catches `Exception`. Python termination exceptions such as `KeyboardInterrupt` and `SystemExit` inherit from `BaseException`, not `Exception`.

The verifier therefore replaced only the helper used for caller-visible publication, allowed the first real `_replace_exact(transition_store, staged_transition_store)` write to complete, and then raised `KeyboardInterrupt`. No builder state was pre-edited, no hash/signature/credential/transition was forged, and no hard process kill or power loss was modeled.

## Result

Verdict: `FAIL_KEYBOARDINTERRUPT_BYPASSES_WAVE121_PUBLICATION_ROLLBACK`.

Reproduced in normal Python and `python -O`.

After the injected `KeyboardInterrupt` immediately after the first public write:

- the public transition store had changed;
- retained state remained at its pre-call snapshot;
- binding state remained at its pre-call snapshot;
- private signer state remained at its pre-call snapshot;
- commit status became `UNRESOLVED_COMMIT_STATUS` with reason `retained-unmanifested-transition-evidence`;
- authority became `HOLD_COMMIT_STATUS_UNRESOLVED`;
- exact legitimate retry did not return a prepare tuple and failed with `ValueError:Wave 121 rotation predecessor HOLD`;
- stale authority was **not** accepted.

So the tested ordinary-exception repair survives, but the broader phrase “same-process exception transactionality” is too broad for the current implementation. The current bounded result is ordinary `Exception` rollback for the modeled publication faults, not all same-process termination/cancellation paths.

## Independent CI evidence

- verifier branch tested commit: `b9564b08c8449738b62bb4e55ca4a5f01d7a6044`
- workflow run: `35275924241`
- job: `105386418339`
- conclusion: success
- artifact: `10520647551`
- artifact ZIP SHA-256: `53da634a88895bf91c242c61f74f7e3b2f74532987be7a093fa39a85b325d342`
- artifact size: `13182` bytes

The workflow reran the unchanged Wave 121 builder self-test in normal and optimized Python before running this adversarial test in both modes.

## Truth boundary

This finding does **not** establish stale-authority takeover, hash/credential forgery, hard-process-kill or power-loss behavior, timing/energy behavior, network/device/provider independence, or any retained/incremental/dormant-compute performance result. It is a same-process termination-exception publication/recovery counterexample.

## Next adversarial gate

Do not merely swallow every `BaseException`. Make publication/recovery cancellation-safe by construction: a single-version/atomic publication pointer, durable transaction/publication record, or equivalent mechanism should make partial publication recoverable even if normal cleanup cannot run.

Then inject `RuntimeError`, `KeyboardInterrupt`, `SystemExit`, and relevant task cancellation at every publication boundary and prove exact retry/recovery without stale authority acceptance. Also test concurrent readers during the four current public replacements: even without an exception, a reader can potentially observe an intermediate mixed version. Only after that should the separate-OS-process durable witness gate be treated as the next stronger finality step.
