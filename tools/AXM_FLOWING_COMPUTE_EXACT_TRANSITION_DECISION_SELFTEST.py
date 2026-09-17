#!/usr/bin/env python3
"""Wave 114 exact-API positive/negative self-test.

Reproduces verifier PR #38 against unchanged Wave 113, then requires Wave 114 to preserve the exact
transition identity in a pre-bound append-only commit-decision ledger, reject extension-field
transition identities, fail closed on decision loss/tamper, and still recover the intended one-row
lower-commit -> provenance crash state.
"""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

import AXM_FLOWING_COMPUTE_EXACT_TRANSITION_DECISION as w
import AXM_FLOWING_COMPUTE_RECOVERY_ATOMICITY as w113
import AXM_FLOWING_COMPUTE_TRANSITION_PROVENANCE_LEDGER as w111
import AXM_FLOWING_COMPUTE_TRANSITION_EVIDENCE_GUARD as w110
import AXM_FLOWING_COMPUTE_REMOTE_REGISTRY_MONOTONICITY as w100
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w104

q = w.q
g = w.g


def check(report: dict, name: str, ok: bool, detail=None):
    report["controls"].append({"name": name, "ok": bool(ok), "detail": detail})
    if not ok:
        report["failed"] += 1


def new_world114():
    st, priv, boot, rt, services, tokens, rs = q.fixture()
    ts = {}
    cs = g.new_certificate_store()
    domain = w104.new_certificate_witness_domain()
    bs = {}
    w.adopt_genesis(rt, st, boot, services, rs, ts, cs, domain, bs)
    return st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs


def new_world113():
    st, priv, boot, rt, services, tokens, rs = q.fixture()
    ts = {}
    cs = g.new_certificate_store()
    domain = w104.new_certificate_witness_domain()
    bs = {}
    w113.adopt_genesis(rt, st, boot, services, rs, ts, cs, domain, bs)
    return st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs


def replacement_transition(original: dict, label: str) -> dict:
    replacement = deepcopy(original)
    replacement["verifier_replacement_nonce"] = label
    replacement["transition_sha"] = ""
    return w100._seal(replacement, "transition_sha")


def reproduce_verifier38_against_wave113() -> dict:
    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world113()
    w113.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs,
        "wave114-verifier38-base-e1",
    )
    cp2, use2, link2, tr2, body2 = w113.prepare(
        rt, st, priv, boot, services, rs, ts, cs, domain, bs,
        target_user_app_state_sha="73" * 32,
    )
    original = deepcopy(ts[tr2])
    lower = w110.commit(rt, st, boot, rs, ts, link2["authority_sha"], tr2, bs)
    before = w113.commit_status_state(st, boot, rt, rs, bs, ts)

    del ts[tr2]
    replacement = replacement_transition(original, "wave114-reproduce-pr38")
    replacement_sha = w100.put_transition(ts, replacement)

    result = None
    error = None
    try:
        result = w113.commit(
            rt, st, boot, rs, ts, link2["authority_sha"], replacement_sha, bs
        )
    except Exception as exc:
        error = f"{type(exc).__name__}:{exc}"
    after = w113.commit_status_state(st, boot, rt, rs, bs, ts)
    rows = w111._provenance_rows(st)
    target = [
        body for _sha, body in (rows or [])
        if body.get("authority_sha") == link2["authority_sha"]
    ]
    bound = target[0].get("transition_sha") if len(target) == 1 else None

    reproduced = (
        lower == "COMMITTED"
        and before.get("status") == w113.HISTORY_INCOMPLETE
        and replacement_sha != tr2
        and result == "COMMITTED_RECOVERED_PROVENANCE_ATOMIC"
        and error is None
        and after.get("status") == w113.HISTORY_VALID
        and bound == replacement_sha
    )
    return {
        "lower_commit": lower,
        "status_before": before.get("status"),
        "original_transition_sha": tr2,
        "replacement_transition_sha": replacement_sha,
        "recovery_result": result,
        "error": error,
        "status_after": after.get("status"),
        "bound_transition_sha": bound,
        "reproduced": reproduced,
    }


def crash_after_lower_commit_world():
    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world114()
    w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs,
        "wave114-e1",
    )
    cp2, use2, link2, tr2, body2 = w.prepare(
        rt, st, priv, boot, services, rs, ts, cs, domain, bs,
        target_user_app_state_sha="74" * 32,
    )
    error = None
    try:
        w.commit(
            rt, st, boot, rs, ts, link2["authority_sha"], tr2, bs,
            fault_after_lower_commit=True,
        )
    except Exception as exc:
        error = f"{type(exc).__name__}:{exc}"
    return {
        "st": st, "priv": priv, "boot": boot, "rt": rt,
        "services": services, "tokens": tokens, "rs": rs, "ts": ts,
        "cs": cs, "domain": domain, "bs": bs,
        "cp2": cp2, "use2": use2, "link2": link2, "tr2": tr2, "body2": body2,
        "crash_error": error,
    }


def exact_decision_survives_crash() -> dict:
    x = crash_after_lower_commit_world()
    rows = w._decision_rows(x["st"])
    status = w.commit_status_state(
        x["st"], x["boot"], x["rt"], x["rs"], x["bs"], x["ts"]
    )
    matches = [
        body for _sha, body in (rows or [])
        if body.get("authority_sha") == x["link2"]["authority_sha"]
    ]
    return {
        "crash_error": x["crash_error"],
        "decision_count": len(rows or []),
        "target_decision_count": len(matches),
        "bound_transition_sha": matches[0]["transition_sha"] if len(matches) == 1 else None,
        "expected_transition_sha": x["tr2"],
        "status_after_crash": status.get("status"),
    }


def substitution_rejected() -> dict:
    x = crash_after_lower_commit_world()
    original_sha = x["tr2"]
    original = deepcopy(x["ts"][original_sha])
    pstore_before = deepcopy(x["st"][w.PROVENANCE_STORE])

    del x["ts"][original_sha]
    replacement = replacement_transition(original, "wave114-substitution")
    replacement_sha = w100.put_transition(x["ts"], replacement)

    result = None
    error = None
    try:
        result = w.commit(
            x["rt"], x["st"], x["boot"], x["rs"], x["ts"],
            x["link2"]["authority_sha"], replacement_sha, x["bs"],
        )
    except Exception as exc:
        error = f"{type(exc).__name__}:{exc}"

    status = w.commit_status_state(
        x["st"], x["boot"], x["rt"], x["rs"], x["bs"], x["ts"]
    )
    auth = w.authority(
        x["rt"], x["st"], x["boot"], x["services"], x["rs"], x["ts"],
        x["cs"], x["domain"], x["bs"],
    )
    decisions = w._decision_rows(x["st"])
    target = [
        body for _sha, body in (decisions or [])
        if body.get("authority_sha") == x["link2"]["authority_sha"]
    ]
    return {
        "original_transition_sha": original_sha,
        "replacement_transition_sha": replacement_sha,
        "different_identity": replacement_sha != original_sha,
        "result": result,
        "error": error,
        "provenance_store_unchanged": x["st"][w.PROVENANCE_STORE] == pstore_before,
        "status": status.get("status"),
        "authority": auth,
        "decision_still_binds_original": len(target) == 1 and target[0]["transition_sha"] == original_sha,
    }


def clean_exact_recovery() -> dict:
    x = crash_after_lower_commit_world()
    before = w.commit_status_state(
        x["st"], x["boot"], x["rt"], x["rs"], x["bs"], x["ts"]
    )
    recovered = w.commit(
        x["rt"], x["st"], x["boot"], x["rs"], x["ts"],
        x["link2"]["authority_sha"], x["tr2"], x["bs"],
    )
    after = w.commit_status_state(
        x["st"], x["boot"], x["rt"], x["rs"], x["bs"], x["ts"]
    )
    repeated = w.commit(
        x["rt"], x["st"], x["boot"], x["rs"], x["ts"],
        x["link2"]["authority_sha"], x["tr2"], x["bs"],
    )
    return {
        "before": before.get("status"),
        "recovered": recovered,
        "after": after.get("status"),
        "repeated": repeated,
    }


def extension_field_rejected_before_decision() -> dict:
    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world114()
    cp, use, link, tr, body = w.prepare(
        rt, st, priv, boot, services, rs, ts, cs, domain, bs,
        target_user_app_state_sha="75" * 32,
    )
    replacement = replacement_transition(ts[tr], "wave114-extra-field")
    replacement_sha = w100.put_transition(ts, replacement)
    before = deepcopy(st[w.DECISION_STORE])
    result = None
    error = None
    try:
        result = w.commit(
            rt, st, boot, rs, ts, link["authority_sha"], replacement_sha, bs
        )
    except Exception as exc:
        error = f"{type(exc).__name__}:{exc}"
    return {
        "result": result,
        "error": error,
        "decision_store_unchanged": st[w.DECISION_STORE] == before,
        "replacement_sha": replacement_sha,
        "original_sha": tr,
    }


def missing_decision_fails_closed() -> dict:
    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world114()
    w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs,
        "wave114-missing-decision",
    )
    store = st[w.DECISION_STORE]
    only = next(iter(store))
    del store[only]
    status = w.commit_status_state(st, boot, rt, rs, bs, ts)
    auth = w.authority(rt, st, boot, services, rs, ts, cs, domain, bs)
    return {"status": status.get("status"), "authority": auth}


def tampered_decision_fails_closed() -> dict:
    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world114()
    w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs,
        "wave114-tampered-decision",
    )
    store = st[w.DECISION_STORE]
    only = next(iter(store))
    store[only]["transition_sha"] = "f" * 64
    status = w.commit_status_state(st, boot, rt, rs, bs, ts)
    auth = w.authority(rt, st, boot, services, rs, ts, cs, domain, bs)
    return {"status": status.get("status"), "authority": auth, "key": only}


def normal_two_epoch_progress() -> dict:
    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world114()
    first = w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs,
        "wave114-normal-e1",
    )
    second = w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs,
        "wave114-normal-e2",
    )
    status = w.commit_status_state(st, boot, rt, rs, bs, ts)
    auth = w.authority(rt, st, boot, services, rs, ts, cs, domain, bs)
    decisions = w._decision_rows(st)
    return {
        "status": status.get("status"),
        "authority": auth,
        "decision_count": len(decisions or []),
        "transition_shas": [first[3], second[3]],
        "decision_transition_shas": [body["transition_sha"] for _sha, body in (decisions or [])],
    }


def whole_domain_rollback_counterexample() -> dict:
    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world114()
    w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs,
        "wave114-rb-e1",
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
        "wave114-rb-e2",
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
        "schema": "axm.flowing-compute.wave114.exact-transition-decision-selftest/v1",
        "truth_boundary": {
            "same_modeled_python_failure_domain": True,
            "decision_store_is_not_separate_os_process": True,
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

    old = reproduce_verifier38_against_wave113()
    report["wave113_verifier38_reproduction"] = old
    check(report, "wave113-verifier38-reproduced", old["reproduced"], old)

    crash = exact_decision_survives_crash()
    report["decision_before_lower_commit_crash"] = crash
    check(
        report, "exact-decision-survives-lower-commit-provenance-crash",
        isinstance(crash["crash_error"], str)
        and "injected-wave114-crash-after-lower-commit-before-provenance" in crash["crash_error"]
        and crash["target_decision_count"] == 1
        and crash["bound_transition_sha"] == crash["expected_transition_sha"],
        crash,
    )
    check(
        report, "crash-window-remains-held-before-recovery",
        crash["status_after_crash"] == w.HISTORY_INCOMPLETE,
        crash,
    )

    attack = substitution_rejected()
    report["substitution_attack"] = attack
    check(
        report, "replacement-transition-identity-rejected",
        attack["result"] is None
        and isinstance(attack["error"], str)
        and (
            "recovery-transition-does-not-match-durable-commit-decision" in attack["error"]
            or "transition-field-set-mismatch" in attack["error"]
        ),
        attack,
    )
    check(report, "failed-substitution-does-not-write-provenance", attack["provenance_store_unchanged"], attack)
    check(report, "decision-remains-bound-to-original-transition", attack["decision_still_binds_original"], attack)
    check(report, "substitution-world-remains-non-authoritative", not attack["authority"].startswith("AUTHORITATIVE"), attack)

    clean = clean_exact_recovery()
    report["clean_exact_recovery"] = clean
    check(report, "clean-exact-recovery-succeeds", clean["recovered"] == "COMMITTED_RECOVERED_EXACT_DECISION", clean)
    check(report, "clean-exact-recovery-restores-valid-history", clean["after"] == w.HISTORY_VALID, clean)
    check(report, "exact-recovery-is-idempotent", clean["repeated"] == "ALREADY_COMMITTED", clean)

    extra = extension_field_rejected_before_decision()
    report["strict_transition_schema"] = extra
    check(
        report, "unknown-transition-extension-field-rejected",
        extra["result"] is None
        and isinstance(extra["error"], str)
        and "transition-field-set-mismatch" in extra["error"],
        extra,
    )
    check(report, "strict-schema-rejection-does-not-create-decision", extra["decision_store_unchanged"], extra)

    missing = missing_decision_fails_closed()
    report["missing_decision"] = missing
    check(report, "missing-decision-classified-incomplete", missing["status"] == w.HISTORY_INCOMPLETE, missing)
    check(report, "missing-decision-blocks-authority", not missing["authority"].startswith("AUTHORITATIVE"), missing)

    tampered = tampered_decision_fails_closed()
    report["tampered_decision"] = tampered
    check(report, "tampered-decision-classified-incomplete", tampered["status"] == w.HISTORY_INCOMPLETE, tampered)
    check(report, "tampered-decision-blocks-authority", not tampered["authority"].startswith("AUTHORITATIVE"), tampered)

    normal = normal_two_epoch_progress()
    report["normal_two_epoch_progress"] = normal
    check(report, "normal-two-epoch-history-valid", normal["status"] == w.HISTORY_VALID, normal)
    check(report, "normal-two-epoch-authority-survives", normal["authority"].startswith("AUTHORITATIVE"), normal)
    check(report, "decision-ledger-tracks-exact-transitions", normal["decision_transition_shas"] == normal["transition_shas"], normal)

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
