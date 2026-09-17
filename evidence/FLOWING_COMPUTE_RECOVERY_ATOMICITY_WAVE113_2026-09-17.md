# Flowing Compute Wave 113 — recovery atomicity and honest idempotence

Date: 2026-09-17
Lane: `chatgpt/lane-001-platform-extract` / PR #2
Status: experimental, unmerged, non-CANON

## Why this wave changed direction

Independent verifier PR #37 challenged exact Wave 112 builder head
`a1cf4ccb535142a63a328c4a0dadc86984deaa3b` / tested source
`1be9303bba0712869d40444f5cf1b0e878948ab7`.

Verifier verdict:
`FAIL_FAILED_RECOVERY_MUTATES_LEDGER_AND_THEN_MISREPORTS_ALREADY_COMMITTED`.

The attack keeps a legitimate lower-layer epoch-2 commit and the documented missing trailing
provenance row, but replaces the retained epoch-1 provenance row with a newly content-addressed,
structurally valid row whose `target_state_sha` is semantically wrong. Wave 112 already classifies
that world INCOMPLETE/HOLD before retry. Its recovery retry nevertheless appends epoch 2 provenance
first, then discovers the older corruption. That failed retry therefore mutates retained evidence.
A second exact retry then reports `ALREADY_COMMITTED` while complete history remains INCOMPLETE.

This is a recovery/evidence-integrity and liveness defect. The verifier did not demonstrate stale
authority acceptance.

## Wave 113 change

New reusable tool:
`tools/AXM_FLOWING_COMPUTE_RECOVERY_ATOMICITY.py`

Wave 113 is additive over Wave 112 and changes only the narrow one-row crash-recovery path:

1. Fully validate every already-retained provenance-prefix row against its exact authority link,
   checkpoint, signer-use body, transition semantics, registry lineage and Wave-108 marker pair
   before any recovery write.
2. Require exactly one missing trailing provenance row, the exact committed suffix authority, and
   exactly one retained transition targeting that authority.
3. Snapshot only the provenance store immediately before the allowed append. If the append itself
   raises, an injected failure occurs after append, or complete Wave-112 validation fails, restore
   the exact pre-write provenance store before propagating the error.
4. Return `ALREADY_COMMITTED` only when the requested authority is already bound to the exact
   transition *and* complete Wave-112 history currently validates as `VALID`.
5. Bypass Wave 112's old recovery helper for new commits so an already-committed damaged state cannot
   accidentally fall back into the verifier-identified mutate-then-fail path.

## Exact verifier reproduction and repaired behavior

The Wave-113 self-test first reproduces the unchanged Wave-112 failure:

- first Wave-112 retry: raises after appending the missing row;
- provenance store mutated: **yes**;
- second Wave-112 retry: `ALREADY_COMMITTED`;
- complete history after both retries: `INCOMPLETE_OR_CORRUPT`;
- authority: `HOLD_COMMITTED_HISTORY_INCOMPLETE`.

Against Wave 113, the same damaged prefix is rejected before mutation with
`ValueError:recovery-prefix-target-state-mismatch`; the provenance store is byte-for-structure
identical before and after the failed retry, history remains INCOMPLETE, and authority remains HOLD.

A separately constructed state that already contains the trailing provenance row but still has the
corrupted older prefix is also rejected with
`already-committed-provenance-present-but-history-not-valid`; Wave 113 does not return a false
`ALREADY_COMMITTED`.

## Positive and negative controls

Exact-source CI run: `35222795865`
Job: `105206836767`
Tested source commit: `dfedcab483ba6f798e0cd8e18a8a0c893397efd5`

Results:

- unchanged Wave 112 regression: **22/22 PASS**;
- Wave 113 normal Python: **25/25 PASS**;
- Wave 113 `python -O`: **25/25 PASS**.

Wave 113 controls include:

- direct verifier-37 reproduction against unchanged Wave 112;
- semantic damage in an older retained provenance prefix;
- false `ALREADY_COMMITTED` prevention while full history is invalid;
- clean one-row lower-commit -> provenance crash recovery;
- exact retry after clean recovery;
- mismatched transition rejection without provenance mutation;
- injected failure *during* the append after a partial test mutation, requiring exact rollback;
- injected failure *after* a successful append but before final acceptance, requiring exact rollback;
- successful retry after both injected rollback cases;
- normal two-epoch progress and old/latest exact idempotent retry;
- preserved whole-modeled-domain rollback counterexample.

CI artifact:
`wave113-recovery-atomicity-reports` / artifact `10498630052`
SHA-256: `b97cbe185a1c69ff28cb4a7cc220dd750e71711ba0a5db7f9d16f73c56dac358`

## Preserved counterexample / truth boundary

Wave 113's rollback is an in-memory transaction over the provenance dictionary. It is **not** proof
of process-crash or power-loss atomicity. If the process disappears after a durable write, Python
cannot run the rollback handler.

The older full-domain counterexample also remains: if the authority world, transition/provenance
history, markers, certificates and modeled witnesses are all restored together to a genuine older
snapshot, the older world can still return `AUTHORITATIVE_QUORUM_3_OF_3_MODELED` because no
independent newer fact survives.

No fresh AXM/monolith workload, wall-clock benchmark, synthetic scaling benchmark, energy
measurement, retained/incremental/dormant-compute win, OS-process independence, device independence,
network independence, physical monotonicity, or provider independence is claimed in Wave 113. This
wave is a correctness/recovery repair only.

## Next gate — Wave 114

Move the commit-decision/provenance witness into an actually separate OS process with its own durable
store and credential, while keeping the local Wave-113 checks. Attack at least:

- crash before decision publication;
- crash after durable decision publication but before local provenance persistence;
- crash immediately after local provenance persistence;
- full local rollback while the independent decision witness remains newer;
- stale/cloned local disk;
- witness outage and stale witness restart;
- saved-genesis restart;
- partitions/reconnects and simultaneous old/new process views;
- witness-store corruption/truncation and credential substitution.

Success at that gate would be process/store-separation evidence only. It would still not establish
physical/provider-independent finality or prove retained/incremental/dormant compute is beneficial.
