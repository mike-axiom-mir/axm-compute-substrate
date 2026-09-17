#!/usr/bin/env python3
"""Wave 115 exact-API positive/negative self-test.

First reproduces verifier PR #39 against unchanged Wave 114. Then requires Wave 115 to reject
semantically invalid strict-field transitions before any real decision write, preserve legitimate
retry, survive both decision->lower and lower->provenance crash windows, keep normal progress, and
retain the known whole-modeled-domain rollback counterexample.
"""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

import AXM_FLOWING_COMPUTE_PREVALIDATED_COMMIT_DECISION as w
import AXM_FLOWING_COMPUTE_EXACT_TRANSITION_DECISION as w114
import AXM_FLOWING_COMPUTE_REMOTE_REGISTRY_MONOTONICITY as w100
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w104

q = w.q
g = w.g


def check(report: dict, name: str, ok: bool, detail=None):
    report["controls"].append({"name": name, "ok": bool(ok), "detail": detail})
    if not ok:
        report["failed"] += 1


def new_world(module=w):
    st, priv, boot, rt, services, tokens, rs = q.fixture()
    ts = {}
    cs = g.new_certificate_store()
    domain = w104.new_certificate_witness_domain()
    bs = {}
    module.adopt_genesis(rt, st, boot, services, rs, ts, cs, domain, bs)
    return st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs


def resealed_variant(original: dict, **changes) -> dict:
    body = deepcopy(original)
    body.update(changes)
    body["transition_sha"] = ""
    return w100._seal(body, "transition_sha")


def reproduce_verifier39_against_wave114() -> dict:
    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world(w114)
    cp, use, link, genuine_sha, body = w114.prepare(
        rt, st, priv, boot, services, rs, ts, cs, domain, bs,
        target_user_app_state_sha="81" * 32,
    )
    genuine = deepcopy(ts[genuine_sha])
    adversarial = resealed_variant(
        genuine,
        transition_kind=(
            "CREDENTIAL_ROTATION" if genuine["transition_kind"] == "SAME" else "SAME"
        ),
    )
    adversarial_sha = w100.put_transition(ts, adversarial)

    before = deepcopy(st[w114.DECISION_STORE])
    first = w114.commit(
        rt, st, boot, rs, ts, link["authority_sha"], adversarial_sha, bs
    )
    rows = w114._decision_rows(st) or []
    bound = [
        d for _sha, d in rows if d.get("authority_sha") == link["authority_sha"]
    ]
    retry_result = None
    retry_error = None
    try:
        retry_result = w114.commit(
            rt, st, boot, rs, ts, link["authority_sha"], genuine_sha, bs
        )
    except Exception as exc:
        retry_error = f"{type(exc).__name__}:{exc}"

    reproduced = (
        before == {}
        and first == "TRANSITION_DELTA_HOLD"
        and len(bound) == 1
        and bound[0].get("transition_sha") == adversarial_sha
        and retry_result is None
        and isinstance(retry_error, str)
        and "decision-authority-bound-to-different-transition" in retry_error
    )
    return {
        "genuine_transition_sha": genuine_sha,
        "adversarial_transition_sha": adversarial_sha,
        "first_commit_result": first,
        "decision_count": len(rows),
        "bound_transition_sha": bound[0].get("transition_sha") if len(bound) == 1 else None,
        "genuine_retry_result": retry_result,
        "genuine_retry_error": retry_error,
        "reproduced": reproduced,
    }


def verifier39_blocked_and_retry_succeeds() -> dict:
    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world()
    cp, use, link, genuine_sha, body = w.prepare(
        rt, st, priv, boot, services, rs, ts, cs, domain, bs,
        target_user_app_state_sha="82" * 32,
    )
    genuine = deepcopy(ts[genuine_sha])
    adversarial = resealed_variant(
        genuine,
        transition_kind=(
            "CREDENTIAL_ROTATION" if genuine["transition_kind"] == "SAME" else "SAME"
        ),
    )
    adversarial_sha = w100.put_transition(ts, adversarial)
    before = deepcopy(st[w.DECISION_STORE])

    bad = w.commit(rt, st, boot, rs, ts, link["authority_sha"], adversarial_sha, bs)
    unchanged = st[w.DECISION_STORE] == before
    good = w.commit(rt, st, boot, rs, ts, link["authority_sha"], genuine_sha, bs)

    for slot in q.REMOTE_IDS:
        w.publish(rt, st, boot, services, tokens, rs, slot)
    w.certify_and_sync(rt, st, boot, services, rs, cs, domain)
    status = w.commit_status_state(st, boot, rt, rs, bs, ts)
    auth = w.authority(rt, st, boot, services, rs, ts, cs, domain, bs)
    rows = w._decision_rows(st) or []
    target = [d for _sha, d in rows if d.get("authority_sha") == link["authority_sha"]]

    return {
        "bad_result": bad,
        "decision_unchanged_after_bad": unchanged,
        "good_result": good,
        "status": status.get("status"),
        "authority": auth,
        "target_decision_count": len(target),
        "bound_transition_sha": target[0].get("transition_sha") if len(target) == 1 else None,
        "expected_transition_sha": genuine_sha,
    }


def lower_hold_does_not_write_decision(case: str) -> dict:
    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world()
    cp, use, link, genuine_sha, body = w.prepare(
        rt, st, priv, boot, services, rs, ts, cs, domain, bs,
        target_user_app_state_sha="83" * 32,
    )
    original = deepcopy(ts[genuine_sha])
    if case == "generation":
        variant = resealed_variant(
            original, current_generation=original["current_generation"] + 1
        )
        expected = "TRANSITION_GENERATION_HOLD"
    elif case == "state-binding":
        variant = resealed_variant(original, target_app_state_sha="84" * 32)
        expected = "TRANSITION_STATE_BINDING_HOLD"
    elif case == "missing-registry":
        variant = resealed_variant(original, target_registry_sha="f" * 64)
        expected = "TRANSITION_VALIDATION_HOLD"
    else:
        raise ValueError(case)

    variant_sha = w100.put_transition(ts, variant)
    before_decisions = deepcopy(st[w.DECISION_STORE])
    before_rt = deepcopy(rt)
    before_provenance = deepcopy(st[w.PROVENANCE_STORE])
    result = w.commit(rt, st, boot, rs, ts, link["authority_sha"], variant_sha, bs)
    return {
        "case": case,
        "result": result,
        "expected": expected,
        "decision_store_unchanged": st[w.DECISION_STORE] == before_decisions,
        "runtime_unchanged": rt == before_rt,
        "provenance_store_unchanged": st[w.PROVENANCE_STORE] == before_provenance,
    }


def crash_after_decision_before_lower_commit_precise() -> dict:
    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world()
    cp, use, link, tr, body = w.prepare(
        rt, st, priv, boot, services, rs, ts, cs, domain, bs,
        target_user_app_state_sha="86" * 32,
    )
    before_rt = deepcopy(rt)
    before_provenance = deepcopy(st[w.PROVENANCE_STORE])
    error = None
    try:
        w.commit(
            rt, st, boot, rs, ts, link["authority_sha"], tr, bs,
            fault_after_decision_before_lower_commit=True,
        )
    except Exception as exc:
        error = f"{type(exc).__name__}:{exc}"
    rt_unchanged = rt == before_rt
    provenance_unchanged = st[w.PROVENANCE_STORE] == before_provenance
    status_fault = w.commit_status_state(st, boot, rt, rs, bs, ts)
    rows = w._decision_rows(st) or []
    target = [d for _sha, d in rows if d.get("authority_sha") == link["authority_sha"]]
    retry = w.commit(rt, st, boot, rs, ts, link["authority_sha"], tr, bs)
    status_retry = w.commit_status_state(st, boot, rt, rs, bs, ts)
    return {
        "error": error,
        "runtime_unchanged": rt_unchanged,
        "provenance_unchanged": provenance_unchanged,
        "status_after_fault": status_fault.get("status"),
        "decision_count_after_fault": len(target),
        "decision_transition_sha": target[0].get("transition_sha") if len(target) == 1 else None,
        "expected_transition_sha": tr,
        "retry": retry,
        "status_after_retry": status_retry.get("status"),
    }


def crash_after_lower_commit_and_recover() -> dict:
    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world()
    w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs,
        "wave115-crash-base-e1",
    )
    cp, use, link, tr, body = w.prepare(
        rt, st, priv, boot, services, rs, ts, cs, domain, bs,
        target_user_app_state_sha="87" * 32,
    )
    error = None
    try:
        w.commit(
            rt, st, boot, rs, ts, link["authority_sha"], tr, bs,
            fault_after_lower_commit=True,
        )
    except Exception as exc:
        error = f"{type(exc).__name__}:{exc}"
    before = w.commit_status_state(st, boot, rt, rs, bs, ts)
    recovered = w.commit(rt, st, boot, rs, ts, link["authority_sha"], tr, bs)
    after = w.commit_status_state(st, boot, rt, rs, bs, ts)
    return {
        "error": error,
        "before": before.get("status"),
        "recovered": recovered,
        "after": after.get("status"),
    }


def normal_two_epoch_progress() -> dict:
    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world()
    first = w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs,
        "wave115-normal-e1",
    )
    second = w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs,
        "wave115-normal-e2",
    )
    status = w.commit_status_state(st, boot, rt, rs, bs, ts)
    auth = w.authority(rt, st, boot, services, rs, ts, cs, domain, bs)
    decisions = w._decision_rows(st) or []
    return {
        "status": status.get("status"),
        "authority": auth,
        "decision_count": len(decisions),
        "transition_shas": [first[3], second[3]],
        "decision_transition_shas": [d["transition_sha"] for _sha, d in decisions],
    }


def whole_domain_rollback_counterexample() -> dict:
    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world()
    w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs,
        "wave115-rb-e1",
    )
    snap_st = deepcopy(st)
    snap_rt = deepcopy(rt)
    snap_services = deepcopy(services)
    snap_ts = deepcopy(ts)
    snap_cs = deepcopy(cs)
    snap_bs = deepcopy(bs)
    snap_disks = domain.disk_snapshots()

    w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs,
        "wave115-rb-e2",
    )
    domain.restore_disks(snap_disks)
    auth = w.authority(
        snap_rt, snap_st, boot, snap_services, rs, snap_ts, snap_cs, domain, snap_bs
    )
    return {
        "authority": auth,
        "boundary": "whole modeled failure-domain rollback still removes the newer decision too",
    }


def run() -> dict:
    report = {
        "schema": "axm.flowing-compute.wave115.prevalidated-commit-decision-selftest/v1",
        "truth_boundary": {
            "same_modeled_python_failure_domain": True,
            "deepcopy_preflight_is_not_process_independence": True,
            "concurrent_mutation_proof": False,
            "process_or_power_loss_atomicity_claim": False,
            "physical_or_provider_independence_claim": False,
            "real_axm_or_monolith_workload_run": False,
            "synthetic_scaling_run": False,
            "wall_clock_performance_claim": False,
            "energy_claim": False,
            "retained_incremental_dormant_compute_claim": False,
        },
        "controls": [],
        "failed": 0,
    }

    old = reproduce_verifier39_against_wave114()
    report["wave114_verifier39_reproduction"] = old
    check(report, "wave114-verifier39-reproduced", old["reproduced"], old)

    fixed = verifier39_blocked_and_retry_succeeds()
    report["wave115_verifier39_repair"] = fixed
    check(report, "invalid-transition-rejected-before-real-decision", fixed["bad_result"] == "TRANSITION_DELTA_HOLD", fixed)
    check(report, "rejected-transition-does-not-write-real-decision", fixed["decision_unchanged_after_bad"], fixed)
    check(report, "genuine-transition-retry-commits", fixed["good_result"] == "COMMITTED", fixed)
    check(report, "genuine-retry-binds-exact-transition", fixed["bound_transition_sha"] == fixed["expected_transition_sha"], fixed)
    check(report, "genuine-retry-restores-valid-authority", fixed["status"] == w.HISTORY_VALID and fixed["authority"].startswith("AUTHORITATIVE"), fixed)

    for case in ("generation", "state-binding", "missing-registry"):
        hold = lower_hold_does_not_write_decision(case)
        report[f"prevalidation_{case}"] = hold
        check(report, f"{case}-lower-hold-preserved", hold["result"] == hold["expected"], hold)
        check(report, f"{case}-hold-does-not-write-decision", hold["decision_store_unchanged"], hold)
        check(report, f"{case}-hold-does-not-mutate-runtime", hold["runtime_unchanged"], hold)
        check(report, f"{case}-hold-does-not-write-provenance", hold["provenance_store_unchanged"], hold)

    crash1 = crash_after_decision_before_lower_commit_precise()
    report["decision_to_lower_crash"] = crash1
    check(report, "decision-to-lower-crash-injected", isinstance(crash1["error"], str) and "injected-wave115-crash-after-decision-before-lower-commit" in crash1["error"], crash1)
    check(report, "decision-to-lower-crash-leaves-lower-runtime-unchanged", crash1["runtime_unchanged"], crash1)
    check(report, "decision-to-lower-crash-leaves-provenance-unchanged", crash1["provenance_unchanged"], crash1)
    check(report, "decision-to-lower-crash-keeps-exact-decision", crash1["decision_count_after_fault"] == 1 and crash1["decision_transition_sha"] == crash1["expected_transition_sha"], crash1)
    check(report, "decision-to-lower-crash-is-not-valid-history", crash1["status_after_fault"] != w.HISTORY_VALID, crash1)
    check(report, "exact-retry-after-decision-crash-commits", crash1["retry"] == "COMMITTED" and crash1["status_after_retry"] == w.HISTORY_VALID, crash1)

    crash2 = crash_after_lower_commit_and_recover()
    report["lower_to_provenance_crash"] = crash2
    check(report, "lower-to-provenance-crash-injected", isinstance(crash2["error"], str) and "injected-wave115-crash-after-lower-commit-before-provenance" in crash2["error"], crash2)
    check(report, "lower-to-provenance-crash-held-before-recovery", crash2["before"] != w.HISTORY_VALID, crash2)
    check(report, "lower-to-provenance-exact-recovery-succeeds", crash2["recovered"] == "COMMITTED_RECOVERED_EXACT_DECISION", crash2)
    check(report, "lower-to-provenance-recovery-restores-valid-history", crash2["after"] == w.HISTORY_VALID, crash2)

    normal = normal_two_epoch_progress()
    report["normal_two_epoch_progress"] = normal
    check(report, "normal-two-epoch-history-valid", normal["status"] == w.HISTORY_VALID, normal)
    check(report, "normal-two-epoch-authority-survives", normal["authority"].startswith("AUTHORITATIVE"), normal)
    check(report, "normal-decision-ledger-tracks-exact-transitions", normal["decision_transition_shas"] == normal["transition_shas"], normal)

    rollback = whole_domain_rollback_counterexample()
    report["whole_domain_rollback_counterexample"] = rollback
    check(report, "whole-domain-rollback-counterexample-preserved", rollback["authority"].startswith("AUTHORITATIVE"), rollback)

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
        path = Path(args.json_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
