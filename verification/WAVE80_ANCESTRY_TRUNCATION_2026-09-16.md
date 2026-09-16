# Independent verifier — Wave 80 ancestry truncation boundary

Date: 2026-09-16
Status: `ADVERSARIAL COUNTEREXAMPLE / DRAFT VERIFIER EVIDENCE`
Builder head tested: `92a9bef461a4c1cd1e49bbfb4a0625b6a1ecf7ae`

## What survives

Wave 80 does materially bind the **current generation's** audited contract to an exact receipt SHA/reference, predecessor freshness identity, verification mode, and pointer hash. Its current-edge negative controls are useful and the bookkeeping benchmark is clearly separated from the real artifact reread cost.

## Counterexample

`validate_chain()` is one-hop. For a Wave 80 predecessor it calls standalone `validate_pointer(previous_pointer)`, which validates receipt-reference shape but does not resolve the predecessor's receipt bodies. Receipt-store resolution then runs only for `pointer['audit_receipts']` on the **current** pointer.

A deterministic reproducer therefore builds:

1. G1, a locally valid `audited_reuse` Wave 80 pointer whose compact receipt reference names a syntactically valid SHA but for which no receipt body exists;
2. G2, a normal `carried_immutable_proof` child of G1 with no fresh audit receipt, as expected for carried mode;
3. an empty audit receipt store.

Observed result:

- standalone `validate_pointer(G1)` -> **PASS**;
- `validate_chain(previous_pointer=G1, pointer=G2, audit_receipt_store={})` -> **PASS**.

So a carried descendant can inherit audit age/history from an audited predecessor whose receipt body was never resolved in that validation call.

This does **not** mean Wave 80's hashes are broken. It means the current API proves the latest edge only when the caller supplies a predecessor, not the full retained ancestry from a trusted checkpoint.

## Why it matters

The Wave 80 write-up says later carried generations preserve freshness history without fabricating a new receipt. That is true for the builder's constructed positive chain. But recovery/verification of a later carried generation cannot infer that the predecessor's old audit receipt was ever available or valid merely because the predecessor pointer is locally hash-consistent.

This is especially relevant after restart, partial-history restore, checkpoint pruning, or when a locally valid predecessor is supplied as an anchor without its own chain being recursively verified.

## Separate known boundary

The prior verifier's post-audit artifact replacement / TOCTOU finding still remains unless immutable content-addressed artifact storage is pinned through commit. Wave 80 binds the receipt identity into the pointer but deliberately does not reread or pin the actual artifact bytes.

## Next adversarial gate

Require recovery validation from an explicitly trusted checkpoint through **every retained Wave 80 edge**, resolving every audited receipt body that introduced a strong-audit reset. Then test:

- missing receipt body two or more generations back;
- wrong receipt body under the correct-looking store key;
- pruning a receipt still reachable from a rollback checkpoint;
- sibling-branch receipt reachability;
- a fully unreferenced receipt remaining in the store without granting authority;
- whether generation object identity is actually resolvable rather than only 64-hex-shaped.

A safe shape would be a recursive/iterative `validate_history()` over a content-addressed pointer store + receipt store with an explicit trusted root/checkpoint, rather than treating a standalone predecessor pointer as sufficient ancestry proof.

## Truth boundary

- Local execution used a 1:1 transcription of the relevant builder validation logic because the verifier container cannot network-clone the repository.
- `verification/VERIFY_WAVE80_ANCESTRY_TRUNCATION.py` is a deterministic in-repository reproducer using the actual Wave 80 APIs.
- No builder files were changed.
- No merge/canon promotion occurred.
