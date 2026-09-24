# Flowing Compute Wave 22 — Content-Addressed Root Spine

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST RUNTIME EVIDENCE`

## Question

After Wave 21 content-addressed the current-state pages, can the remaining ~1.3 KB generation root stop repeating mostly unchanged block references every generation?

Wave 22 splits that root into:

1. a content-addressed block-reference table;
2. an append-only generation spine;
3. one tiny mutable current pointer.

The Wave-21 page CAS and the complete overlay history remain unchanged.

## Binary shapes

### Block-reference table

A content-addressed table binds:

- immutable base artifact/source/semantic identity;
- page widths;
- current page -> block hash / entry-count references.

The saturated table is ~773 bytes.

### Generation spine record

Each generation appends a **292-byte** content-addressed record carrying:

- sequence;
- parent generation hash + offset/length;
- block-table hash + offset/length;
- current overlay artifact hash;
- history-chain root;
- proof-manifest identity;
- final source identity;
- final semantic identity.

The append-only framing is 296 bytes/generation.

### Current pointer

The only mutable spine surface is an **88-byte** pointer to the current generation record.

Rollback moves this pointer to a preserved ancestor; generation records are not rewritten.

## Exact equivalence / rollback

All 64 Wave-21 generations were converted.

At every depth, Wave-22 wake reproduced the exact same edge/local/signature current-state overrides and final semantic identity as the corresponding Wave-21 root.

Explicit pointer moves to generations 1, 5, 6, 24, 63, and 64 all woke the correct historical semantic state.

## Content-addressed table reuse

Only **5 unique block-reference table versions** were needed across all 64 generations.

After the reversible table versions had appeared, later generations reused prior table objects by content hash.

From depth 6 onward, generation metadata persistence is therefore:

- spine append: 296 bytes;
- current pointer rewrite: 88 bytes;
- new table bytes: 0;
- total: **384 bytes/generation**.

## Persistence reduction

Across 64 generations:

- Wave-21 root rewrites: **83,961 bytes**;
- Wave-22 block-table + spine + pointer writes: **28,362 bytes**;
- metadata write reduction: **66.22%**.

The Wave-21 state-block CAS write cost is unchanged between the designs. Including that shared cost:

- Wave-21 total persistent writes: **124,784 bytes**;
- Wave-22 equivalent total persistent writes: **69,185 bytes**;
- additional total write reduction versus Wave 21: **44.56%**.

Relative to Wave 20's monolithic generation-head rewriting, the cumulative reduction is larger still, but Wave 22 claims only its directly controlled comparison against Wave 21.

## Wake tradeoff

Using the same resident state-block CAS backend:

- Wave-21 current root wake median: ~2.374 ms CPU;
- Wave-22 pointer -> spine -> table wake median: ~2.453 ms;
- overhead: **~3.33%**.

The extra indirection is therefore measurable but small on this body.

## Truth boundary

- one host / one current-head contract;
- CPU time is not joules;
- pointer movement is tested as logical rollback, not power-loss atomicity yet;
- table/spine content hashes provide integrity/content identity, not external authentication;
- Wave 22 optimizes persistence/history structure; it does not claim every workload should use this layout;
- no claim of compute/energy from nothing.

## Next gate

Test **crash consistency**. A generation update now has an intentional ordering opportunity:

`content objects -> append spine generation -> atomically move current pointer`.

Inject failure after each stage, prove the previous committed generation remains recoverable, and build a bounded recovery scanner that can distinguish a valid unpointed generation from corrupt/incomplete tail bytes without silently promoting it.
