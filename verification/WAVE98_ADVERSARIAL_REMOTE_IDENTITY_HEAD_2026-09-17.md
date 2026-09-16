# Wave 98 adversarial verification — remote identity / mutable-head boundary

Date: 2026-09-17  
Lane: `verifier/wave98-remote-identity-head-monotonicity`  
Status: verifier evidence only; keep draft/unmerged; no builder rewrite or CANON promotion.

## Exact target

- Builder head: `56bb92218f9af62aceacee1ee625755b8ef54789`
- Wave 98 tool: `tools/AXM_FLOWING_COMPUTE_DUAL_REMOTE_WITNESS.py`
- Tool blob: `bc4347a75f04f6d9ff97e58128d2f5f0a16c85a1`
- Wave 98 report blob: `397e1023f1ec1e233e3b0a6943d4b6e62854512b`

The verifier imports that unchanged tool and re-runs its own controls before adversarial cases.

## What survives

Wave 98 materially repairs verifier PR #22 on the tested normal path:

- local commit now accepts an authority SHA rather than trusting an unsealed caller wrapper;
- content-addressed authority bodies are re-resolved before commit;
- remote record bodies are sealed and key/body checked;
- remote record chains enforce record sequence and previous-record continuity from the selected head;
- an untouched pair of modeled remotes detects ordinary local rollback;
- a direct remote record-body mutation is detected;
- one honest remote outage causes HOLD;
- the builder keeps timing claims bounded to synthetic single-process protocol cost and makes no retained/incremental/dormant compute or energy claim.

## Primary counterexample — one remote can be counted twice

The final `authority()` API iterates caller-supplied keys `remote-a` and `remote-b`, but `verify_remote_chain()` only checks that each supplied service body's `service_id` is *one of* the allowed IDs. It does not require:

- map slot `remote-a` -> service body whose ID is exactly `remote-a`;
- map slot `remote-b` -> service body whose ID is exactly `remote-b`;
- the two resolved service IDs to be distinct;
- the two credential identities to be distinct at authority-read time;
- the two service objects/failure-domain identities to be distinct.

Exact negative case:

1. Build two normal authoritative epochs with both honest remotes.
2. Mark the real `remote-b` offline; unchanged Wave 98 correctly returns `HOLD_REMOTE_UNAVAILABLE`.
3. Construct the caller map with the same real `remote-a` service object in both `remote-a` and `remote-b` slots.
4. No record is forged, rewritten, or resealed.
5. `authority()` accepts the same `remote-a` chain twice and returns an `AUTHORITATIVE...` verdict.

This means the reusable API does not mechanically enforce the report's stronger statement that *both remote witnesses independently report the current authority*. Distinctness currently exists in the fixture, not in the authority contract.

This is not a claim that a real remote provider would necessarily expose this substitution. It is a model/state-boundary failure: the protocol function itself cannot distinguish two independent witnesses from one witness supplied twice.

## Secondary counterexample — immutable newer records do not prevent head rewind

Wave 98 calls each remote chain monotonic, but the service `head` is a mutable unsealed field. `verify_remote_chain()` validates only the chain reachable from the current head and ignores newer valid records that remain in the same immutable record store but are no longer reachable from that head.

Exact negative case:

1. Build authoritative epochs 1 and 2.
2. Preserve the complete epoch-2 remote record stores unchanged, including both newer epoch-2 records.
3. Roll only local runtime authority back to epoch 1. With untouched remote heads, Wave 98 correctly returns `HOLD_REMOTE_DIVERGED`.
4. Change only each modeled remote's mutable `head` back to its epoch-1 record. Do not delete or alter the newer epoch-2 records.
5. `authority()` again returns an `AUTHORITATIVE...` verdict for epoch 1.

This is narrower than Wave 98's already-disclosed whole-domain rollback counterexample: the content-addressed remote stores still contain the newer evidence. Only the mutable head pointers and local runtime authority move backward. The verifier therefore does not treat the current head as mechanically monotonic.

## Benchmark / extrapolation boundary

The Wave 98 report is appropriately cautious. Its 1/4/8-depth timing rows are synthetic single-process authority reads, not network latency, physical independence, energy, or Flowing Compute efficiency evidence. This verifier does not falsify those bounded timings.

However, the two findings above show that the remote count and monotonicity assumptions are partly supplied by caller/configuration state. Performance measurements should not be promoted into claims about independent remote quorum or anti-rollback behavior until witness identity and head monotonicity are themselves authority-bound.

## Required next adversarial gate

Before treating Wave 99 as an independent-failure-domain result:

1. Bind an explicit remote-witness registry into local authority state: exact slot -> exact service ID -> exact credential/public identity -> expected failure-domain identity.
2. Require uniqueness across all required witness identities; reject duplicate/aliased service IDs and duplicate credential identities before counting witnesses.
3. Make remote head advancement itself monotonic and tamper-evident. A verifier must reject a selected head if a later committed head/generation exists, or rely on an external monotonic primitive whose rollback assumptions are explicit.
4. Reproduce outage, reconnect, stale-head replay, duplicate-service substitution, service swap, credential rotation, poisoned-witness recovery, and local rollback while newer remote records remain present.
5. Only then deploy the same contract across genuinely separate machines/providers and test partitions/recovery.

Keep the existing all-current-signer compromise and whole-domain rollback counterexamples visible.
