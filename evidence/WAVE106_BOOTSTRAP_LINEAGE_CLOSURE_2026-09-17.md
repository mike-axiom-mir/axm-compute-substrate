# Wave 106 — bootstrap-lineage closure

Status: **experimental builder evidence; PASS on exact source; no merge / no CANON promotion**

## Why this wave happened

Independent verifier PR #30 found a post-history bootstrap re-entry hole in Wave 105. After a real accepted epoch, a caller could keep the original accepted world intact but supply a saved genesis runtime, saved genesis remote snapshots, a fresh empty certificate store, and a fresh legitimate certificate-witness domain. Unchanged Wave 105 then allowed `adopt_genesis()` again and returned `AUTHORITATIVE_GENESIS_MODELED` for the second world.

Verifier identity preserved exactly:

- verifier PR: `#30`
- verifier head: `ddefa0f3bc1aff5de804efaac1192433a6595ee1`
- evidence blob: `847fb896cb5d4d3c5ac7d7ab264c94833c49225b`
- reproducer blob: `975258a690ae9d8756797666be56ee29b5118051`
- Wave 105 builder base: `5c683032e0834e8a57e1bb780f624eb1cb312d3c`

## Smallest repair tested

Wave 106 adds one append-only lineage store inside the retained authority state `st`.

1. The first genesis root adoption writes one sealed adoption record binding the bootstrap identity, initial user-app state, genesis remote-registry SHA, exact certificate-witness registry SHA, and exact Wave-105 genesis binding SHA.
2. The first successful authority commit appends one sealed closure record binding the adoption record, first authority SHA, first checkpoint SHA, and first Wave-105 binding SHA.
3. Genesis authority is refused after retained authority evidence or a closure exists.
4. If the Wave-106 lineage store disappears while structurally valid authority bodies remain in `st`, bootstrap fails closed instead of selecting a fresh root.
5. Same-root genesis adoption remains idempotent only while bootstrap is still genuinely open.

This is additive. No Wave-105 file was rewritten.

## Positive and negative results

Exact-source CI run `35187496172`, job `105092603905`:

- unchanged Wave 105 regression: **35/35**
- Wave 106 normal Python: **36/36**
- Wave 106 `python -O`: **36/36**
- uploaded report artifact: `10482737736`
- artifact ZIP SHA-256: `a959621c57322ea589089a73299697b27b5d0b86854f8b2fa9ac12941d0bf2f1`
- report JSON SHA-256: `e57a155f33b1e5c753f4f03aa106c5883bee3bd7e3e5bca00643ee614715c61c`

The self-test first reproduces PR #30 against unchanged Wave 105:

`AUTHORITATIVE_GENESIS_MODELED`

The same retained accepted world under Wave 106 no longer permits a new root. A fresh replacement certificate-witness domain is rejected, while a saved genesis view using the already-bound root returns:

`HOLD_BOOTSTRAP_CLOSED`

The original accepted world remains:

`AUTHORITATIVE_QUORUM_3_OF_3_MODELED`

The test also covers exact root/adoption identity, idempotent same-root adoption before closure, different-root rejection before closure, first-authority closure binding, loss of the lineage store with retained authority bodies, tampered adoption evidence, fresh empty certificate-store substitution, same-root saved-genesis replay, explicit reproduction of Wave 105's old failure, forward progress to epoch 2 with only one retained closure record, and `python -O` behavior.

## Failures and counterexamples deliberately preserved

Wave 106 does **not** make bootstrap physically monotonic.

A whole rollback/substitution of the entire retained authority state `st` to a pre-adoption image removes both the lineage memory and the signed authority history. In that fully rolled-back one-process world a new genesis root can still look authoritative. That counterexample is in the passing suite.

There is also an intentional crash-window result: if the lower authority commit succeeds but the process dies before the Wave-106 closure record is appended, Wave 106 returns `HOLD_BOOTSTRAP_CLOSURE_MISSING`. This is a safe availability failure, not an atomic durable transaction.

For migration from older state, a structurally valid prepared-but-uncommitted authority body is conservatively treated as bootstrap-closing evidence if the Wave-106 store is absent. That can sacrifice availability after an abandoned prepare, but it avoids silently reopening genesis when `st` alone cannot prove whether the runtime commit happened.

Initial root choice is still a configuration/bootstrap trust boundary. The adoption record is content-addressed, not independently signed or physically monotonic. Symmetric witness credentials remain test-only. Credential theft, registry rotation, and physical/provider compromise are outside this repair.

## Scope / truth boundary

This wave is a correctness/finality repair. It did **not** run a fresh AXM/monolith performance workload and makes no new performance, energy, network, retained-compute, incremental-compute, dormant-compute, OS-process, device, or provider-independence claim.

## Next gate

Wave 107 should move the repaired bootstrap + authority + certificate contract into separate durable OS-process failure domains and make restart/recovery explicit.

Minimum attacks: process kill/restart before and after bootstrap closure; crash exactly between lower commit and closure persistence; saved-genesis process image restoration; stale/cloned disk restoration; fresh empty certificate-store substitution after restart; lineage-store loss with retained signed authority history; one process offline plus one stale process; two-process rollback; partition/reconnect; credential theft/rotation; and simultaneous old/new process views.

The key question is no longer merely whether three Python objects disagree. It is whether independently persisted processes can recover **one** accepted lineage without silently recreating bootstrap, while whole-store rollback and unavailable-newer-witness counterexamples remain visible.
