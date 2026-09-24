# Flowing Compute Wave 37 — Append-Only Authorization Receipt Chain

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST AUTHORIZATION-HISTORY EVIDENCE`

## Question

Wave 36 binds the current pointer to the selected intent, but dual pointer rotation eventually overwrites old pointers. Can authorization provenance remain append-only across many commits rather than surviving only as long as an old pointer slot survives?

## Structure

Wave 37 adds content-addressed authorization receipt objects. Each receipt binds:

- exact checkpoint target identity / location;
- exact selected intent hash;
- target checkpoint's parent checkpoint hash;
- parent authorization receipt hash.

The current pointer carries only the current receipt hash. Pointer size remains **120 bytes**: the 32-byte intent field from Wave 36 is replaced by the 32-byte receipt identity.

Recovery validates the current checkpoint, current receipt, exact intent, and the parent-linked receipt chain.

## Three-commit test

Starting from a legacy committed checkpoint at generation 1,024, three explicitly authorized checkpoint commits were materialized:

- 2,048;
- 3,072;
- 4,096.

After the third commit, the two physical pointer slots contained only:

- 3,072;
- 4,096.

The generation-2,048 pointer had therefore been overwritten.

The current 4,096 receipt tip still audited a receipt chain of depth **3** with exact sequences:

`2,048 -> 3,072 -> 4,096`

and exact selected intent hashes for all three transitions.

Authorization receipt store size for this prototype chain: **2,036 bytes**.

## Historical-provenance corruption control

The oldest authorization receipt (2,048) was corrupted while current/previous pointer slots and checkpoint bodies remained intact.

Result:

`HOLD_NO_VALID_RECEIPTED_POINTER`

Neither 4,096 nor 3,072 was allowed to claim a complete authorization chain whose oldest preserved receipt no longer validated.

Restoring the exact old receipt bytes restored generation 4,096 with receipt-chain depth 3.

## Interpretation

Current-state pointers and authorization history are now separate layers:

```text
current checkpoint pointer
        -> current receipt
        -> prior receipt
        -> prior receipt
        -> ...
```

Old pointer replacement no longer erases which explicit prior intents produced the current authorization lineage.

## Truth boundary

- this is authorization provenance evidence, not application-state authority by itself;
- losing old provenance can make a provenance-bound pointer HOLD even if checkpoint bytes still exist;
- current implementation walks the complete authorization-receipt chain during recovery, so recovery cost currently grows with authorization-history depth;
- content hashes prove identity/integrity, not external human authorization semantics;
- one host/filesystem/runtime;
- no claim of compute/energy from nothing.

## Next gate

Separate fast carried authorization proof from full authorization-history audit. Recovery should not need to walk an unbounded receipt chain on every boot, but the full append-only chain must remain available for explicit audit. Acceleration metadata must never become authorization authority.
