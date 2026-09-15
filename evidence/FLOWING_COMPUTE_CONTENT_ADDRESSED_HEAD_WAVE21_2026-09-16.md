# Flowing Compute Wave 21 — Content-Addressed Current Head Blocks

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST RUNTIME EVIDENCE`

## Question

Can the Wave-20 resolved current head stop rewriting unchanged current-state bytes every generation by storing override pages as content-addressed objects, while preserving exact current state and append-only history?

## Logical form

The saturated Wave-20 head contains:

- 82 edge-digest overrides;
- 82 component-local-hash overrides;
- 127 propagated-signature overrides.

Later reversible generations change only:

- 1 edge digest;
- 1 local hash;
- 42 signatures.

Wave 21 partitions those overrides into fixed deterministic pages and stores page bodies by SHA-256. The generation root stores only block references plus current source/semantic/history identity.

## Exact equivalence

All 64 Wave-20 generations were converted sequentially. At every depth, waking the content-addressed head reproduced the exact same edge/local/signature overrides and final native semantic identity as the Wave-20 monolithic head.

## File-per-block negative control

The first physical CAS used one file per block. Storage was excellent, but saturated updates were ~86% slower CPU because the updater reopened/parsed five tiny block files.

That physical layout was rejected.

## Append-only packed CAS

The second layout stores unique blocks once in one append-only block pack plus a compact hash->offset index.

Final store after 64 generations:

- unique block payloads: 47;
- pack bytes: 33,439;
- index bytes: 2,112.

Across all 64 generation writes:

- Wave-20 monolithic head rewrites: **671,761 bytes**;
- Wave-21 packed-CAS persistent writes (new pack records + index generations + roots): **124,784 bytes**;
- persistent write reduction: **81.42%**.

After depth 5, both states of the reversible changed pages already existed in the CAS. From depth 6 onward, later toggles emitted **zero new state blocks**; only the ~1.3 KB generation root changed.

This demonstrates non-adjacent reuse: when state returns to a previously seen page body, the new generation points back to the existing content-addressed object.

## Resident runtime update

A second control removed unnecessary CAS rereads. After wake, current pages remain resident and an overlay mutates those resident pages directly. Persistence writes only changed page versions plus the generation root.

Across actual late generations 7..64:

- monolithic head update median: ~0.50–0.52 ms CPU;
- resident packed-CAS update median: ~0.48–0.50 ms;
- observed update saving across repeated batches: **3.35–4.80% CPU**;
- no new state blocks were written across those 58 reversible generations.

## Wake tradeoff

The content-addressed representation currently has a small wake penalty because a fresh runtime resolves multiple referenced pages instead of parsing one 10.7 KB monolithic head.

Three repeated same-host batches observed:

- wake CPU overhead: **10.60–13.58%**;
- resident-update CPU saving: **3.35–4.80%**;
- CPU-only break-even: **~8.15–13.22 updates per wake**, median ~13.08.

So Wave 21 does **not** establish content-addressing as a universal replacement for the monolithic head.

## Policy implication

For this exact body/host:

- update-heavy / write-amplification-sensitive use -> content-addressed head is attractive;
- wake-heavy/read-mostly use -> monolithic head remains cheaper CPU;
- intermediate use -> preserve uncertainty / measure rather than forcing a default.

`AXM_FLOWING_COMPUTE_HEAD_STORAGE_POLICY.py` encodes a conservative CPU HOLD band (8–14 expected updates per wake) and keeps CPU vs write-byte objectives separate.

## Truth boundary

- one host and one current-head state contract;
- CPU time is not joules;
- file-per-block failure is preserved, not discarded;
- packed CAS still has higher wake CPU in current form;
- persistent write reduction is not equivalent to CPU reduction;
- resident update measurements assume the current head is already awake;
- content hashes provide integrity/content identity, not external authentication;
- no claim of compute/energy from nothing.

## Next gate

Remove the remaining generation-root rewrite amplification. The ~1.3 KB root repeats mostly unchanged block references and history metadata every generation. Test a content-addressed **root spine** where unchanged block-reference tables are retained and only the generation delta + current pointer are written, while fresh wake remains bounded and rollback/audit retain exact generation identity.
