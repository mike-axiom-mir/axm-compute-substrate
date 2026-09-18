# Wave 109 — Commit-status ambiguity guard

Date: 2026-09-17
Lane: `chatgpt/lane-001-platform-extract` / PR #2
Status: experimental, unmerged, not CANON

## Trigger

Independent verifier PR #33 tested builder head `7573e1e97d026ed07065fcca46cc0d88a26e64b5` and exact Wave-108 source commit `7b9ec8548bde69df1d8971567aaf04abd0fa2e5c`.

Verifier source/provenance identity:

- verifier PR: #33
- verifier head: `49a8bfe61d7e062c52e419d9670cb95e41730e98`
- verifier CI head: `d2d5851a1bf3088d1d2c96af909777bc6ea2ed6f`
- verifier evidence blob: `b69e34546378a0e7a38f550e89afb926a8909e21`
- verifier reproducer blob: `196482bc43391d151508f70fa176f20ea7e8e72a`
- verifier CI run: `35198901311`
- normal job: `105128625588`
- optimized job: `105128625455`
- preserved verdict: `FAIL_COMMITTED_MARKER_TAIL_TRUNCATION_RECLASSIFIES_ACCEPTED_EPOCH_AS_PREPARED_AND_PERMITS_STALE_QUORUM`

The verifier established a semantic hole rather than a hash/credential forgery: after epoch 2 had really been accepted, removing only seq-2 from both Wave-108 marker chains while retaining epoch-2 L/C/U and the full Wave-105 binding store let Wave 108 relabel epoch 2 as prepared-only after the mutable runtime was restored to epoch 1. With remote B+C and certificate-witness B+C restored to legitimate epoch-1 state, the local certificate tail restored to cert1, and the genuine newer cert-A witness unavailable, stale epoch 1 regained authority. Remote A, the genuine cert-A disk, epoch-2 L/C/U, and the epoch-2 Wave-105 binding body still retained newer evidence.

## Wave 109 change

Wave 109 deliberately does **not** invent a missing durable commit bit. It changes the unsafe classification rule.

`UNRESOLVED_COMMIT_STATUS` now means retained transaction evidence exists beyond what the paired Wave-108 commit/high-water ledgers name. Authority returns `HOLD_COMMIT_STATUS_UNRESOLVED` rather than guessing that the extra evidence was merely prepared.

The guard cross-checks:

1. exact authority links named by the Wave-108 commit ledger;
2. their exact checkpoint and signer-use bodies;
3. the Wave-105 certificate-witness-root binding chain mechanically named by checkpoint state identities;
4. every retained L/C/U/binding row not accounted for by that manifested chain.

Any extra retained L/C/U/binding row is unresolved. This includes a legitimate in-flight prepare. That is intentional: the read side cannot truthfully distinguish “prepared but never committed” from “committed, then both local commit-marker tails were lost” inside the same failure domain. The existing commit path can still finish from its carried transaction identities; after Wave 108 appends the paired marker rows, the ambiguity clears.

## Positive cases

The self-test covers:

- clean genesis;
- clean accepted epochs 1 and 2;
- exact checkpoint-to-root-binding identity matching;
- a legitimate prepare entering `UNRESOLVED_COMMIT_STATUS`;
- completion of that prepared transaction clearing the ambiguity after the paired marker append;
- clean retained depth 6 as **synthetic correctness-only scaling**, not a benchmark.

## Negative / adversarial cases

The self-test preserves and attacks:

- verifier PR #33’s exact Wave-108 marker-tail reclassification;
- verifier PR #33’s stronger partial stale-quorum case;
- marker-tail loss plus newest L loss;
- marker-tail loss plus complete newest L/C/U loss while the newer binding remains;
- checkpoint loss and signer-use loss around an unmanifested retained link;
- marker hash corruption.

Expected Wave-109 result for the exact PR #33 attack: `HOLD_COMMIT_STATUS_UNRESOLVED`.

## Preserved counterexample

Wave 109 is intentionally not presented as a complete durability solution.

If an attacker/failure restores both Wave-108 marker chains **and also erases every newer local L/C/U/root-binding body**, the local retained transaction evidence becomes a genuine older prefix. In the same partial stale-quorum configuration used by verifier #33, with the only genuine newer certificate witness unavailable, this one-process model can still accept the stale prefix.

That counterexample matters: a same-domain ambiguity guard can refuse to misclassify surviving evidence, but it cannot recover a fact after all local evidence of that fact is gone.

## Truth boundary

Not claimed by Wave 109:

- OS-process durability or independence;
- physical/device/provider independence;
- physically monotonic storage;
- atomic crash recovery across commit and marker persistence;
- fresh AXM/monolith workload results;
- performance, energy, network, retained-compute, incremental-compute, or dormant-compute advantage.

No merge or CANON promotion is performed.

## Exact new source blobs before CI

- tool: `tools/AXM_FLOWING_COMPUTE_COMMIT_STATUS_AMBIGUITY_GUARD.py` -> `6dbb03509100fdd724c3576a4938a9406e0eaf3e`
- self-test: `tools/AXM_FLOWING_COMPUTE_COMMIT_STATUS_AMBIGUITY_GUARD_SELFTEST.py` -> `f2142dc67475eba86d4c20975d53551cfb1170b0`
- workflow: `.github/workflows/wave109-commit-status-ambiguity-guard.yml` -> `09137ac0dc550867542ec998300f43aa64082589`

A separate append-only exact-source receipt should be added only after CI verifies the committed source. Failed CI attempts, if any, remain visible rather than being rewritten.

## Next gate

The next gate is no longer “three processes therefore safe.” It is **an independent durable commit-decision boundary plus process restart evidence**.

A follow-up wave should move the authority/certificate path into separate OS processes and give commit status an independently durable witness/receipt that cannot be erased by truncating the same local transaction+marker domain. Then attack:

- kill/restart before prepare, after prepare, after lower commit, before/after durable commit-decision publication;
- stale/cloned disks;
- local marker-tail truncation plus complete newer local L/C/U/binding erasure;
- one independent commit witness unavailable;
- one stale witness plus one unavailable witness;
- certificate-tail truncation independently of commit-decision storage;
- partitions/reconnects and simultaneous old/new process views;
- whole-process rollback.

Success there would be process-level/durable-boundary evidence only, not yet physical/provider-independence proof.
