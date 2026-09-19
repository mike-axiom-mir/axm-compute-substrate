# Independent verifier — Wave 137 lineage-stage regression

**Status: DRAFT / UNMERGED / NON-CANON / DO NOT AUTO-MERGE.**

Builder head challenged: `e6ac6962c6ee1e4b5e6023daa999838873644f56` (`Wave 137: enforce strict rotation namespace provenance`). Parent / Wave-136 evidence head: `411bd123b193eca34f44bec1ff3d9d9af32247c5`.

## Builder evidence state

The newest Wave-137 builder workflow is already red at the exact builder head:

- workflow run `35341670954`
- job `105588741984`
- unchanged Wave-136 regression normal: **success, 11/11**
- unchanged Wave-136 regression optimized: **success, 11/11**
- Wave-137 namespace normal: **failure**
- Wave-137 optimized: skipped after the normal failure

The normal Wave-137 failure occurred in its own `known_lineage_partial_stage_remains_recoverable` case. The exact error was:

`RuntimeError:wave137-unexpected-rotation-artifact:lineage.jsonl.axm-w135-stage-af113b39bb2cbc8bd2c24a9abbae3887`

## Independent reproduced failure

Verdict:

`FAIL_WAVE137_REJECTS_GENUINE_WAVE136_LINEAGE_RECOVERY_STAGE`

The independent verifier does not invent an unknown artifact. It uses the unchanged Wave-136 crash helper to interrupt the real authority-lineage replacement during `partial_write`. This leaves the genuine predecessor recovery stage:

`response_rotation/lineage.jsonl.axm-w135-stage-<content-bound-id>`

Wave 137 then refuses to resume the exact legitimate rotation because its namespace scanner recognizes `.axm-stage-*` and `.tmp-*`, but not the `.axm-w135-stage-*` naming used by the unchanged Wave-135/Wave-136 lineage replacement helper.

The verifier checks that Wave 137 fails before changing the lineage and leaves the residue visible. It then invokes the unchanged Wave-136 rotation path against the **same exact state**. Wave 136 resumes successfully to sequence 1 and removes the recovery stage. A Wave-137 stable validation after that predecessor recovery succeeds.

This independently reproduced in both normal and optimized Python.

## Independent CI

Exact executable verifier head: `987bd7096bf54e8dfa61313f5f0683bac8e01373`.

GitHub Actions:

- run `35344031674`
- job `105596305533`
- conclusion: **success**
- normal verifier: reproduced `FAIL_WAVE137_REJECTS_GENUINE_WAVE136_LINEAGE_RECOVERY_STAGE`
- optimized verifier: reproduced the same verdict
- environment: Ubuntu 24.04.5, Python 3.12.14, OpenSSL 3.0.13, Linux 6.17.0-1022-azure; worker uid 1001 with `CapPrm=0` / `CapEff=0`; dedicated authority uid 23001

Artifact:

- id `10546097939`
- name `wave137-lineage-stage-regression-verifier`
- size 4,167 bytes
- SHA-256 `57cee20e0fe75575a8655ec2d94f5cb46cd265b3f12604db8ad939674c4f0f85`

Files:

- reproducer: `verification/wave137_lineage_stage_regression_repro.py`
- workflow: `.github/workflows/verifier-wave137-lineage-stage-regression.yml`
- this evidence record: `verification/WAVE137_LINEAGE_STAGE_REGRESSION_VERIFICATION_2026-09-18.md`

## Bounded interpretation

This is a **fail-closed liveness / compatibility regression**, not stale-authority acceptance. No response key, credential, signature, certificate, ledger row, or signed lineage is forged or rewritten by the verifier. The lower recovery residue is produced by the unchanged Wave-136 production recovery path.

The direct Wave-137 claim therefore does **not** currently survive: its strict namespace contract rejects one of the genuine in-flight recovery forms that its own self-test says must remain recoverable. The older Wave-136 transaction-recovery controls remain green.

This result says nothing about speed, energy, throughput, retained/incremental/dormant-compute efficiency, cross-host uniqueness, user namespaces, hardware custody, provider independence, or physical finality.

## Next adversarial gate

Repair the namespace model from a **single authoritative grammar shared by the writer and scanner**, rather than duplicating filename assumptions in Wave 137. The strict scanner must recognize only recovery artifacts that the current production writers can genuinely emit, including the Wave-135 lineage replacement stage, and still reject attacker-made lookalikes.

Then test every legitimate recovery family (`pending_*`, authority lineage, witness lineage, current-key publication, bootstrap) across every crash stage while also injecting wrong owner, wrong mode, wrong bytes, wrong generation, wrong content-bound suffix, symlink/non-regular objects, multiple ambiguous stages, and stale stages from earlier generations. Only after the full legitimate-recovery matrix passes strict preflight should the verifier return to the larger copied-authority / separate-network-namespace / second-host uniqueness gate.
