# Independent adversarial verification — Wave 101

Date: 2026-09-17  
Lane: `verifier/wave101-quorum-global-maximum`  
Status: verifier evidence only; draft/unmerged; no CANON promotion.

## Exact target

- repository: `mike-axiom-mir/axm-compute-substrate`
- builder branch: `chatgpt/lane-001-platform-extract`
- exact Wave 101 builder head: `08bed3007e118fdcc2499c873da85ed9355c96d2`
- Wave 101 protocol blob reported by builder: `9283b748aefcc1914eb763748674ee83a5ec3b15`
- Wave 101 self-test blob reported by builder: `4bddbd849319b7475ac399dd96cd72ceb498545a`

The verifier imports the unchanged Wave 101 implementation. No builder source is patched.

## What survives

Wave 101 materially closes verifier PR #25's direct per-witness `epoch 1 -> 2 -> 1` append attack. A retained individual witness history must now begin at authority epoch 1 and increase exactly by one record at a time. Equal-epoch sibling appends and skipped epochs are rejected by the new history check. The report also keeps benchmark language properly bounded to synthetic single-process protocol bookkeeping rather than retained/incremental/dormant-compute, energy, network, or physical-provider evidence.

## New counterexample — quorum has no global remembered maximum

The new monotonicity is per witness, but quorum authority does not reject an older local world merely because one intact witness still retains proof of a newer world that previously reached quorum.

Exact sequence reproduced:

1. Establish epoch 1 on remote A, B, and C.
2. Advance normally to epoch 2 locally and publish only to A and B.
3. Confirm Wave 101 reports epoch 2 authoritative by 2-of-3 quorum. C is deliberately only lagging at epoch 1.
4. Restore only the mutable local runtime/current pointer to its epoch-1 value. Keep the current content-addressed local store, including epoch-2 authority/checkpoint bodies. With A+B still at epoch 2, Wave 101 correctly HOLDs. This is the control.
5. Restore only remote B's service store to its earlier epoch-1 snapshot. Do not alter remote A. Remote A still retains `[1, 2]`; B now has `[1]`; C naturally still has `[1]`.
6. Ask unchanged Wave 101 `authority()` about the old local epoch-1 runtime.
7. Wave 101 counts B+C as the current 2-of-3 quorum, treats intact newer A merely as divergent, and returns `AUTHORITATIVE_QUORUM_2_OF_3_MODELED` for epoch 1.

This is narrower than the builder's already-preserved whole-modeled-domain rollback counterexample. It does **not** roll all three remotes back together. One remote remains intact with the newer previously-authoritative epoch, and the newer local content-addressed bodies remain present. The failure needs one stale remote-store restoration plus one witness that legitimately lagged the prior 2-of-3 commit, together with the mutable local current pointer being restored.

## Why it matters

Per-witness chronology is not yet a quorum-level monotonic authority maximum. Once epoch 2 has been accepted by quorum, an intact witness retaining epoch 2 does not veto a later claim that epoch 1 is authoritative. In a stale-store/restart experiment, process separation by itself will not close this: the decision rule must remember or derive the highest authority known to have reached authoritative quorum, or otherwise make an intact ahead witness prevent an older quorum from being accepted.

This does not claim an unauthenticated remote append forgery, physical/provider compromise, or production-distributed-consensus break. The modeled system still uses symmetric test credentials and in-process objects. The reproduced failure is specifically a stale-proof / quorum-maximum contract gap.

## Exact reproducer

`verification/wave101_quorum_global_maximum_repro.py`

Expected terminal verdict:

`FAIL_PREVIOUSLY_AUTHORITATIVE_NEWER_EPOCH_CAN_BE_FORGOTTEN_BY_ONE_STALE_REMOTE_PLUS_ONE_LAGGING_REMOTE`

The reproducer first proves epoch 2 was authoritative, proves local-pointer-only rollback is rejected, then performs the narrower B-only stale-store restoration and records the false old-world authority result.

## Next adversarial gate

Before treating Wave 102 process separation as a stronger safety result, bind a quorum-level monotonic maximum. A healthy witness that is ahead of the candidate local authority should not be silently outvoted by two older heads when that ahead epoch was previously authoritative. Possible designs include an independently durable quorum certificate/maximum, or remote records that carry enough quorum-commit evidence to prove which authority epochs crossed the acceptance threshold.

Then attack: one stale remote plus one laggard; one unavailable newer witness; restart with a stale local pointer while newer local bodies remain; partial publish before and after quorum; stale credential rotation; and recovery that must distinguish `newer but never quorum-committed` from `newer and previously authoritative`.
