# Independent verification — Wave 105 post-history bootstrap re-entry

Status: **FAIL preserved — experimental verifier evidence only**  
Builder base: `5c683032e0834e8a57e1bb780f624eb1cb312d3c`  
Wave 105 tool blob: `1e0e543c57f880c3e631619fa1859c24ace5ff79`  
Wave 105 self-test blob: `c6d39f469e98590823af3a576c4efbb18957d00b`  
Verifier PR: `#30`  
No builder file rewritten. No merge. No CANON promotion.

## What survived

Wave 105 does block the direct PR #29 fresh-domain substitution while the accepted Wave-105 runtime/root history is the active view. The builder's own receipt records Wave 104 regression `46/46`, Wave 105 normal `35/35`, and Wave 105 `python -O` `35/35`.

## New adversarial case

The public `adopt_genesis()` gate decides that bootstrap is still available from two caller-visible facts:

1. `q.current_local(rt, st, boot)` reports `GENESIS` for the supplied mutable runtime pointer; and
2. the supplied certificate store has no retained certificate maximum.

It does not independently discover that accepted signed authority bodies already exist in `st`, nor does it bind one durable certificate-store identity/bootstrap-closed marker that survives caller substitution.

The reproducer therefore:

1. starts from a clean Wave-105 fixture;
2. binds certificate-witness root A;
3. advances normally to authority epoch 1, publishes to all remotes, certifies it, syncs all three registered certificate witnesses, and verifies `AUTHORITATIVE_QUORUM_3_OF_3_MODELED`;
4. leaves that entire accepted world intact;
5. supplies a saved genesis runtime view and saved genesis remote-service snapshots, plus a fresh empty certificate store and a new legitimate certificate-witness domain B;
6. calls unchanged Wave-105 `adopt_genesis()` again against the same retained `st` containing the accepted signed checkpoint/authority bodies;
7. asks unchanged Wave-105 `authority()` about that parallel stale view.

Result:

`AUTHORITATIVE_GENESIS_MODELED`

At the same time the original accepted world remains:

`AUTHORITATIVE_QUORUM_3_OF_3_MODELED`

The original certificate store remains non-empty; the original registered certificate witnesses remain at certificate sequence 1; the original newer remote objects are not modified; signed checkpoint/authority bodies are not deleted; no old certificate-witness credential is stolen; no hash is forged.

This is therefore not merely the disclosed "bootstrap selection before the first accepted checkpoint" case: bootstrap is mechanically re-entered **after** an accepted checkpoint exists, by supplying stale/substitute caller-side views. It also differs from the disclosed same-root whole-domain rollback because the original root/domain remains intact and authoritative while a fresh second root/domain becomes authoritative at genesis in parallel.

## Exact CI reproduction

Workflow run: `35185226846`

Normal Python job `105085747729`: **success**. Exact verdict:

`FAIL_POSTHISTORY_BOOTSTRAP_REENTRY_CREATES_PARALLEL_AUTHORITATIVE_GENESIS`

Optimized Python job `105085747845`: **success**. Same exact verdict.

Normal artifact: `10481706864`, ZIP SHA-256 `745c707574e83f305985f4492fd80592e0fd5026768829e388c5e132c004c5c1`.

Optimized artifact: `10482450398`, ZIP SHA-256 `ff24de12b2625972a42e21bfc79bc500fc2c37a6592ca6afaec29516a23f84b4`.

## Bounded interpretation

This does **not** falsify the narrower statement that an already-active Wave-105 authority/checkpoint chain cross-binds the exact certificate-witness registry SHA. That direct repair survives.

It does falsify treating the root as durably closed merely because authority history once existed. The system currently has no non-substitutable, monotonic fact saying "bootstrap has permanently ended for this lineage." Mutable/stale caller views can re-open genesis and create a second authoritative root/world.

No performance, energy, retained-compute, incremental-compute, dormant-compute, networking, OS-process, device, or provider result is inferred from this failure.

## Next adversarial gate

Before process separation is treated as stronger finality evidence, make bootstrap closure itself part of durable authority:

- a one-way lineage/bootstrap marker or genesis identity must survive runtime-pointer and certificate-store substitution;
- `adopt_genesis()` must reject if **any accepted authority lineage** for that substrate identity already exists, not only when the currently supplied pointer/store says so;
- runtime, certificate-store, remote-service, binding-store, and witness-domain roots need one coherent substrate/lineage identity rather than independently caller-swappable views;
- restart must recover the one accepted root from durable evidence instead of permitting fresh root selection.

Then attack saved-genesis runtime restore, fresh empty certificate-store substitution, stale remote-process images, cloned disks, binding-store loss, certificate-store loss, partial restart, and simultaneous old/new process views.