# Flowing Compute Wave 24 — Transactional Commit + Bounded Tail Repair

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST FILESYSTEM FAILURE-INJECTION EVIDENCE`

## Question

Can the Wave-23 crash-recovery model become an actual transaction discipline: durable immutable dependencies first, append-only generation second, and only then an atomic dual-slot pointer commit — while repair truncates only tail bytes proven invalid?

## Transaction order

The prototype writer uses:

1. append new immutable state blocks + `fsync`;
2. atomically rebuild the non-authoritative CAS index from the durable block pack;
3. append new content-addressed table + `fsync`;
4. append generation spine record + `fsync`;
5. write + `fsync` inactive pointer temporary file;
6. `os.replace()` temp -> inactive pointer slot + directory `fsync`.

The CAS index is convenience only. Recovery validates from append-only pack/table/spine content and dual pointers.

## Injected transaction crashes — 7 / 7 PASS

Transition: committed generation 4 -> generation 5.

- no failure -> recover generation 5;
- after state blocks -> generation 4;
- after rebuilt index -> generation 4;
- after table append -> generation 4;
- after spine append -> generation 4;
- after pointer-temp fsync -> generation 4;
- immediately after pointer replacement + directory fsync -> generation 5.

Crashes after the complete spine append or pointer-temp write expose generation 5 as a valid unpointed candidate while generation 4 remains authoritative.

## Bounded repair — 8 / 8 PASS

Repair truncates only append-only tail bytes already proven outside the valid prefix.

Observed repairs:

- torn block pack tail: **332 bytes**;
- torn table-store tail: **404 bytes**;
- torn spine tail: **148 bytes**;
- corrupted generation-5 table tail: **809 bytes**;
- corrupted generation-5 block tail: **3,978 bytes**.

Controls:

- valid unpointed generation 5: **0 bytes truncated**, generation 4 stays current and generation 5 remains discoverable;
- valid committed generation 5: **0 bytes truncated**, generation 5 stays current;
- torn pointer-5: append-only stores unchanged; generation 4 is recovered and valid unpointed generation 5 remains visible.

## Recovery cost at current scale

300-run same-process medians:

- committed generation 4 (~33.8 KB scanned): **0.574 ms CPU**, p95 **0.657 ms**;
- committed generation 5 (~38.9 KB): **0.612 ms**, p95 **1.000 ms**;
- generation 4 + valid unpointed 5 (~38.9 KB): **0.792 ms**, p95 **0.989 ms**.

Recovery remains cheap at this tiny history, but it still scans append-only stores from the beginning. Bounded recovery cost is therefore not yet established.

## Truth boundary

- `fsync` calls are issued in this environment; this is not a universal guarantee for every filesystem, drive cache, kernel or power-loss model;
- same-directory `os.replace()` expresses atomic-pointer intent but filesystem-specific guarantees remain external;
- valid unpointed generations are quarantined evidence, not current state and not garbage;
- repair truncates only scanner-proven invalid append-only tails;
- pointer-temp leftovers are ignored rather than silently committed;
- hashes provide content integrity, not external authentication;
- one host / one file-layout contract;
- no claim of compute or energy from nothing.

## Next gate

Recovery scanning is still linear in append-only history. Build a non-authoritative recovery checkpoint / sparse index so normal recovery can begin near the tail, while corruption of that checkpoint always falls back to the authoritative append-only scan. Benchmark thousands of generations and preserve a no-index truth path.
