# Wave 135 independent adversarial verification — pending-private crash residue

Status: **DRAFT / UNMERGED / NON-CANON / DO NOT AUTO-MERGE**.

Builder evidence head challenged: `e486f7fd1383115f020f2c6d047ee2c63d91c6d7`.
Exact green Wave-135 implementation named by that receipt: `03cfcd0ceab3884796c28ed5d25fa8cc0f3b2c71`.

## What survives independently

The unchanged Wave-135 focused self-test passed in the verifier workflow in both normal Python and `python -O`. That preserves Wave 135's bounded claim: post-pending current-key publication reuses deterministic content-bound staging, repairs the PR-59 historical `response_private.pem.tmp-*` amplification case, rejects wrong-byte/foreign-owner stages, and keeps clean two-rotation lineage valid within its stated same-host boundary.

No performance, speed, energy, retained/incremental/dormant-compute, throughput, scaling, cross-host uniqueness, physical-finality, or provider-independence claim is inferred.

## New reproduced next-gate failure

`FAIL_PENDING_PRIVATE_SIGKILL_RETRIES_ACCUMULATE_DISTINCT_SECRET_TEMPS_UNSEEN_BY_WAVE135_VALIDATOR`

Wave 135 explicitly leaves **pending-transaction creation** open. The lower Wave-132 path still creates `response_rotation/pending_private.pem` with the older random-temp `_atomic_write` before `pending.json` becomes durable.

The verifier pauses only after the full `pending_private.pem.tmp-*` private key has been written and fsynced and immediately before the real `os.replace(temp, pending_private.pem)`, then the root orchestrator sends real `SIGKILL` to the authority-UID child.

The exact same requested rotation was cut **10 times**. Because `pending.json` was still absent after each kill, every retry generated a fresh successor keypair. The successful verifier gate requires and observed:

- residue count grew exactly `1,2,3,4,5,6,7,8,9,10`;
- all 10 retained files were complete authority-owned mode-`0600` private-key temps;
- all 10 private-key SHA-256 values were distinct;
- all 10 derived public-key fingerprints were distinct;
- `pending.json` remained absent across the cuts;
- a clean exact Wave-135 retry then completed rotation sequence 1;
- all 10 abandoned private-key temps remained;
- a second clean authorized rotation completed sequence 2;
- all 10 abandoned private-key temps still remained;
- Wave-135 validation nevertheless returned green at sequence 2;
- the current live key was not any of the 10 abandoned retained keys.

This is not stale-authority acceptance and does not falsify Wave 135's stated post-pending repair. It is a **retained-secret amplification / crash-residue failure at the explicitly unproved pending-creation boundary**. Repeated crashes can still grow secret material one-for-one, and Wave 135's `_rotation_residue(...)` does not scan the `pending_private.pem.tmp-*` family after later valid rotations.

No worker process read or entered the authority-owned `0700` directory, no signature/key/hash/ledger/certificate was forged, and no root/kernel or authority-UID compromise is asserted.

## Exact CI evidence

Verifier executable head: `97bbfefebd7a3b43a838a84c491a547e426493a6`.

GitHub Actions run: `35333545080`.
Job: `105563088874`.
Conclusion: **success**.

The job completed all of these required steps successfully:

- unchanged Wave-135 control normal;
- unchanged Wave-135 control optimized;
- pending-private adversarial gate normal;
- pending-private adversarial gate optimized;
- exact source identity capture;
- evidence artifact upload.

Artifact: `10541513376` (`wave135-pending-private-temp-residue-verifier`).
Size: 10,601 bytes.
SHA-256: `79422dca7fa1ac5ca34d62bc9e8961988e1c4cbed1bffd0a957e08bd8ed7f4d7`.

Reproducer: `verification/wave135_pending_private_temp_residue_repro.py`.
Workflow: `.github/workflows/verifier-wave135-pending-private-temp-residue.yml`.

## Next adversarial gate

Extend deterministic exact-intent recovery **before** the pending transaction becomes authoritative, especially `pending_private.pem`, `pending_public.pem`, `pending_cert.json`, and `pending.json` as one recoverable transaction. A retry should reuse or safely retire only provably related intended bytes rather than silently generating a new secret on every pre-pending crash.

Then cut at temp creation, partial write, pre/post fsync, pre/post close, pre/post rename, between each of the four pending publications, and during cleanup. Repeat important cuts at 1/10/100 scale and require both semantic recovery and bounded secret residue. Wrong-byte, foreign-owner, stale-generation, ambiguous, and unrelated leftovers must remain visible/fail-closed.

After pending creation is closed, attack partial append/fsync boundaries in authority/witness lineage, cleanup removals, validation-to-service object identity, then resume the genuine copied-key cross-namespace/cross-host fork gate.
