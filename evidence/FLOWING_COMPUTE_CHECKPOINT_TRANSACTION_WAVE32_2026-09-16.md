# Flowing Compute Wave 32 — Crash-Consistent Checkpoint-Spine Commit

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST FAILURE-INJECTION EVIDENCE`

## Question

Can the content-addressed checkpoint history introduced in Wave 31 use the same commit discipline as generation state: immutable proof first, append-only checkpoint record second, tiny dual-slot pointer last?

## Transaction order

Wave 32 adds `AXM_FLOWING_COMPUTE_CHECKPOINT_TRANSACTION.py`.

For one newly completed segment:

1. append/fsync immutable content-addressed segment proof;
2. append/fsync parent-linked checkpoint-spine record;
3. write/fsync inactive checkpoint pointer temp;
4. atomic replace inactive pointer + directory fsync.

Only step 4 can advance current checkpoint.

Recovery uses prefix-tolerant scanners for both the segment-object store and checkpoint spine, then validates each pointer's complete checkpoint dependency chain. Unpointed valid checkpoint records remain visible candidates but are never promoted automatically.

## Failure-injection matrix

Real two-segment checkpoint history (1,024 and 2,048) was used.

Passed **9/9** cases:

1. crash after new segment object -> current remains **1,024**;
2. crash after checkpoint record -> current remains **1,024**, valid unpointed **2,048** reported;
3. crash after pointer temp -> current remains **1,024**, valid unpointed 2,048 reported;
4. crash immediately after pointer replacement -> current becomes **2,048**;
5. normal commit -> 2,048;
6. corrupt newly committed pointer -> fallback to **1,024**;
7. corrupt newest segment object -> prefix scanner rejects newest object, fallback to **1,024**;
8. corrupt newest checkpoint record -> prefix scanner rejects newest record, fallback to **1,024**;
9. append garbage/torn bytes after both valid stores -> current **2,048** remains recoverable while tail byte counts remain visible.

## Important state distinction

Wave 32 preserves:

- **exists** — bytes/object/record are present;
- **valid** — content-addressed dependencies verify;
- **committed current** — a valid dual-slot pointer selects that checkpoint.

A valid unpointed checkpoint is evidence/history, not current state.

## Truth boundary

- software failure injection on one host/filesystem; not a universal power-loss guarantee;
- `fsync`/`os.replace` behavior is platform/filesystem dependent;
- prefix-tolerant scans preserve older valid prefixes but do not authenticate storage against an external adversary;
- hashes provide integrity/content identity, not external authentication;
- checkpoint pointer is current checkpoint-proof authority, not application-state authority;
- CPU time is not joules;
- no claim of compute/energy from nothing.

## Next gate

Add bounded checkpoint-store tail repair. It may truncate only scanner-proven invalid suffix bytes. Valid unpointed segment proofs/checkpoint records must survive repair, current pointer selection must remain unchanged, and rebuilt convenience indexes, if added later, must remain non-authoritative.
