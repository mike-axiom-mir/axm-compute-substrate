# Independent verifier — Wave 97 authority-boundary challenge

Date: 2026-09-16  
Lane: `verifier/wave97-authority-wrapper-anchor-integrity`  
Status: verifier-only evidence; draft/unmerged; no CANON promotion.

## Exact target

- Repository: `mike-axiom-mir/axm-compute-substrate`
- Builder branch: `chatgpt/lane-001-platform-extract`
- Exact Wave 97 builder head: `20e82977205040168c5fa79b967ee6868aa3f7db`
- Exact Wave 97 tool: `tools/AXM_FLOWING_COMPUTE_SECRET_SIGNER_LINEAGE.py`
- Exact Wave 97 tool blob: `f5ca09a21e64ec390c15e5825751d0d6977d023d`
- Builder report blob: `9e5fcdba8c6dbac9916c2fefd2c05f78e34ed31b`
- Prior verifier incorporated by builder: PR #21, head `2933d68ab47577aa4afd52392ba10d832c1d7e11`

The reproducer independently recomputes the Git blob identity of the imported Wave 97 tool before running attacks.

## What survives

The exact Wave 97 module's own 25 controls are re-run first and remain 25/25 passing. The secret-seeded Lamport change materially closes Wave 96's public-label private-key regeneration bug; successor signer bodies are resolved before acceptance; committed signer-use evidence is part of the authority closure; and an untouched modeled external anchor still detects a simple local rollback.

The builder's benchmark wording is also appropriately narrow: it is synthetic single-host signer/checkpoint bookkeeping, not a retained/incremental/dormant-compute, energy, remote-latency, or distributed-consensus result.

## Failure A — `commit()` trusts an unsealed caller wrapper before resolving the stored authority link

Wave 97 reports `old_replay_blocked` as a passing control. With the honest old authority-link object this is true: `commit()` returns `PREDECESSOR_HOLD`.

However, `commit()` reads `l["predecessor_authority_sha"]` from the caller-supplied Python object before resolving the content-addressed `authority_sha` from `st["L"]`. The resolved stored object is validated, but it is never compared back to the caller wrapper that supplied the predecessor used by the gate.

Exact reproducer:

1. Commit and externally publish epoch 1.
2. Commit and externally publish epoch 2.
3. Confirm honest replay of epoch 1 returns `PREDECESSOR_HOLD`.
4. Copy the old epoch-1 link object and change only its `predecessor_authority_sha` to the current epoch-2 authority SHA. Do **not** reseal it. `chk(..., "authority_sha")` correctly says the wrapper is invalid.
5. Pass that invalid wrapper to unchanged Wave 97 `commit()`.

Observed result: `commit()` returns **`COMMITTED`** and moves all three local witnesses plus `rt["a"]` back to the old epoch-1 authority SHA. The content-addressed store still contains the honest old link whose predecessor is `None`; only the unsealed caller wrapper claimed epoch 2 as predecessor.

The already-published external anchor then forces `auth()` to `HOLD_EXTERNAL_AHEAD`, so this is currently a **local commit/state-boundary failure**, not a demonstrated defeat of the final external-anchor check. It still falsifies the stronger reading of `old_replay_blocked`: replay is blocked only when the caller supplies an honest wrapper.

## Failure B — `auth()` does not validate the modeled external-anchor record it trusts

`pubext()` creates a sealed `modeled-external-anchor/v2` record containing epoch, authority SHA, checkpoint SHA, previous-record SHA, and record SHA. But `auth()` does not call `chk()` on that record, does not validate its schema, epoch, `previous_record_sha`, or chain, and does not resolve the record by content address. It compares only two mutable fields on `ext[-1]`: `authority_sha` and `checkpoint_sha`.

Two exact negative cases survive:

- After a legitimate epoch-2 publication, corrupt the latest anchor's `epoch`, `previous_record_sha`, and `record_sha` so its seal is invalid while leaving authority/checkpoint fields untouched. `chk()` rejects the record, but `auth()` still returns **`AUTHORITATIVE_SECRET_SIGNER_CHECKPOINTED`**.
- Roll local runtime state back to epoch 1. The untouched external anchor correctly returns `HOLD_EXTERNAL_AHEAD`. Then alter only the latest record's authority/checkpoint fields to epoch 1 **without resealing it**, leaving the two-record external history present. `chk()` again rejects the latest record, but `auth()` returns **authoritative** for the stale local state.

This does not require a hash collision, signer-seed compromise, forged Lamport signature, deleting the whole anchor list, or rolling the entire external domain back to a prior snapshot. It requires corruption/tampering of the latest supplied anchor object; Wave 97 currently has no read-time integrity check to distinguish that from a valid external record.

## Benchmark / retained-state boundary

Wave 97's reported timing samples only fresh epoch-1 verification. Current `vuse()` walks predecessor signer-use bodies backwards through the full retained use chain. The verifier wraps only `st["U"]` in a counting dictionary after constructing history and confirms that an authority read at epoch 6 performs more signer-use store reads than at epoch 1.

This is **not** a contradiction of the builder's published performance claim, because the builder explicitly refuses a compute-efficiency or scaling claim. It is an important anti-extrapolation boundary: the epoch-1 median cannot be treated as stable long-run verification cost, and Wave 97's tool does not itself demonstrate preservation of Wave 95/96 compaction/pruning behavior.

## Bounded verdict

Wave 97's secret-seed and successor-key repairs survive the reproduced controls. The latest authority model nevertheless fails two content-addressing/state-boundary adversarial cases:

1. local commit gating trusts an unsealed caller wrapper separately from the stored link it resolves; and
2. final authority trusts mutable external-anchor fields without validating the anchor record's own seal/lineage.

Therefore the correct verifier verdict is:

`FAIL_WAVE97_AUTHORITY_BOUNDARIES_NOT_FULLY_CONTENT_ADDRESSED`

## Next adversarial gate

Before Wave 98 relies on real remote/device witnesses:

- make `commit()` accept an authority SHA (or immediately resolve the supplied link and use only the resolved body's predecessor/epoch fields); reject any caller object whose body/hash does not exactly equal the stored content-addressed object;
- make `auth()` verify the external record seal, schema, epoch, previous-record chain/head identity, and exact binding to the resolved local authority/checkpoint before granting authority;
- define whether external witness records are fetched by immutable content address, monotonic sequence, authenticated remote API, or all three;
- repeat stale replay with malformed wrappers, valid-but-old remote records, forked remote histories, one remote witness compromised, one unavailable, and partial publication;
- keep long-history validation/compaction cost visible rather than extrapolating the epoch-1 synthetic median.

No builder file is rewritten in this verifier lane. No auto-merge or CANON promotion is requested.
