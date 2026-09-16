# Wave 84 adversarial verification — same-store epoch reset + rollback-target boundary

Date: 2026-09-16  
Status: `FAIL — BOUNDED RECOVERY/SELECTION CONTRACT; NARROW CAS RESULT NOT INVALIDATED`

Builder head verified: `8c6e1830812d014d1624cf0a45f338a66cb0ede3`

This lane is independent verifier evidence only. It does not rewrite builder files, merge, or promote canon.

## What survives

Wave 84's narrow same-live-history idea remains structurally meaningful: when a store is already correctly initialized and all state movement goes through `epoch_cas()`, the current pointer identity + commit epoch distinguishes the first visit to retention A from a later visit to the same retention content. The code also validates predecessor epochs one-by-one and the published evidence keeps the one-winner race claim bounded to local POSIX locking rather than fairness or distributed consensus.

I did not independently rerun the published 80-process race benchmark in this verifier turn, so this is not an independent timing/concurrency reproduction.

## Primary counterexample — public reinitialization rewinds the live epoch

Wave 84 says restoring an old pointer body is deliberately not the supported rollback operation. However, `initialize()` has no virgin-store/current-pointer precondition.

It always constructs the deterministic epoch-0 pointer, stores it, and then replaces the current-pointer file with it. On an already-live store this produces:

1. initialize exact A -> `A@0`;
2. normal `epoch_cas()` -> `B@1`;
3. call `initialize()` again on the **same pointer path and same pointer-object store** -> current becomes the exact old `A@0` pointer again;
4. a writer that captured `A@0` before step 2 now calls normal `epoch_cas()` and returns `COMMITTED`.

So the ordinary same-store API can recreate the exact ABA condition the commit epoch is meant to prevent. This does not require a whole-store backup restore, hash forgery, direct current-file tampering, or deletion of the pointer history. The old history remains in the object store; current authority is simply reset to epoch zero by `initialize()`.

If `initialize()` is intended only for virgin paths, that requirement currently exists as convention rather than an enforced contract.

The verifier reproducer imports the actual Wave 84 module and asserts this exact sequence.

## Secondary counterexample — `ROLLBACK` does not prove an old/existing retention target

`epoch_cas()` checks only that `candidate_retention_sha256` is a 64-character string. It does not resolve a retention object, prove the target exists, prove it was previously selected, or prove ancestry/checkpoint eligibility.

Using the official commit path, a fresh `A@0` can commit:

- candidate retention: `ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff`
- `selection_kind='ROLLBACK'`

The call returns `COMMITTED`, and `read_current()` accepts the resulting pointer chain. Therefore Wave 84's epoch layer orders **retention-hash claims**, but the reusable contract does not itself establish that a rollback selected old retention content.

This is a referential/semantic boundary, not a SHA-256 break. It also means `selection_kind` is currently descriptive evidence rather than a validated statement about the relationship between predecessor and selected retention.

## Durability boundary still open

`PointerStore.put()` fsyncs the new object file but does not fsync the pointer-object-store directory after creating the directory entry. The current-pointer replacement does fsync its own parent directory. Therefore the published crash simulation is useful process-level evidence, but power-loss ordering where the current pointer survives while a newly created predecessor/object directory entry does not remains unproven across filesystems.

I did not claim a reproduced power-loss failure in this turn.

## Benchmark / compute boundary

No new retained/incremental/dormant-compute performance claim is challenged here. Wave 84 already labels its ~hundreds-of-microseconds measurements as synthetic pointer/object-store infrastructure work rather than monolith workload, end-to-end latency, joules, or compute-efficiency evidence.

## Next adversarial gate

Wave 85's planned durable epoch anchor should also close the easier same-store reset path before relying on whole-store rewind detection:

1. make initialization creation-exclusive and fail closed if a current pointer / epoch anchor already exists;
2. separate any destructive recovery/reset operation from initialization and ensure it cannot rewind the monotonic anchor;
3. resolve and validate the exact candidate retention object before pointer publication;
4. require `ROLLBACK` targets to carry explicit prior-selection/checkpoint/ancestry evidence rather than accepting any 64-character identity;
5. fsync the pointer-object-store directory before publishing a current pointer that depends on a newly created object;
6. then attack whole-store backup rewind, anchor/store split-brain, stale-anchor restoration, and crash ordering around anchor advancement.

Evaluator/actor legitimacy remains a separate boundary; none of these findings claim that content hashes authenticate an actor or grant constitutional authority.
