# Independent verifier — Wave 81 semantic / retention boundary

Date: 2026-09-16  
Builder base: `c28e7d670e216cc344d6023f3a16a4f085086f74`  
Status: `ADVERSARIAL BOUNDARY FOUND — VERIFIER ONLY / NOT CANON`

## What was challenged

Wave 81 adds a content-addressed receipt/checkpoint store plus hashed retention manifests and claims restart recovery verifies retained receipt identity while GC removes only receipts that are unreachable from retained checkpoints.

The narrow positive mechanism survives inspection:

- exact receipt bodies are keyed by their receipt digest;
- wrong/missing bodies fail closed when a retained checkpoint references them;
- an unreferenced stored receipt is not automatically recovery-authoritative;
- deletion is refused when the **supplied** retention manifest resolves the receipt as reachable.

This verification did not independently reread the 11,255,808-byte monolith artifact; Wave 81 itself also explicitly reuses the prior Wave 79 receipt rather than re-auditing those bytes.

## Boundary 1 — checkpoint constructor/validator semantic split

`checkpoint()` requires every receipt reference to have the same `sequence` as the checkpoint. That invariant is not re-enforced by `validate_checkpoint()` or `recover()`.

Counterexample:

1. build a valid checkpoint at sequence 1 referencing the real Wave 79 receipt at sequence 1;
2. change only the checkpoint's outer `sequence` to 999;
3. recompute `checkpoint_sha256`;
4. `put_checkpoint()` accepts it because `validate_checkpoint()` checks schema + self-hash only;
5. `recover()` accepts it because it checks receipt sequence against the embedded ref sequence (1), but never checks checkpoint sequence 999 against that ref sequence;
6. the recovery report then records the reachable receipt under checkpoint sequence **999** although the receipt/ref are sequence **1**.

This is not a SHA-256 break and does not require altering the receipt body. It is a semantic-validation gap: the deserialized/hash-valid object can violate an invariant that the constructor itself treats as mandatory.

## Boundary 2 — retention constructor/validator + GC split

`retention()` explicitly rejects an empty retained-root set. `validate_retention()` does not re-enforce that rule.

Counterexample:

1. start from a valid non-empty retention manifest;
2. set `retained_checkpoints` to `[]`;
3. recompute `retention_sha256`;
4. `validate_retention()` accepts it;
5. `recover()` reports zero retained checkpoints;
6. `candidates()` therefore marks every stored receipt as unreachable;
7. `delete_if_unreachable()` can physically remove a receipt that was reachable under the valid manifest immediately before it.

Wave 81 already states that retention policy is the authority boundary and Wave 82 should add predecessor binding / explicit root-drop evidence. The new verifier result is narrower: **the current validator accepts a retention shape that the current constructor itself forbids**, so constructor semantics and recovery/GC semantics are not yet one contract.

## Benchmark boundary

The Wave 81 median (~116.3 microseconds) is useful bookkeeping evidence, but the self-test obtains it from 1,000 `recover(root, manifest)` calls in one process against the same small store. Files are reread, but OS/process caches are warm. Treat this as warm filesystem/cache recovery bookkeeping, not cold-process restart latency or cold-storage I/O evidence.

No issue with the existing truth statement that the benchmark excludes underlying artifact rereads and is not an energy measurement.

## Reproducer

`verifier/wave81_semantic_retention_boundary.py` imports the actual Wave 81 builder module and deterministically exercises both boundaries. It writes no builder state and uses temporary stores only.

A separate local harness copied the relevant current Wave 81 validation/recovery logic and reproduced both acceptances before this verifier evidence was written:

- sequence-split checkpoint: accepted; recovery reports checkpoint sequence 999 while receipt/ref remain sequence 1;
- rehashed empty retention manifest: accepted by `validate_retention()` despite `retention()` rejecting an empty set.

## Truth boundary

- no claim that SHA-256 was broken;
- no claim of actor authentication, signatures, or remote attestation;
- no claim that the real Wave 79 receipt body recovery failed;
- no claim that the Wave 81 positive missing/tamper controls are false;
- findings are about **semantic invariant enforcement and GC authority input**, not the existence of content-addressed storage;
- verifier branch only; no merge/canon promotion.

## Next adversarial gate

Wave 82 should make the retention state itself a predecessor-linked, current-pointer-selected object and validate constructor invariants on every load, not only at construction time. Then attack:

- stale retention generation passed to GC after a newer root-add;
- crash after mark but before retention pointer move;
- crash after root-drop pointer move but before sweep;
- sibling retention branches with conflicting root sets;
- deep rollback roots whose receipt bodies are shared with newer checkpoints;
- checkpoint sequence / receipt-ref sequence / source-generation sequence cross-binding;
- cold-process restart measurements separately from warm-cache bookkeeping.
