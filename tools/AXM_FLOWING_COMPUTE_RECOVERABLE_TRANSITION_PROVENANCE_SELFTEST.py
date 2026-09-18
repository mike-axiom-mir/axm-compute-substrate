#!/usr/bin/env python3
"""Wave 112 exact-API positive/negative self-test.

Reproduces verifier PR #36's Wave-111 crash/retry failure first, then requires exact idempotent
provenance closure and rejects mismatched or over-broad recovery. Also instruments retained-history
marker-chain linearization at synthetic depths 1/4/8. The scaling probe is structural correctness
only: no wall-clock, energy, or end-to-end performance claim is made.
"""
from __future__ import annotations

import argparse
import json
from copy import deepcopy

import AXM_FLOWING_COMPUTE_RECOVERABLE_TRANSITION_PROVENANCE as w
import AXM_FLOWING_COMPUTE_TRANSITION_PROVENANCE_LEDGER as w111
import AXM_FLOWING_COMPUTE_TRANSITION_EVIDENCE_GUARD as w110
import AXM_FLOWING_COMPUTE_COMMITTED_HISTORY_MANIFEST as w108
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w104

q = w.q
g = w.g


def new_world():
    st, priv, boot, rt, services, tokens, rs = q.fixture()
    ts = {}
    cs = g.new_certificate_store()
    domain = w104.new_certificate_witness_domain()
    bs = {}
    w.adopt_genesis(rt, st, boot, services, rs, ts, cs, domain, bs)
    return st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs


def check(report: dict, name: str, ok: bool, detail=None):
    report["controls"].append({"name": name, "ok": bool(ok), "detail": detail})
    if not ok:
        report["failed"] += 1


def crash_world():
    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world()
    cp, use, link, tr, body = w.prepare(
        rt, st, priv, boot, services, rs, ts, cs, domain, bs,
        target_user_app_state_sha="41" * 32,
    )
    lower = w110.commit(rt, st, boot, rs, ts, link["authority_sha"], tr, bs)
    return (st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs,
            cp, use, link, tr, body, lower)


def reproduce_wave111_failure() -> dict:
    (st, _priv, boot, rt, services, _tokens, rs, ts, cs, domain, bs,
     _cp, _use, link, tr, _body, lower) = crash_world()
    before = w111.commit_status_state(st, boot, rt, rs, bs, ts)
    authority_before = w111.authority(rt, st, boot, services, rs, ts, cs, domain, bs)
    retry_result = None
    retry_exception = None
    try:
        retry_result = w111.commit(rt, st, boot, rs, ts, link["authority_sha"], tr, bs)
    except Exception as exc:
        retry_exception = f"{type(exc).__name__}:{exc}"
    after = w111.commit_status_state(st, boot, rt, rs, bs, ts)
    return {
        "lower_commit": lower,
        "before": before,
        "authority_before": authority_before,
        "retry_result": retry_result,
        "retry_exception": retry_exception,
        "after": after,
        "recovered": after.get("status") == w111.HISTORY_VALID,
    }


def wave112_recovery_case() -> dict:
    (st, _priv, boot, rt, services, tokens, rs, ts, cs, domain, bs,
     _cp, _use, link, tr, _body, lower) = crash_world()
    before = w.commit_status_state(st, boot, rt, rs, bs, ts)
    authority_before = w.authority(rt, st, boot, services, rs, ts, cs, domain, bs)
    recovered = w.commit(rt, st, boot, rs, ts, link["authority_sha"], tr, bs)
    after = w.commit_status_state(st, boot, rt, rs, bs, ts)
    repeated = w.commit(rt, st, boot, rs, ts, link["authority_sha"], tr, bs)
    for slot in q.REMOTE_IDS:
        w.publish(rt, st, boot, services, tokens, rs, slot)
    w.certify_and_sync(rt, st, boot, services, rs, cs, domain)
    final_authority = w.authority(rt, st, boot, services, rs, ts, cs, domain, bs)
    return {
        "lower_commit": lower,
        "before": before,
        "authority_before": authority_before,
        "recovery_result": recovered,
        "after": after,
        "repeat_result": repeated,
        "final_authority": final_authority,
    }


def mismatch_recovery_case() -> dict:
    (st, _priv, boot, rt, _services, _tokens, rs, ts, _cs, _domain, bs,
     _cp, _use, link, tr, _body, lower) = crash_world()
    wrong = "f" * 64 if tr != "f" * 64 else "e" * 64
    error = None
    try:
        w.commit(rt, st, boot, rs, ts, link["authority_sha"], wrong, bs)
    except Exception as exc:
        error = f"{type(exc).__name__}:{exc}"
    after_wrong = w.commit_status_state(st, boot, rt, rs, bs, ts)
    exact = w.commit(rt, st, boot, rs, ts, link["authority_sha"], tr, bs)
    after_exact = w.commit_status_state(st, boot, rt, rs, bs, ts)
    return {
        "lower_commit": lower,
        "wrong_transition": wrong,
        "exact_transition": tr,
        "wrong_retry_error": error,
        "after_wrong": after_wrong,
        "exact_retry_result": exact,
        "after_exact": after_exact,
    }


def non_trailing_loss_case() -> dict:
    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world()
    _cp1, _use1, link1, tr1, _body1, _cert1, _certbody1 = w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs, "wave112-loss-e1"
    )
    _cp2, _use2, link2, tr2, _body2, _cert2, _certbody2 = w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs, "wave112-loss-e2"
    )
    st[w.PROVENANCE_STORE].clear()
    before = w.commit_status_state(st, boot, rt, rs, bs, ts)
    error = None
    try:
        w.commit(rt, st, boot, rs, ts, link2["authority_sha"], tr2, bs)
    except Exception as exc:
        error = f"{type(exc).__name__}:{exc}"
    after = w.commit_status_state(st, boot, rt, rs, bs, ts)
    return {
        "first_authority": link1["authority_sha"],
        "first_transition": tr1,
        "second_authority": link2["authority_sha"],
        "second_transition": tr2,
        "before": before,
        "retry_error": error,
        "after": after,
    }


def abandoned_prepare_case() -> dict:
    st, priv, boot, rt, services, _tokens, rs, ts, cs, domain, bs = new_world()
    _cp, _use, _link, _tr, _body = w.prepare(
        rt, st, priv, boot, services, rs, ts, cs, domain, bs,
        target_user_app_state_sha="55" * 32,
    )
    state = w.commit_status_state(st, boot, rt, rs, bs, ts)
    auth = w.authority(rt, st, boot, services, rs, ts, cs, domain, bs)
    second_error = None
    try:
        w.prepare(
            rt, st, priv, boot, services, rs, ts, cs, domain, bs,
            target_user_app_state_sha="56" * 32,
        )
    except Exception as exc:
        second_error = f"{type(exc).__name__}:{exc}"
    return {"state": state, "authority": auth, "second_prepare_error": second_error}


def marker_scaling_case(depth: int) -> dict:
    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world()
    for i in range(1, depth + 1):
        w.advance_all(
            st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs,
            f"wave112-synthetic-depth-{depth}-epoch-{i}",
        )

    calls = {"marker_chains": 0}
    original = w108._marker_chains

    def counted(state):
        calls["marker_chains"] += 1
        return original(state)

    w108._marker_chains = counted
    try:
        state = w.commit_status_state(st, boot, rt, rs, bs, ts)
    finally:
        w108._marker_chains = original
    return {
        "depth": depth,
        "status": state.get("status"),
        "marker_chains_calls": calls["marker_chains"],
        "structural_only": True,
    }


def whole_domain_rollback_counterexample() -> dict:
    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world()
    w.advance_all(st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs, "wave112-rb-e1")
    snap_st = deepcopy(st)
    snap_rt = deepcopy(rt)
    snap_services = deepcopy(services)
    snap_ts = deepcopy(ts)
    snap_cs = deepcopy(cs)
    snap_bs = deepcopy(bs)
    snap_disks = domain.disk_snapshots()
    w.advance_all(st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs, "wave112-rb-e2")
    domain.restore_disks(snap_disks)
    authority = w.authority(
        snap_rt, snap_st, boot, snap_services, rs, snap_ts, snap_cs, domain, snap_bs
    )
    return {
        "name": "whole-modeled-domain-rollback-to-genuine-prefix",
        "authority": authority,
        "expected_boundary": "still-authoritative-because-no-independent-newer-fact-survives",
    }


def run() -> dict:
    report = {
        "schema": "axm.flowing-compute.wave112.recoverable-transition-provenance-selftest/v1",
        "truth_boundary": {
            "synthetic_scaling_is_structural_correctness_only": True,
            "wall_clock_performance_claim": False,
            "energy_claim": False,
            "retained_incremental_dormant_compute_claim": False,
            "os_process_or_provider_independence_claim": False,
            "independent_durable_commit_witness_claim": False,
            "abandoned_prepare_auto_cleanup": False,
            "same_modeled_failure_domain": True,
        },
        "controls": [],
        "failed": 0,
    }

    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world()
    check(report, "genesis-valid", w.commit_status_state(st, boot, rt, rs, bs, ts).get("status") == w.HISTORY_VALID)
    first = w.advance_all(st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs, "wave112-e1")
    second = w.advance_all(st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs, "wave112-e2")
    normal = w.commit_status_state(st, boot, rt, rs, bs, ts)
    check(report, "normal-two-epoch-history-valid", normal.get("status") == w.HISTORY_VALID, normal)
    check(report, "normal-two-epoch-authoritative", w.authority(rt, st, boot, services, rs, ts, cs, domain, bs).startswith("AUTHORITATIVE"))
    retry_old = w.commit(rt, st, boot, rs, ts, first[2]["authority_sha"], first[3], bs)
    retry_latest = w.commit(rt, st, boot, rs, ts, second[2]["authority_sha"], second[3], bs)
    check(report, "committed-old-exact-retry-idempotent", retry_old == "ALREADY_COMMITTED", retry_old)
    check(report, "committed-latest-exact-retry-idempotent", retry_latest == "ALREADY_COMMITTED", retry_latest)

    old = reproduce_wave111_failure()
    report["verifier36_reproduction"] = old
    check(report, "wave111-crash-retry-failure-reproduced", old["lower_commit"] == "COMMITTED" and old["before"].get("status") == w111.HISTORY_INCOMPLETE and not old["recovered"], old)

    recovered = wave112_recovery_case()
    report["wave112_exact_recovery"] = recovered
    check(report, "wave112-crash-state-fails-closed-before-retry", recovered["before"].get("status") == w.HISTORY_INCOMPLETE and recovered["authority_before"] == w.HOLD_INCOMPLETE, recovered)
    check(report, "wave112-exact-retry-appends-only-missing-provenance", recovered["recovery_result"] == "COMMITTED_RECOVERED_PROVENANCE", recovered)
    check(report, "wave112-recovered-history-valid", recovered["after"].get("status") == w.HISTORY_VALID, recovered)
    check(report, "wave112-repeated-retry-idempotent", recovered["repeat_result"] == "ALREADY_COMMITTED", recovered)
    check(report, "wave112-recovered-world-can-return-authoritative-after-publication", recovered["final_authority"].startswith("AUTHORITATIVE"), recovered)

    mismatch = mismatch_recovery_case()
    report["mismatched_transition_recovery"] = mismatch
    check(report, "mismatched-transition-cannot-recover", isinstance(mismatch["wrong_retry_error"], str) and "recovery-transition-sha-does-not-match-lower-committed-evidence" in mismatch["wrong_retry_error"], mismatch)
    check(report, "mismatched-recovery-attempt-leaves-history-held", mismatch["after_wrong"].get("status") == w.HISTORY_INCOMPLETE, mismatch)
    check(report, "exact-retry-still-recovers-after-mismatch", mismatch["exact_retry_result"] == "COMMITTED_RECOVERED_PROVENANCE" and mismatch["after_exact"].get("status") == w.HISTORY_VALID, mismatch)

    broad = non_trailing_loss_case()
    report["overbroad_recovery_rejected"] = broad
    check(report, "multiple-missing-provenance-rows-remain-incomplete", broad["before"].get("status") == w.HISTORY_INCOMPLETE, broad)
    check(report, "recovery-refuses-to-infer-multiple-missing-rows", isinstance(broad["retry_error"], str) and "recovery-requires-exactly-one-missing-trailing-provenance-row" in broad["retry_error"], broad)
    check(report, "overbroad-recovery-does-not-mutate-to-valid", broad["after"].get("status") == w.HISTORY_INCOMPLETE, broad)

    abandoned = abandoned_prepare_case()
    report["preserved_abandoned_prepare_boundary"] = abandoned
    check(report, "abandoned-prepare-still-holds", abandoned["state"].get("status") == w.HISTORY_UNRESOLVED and abandoned["authority"] == w.HOLD_UNRESOLVED, abandoned)
    check(report, "abandoned-prepare-not-silently-cleaned", isinstance(abandoned["second_prepare_error"], str) and "Wave 112 predecessor HOLD" in abandoned["second_prepare_error"], abandoned)

    scaling = [marker_scaling_case(depth) for depth in (1, 4, 8)]
    report["synthetic_structural_scaling"] = scaling
    check(report, "synthetic-depths-remain-valid", all(row["status"] == w.HISTORY_VALID for row in scaling), scaling)
    check(report, "marker-chain-linearization-count-is-depth-independent", [row["marker_chains_calls"] for row in scaling] == [2, 2, 2], scaling)

    rollback = whole_domain_rollback_counterexample()
    report["preserved_counterexample"] = rollback
    check(report, "whole-domain-rollback-counterexample-still-visible", rollback["authority"].startswith("AUTHORITATIVE"), rollback)

    report["passed"] = len(report["controls"]) - report["failed"]
    report["total"] = len(report["controls"])
    report["verdict"] = "PASS" if report["failed"] == 0 else "FAIL"
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out")
    args = parser.parse_args()
    report = run()
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
