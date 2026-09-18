# Flowing Compute Wave 36 — Intent-Bound Current Pointer

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST AUTHORIZATION-PROVENANCE EVIDENCE`

## Question

Wave 35 required explicit selection when two fully valid authorized children competed for the same current parent. After that selection, can the *committed current pointer itself* preserve which exact prior intent authorized the checkpoint, so a later restart does not have to infer authorization from surviving files/order?

## Change

Wave 36 adds a provenance-aware checkpoint pointer:

- checkpoint sequence / record offset / record length;
- checkpoint SHA-256;
- exact selected `intent_sha256`;
- outer pointer checksum.

The old pointer remains readable as a legacy pointer, but legacy recovery is labeled `LEGACY_UNBOUND` and never claims intent provenance it does not contain.

## Result

A real Wave-35 ambiguous branch fixture was reused. Two distinct valid intents targeted different checkpoint children of the same generation-1,024 parent. Intent A was explicitly selected.

Observed:

- legacy pointer bytes: **88**;
- authorized pointer bytes: **120**;
- provenance cost: **+32 bytes** exactly;
- authorized-pointer parse CPU median: **~1.17 microseconds**;
- selected checkpoint sequence: **2,048**;
- recovered provenance status: `VERIFIED_INTENT`;
- recovered selected intent hash exactly matched the explicit selection;
- unselected intent file remained preserved.

## Provenance-loss control

After commit, the selected intent file was deliberately corrupted while leaving the checkpoint record and provenance-aware pointer intact.

Recovery rejected the sequence-2,048 provenance-aware pointer and fell back to the older valid legacy pointer at sequence **1,024**.

Restoring the exact intent bytes restored sequence 2,048.

This means the machine cannot keep claiming "checkpoint X was authorized by intent Y" after the evidence for Y is lost/corrupt without that loss becoming visible.

## Truth boundary

- content hashes prove byte identity/integrity, not external authorization meaning;
- the intent file remains part of the provenance dependency of this pointer format;
- legacy pointers remain valid state pointers but have no retroactively invented intent provenance;
- one host/filesystem/runtime;
- no claim of compute/energy from nothing.

## Next gate

Dual pointer slots eventually overwrite older pointers. Preserve every `(checkpoint <- selected intent)` binding in append-only authorization receipts so current provenance can be audited beyond the two-pointer retention horizon.
