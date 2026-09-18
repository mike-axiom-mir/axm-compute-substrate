# Flowing Compute Wave 34 — Durable Transaction Intent and Authorized Resume

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST TRANSACTION-RECOVERY EVIDENCE`

## Question

Wave 32 correctly leaves a fully valid checkpoint record non-current if the process dies before its final pointer replacement. Can recovery finish that exact interrupted commit without turning arbitrary unpointed history into current state?

## Intent contract

Wave 34 adds `AXM_FLOWING_COMPUTE_CHECKPOINT_INTENT.py`.

Before checkpoint commit work begins, an immutable content-addressed intent binds the exact current parent checkpoint, target segment proof, target checkpoint-record hash + expected append location, and exact target pointer bytes/hash.

Recovery may resume only when the intent validates, its parent is still current, and all exact intended immutable dependencies exist and validate.

## Controls — 7/7 PASS

1. intent only -> `NO_RESUMABLE_INTENT`, current 1,024;
2. intent + segment only -> no resume;
3. intent + exact checkpoint record, pointer missing -> `RESUMED_COMMIT`, current becomes 2,048;
4. rerun resume -> `ALREADY_COMMITTED`, no duplicate state change;
5. valid unpointed checkpoint 2,048 without intent -> no resume, current stays 1,024;
6. corrupt intent + otherwise valid unpointed target -> intent rejected, no resume;
7. target already committed through normal path -> intent recognized as already complete.

## Interpretation

Wave 34 separates:

- **transaction resumption** — finish one exact previously authorized commit;
- **history discovery** — observe valid unpointed objects/records;
- **state authority** — current checkpoint is still selected only by committed pointer slots.

A valid unpointed checkpoint does not gain authority merely because recovery found it.

## Truth boundary

- durable intent is local integrity evidence, not external authentication;
- same host/filesystem/runtime;
- process/power-loss semantics remain dependent on filesystem `fsync`/atomic-replace behavior;
- intent proves prior authorization only within this software contract; it does not create new user/canonical authority;
- ambiguous multiple exact child intents from the same current parent must HOLD rather than choose one;
- CPU time is not joules;
- no claim of compute/energy from nothing.

## Next gate

Integrate intent creation into normal checkpoint transactions and explicitly test conflicting authorized child intents. If more than one distinct complete intent targets different children of the same still-current parent, recovery must HOLD branch ambiguity and preserve both candidates rather than selecting by sequence/timestamp/order.
