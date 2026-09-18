# Flowing Compute Wave 23 — Crash-Consistent Generation Commit / Recovery

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST FAILURE-INJECTION EVIDENCE`

## Question

Can the Wave-22 append-only generation spine survive interrupted writes without confusing an uncommitted newer generation with the last committed current state?

## Commit model

Wave 23 introduces two checksummed current-pointer slots (`A` / `B`).

A generation becomes current only after this ordering:

1. immutable state blocks/table objects are durable;
2. the append-only generation spine record is durable;
3. the older pointer slot is replaced with a valid pointer to the new generation.

The other slot continues to reference the previous committed generation.

Recovery chooses the highest-sequence pointer slot that is itself valid **and whose full dependency closure validates**.

A newer valid spine generation without a committed pointer is discoverable evidence only. It is never silently promoted.

## Prefix-tolerant recovery

Recovery scanners treat block/table/spine stores as append-only logs:

- complete valid records form the valid prefix;
- incomplete or hash-invalid tail data stops the scan;
- earlier valid objects remain usable;
- the corrupt/torn tail is reported explicitly.

The CAS index is not treated as recovery authority; block content can be rediscovered from the append-only pack itself.

## Failure matrix

Transition tested: committed generation 4 -> generation 5, where generation 5 introduces 5 new state blocks and a new block-reference table.

10 injected cases passed expected recovery:

1. baseline committed generation 4 -> recover 4;
2. torn state-block pack tail -> recover 4;
3. torn table-store tail -> recover 4;
4. torn spine-record tail -> recover 4;
5. complete generation 5, pointer not moved -> recover 4; report valid unpointed 5;
6. torn pointer-5 slot -> recover 4; report valid unpointed 5;
7. valid committed pointer-5 -> recover 5;
8. corrupt current pointer-5 -> fall back to pointer-4;
9. corrupt generation-5 table after pointer commit -> reject 5 and fall back to 4;
10. corrupt generation-5 state block after pointer commit -> reject 5 and fall back to 4.

All 10 expectations passed.

## Important truth behavior

In the unpointed-generation case, the recovery scanner proves that generation 5 and its dependencies are valid, but still selects generation 4 because only generation 4 has a valid committed pointer.

This separates:

- **exists**;
- **valid**;
- **committed current**.

They are intentionally not the same state.

## Truth boundary

- this is software-level failure injection, not a guarantee for every filesystem/power-loss model;
- `fsync`/device-cache semantics are not yet experimentally measured;
- cryptographic hashes provide integrity/content identity, not external authentication;
- fallback is permitted only to an already committed valid pointer slot;
- valid unpointed generations are not promoted automatically;
- no claim of compute/energy from nothing.

## Next gate

Add a transactional writer/recovery repair mode:

- write immutable objects;
- append and sync generation record;
- atomically replace the inactive pointer slot;
- on recovery, optionally truncate only proven-invalid append-only tail bytes;
- quarantine valid unpointed generations for explicit review/commit rather than silently deleting or promoting them.
