# Flowing Compute Wave 84 — ABA-Safe Retention Pointer Epochs

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST POINTER-EPOCH / ROLLBACK EVIDENCE`

## Question

Wave 83 proved that exact retention-content identity plus same-generation CAS gives one current winner, but it also reproduced the classic ABA failure: after `A -> B -> A`, a stale writer prepared against the first A could not tell that history had advanced and returned.

Wave 84 asks whether rollback can remain available while stale pre-rollback writers are rejected.

## Exact prior evidence / provenance

This wave does **not** create new retention semantics or reread a monolith artifact. It places a pointer-history layer over exact identities already preserved by prior waves:

- Wave 81 retention A: `53d91b18e1a12eb27bd503bcfa70b4cd74add598ceaef522c88d7c075fdee4d4`
- Wave 83 DROP retention B: `4078169dce33c5816c7dd1073eaff5920bcfb07284a023726322e67970378dd1`
- Wave 83 KEEP retention: `0f918393dc9d4dfb33fe150bbdca9bd4ecbdca8fab0317becdf94fb9296b1721`
- Wave 83 test-only root-evaluation receipt: `14702460c18e02f50ab09d45b420d4d3188960bde588cc89fad06211bf8fa4ee`
- Wave 82 drop receipt: `9a60bbfb8302bbdc4e06eb39fd7898366b5fc1ef3963978dd857b845946b31a0`

The prior four-root evaluation remains test-only mechanical evidence. Wave 84 does not upgrade it into actor identity or canonical authorization.

## Reusable contract

`tools/AXM_FLOWING_COMPUTE_RETENTION_EPOCH_CAS.py` adds a separate monotonic **commit epoch** to the current retention pointer.

The retention content may move backward during an explicit rollback, but the pointer epoch may only move forward. Every pointer also names the exact predecessor pointer identity, and pointer objects are stored content-addressed before current authority moves.

CAS compares all three visible expectations under the same local lock:

- exact predecessor pointer SHA-256;
- exact predecessor commit epoch;
- exact predecessor retention SHA-256.

This distinction matters: **retention identity answers “what state is selected?”; commit epoch answers “which visit to that state is this?”**

## Positive ABA result

The direct sequence was:

1. exact Wave 81 A selected at pointer epoch **0**;
2. exact Wave 83 DROP B committed at epoch **1**;
3. explicit rollback selected the same old Wave 81 A content at epoch **2**.

The content sequence is therefore still `A -> B -> A`, but the pointer sequence is `A@0 -> B@1 -> A@2`.

A writer prepared against **A@0** then attempted to commit after rollback had reached **A@2**. It returned `CONFLICT` even though the retention content hash was identical to its old expected A.

A newly prepared writer against **A@2** successfully committed the exact Wave 83 KEEP retention at epoch **3**. So the repair does not make rollback a dead end; it only invalidates writers whose history view is stale.

The Wave 83 content-only condition was also kept as a negative control: after `A -> B -> A`, a guard that compares only the A retention hash would still accept the stale A writer. That counterexample remains visible rather than being rewritten away.

## Crash / recovery controls

Wave 84 separates staged pointer evidence from current pointer authority:

- crash after the next pointer object is stored and its temporary current-pointer file is fsynced, but **before** `os.replace`: old pointer/epoch remains current; staged pointer has zero authority;
- retry from the unchanged expected pointer succeeds;
- crash **after** atomic replacement: restart observes and validates the new epoch, including its predecessor chain.

A direct epoch edit without rehashing failed pointer integrity. A forged jump from the recovered pointer to epoch 50 with a recomputed outer pointer hash also failed because the stored predecessor chain did not advance by exactly one epoch.

## Concurrency

Two independent runs each executed **40 true two-process same-epoch races** from the exact Wave 81 retention identity.

Run 1: 17 DROP wins / 23 KEEP wins.  
Run 2: 18 DROP wins / 22 KEEP wins.

Every one of the **80 races** produced exactly one `COMMITTED` writer and one `CONFLICT` writer. The win ratios are scheduler noise and are **not** a fairness claim.

## Controls

The Wave 84 self-test passed **18/18** controls in both independent executions, including:

- exact Wave 81 starting identity;
- explicit reproduction of the legacy content-only ABA weakness;
- forward epoch commit;
- rollback to exact old content without epoch rewind;
- distinct pointer identity for the second visit to A;
- rejection of stale A@0 writer at A@2;
- successful fresh writer after rollback;
- full predecessor-chain validation;
- crash before replace;
- staged evidence without authority;
- retry after pre-replace crash;
- recovery after post-replace crash;
- direct epoch tamper rejection;
- recomputed-hash epoch-jump rejection;
- one-winner concurrent CAS.

## Cost

The synthetic local pointer/object-store benchmark measured successful single-host commits over 100 fresh temporary stores per run:

- run 1 median process CPU: **323.918 microseconds**;
- run 2 median process CPU: **433.891 microseconds**.

These timings are intentionally bounded infrastructure measurements. They are not monolith workloads, not end-to-end filesystem latency, not energy measurements, and not a claim that epoch CAS improves compute efficiency.

## Truth boundary

- The commit epoch is a local software history-ordering mechanism, **not trusted hardware monotonic storage**.
- Rollback is performed by creating a new pointer epoch selecting old retention content; restoring an old pointer body is deliberately not the supported operation.
- The pointer hash + predecessor chain catches the tested contract-level tampering, but does not establish actor identity or protect against a privileged hostile rewrite of the entire pointer/object store.
- This is single-host POSIX evidence using `flock`, fsync, and atomic replacement; it is not distributed consensus and makes no NFS/multi-host claim.
- No fresh monolith audit ran in Wave 84.
- No retained/incremental/dormant compute win is claimed by this wave.
- No canonical merge, automatic promotion, energy, or over-unity claim is made.

## Next gate

**Wave 85: durable epoch-anchor recovery / whole-store rollback attack.** The current repair defeats ordinary ABA inside the modeled pointer history, but a privileged or accidental restore of the *entire* pointer-object store to an older backup could rewind both the current pointer and its predecessor chain together. Test a separate append-only epoch anchor / recovery ledger that can detect whole-store rewind after restart without making ordinary retention rollback impossible.

Evaluator provenance remains a separate later gate: the Wave 83 root-evaluation receipt still proves a mechanical evidence path, not legitimate evaluator identity.
