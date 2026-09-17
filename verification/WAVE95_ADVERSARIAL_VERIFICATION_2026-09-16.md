# Independent verifier — Flowing Compute Wave 95

Date: 2026-09-16  
Lane: `chatgpt/verifier-wave95-checkpoint-replay-recheckpoint`  
Status: **VERIFIER ONLY / DRAFT / DO NOT AUTO-MERGE / NOT CANON**

## Exact source under test

- Builder branch: `chatgpt/lane-001-platform-extract`
- Builder head: `42bf7230f2537fe7229983769b9130f9c58c2393`
- Wave 95 tool: `tools/AXM_FLOWING_COMPUTE_AUTHORITY_CHECKPOINT_COMPACTION.py`
- Tool blob: `5e38d8ad23dc9c659d774127beb95a745b08a151`
- Wave 95 evidence blob: `b202f5724dc340119e656189718ea64f0a9feb71`
- Wave 95 report blob: `c2aee07a7ab9964e33406a55105eb05cb45c06c6`

This verifier imports the published Wave 95 module unchanged. It does not rewrite the builder implementation, merge anything, or promote any result to canon.

## What survives

Wave 95 materially closes verifier PR #19's direct dangling `att-state` / `key-state` predecessor gap on the **pre-checkpoint full-closure path**. The published implementation now walks history, attestation-state snapshots, signer-key-state snapshots, per-root attestation lineage, and per-root key lineage before checkpoint construction. Its current evidence also keeps the benchmark boundary honest: the reported depth scaling is synthetic single-host validation bookkeeping, not a fresh monolith workload, energy result, distributed-consensus result, or general retained-compute win.

The intended one-cut flow is coherent in the tested path: full closure -> checkpoint -> all three checkpoint witnesses converge -> prune old evidence -> checkpointed authority remains valid -> a normal post-cut transition remains possible.

## Primary failure 1 — older valid checkpoint can be re-promoted

`apply_checkpoint()` treats the runtime's current checkpoint SHA only as an allowed old value while fanning out the caller-supplied checkpoint SHA. It does **not** validate the supplied checkpoint, bind it to the current checkpoint as a predecessor, or require its `epoch` to increase.

The executable reproducer uses only normal public Wave 95 APIs:

1. Advance to a legitimate live generation and create/commit valid checkpoint epoch **1**.
2. Advance normally to a newer live generation and create/commit valid checkpoint epoch **2**.
3. Confirm epoch 2 is current and authority is `AUTHORITATIVE_CHECKPOINTED`.
4. Call normal `apply_checkpoint(rt, cp1)` with the already-valid older checkpoint.
5. All three modeled checkpoint witnesses move from checkpoint 2 back to checkpoint 1, `apply_checkpoint()` returns **`COMMITTED`**, and `authority()` returns **`AUTHORITATIVE_CHECKPOINTED`**.
6. The live authority tuple never rolls back; a further normal transition can still commit.

Verdict:

`FAIL_OLDER_VALID_CHECKPOINT_CAN_BE_REPROMOTED_WITHOUT_LIVE_STATE_ROLLBACK`

This is narrower than whole-domain rollback. Runtime live state, content stores, witness tuples, secrets, and history do not need to be restored from an old backup. The normal checkpoint publication API itself accepts a stale, previously valid checkpoint identity and moves the checkpoint authority backward.

The current checkpoint `epoch` therefore behaves as caller-supplied signed metadata, not a monotonic anti-rollback generation.

## Primary failure 2 — compaction is currently one-shot after pruning

Wave 95 intentionally allows pre-cut evidence to be deleted after checkpoint commit. That works for authority validation because `authority()` can stop at the committed cut.

However, `checkpoint()` does not use the already-committed checkpoint as its historical stop. It always calls `full_tuple_closure()` back to genesis. After the Wave 95-recommended prune, those pre-cut bodies intentionally no longer exist.

The executable negative case performs:

1. normal evolution;
2. normal checkpoint commit;
3. normal `prune_precut()`;
4. confirms checkpointed authority still passes;
5. normal post-cut transition commits;
6. attempts a second normal `checkpoint()` at the newer live state.

The second checkpoint fails on a deliberately pruned predecessor body (`... body missing`). Authority of the existing checkpointed live state remains valid, but the cut cannot be advanced using the published constructor.

Verdict:

`FAIL_COMPACTION_CUT_CANNOT_BE_ADVANCED_AFTER_PRECUT_PRUNE`

This creates a hidden long-run cost: post-cut lineage can accumulate again, but the current Wave 95 API cannot periodically compact it without retaining/recovering the evidence that the previous cut explicitly made disposable. The mechanism is therefore a valid **single historical cut**, not yet a reusable rolling compaction protocol.

## Hidden setup cost / benchmark fairness note

The Wave 95 report correctly excludes checkpoint creation from its checkpointed-validation timing and explicitly says setup is not free. Source inspection shows an additional bounded cost worth preserving: `checkpoint()` calls `full_tuple_closure()` and then calls `manifest_for()`, which calls `full_tuple_closure()` again. Checkpoint creation therefore traverses the retained closure twice before producing four root endorsements in the current implementation.

This does **not** falsify the reported validation-only timing table, because the builder labels that table narrowly. It does mean future amortization claims should count the actual two-pass checkpoint-construction cost or refactor manifest capture into the already-performed closure traversal.

## Why this matters

A checkpoint is supposed to turn a long proof history into a smaller trusted cut. For that cut to act as an anti-rollback / long-run compaction substrate, two properties are still missing here:

- **forward checkpoint lineage:** the next current checkpoint must provably descend from the current checkpoint and move a monotonic checkpoint generation forward;
- **rolling cut advancement:** a new checkpoint must be constructible by validating the post-cut suffix back to the already-authoritative prior checkpoint, rather than demanding evidence all the way back to genesis again.

## Next adversarial gate

Before treating a separate/external checkpoint witness as anti-rollback authority, bind each new checkpoint to the exact predecessor checkpoint SHA + monotonic epoch/generation and reject stale replay **before any witness mutation**. Then make checkpoint creation validate `current -> previous committed cut`, capture the new archive/suffix manifest in one pass, and allow a second cut after the first cut's prehistory has been legitimately destroyed.

Then attack:

- stale checkpoint replay after newer checkpoint publication;
- skipped / duplicate / decreasing checkpoint epochs;
- sibling checkpoint ancestry;
- crash between checkpoint witness fan-out and current checkpoint publication;
- second and third compaction cycles after prior prehistory deletion;
- rollback of local runtime + local checkpoint store against one genuinely separate surviving witness;
- public-verification key rotation with destruction of retired private keys.

Keep all failures visible. No auto-merge and no canon promotion.
