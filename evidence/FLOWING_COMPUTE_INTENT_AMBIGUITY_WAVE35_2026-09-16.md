# Flowing Compute Wave 35 — Ambiguous Intent Branch Hold + Explicit Resolution

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST AUTHORITY/BRANCH EVIDENCE`

## Question

Wave 34 can resume one exact durably intended interrupted checkpoint commit. What happens if two different checkpoint children of the same still-current parent are both fully valid and both were durably intended?

The resolver must not invent a tiebreaker.

## Branch test

Starting current parent: checkpoint **1,024**.

Two different target checkpoint children for sequence 2,048 were created. Both segment objects, checkpoint records, and immutable intent receipts validated, and both intents bound the same current parent. Their target checkpoint identities differed.

Generic resume returned:

`HOLD_AMBIGUOUS_INTENTS`

with exactly **2** eligible intents. No pointer moved.

## Explicit resolution

Wave 35 adds `AXM_FLOWING_COMPUTE_INTENT_RESOLUTION.py`.

The caller supplied one exact `intent_sha256`. The resolver revalidated the selected intent, current parent, exact target dependencies, and exact intended pointer bytes. Only then was the chosen target pointer committed.

Observed:

- selected checkpoint became current at sequence **2,048**;
- current checkpoint hash exactly matched the selected intent target;
- both intent files remained preserved;
- the unselected intent then returned `HOLD_SELECTED_INTENT_PARENT_NOT_CURRENT` because its intended parent was no longer current;
- a bogus/nonexistent intent hash returned `HOLD_SELECTED_INTENT_NOT_FOUND_OR_INVALID` and never fell through to another candidate.

## Interpretation

Wave 35 makes branch ambiguity explicit rather than silently resolving it.

No sequence/timestamp/hash/file-order heuristic is allowed to become authority.

## Truth boundary

- the alternative branch proof is a deliberate structurally valid test branch, not an organic user conflict;
- explicit selection here is a software API input; wider AXM product/user authority still belongs to the applicable governance layer;
- content hashes prove identity/integrity, not meaning or external authorization;
- same host/filesystem/runtime;
- no claim of compute/energy from nothing.

## Next gate

Bind the exact intent identity into the normal transaction commit receipt so post-recovery evidence can prove **which prior authorization** produced the current checkpoint. Keep the unselected branch/intents append-only for audit/rollback rather than deleting them during resolution.
