# Independent adversarial verification — Wave 100 authority-epoch rewind

Date: 2026-09-17  
Lane: `chatgpt/verifier-wave100-authority-epoch-rewind`  
Status: verifier evidence only; keep draft/unmerged; no CANON promotion.

## Exact target

Builder branch head inspected: `0fb2caa805cebf29185d0b40c9f1bbd46199263b` (`Wave 100: document monotonic registry evidence and limits`).

Wave 100 report identifies its CI-tested source commit as `c235f8f0682a98f9d5777df12ef97dce8ca0560d`. The two commits after that source commit add only the Wave 100 report and raw report; they do not alter the protocol/self-test source.

Exact Wave 100 blobs preserved by the builder report:

- protocol: `tools/AXM_FLOWING_COMPUTE_REMOTE_REGISTRY_MONOTONICITY.py` — `9fc2dc55c2d3973010b1804ad766cc632b89fa1f`
- self-test: `tools/AXM_FLOWING_COMPUTE_REMOTE_REGISTRY_MONOTONICITY_SELFTEST.py` — `12491f9996bd7bada33ea742dacbb186dfd037c8`

## What survives

Wave 100 materially closes verifier PR #24's direct registry-generation rewind on the tested path. State-only checkpoints keep the exact registry; a registry-changing checkpoint must use an exact direct generation+1 successor; the sealed transition is resolved at commit; and retained remote histories reject lower, sibling, or skipped registry lineage. The builder also keeps the benchmark boundary honest: synthetic single-process authority bookkeeping only, not network, energy, monolith-workload, retained/incremental/dormant-compute, or physical-independence evidence.

## New reproduced failure

The remote history is monotonic in **record sequence** and now monotonic in **registry lineage**, but it is not monotonic in the authority epoch/state that each record endorses.

The reproducer performs two ordinary Wave 100 state-only advances under one unchanged registry:

1. epoch 1 becomes 3-of-3 authoritative;
2. epoch 2 becomes 3-of-3 authoritative;
3. only the local authority state/store is restored to the valid epoch-1 snapshot; all remote epoch-2 records remain physically present and untouched;
4. before any attack, Wave 100 correctly refuses authority for the rolled-back local state;
5. the guarded Wave 100 `publish()` path correctly rejects appending epoch 1 after epoch 2 with `REMOTE_PREDECESSOR_HOLD`;
6. the unchanged Wave 99 `append_raw()` primitive is then called directly for remote A and B, using their still-valid symmetric credentials. It appends new higher-sequence records whose `authority_epoch` and authority/checkpoint identities point back to epoch 1;
7. A/B now retain a literal sequence `... epoch 1 -> epoch 2 -> epoch 1`, while remote C remains at epoch 2 and every record uses the exact same registry SHA/generation;
8. Wave 100 `verify_remote_registry_history()` accepts A/B because it checks registry movement only;
9. Wave 100 `authority()` returns modeled 2-of-3 authority for the rolled-back local epoch 1.

Expected executable verdict:

`FAIL_REMOTE_SEQUENCE_CAN_ADVANCE_WHILE_AUTHORITY_EPOCH_REWINDS`

This uses no remote record deletion, no manual remote-head rewind, no registry rollback, no registry sibling/skip, no hash collision, and no whole-modeled-domain rollback. The newer remote epoch-2 evidence remains stored. The attack does require valid append credentials for two modeled remote witnesses; that is a meaningful bounded threat because Wave 100 explicitly treats direct use of the unchanged Wave 99 raw primitive as part of the adversarial surface for its second-defense history check, and the current credentials are symmetric test tokens.

## Why it matters

Wave 100 repaired one monotonic dimension—registry identity—but the remote anchor itself still permits a fresh append that semantically endorses an older authority world. Sequence numbers alone therefore do not form an authority maximum. Moving the same contract into separate OS processes in Wave 101 would strengthen failure-domain realism but would not remove this protocol-level rollback path.

The smallest next gate is to bind remote append acceptance to an authority monotonicity rule as well as registry monotonicity. At minimum, a new remote record should not endorse a lower authority epoch than its predecessor, and same/higher epochs should be cross-bound to the exact predecessor authority/checkpoint semantics rather than only record sequence. Recovery/rollback, if intentionally allowed, needs an explicit separately authorized transition rather than looking like a normal append.

Then attack: equal-epoch sibling authority, skipped authority epochs, legitimate crash/recovery, stale local restore with two credential compromises, credential rotation across an authority rollback, and whether one poisoned witness can be quarantined without collapsing healthy 2-of-3 availability.

## Files

- `verification/wave100_authority_epoch_rewind_repro.py` — exact-API executable reproducer importing unchanged builder modules.
- `.github/workflows/verifier-wave100-authority-epoch-rewind.yml` — read-only CI, normal Python and `python -O`.

No builder files are rewritten. Do not auto-merge or promote this verifier lane to CANON.
