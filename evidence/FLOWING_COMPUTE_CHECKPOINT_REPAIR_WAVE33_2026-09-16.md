# Flowing Compute Wave 33 — Bounded Checkpoint-Store Tail Repair

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST REPAIR EVIDENCE`

## Question

Can the Wave-32 checkpoint stores remove torn/corrupt append-only suffix bytes without turning repair into garbage collection or changing which checkpoint the committed pointers select?

## Rule

Wave 33 adds `AXM_FLOWING_COMPUTE_CHECKPOINT_REPAIR.py`.

Repair may truncate only bytes beyond the prefix-tolerant scanner's last proven-valid boundary. It must not delete structurally valid unpointed objects/records simply because no current pointer names them.

Before and after selection must remain identical.

## Controls — 4/4 PASS

### Garbage tails after committed checkpoint 2,048

Segment store removed exactly **3** invalid bytes; checkpoint spine removed exactly **2**. Selected checkpoint stayed **2,048**.

### Valid unpointed checkpoint 2,048

A crash after the checkpoint record but before pointer replacement left current 1,024 plus a fully valid unpointed 2,048 candidate. Repair removed only later garbage suffix and preserved the valid unpointed checkpoint/object. Current stayed **1,024**.

### Corrupt newest segment object

Prefix scanning proved the newest segment object invalid, so repair truncated the **359-byte** corrupt suffix. Current stayed 1,024. The structurally valid checkpoint record that referenced the now-missing object was deliberately not silently deleted.

### Corrupt newest checkpoint record

Repair truncated the **556-byte** invalid checkpoint-record suffix while preserving its already-valid content-addressed segment object. Current stayed 1,024.

## Interpretation

Repair is not authority and not garbage collection. It restores append-only stores to scanner-proven valid prefixes while preserving valid-but-uncommitted evidence.

Recovery, repair, and future archival/GC policy remain separate responsibilities.

## Truth boundary

- software corruption/failure injection on one host/filesystem;
- truncation relies on prefix-scanner correctness;
- structurally valid but dependency-invalid history may remain after repair by design;
- valid unpointed history is preserved rather than canonized or deleted;
- repair must not change committed pointer selection;
- hashes provide integrity/content identity, not external authentication;
- no claim of compute/energy from nothing.

## Next gate

Add a content-addressed transaction-intent receipt. Recovery may resume the final pointer replacement only when an unpointed checkpoint exactly matches a previously durable intent bound to the still-current parent checkpoint. Arbitrary unpointed checkpoints without a matching intent must remain non-current.
