# Wave 99 independent adversarial verification — registry generation rollback

Date: 2026-09-17  
Lane: `verifier/wave99-registry-generation-rollback`  
Status: verifier-only evidence; draft/unmerged; no builder rewrite, no auto-merge, no CANON promotion.

## Exact source under test

- Builder head: `0c3ea28b4d731cde942d337c87a046f363d496c2`
- Wave 99 protocol blob: `c4c0a6bcabeafcf19502303857d1fc4da6fe8ea5`
- Wave 99 self-test blob: `6efa792265c4fd3b54e7cfb192f5e1440402010a`
- The builder's append-only exact-source correction is preserved and not rewritten.

## What survives

Wave 99 materially repairs verifier PR #23's two direct attacks on the tested path: duplicate Python service-object aliasing is rejected, and rewinding only a service's mutable `head` while newer records remain in the store is rejected because the selected head must be the maximal retained sequence. Registry rows also bind slot -> service ID -> credential hash -> modeled failure-domain ID, and 2-of-3 quorum behaves as published for one unavailable or one divergent/poisoned witness.

The benchmark/truth boundary is also appropriately narrow. The published timings remain synthetic single-process authority bookkeeping; they are not retained/incremental/dormant compute, network, energy, or physical-failure-domain evidence.

## New reproduced failure

Wave 99 gives registries an explicit `generation` and predecessor chain, but the current-to-target transition is not enforced when a new signed checkpoint is prepared:

- `prepare()` accepts any registry body already present in the registry store as `target_registry_sha`;
- it does not require the target registry to equal the current registry or to be the exact direct successor of the current registry;
- `commit()` checks the checkpoint/state binding but does not check registry generation monotonicity;
- remote `publish()` checks authority predecessor continuity, but not registry-generation continuity;
- `verify_remote_full()` checks record hashes, sequence order, and previous-record hashes, but does not require each record's registry to be the same or a direct successor of the prior record's registry.

The reproducer uses only normal Wave 99 APIs and unchanged witness credentials/domains:

1. Start at registry generation 0.
2. Create and normally commit generation 1 with identical witness rows; publish all three remotes.
3. Create and normally commit generation 2 as the direct successor of generation 1; publish all three remotes.
4. From the fully authoritative generation-2 state, call normal `prepare(..., target_registry_sha=<generation-0>)`.
5. `commit()` returns `COMMITTED`, moving the signed local authority binding from registry generation 2 directly back to generation 0 while the local authority epoch itself advances.
6. Publish only remote A and B through the normal API. Their generation-2 records remain retained in each remote record store; a new generation-0 record is appended after them at the next sequence number.
7. Remote C is left untouched at the newer generation-2 head.
8. `authority()` returns `AUTHORITATIVE_QUORUM_2_OF_3_MODELED` for the generation-0 registry.

No record is deleted, no hash is forged, no remote head is manually rewound, no credential is changed, no service object is aliased, and no old remote history is removed. The registry lineage itself moves backward under a forward authority epoch and two ordinary remote appends.

## Why this matters

The current registry predecessor chain proves that each registry body has some valid ancestry in isolation, but it does not prove that the live authority moved forward along that ancestry. A stale historical registry can become current again through the normal signed/quorum path. That makes the registry generation a descriptive field rather than a mechanically monotonic authority boundary.

This is narrower than the builder's already-preserved whole-modeled-domain rollback counterexample: local authority epoch advances, newer remote records remain physically present in the modeled stores, and one remote remains on the newer registry generation. The rollback is accepted because the new local checkpoint names the stale registry and two witnesses append that stale registry as their newest record.

## Bounded verdict

`FAIL_WAVE99_REGISTRY_GENERATION_CAN_REWIND_THROUGH_NORMAL_SIGNED_QUORUM_PATH`

Wave 99's direct PR #23 repairs survive, but the stronger predecessor-bound registry/credential-lineage story is not yet monotonic across live authority transitions.

## Next adversarial gate

Before treating the registry as an independent authority boundary, bind every live registry transition to the exact current registry:

- normal state-only checkpoints must keep the same registry SHA;
- a registry-changing checkpoint must name the exact current registry as predecessor and require target generation = current generation + 1;
- remote append/recovery records should carry enough registry-transition evidence to reject a lower/sibling/stale registry after a newer one has been observed;
- recovery/credential rotation must validate the changed slot set and transition kind, not only target registry validity in isolation.

Then attack direct generation rollback, sibling-registry jumps, skipped generations, stale registry replay after credential rotation, one-witness stale restoration, partial registry fan-out, and two-provider disagreement before moving to physical multi-process/provider claims.
