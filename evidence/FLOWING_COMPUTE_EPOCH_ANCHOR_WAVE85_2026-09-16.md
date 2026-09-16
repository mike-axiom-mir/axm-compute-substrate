# Flowing Compute Wave 85 — Separate Epoch Anchor / Whole-Store Rewind Detection

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST SOFTWARE-ANCHOR EVIDENCE`

## Question

Wave 84 made ordinary `A -> B -> A` rollback ABA-safe by advancing a commit epoch even when old retention content is selected again. Its known gap was broader: if the entire primary pointer/object store is restored from an older backup, both the current pointer and its local history can rewind together.

Wave 85 asks whether a separate append-only software anchor can preserve a newer fact outside that primary store, detect the rewind after restart, and still allow intentional retention rollback.

## Exact prior identities / provenance

No fresh monolith audit ran in this wave. The reusable probe imports the Wave 84 contract and reuses its exact prior retained-state identities:

- Wave 81 retention A: `53d91b18e1a12eb27bd503bcfa70b4cd74add598ceaef522c88d7c075fdee4d4`
- Wave 83 DROP retention B: `4078169dce33c5816c7dd1073eaff5920bcfb07284a023726322e67970378dd1`
- Wave 83 KEEP retention: `0f918393dc9d4dfb33fe150bbdca9bd4ecbdca8fab0317becdf94fb9296b1721`

This is an infrastructure/recovery wave, not a new retained-compute efficiency result.

## Reusable contract

`tools/AXM_FLOWING_COMPUTE_EPOCH_ANCHOR.py` adds an append-only-by-file **anchor ledger** kept in a separate failure domain from the primary current pointer + pointer-object store.

Each anchor record binds:

- the exact pointer SHA-256;
- the exact retention SHA-256;
- pointer commit epoch;
- pointer predecessor identity;
- selection kind (`INITIAL`, `FORWARD`, or `ROLLBACK`);
- the exact predecessor anchor identity.

The anchor is a **commit decision**, not actor identity or constitutional authority.

The commit order is deliberately write-ahead:

1. store the next pointer object;
2. durably append the next anchor record;
3. atomically move the primary current pointer.

This makes the crash boundary explicit. Before step 2, staged pointer evidence has zero authority. After step 2, a restart may complete step 3 only when the anchored pointer object exists and exactly matches the anchored predecessor/binding.

## Positive result

Intentional retention rollback still works:

- A is selected at epoch 0;
- B is selected at epoch 1;
- old A content is intentionally selected again at epoch 2;
- the separate anchor also advances to epoch 2.

So rollback of **content** remains available without rollback of **history order**.

A crash after the anchor became durable but before the current-pointer replace was reproduced. Restart reported `ANCHORED_COMMIT_PENDING_POINTER_MOVE`; exact binding validation succeeded; recovery completed the already-decided commit.

A crash before the anchor append left the prior pointer/epoch current, while the staged pointer object remained non-authoritative.

## Whole-primary-store rewind attack

Two older primary backups were restored while the separate anchor ledger was deliberately left at epoch 2.

- restoring the primary store all the way to A@0 produced `REWIND_DETECTED_MULTI_EPOCH`;
- restoring the primary store to B@1 while the committed A@2 pointer object was absent produced `REWIND_DETECTED_MISSING_COMMITTED_POINTER`.

The important distinction is that the second case is **detected loss**, not silently repaired. The anchor says a newer commit decision existed, but the primary backup no longer contains the exact committed pointer object needed to complete it.

## Tamper / truncation controls

Direct anchor-body mutation without rehashing was rejected by anchor integrity validation.

Deleting the newest anchor while leaving a newer primary pointer produced `UNANCHORED_POINTER_ADVANCE` instead of silently accepting the primary as valid history.

## Preserved counterexample / hard truth boundary

Wave 85 also intentionally restored **both** the primary pointer/object store **and** the separate software anchor ledger to their old genesis snapshots.

The validator then reported the restored A@0 state as internally `CONSISTENT`.

That is an important negative result: a software anchor only detects primary-store rewind while some newer anchor fact survives in a separate failure domain. If a privileged actor or backup process rewinds **both** domains together, this contract has no trusted external fact with which to prove that time advanced.

The counterexample is part of the passing self-test and is not hidden or converted into a stronger claim.

## Controls

Two independent executions of the exact committed tool passed **12/12** controls each, including:

- exact Wave 81 genesis identity;
- consistent genesis pointer/anchor binding;
- pre-anchor crash leaves staged pointer non-authoritative;
- post-anchor/pre-pointer crash becomes recoverable pending commit;
- restart completes the exact anchored commit;
- ordinary retention rollback remains allowed;
- rollback advances anchor epoch;
- multi-epoch primary-store rewind detection;
- one-epoch rewind with missing committed pointer detection;
- direct anchor tamper rejection;
- newest-anchor truncation detection;
- explicit reproduction of the combined-primary+anchor rollback limitation.

## Cost

A synthetic single-host infrastructure benchmark measured one successful anchored commit across 100 fresh temporary stores per run:

- run 1 median process CPU: **649.909 microseconds**;
- run 2 median process CPU: **651.831 microseconds**.

These figures are process CPU time for local JSON/hash/fsync orchestration. They are not wall-clock storage latency, not joules, not monolith workload timing, and not evidence that this layer improves compute efficiency.

## Truth boundary

- The anchor is ordinary software storage, **not trusted hardware monotonic state**.
- The result is single-host POSIX evidence, not distributed consensus.
- A surviving separate anchor detects the tested primary-store rewinds; rolling primary and anchor back together remains undetectable by this contract.
- Hashes prove exact content relationships inside the modeled evidence; they do not establish actor identity or evaluator legitimacy.
- No fresh monolith audit, no new retained/incremental/dormant compute win, no energy claim, and no automatic canon/merge action occurred.

## Next gate

**Wave 86: multiple independent anchor witnesses / disagreement recovery.** Test two or more anchor witnesses in separate failure domains so one surviving newer witness can expose rollback of the primary plus another witness. Fail closed on divergent valid witness histories rather than silently choosing a majority or newest-looking record. Preserve the same hard boundary: if every witness and the primary are rolled back together, software-only evidence still cannot prove the lost future.

Evaluator provenance from Wave 83 remains a separate later gate.
