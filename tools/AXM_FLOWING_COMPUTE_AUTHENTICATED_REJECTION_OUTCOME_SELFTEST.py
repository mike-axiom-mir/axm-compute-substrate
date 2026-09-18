#!/usr/bin/env python3
"""Wave 116 authenticated rejection outcome positive/negative self-test.

First reproduces verifier PR #40 against unchanged Wave 115. Then proves Wave 116 fails closed on
unauthenticated, forged, duplicate, contradictory, credential-substituted, and COMMIT+REJECT
terminal evidence while preserving the normal rejected-sibling -> genuine-commit path.

The raw-rejection -> authenticated-outcome crash window is intentionally kept visible: after the
raw append but before authenticated publication, history HOLDs and this wave does not invent the
missing authenticated fact. That recovery belongs to the next independent-process witness gate.
"""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

import AXM_FLOWING_COMPUTE_AUTHENTICATED_REJECTION_OUTCOME as w
import AXM_FLOWING_COMPUTE_PREVALIDATED_COMMIT_DECISION as w115
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
    certificate_domain = w104.new_certificate_witness_domain()
    bs = {}
    if module is w:
        outcome_domain = w.new_outcome_authority_domain()
        w.adopt_genesis(
            rt, st, boot, services, rs, ts, cs, certificate_domain, bs, outcome_domain
        )
        return st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, outcome_domain
    module.adopt_genesis(rt, st, boot, services, rs, ts, cs, certificate_domain, bs)
    return st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs


def resealed_variant(original: dict, **changes) -> dict:
    body = deepcopy(original)
    body.update(changes)
    body["transition_sha"] = ""
    return w100._seal(body, "transition_sha")


def prepare_bad_sibling(world, app_hex="a1"):
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, outcome_domain = world
    cp, use, link, genuine_sha, body = w.prepare(
        rt,
        st,
        priv,
        boot,
        services,
        rs,
        ts,
        cs,
        certificate_domain,
        bs,
        outcome_domain,
        target_user_app_state_sha=app_hex * 32,
    )
    genuine = deepcopy(ts[genuine_sha])
    bad = resealed_variant(
        genuine,
        transition_kind=("CREDENTIAL_ROTATION" if genuine["transition_kind"] == "SAME" else "SAME"),
    )
    bad_sha = w100.put_transition(ts, bad)
    return link, genuine_sha, bad_sha


def reproduce_verifier40_against_wave115() -> dict:
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs = new_world(w115)
    cp, use, link, genuine_sha, body = w115.prepare(
        rt, st, priv, boot, services, rs, ts, cs, certificate_domain, bs,
        target_user_app_state_sha="b1" * 32,
    )
    genuine = deepcopy(ts[genuine_sha])
    bad = resealed_variant(
        genuine,
        transition_kind=("CREDENTIAL_ROTATION" if genuine["transition_kind"] == "SAME" else "SAME"),
    )
    bad_sha = w100.put_transition(ts, bad)
    first = w115.commit(rt, st, boot, rs, ts, link["authority_sha"], bad_sha, bs)
    rows = w115._rejection_rows(st, ts) or []
    first_sha, first_body = rows[0]
    repeated_actual = w115._prevalidate_lower_commit(
        rt, st, boot, rs, ts, link["authority_sha"], bad_sha, bs
    )
    contradictory = w115._seal_rejection({
        "schema": w115.REJECTION_SCHEMA,
        "seq": 2,
        "predecessor_rejection_sha": first_sha,
        "authority_sha": first_body["authority_sha"],
        "transition_sha": bad_sha,
        "checkpoint_sha": first_body["checkpoint_sha"],
        "lower_result": "TRANSITION_GENERATION_HOLD",
        "rejection_sha": "",
    })
    st[w115.REJECTION_STORE][contradictory["rejection_sha"]] = contradictory
    accepted_rows = w115._rejection_rows(st, ts) or []
    good = w115.commit(rt, st, boot, rs, ts, link["authority_sha"], genuine_sha, bs)
    for slot in q.REMOTE_IDS:
        w115.publish(rt, st, boot, services, tokens, rs, slot)
    w115.certify_and_sync(rt, st, boot, services, rs, cs, certificate_domain)
    status = w115.commit_status_state(st, boot, rt, rs, bs, ts)
    authority = w115.authority(rt, st, boot, services, rs, ts, cs, certificate_domain, bs)
    reproduced = (
        first == "TRANSITION_DELTA_HOLD"
        and repeated_actual == "TRANSITION_DELTA_HOLD"
        and len(accepted_rows) == 2
        and good == "COMMITTED"
        and status.get("status") == w115.HISTORY_VALID
        and authority.startswith("AUTHORITATIVE")
    )
    return {
        "reproduced": reproduced,
        "first_result": first,
        "repeated_actual": repeated_actual,
        "accepted_rejection_rows": len(accepted_rows),
        "good_result": good,
        "status": status.get("status"),
        "authority": authority,
        "bad_transition_sha": bad_sha,
    }


def normal_reject_then_genuine_commit() -> dict:
    world = new_world()
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, outcome_domain = world
    link, genuine_sha, bad_sha = prepare_bad_sibling(world, "b2")
    bad = w.commit(rt, st, boot, rs, ts, link["authority_sha"], bad_sha, bs, outcome_domain)
    raw = w115._rejection_rows(st, ts) or []
    outcomes = w._outcome_rows(st, outcome_domain) or []
    retry = w.commit(rt, st, boot, rs, ts, link["authority_sha"], bad_sha, bs, outcome_domain)
    raw_after_retry = w115._rejection_rows(st, ts) or []
    outcomes_after_retry = w._outcome_rows(st, outcome_domain) or []
    good = w.commit(rt, st, boot, rs, ts, link["authority_sha"], genuine_sha, bs, outcome_domain)
    for slot in q.REMOTE_IDS:
        w.publish(rt, st, boot, services, tokens, rs, slot)
    w.certify_and_sync(rt, st, boot, services, rs, cs, certificate_domain)
    status = w.commit_status_state(st, boot, rt, rs, bs, ts, outcome_domain)
    authority = w.authority(
        rt, st, boot, services, rs, ts, cs, certificate_domain, bs, outcome_domain
    )
    return {
        "bad": bad,
        "retry": retry,
        "raw_count": len(raw),
        "outcome_count": len(outcomes),
        "raw_count_after_retry": len(raw_after_retry),
        "outcome_count_after_retry": len(outcomes_after_retry),
        "good": good,
        "status": status.get("status"),
        "authority": authority,
        "bad_sha": bad_sha,
        "genuine_sha": genuine_sha,
    }


def contradictory_raw_only_fails_closed() -> dict:
    world = new_world()
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, outcome_domain = world
    link, genuine_sha, bad_sha = prepare_bad_sibling(world, "b3")
    first = w.commit(rt, st, boot, rs, ts, link["authority_sha"], bad_sha, bs, outcome_domain)
    rows = w115._rejection_rows(st, ts) or []
    first_sha, first_body = rows[0]
    contradictory = w115._seal_rejection({
        "schema": w115.REJECTION_SCHEMA,
        "seq": 2,
        "predecessor_rejection_sha": first_sha,
        "authority_sha": first_body["authority_sha"],
        "transition_sha": bad_sha,
        "checkpoint_sha": first_body["checkpoint_sha"],
        "lower_result": "TRANSITION_GENERATION_HOLD",
        "rejection_sha": "",
    })
    st[w115.REJECTION_STORE][contradictory["rejection_sha"]] = contradictory
    status = w.commit_status_state(st, boot, rt, rs, bs, ts, outcome_domain)
    authority = w.authority(
        rt, st, boot, services, rs, ts, cs, certificate_domain, bs, outcome_domain
    )
    return {"first": first, "status": status, "authority": authority}


def contradictory_even_if_authenticated_fails_closed() -> dict:
    world = new_world()
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, outcome_domain = world
    link, genuine_sha, bad_sha = prepare_bad_sibling(world, "b4")
    first = w.commit(rt, st, boot, rs, ts, link["authority_sha"], bad_sha, bs, outcome_domain)
    raw_rows = w115._rejection_rows(st, ts) or []
    outcome_rows = w._outcome_rows(st, outcome_domain) or []
    first_raw_sha, first_raw = raw_rows[0]
    first_outcome_sha, first_outcome = outcome_rows[0]
    contradictory = w115._seal_rejection({
        "schema": w115.REJECTION_SCHEMA,
        "seq": 2,
        "predecessor_rejection_sha": first_raw_sha,
        "authority_sha": first_raw["authority_sha"],
        "transition_sha": bad_sha,
        "checkpoint_sha": first_raw["checkpoint_sha"],
        "lower_result": "TRANSITION_GENERATION_HOLD",
        "rejection_sha": "",
    })
    contradictory_sha = contradictory["rejection_sha"]
    st[w115.REJECTION_STORE][contradictory_sha] = contradictory
    authenticated = w._seal_outcome({
        "schema": w.OUTCOME_SCHEMA,
        "seq": 2,
        "predecessor_outcome_sha": first_outcome_sha,
        "rejection_sha": contradictory_sha,
        "authority_sha": contradictory["authority_sha"],
        "transition_sha": bad_sha,
        "checkpoint_sha": contradictory["checkpoint_sha"],
        "lower_result": contradictory["lower_result"],
        "outcome_authority_id": outcome_domain.authority_id,
        "outcome_auth_tag": "",
        "outcome_sha": "",
    }, outcome_domain)
    st[w.OUTCOME_STORE][authenticated["outcome_sha"]] = authenticated
    status = w.commit_status_state(st, boot, rt, rs, bs, ts, outcome_domain)
    authority = w.authority(
        rt, st, boot, services, rs, ts, cs, certificate_domain, bs, outcome_domain
    )
    return {"first": first, "status": status, "authority": authority}


def forged_outcome_authentication_fails_closed() -> dict:
    world = new_world()
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, outcome_domain = world
    link, genuine_sha, bad_sha = prepare_bad_sibling(world, "b5")
    result = w.commit(rt, st, boot, rs, ts, link["authority_sha"], bad_sha, bs, outcome_domain)
    outcome_rows = w._outcome_rows(st, outcome_domain) or []
    outcome_sha, original = outcome_rows[0]
    attacker = w.new_outcome_authority_domain()
    forged = deepcopy(original)
    forged["outcome_auth_tag"] = attacker.sign(w._outcome_payload(forged))
    forged["outcome_sha"] = ""
    forged["outcome_sha"] = w114._canonical_sha(forged, "outcome_sha")
    del st[w.OUTCOME_STORE][outcome_sha]
    st[w.OUTCOME_STORE][forged["outcome_sha"]] = forged
    status = w.commit_status_state(st, boot, rt, rs, bs, ts, outcome_domain)
    return {"result": result, "status": status}


def credential_substitution_fails_closed() -> dict:
    world = new_world()
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, outcome_domain = world
    substitute = w.new_outcome_authority_domain()
    status = w.commit_status_state(st, boot, rt, rs, bs, ts, substitute)
    authority = w.authority(
        rt, st, boot, services, rs, ts, cs, certificate_domain, bs, substitute
    )
    return {"status": status, "authority": authority}


def commit_and_reject_overlap_fails_closed() -> dict:
    world = new_world()
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, outcome_domain = world
    link, genuine_sha, bad_sha = prepare_bad_sibling(world, "b6")
    rejected = w.commit(rt, st, boot, rs, ts, link["authority_sha"], bad_sha, bs, outcome_domain)
    w114._ensure_commit_decision(st, boot, rs, ts, link["authority_sha"], bad_sha)
    status = w.commit_status_state(st, boot, rt, rs, bs, ts, outcome_domain)
    return {"rejected": rejected, "status": status}


def retriable_hold_is_not_terminalized() -> dict:
    world = new_world()
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, outcome_domain = world
    cp, use, link, genuine_sha, body = w.prepare(
        rt, st, priv, boot, services, rs, ts, cs, certificate_domain, bs, outcome_domain,
        target_user_app_state_sha="b7" * 32,
    )
    original = deepcopy(ts[genuine_sha])
    hold = resealed_variant(original, target_registry_sha="f" * 64)
    hold_sha = w100.put_transition(ts, hold)
    result = w.commit(rt, st, boot, rs, ts, link["authority_sha"], hold_sha, bs, outcome_domain)
    raw = w115._rejection_rows(st, ts) or []
    outcomes = w._outcome_rows(st, outcome_domain) or []
    status = w.commit_status_state(st, boot, rt, rs, bs, ts, outcome_domain)
    return {"result": result, "raw_count": len(raw), "outcome_count": len(outcomes), "status": status}


def raw_to_outcome_crash_holds_without_inventing_fact() -> dict:
    world = new_world()
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, outcome_domain = world
    link, genuine_sha, bad_sha = prepare_bad_sibling(world, "b8")
    error = None
    try:
        w.commit(
            rt, st, boot, rs, ts, link["authority_sha"], bad_sha, bs, outcome_domain,
            fault_after_raw_rejection_before_outcome=True,
        )
    except Exception as exc:
        error = f"{type(exc).__name__}:{exc}"
    raw = w115._rejection_rows(st, ts) or []
    outcomes = w._outcome_rows(st, outcome_domain) or []
    status = w.commit_status_state(st, boot, rt, rs, bs, ts, outcome_domain)
    authority = w.authority(
        rt, st, boot, services, rs, ts, cs, certificate_domain, bs, outcome_domain
    )
    return {
        "error": error,
        "raw_count": len(raw),
        "outcome_count": len(outcomes),
        "status": status,
        "authority": authority,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out")
    args = parser.parse_args()
    report = {
        "schema": "axm.flowing-compute.wave116.selftest/v1",
        "wave": 116,
        "source": w.SRC,
        "controls": [],
        "failed": 0,
    }

    repro = reproduce_verifier40_against_wave115()
    report["verifier40_reproduction"] = repro
    check(report, "wave115 verifier40 contradiction reproduces", repro["reproduced"], repro)

    normal = normal_reject_then_genuine_commit()
    report["normal_reject_then_genuine_commit"] = normal
    check(report, "stable bad transition rejected", normal["bad"] == "TRANSITION_DELTA_HOLD", normal)
    check(report, "exact rejected retry returns same result", normal["retry"] == "TRANSITION_DELTA_HOLD", normal)
    check(report, "one raw rejection only", normal["raw_count"] == 1 and normal["raw_count_after_retry"] == 1, normal)
    check(report, "one authenticated outcome only", normal["outcome_count"] == 1 and normal["outcome_count_after_retry"] == 1, normal)
    check(report, "genuine sibling commits", normal["good"] == "COMMITTED", normal)
    check(report, "normal final history valid", normal["status"] == w.HISTORY_VALID, normal)
    check(report, "normal final authority authoritative", normal["authority"].startswith("AUTHORITATIVE"), normal)

    raw_conflict = contradictory_raw_only_fails_closed()
    report["raw_conflict"] = raw_conflict
    check(report, "unauthenticated contradictory raw row fails history", raw_conflict["status"].get("status") == w.HISTORY_INCOMPLETE, raw_conflict)
    check(report, "unauthenticated contradictory raw row holds authority", raw_conflict["authority"] == w.HOLD_INCOMPLETE, raw_conflict)

    auth_conflict = contradictory_even_if_authenticated_fails_closed()
    report["authenticated_conflict"] = auth_conflict
    check(report, "even authenticated contradictory terminal outcomes fail history", auth_conflict["status"].get("status") == w.HISTORY_INCOMPLETE, auth_conflict)
    check(report, "authenticated contradiction reason names uniqueness", "terminal-outcome-not-unique" in auth_conflict["status"].get("reason", ""), auth_conflict)
    check(report, "authenticated contradictory outcomes hold authority", auth_conflict["authority"] == w.HOLD_INCOMPLETE, auth_conflict)

    forged = forged_outcome_authentication_fails_closed()
    report["forged_outcome"] = forged
    check(report, "forged outcome tag fails history", forged["status"].get("status") == w.HISTORY_INCOMPLETE, forged)
    check(report, "forged outcome reason names authentication", "outcome-authentication-failed" in forged["status"].get("reason", ""), forged)

    substitution = credential_substitution_fails_closed()
    report["credential_substitution"] = substitution
    check(report, "credential substitution fails history", substitution["status"].get("status") == w.HISTORY_INCOMPLETE, substitution)
    check(report, "credential substitution holds authority", substitution["authority"] == w.HOLD_INCOMPLETE, substitution)

    overlap = commit_and_reject_overlap_fails_closed()
    report["commit_reject_overlap"] = overlap
    check(report, "commit and reject terminal overlap fails history", overlap["status"].get("status") == w.HISTORY_INCOMPLETE, overlap)
    check(report, "commit and reject overlap reason explicit", "both-commit-and-reject" in overlap["status"].get("reason", ""), overlap)

    hold = retriable_hold_is_not_terminalized()
    report["retriable_hold"] = hold
    check(report, "retriable missing-registry hold preserved", hold["result"] == "TRANSITION_VALIDATION_HOLD", hold)
    check(report, "retriable hold does not create raw reject", hold["raw_count"] == 0, hold)
    check(report, "retriable hold does not create authenticated terminal outcome", hold["outcome_count"] == 0, hold)
    check(report, "retriable hold remains non-valid rather than invented finality", hold["status"].get("status") != w.HISTORY_VALID, hold)

    crash = raw_to_outcome_crash_holds_without_inventing_fact()
    report["raw_to_outcome_crash"] = crash
    check(report, "raw-to-outcome crash injected", isinstance(crash["error"], str) and "injected-wave116-crash" in crash["error"], crash)
    check(report, "raw-to-outcome crash preserves raw evidence", crash["raw_count"] == 1, crash)
    check(report, "raw-to-outcome crash does not invent auth outcome", crash["outcome_count"] == 0, crash)
    check(report, "raw-to-outcome crash fails history closed", crash["status"].get("status") == w.HISTORY_INCOMPLETE, crash)
    check(report, "raw-to-outcome crash holds authority", crash["authority"] == w.HOLD_INCOMPLETE, crash)

    report["passed"] = len(report["controls"]) - report["failed"]
    report["total"] = len(report["controls"])
    report["truth_boundary"] = {
        "same_modeled_python_failure_domain": True,
        "hmac_credential_is_os_process_independence": False,
        "hmac_credential_is_hardware_key_security": False,
        "power_loss_atomicity_proved": False,
        "physical_or_provider_independence_proved": False,
        "real_axm_or_monolith_workload_run": False,
        "synthetic_scaling_run": False,
        "performance_claim": False,
        "energy_claim": False,
        "retained_incremental_dormant_compute_claim": False,
        "known_failure": "raw rejection durable but authenticated outcome missing => HOLD with no public recovery in Wave 116",
        "whole_modeled_domain_rollback_counterexample_inherited": True,
    }

    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.json_out:
        path = Path(args.json_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
