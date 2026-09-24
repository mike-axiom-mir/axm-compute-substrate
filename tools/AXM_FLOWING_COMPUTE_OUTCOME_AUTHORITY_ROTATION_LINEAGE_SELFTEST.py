#!/usr/bin/env python3
"""Wave 118 old-root-authorized outcome-authority rotation lineage self-test."""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

import AXM_FLOWING_COMPUTE_OUTCOME_AUTHORITY_ROTATION_LINEAGE as w
import AXM_FLOWING_COMPUTE_OUTCOME_AUTHORITY_ROOT_ANCHOR as w117
import AXM_FLOWING_COMPUTE_PREVALIDATED_COMMIT_DECISION as w115
import AXM_FLOWING_COMPUTE_REMOTE_REGISTRY_MONOTONICITY as w100

q = w.q
g = w.g


def check(report: dict, name: str, ok: bool, detail=None) -> None:
    report["controls"].append({"name": name, "ok": bool(ok), "detail": detail})
    if not ok:
        report["failed"] += 1


def new_world():
    st, priv, boot, rt, services, tokens, rs = q.fixture()
    ts = {}
    cs = g.new_certificate_store()
    certificate_domain = w.w104.new_certificate_witness_domain()
    bs = {}
    initial = w.new_outcome_authority_domain()
    keyring = w.new_outcome_authority_keyring(initial)
    w.adopt_genesis(
        rt, st, boot, services, rs, ts, cs, certificate_domain, bs, keyring
    )
    return st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring


def resealed_variant(original: dict, **changes) -> dict:
    body = deepcopy(original)
    body.update(changes)
    body["transition_sha"] = ""
    return w100._seal(body, "transition_sha")


def prepare_bad_sibling(world, app_hex="a1"):
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    cp, use, link, genuine_sha, body = w.prepare(
        rt, st, priv, boot, services, rs, ts, cs, certificate_domain, bs, keyring,
        target_user_app_state_sha=app_hex * 32,
    )
    genuine = deepcopy(ts[genuine_sha])
    bad = resealed_variant(
        genuine,
        transition_kind=("CREDENTIAL_ROTATION" if genuine["transition_kind"] == "SAME" else "SAME"),
    )
    bad_sha = w100.put_transition(ts, bad)
    return link, genuine_sha, bad_sha


def settle(world) -> tuple[str, str]:
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    for slot in q.REMOTE_IDS:
        result = w.publish(rt, st, boot, services, tokens, rs, slot)
        if result not in ("APPENDED", "ALREADY_CURRENT"):
            raise RuntimeError(f"unexpected publish result {slot}: {result}")
    cert_result, _cert = w.certify_and_sync(
        rt, st, boot, services, rs, cs, certificate_domain
    )
    authority = w.authority(
        rt, st, boot, services, rs, ts, cs, certificate_domain, bs, keyring
    )
    return cert_result, authority


def rotate_once(world, successor=None, *, fault=False) -> dict:
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    predecessor_id = keyring.current.authority_id
    successor = successor or w.new_outcome_authority_domain()
    prepared = w.prepare_rotation(
        rt, st, priv, boot, services, rs, ts, cs, certificate_domain, bs, keyring, successor
    )
    cp, use, link, transition_sha, binding_body, root, envelope = prepared
    error = None
    result = None
    try:
        result = w.commit_rotation(
            rt, st, boot, rs, ts, link["authority_sha"], transition_sha,
            bs, keyring, successor,
            fault_after_checkpoint_before_activation=fault,
        )
    except Exception as exc:
        error = f"{type(exc).__name__}:{exc}"
    return {
        "successor": successor,
        "predecessor_id": predecessor_id,
        "prepared": prepared,
        "result": result,
        "error": error,
        "root": root,
        "envelope": envelope,
    }


def positive_rotation_and_followup() -> dict:
    world = new_world()
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    first = w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring,
        "wave118-before-rotation",
    )
    rotated = rotate_once(world)
    cert_result, authority_after_rotation = settle(world)
    after_rotation = w.commit_status_state(st, boot, rt, rs, bs, ts, keyring)
    follow = w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring,
        "wave118-after-rotation",
    )
    final = w.commit_status_state(st, boot, rt, rs, bs, ts, keyring)
    _b, _e, root, status, lineage = w._current_anchor(rt, st, boot, rs, bs, keyring)
    return {
        "first_status": first[-1].get("status"),
        "rotation_result": rotated["result"],
        "rotation_error": rotated["error"],
        "cert_result": cert_result,
        "authority_after_rotation": authority_after_rotation,
        "after_rotation_status": after_rotation,
        "follow_status": follow[-1].get("status"),
        "final_status": final,
        "current_generation": root["generation"],
        "lineage_generations": [r["generation"] for r in lineage],
        "lineage_authority_ids": [r["outcome_authority_id"] for r in lineage],
        "current_keyring_id": keyring.current.authority_id,
        "anchor_status": status,
    }


def old_root_crossover_fails_closed() -> dict:
    world = new_world()
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    old_domain = keyring.current
    w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring,
        "wave118-crossover-pre",
    )
    rotated = rotate_once(world)
    settle(world)
    new_id = keyring.current.authority_id
    st[w.w116.OUTCOME_BINDING] = w.w116._seal_binding(old_domain.authority_id)
    keyring.set_current(old_domain.authority_id)
    status = w.commit_status_state(st, boot, rt, rs, bs, ts, keyring)
    authority = w.authority(
        rt, st, boot, services, rs, ts, cs, certificate_domain, bs, keyring
    )
    return {
        "rotation_result": rotated["result"],
        "old_id": old_domain.authority_id,
        "new_id": new_id,
        "status": status,
        "authority": authority,
    }


def substituted_successor_fails_closed() -> dict:
    world = new_world()
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring,
        "wave118-substitute-pre",
    )
    rotated = rotate_once(world)
    settle(world)
    anchored_id = keyring.current.authority_id
    substitute = w.new_outcome_authority_domain()
    keyring.add(substitute, make_current=True)
    st[w.w116.OUTCOME_BINDING] = w.w116._seal_binding(substitute.authority_id)
    status = w.commit_status_state(st, boot, rt, rs, bs, ts, keyring)
    return {
        "rotation_result": rotated["result"],
        "anchored_id": anchored_id,
        "substitute_id": substitute.authority_id,
        "status": status,
    }


def rotated_root_tamper_fails_closed() -> dict:
    world = new_world()
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring,
        "wave118-tamper-pre",
    )
    rotated = rotate_once(world)
    settle(world)
    root = rotated["root"]
    tampered = deepcopy(root)
    tampered["predecessor_auth_tag"] = "0" * 64
    st[w.w117.OUTCOME_ROOT_STORE][root["root_sha"]] = tampered
    status = w.commit_status_state(st, boot, rt, rs, bs, ts, keyring)
    authority = w.authority(
        rt, st, boot, services, rs, ts, cs, certificate_domain, bs, keyring
    )
    return {"status": status, "authority": authority}


def missing_rotation_tail_fails_closed() -> dict:
    world = new_world()
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring,
        "wave118-tail-pre",
    )
    rotated = rotate_once(world)
    settle(world)
    root_sha = rotated["root"]["root_sha"]
    del st[w.w117.OUTCOME_ROOT_STORE][root_sha]
    status = w.commit_status_state(st, boot, rt, rs, bs, ts, keyring)
    return {"status": status, "root_sha": root_sha}


def crash_then_exact_recovery() -> dict:
    world = new_world()
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring,
        "wave118-crash-pre",
    )
    predecessor_id = keyring.current.authority_id
    successor = w.new_outcome_authority_domain()
    rotated = rotate_once(world, successor, fault=True)
    held = w.commit_status_state(st, boot, rt, rs, bs, ts, keyring)
    held_authority = w.authority(
        rt, st, boot, services, rs, ts, cs, certificate_domain, bs, keyring
    )
    binding_before_wrong = deepcopy(st[w.w116.OUTCOME_BINDING])
    current_before_wrong = keyring.current_authority_id
    wrong = w.new_outcome_authority_domain()
    wrong_error = None
    try:
        w.recover_rotation_activation(
            rt, st, boot, rs, ts, bs, keyring, wrong
        )
    except Exception as exc:
        wrong_error = f"{type(exc).__name__}:{exc}"
    unchanged_after_wrong = (
        st[w.w116.OUTCOME_BINDING] == binding_before_wrong
        and keyring.current_authority_id == current_before_wrong
    )
    recovered = w.recover_rotation_activation(
        rt, st, boot, rs, ts, bs, keyring, successor
    )
    settled = w.commit_status_state(st, boot, rt, rs, bs, ts, keyring)
    cert_result, authority = settle(world)
    return {
        "rotation_error": rotated["error"],
        "predecessor_id": predecessor_id,
        "successor_id": successor.authority_id,
        "held_status": held,
        "held_authority": held_authority,
        "wrong_recovery_error": wrong_error,
        "unchanged_after_wrong": unchanged_after_wrong,
        "recovered": recovered,
        "settled_status": settled,
        "cert_result": cert_result,
        "authority": authority,
    }


def outcomes_survive_rotation_lineage() -> dict:
    world = new_world()
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    first_id = keyring.current.authority_id
    link1, genuine1, bad1 = prepare_bad_sibling(world, "b1")
    reject1 = w.commit(
        rt, st, boot, rs, ts, link1["authority_sha"], bad1, bs, keyring
    )
    good1 = w.commit(
        rt, st, boot, rs, ts, link1["authority_sha"], genuine1, bs, keyring
    )
    settle(world)

    successor = w.new_outcome_authority_domain()
    rotated = rotate_once(world, successor)
    settle(world)
    second_id = keyring.current.authority_id

    link2, genuine2, bad2 = prepare_bad_sibling(world, "b2")
    reject2 = w.commit(
        rt, st, boot, rs, ts, link2["authority_sha"], bad2, bs, keyring
    )
    good2 = w.commit(
        rt, st, boot, rs, ts, link2["authority_sha"], genuine2, bs, keyring
    )
    cert_result, authority = settle(world)
    status = w.commit_status_state(st, boot, rt, rs, bs, ts, keyring)
    rows = w._outcome_rows(st, keyring) or []
    return {
        "reject1": reject1,
        "good1": good1,
        "rotation_result": rotated["result"],
        "reject2": reject2,
        "good2": good2,
        "cert_result": cert_result,
        "authority": authority,
        "status": status,
        "outcome_authority_ids": [body["outcome_authority_id"] for _sha, body in rows],
        "first_id": first_id,
        "second_id": second_id,
        "outcome_count": len(rows),
    }


def forged_predecessor_authorization_rejected() -> dict:
    world = new_world()
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    _b, _e, predecessor, _status, _lineage = w._current_anchor(rt, st, boot, rs, bs, keyring)
    successor = w.new_outcome_authority_domain()
    forged = w._seal_rotated_root(predecessor, keyring.current, successor)
    forged["predecessor_auth_tag"] = successor.sign(w._rotation_payload(forged))
    forged["root_sha"] = w.w114._canonical_sha(forged, "root_sha")
    error = None
    try:
        w._verify_direct_successor(predecessor, forged, keyring)
    except Exception as exc:
        error = f"{type(exc).__name__}:{exc}"
    return {"error": error}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out")
    args = parser.parse_args()
    report = {
        "schema": "axm.flowing-compute.wave118.selftest/v1",
        "wave": 118,
        "source": w.SRC,
        "controls": [],
        "failed": 0,
    }

    positive = positive_rotation_and_followup()
    report["positive_rotation"] = positive
    check(report, "pre-rotation epoch valid", positive["first_status"] == w.HISTORY_VALID, positive)
    check(report, "rotation commits", positive["rotation_result"] == "COMMITTED_ROTATED", positive)
    check(report, "rotation has no exception", positive["rotation_error"] is None, positive)
    check(report, "post-rotation authority settles", positive["authority_after_rotation"].startswith("AUTHORITATIVE"), positive)
    check(report, "post-rotation commit history valid", positive["after_rotation_status"].get("status") == w.HISTORY_VALID, positive)
    check(report, "normal successor epoch still valid", positive["follow_status"] == w.HISTORY_VALID, positive)
    check(report, "final history valid", positive["final_status"].get("status") == w.HISTORY_VALID, positive)
    check(report, "root lineage is generation zero then one", positive["lineage_generations"] == [0, 1], positive)
    check(report, "current credential matches generation one root", positive["current_keyring_id"] == positive["lineage_authority_ids"][-1], positive)

    crossover = old_root_crossover_fails_closed()
    report["old_root_crossover"] = crossover
    check(report, "old-root crossover is incomplete", crossover["status"].get("status") == w.HISTORY_INCOMPLETE, crossover)
    check(report, "old-root crossover authority holds", crossover["authority"] == w.HOLD_INCOMPLETE, crossover)

    substitute = substituted_successor_fails_closed()
    report["substituted_successor"] = substitute
    check(report, "substituted current successor is incomplete", substitute["status"].get("status") == w.HISTORY_INCOMPLETE, substitute)
    check(report, "substituted successor differs from anchored", substitute["anchored_id"] != substitute["substitute_id"], substitute)

    tamper = rotated_root_tamper_fails_closed()
    report["rotated_root_tamper"] = tamper
    check(report, "rotated root tamper is incomplete", tamper["status"].get("status") == w.HISTORY_INCOMPLETE, tamper)
    check(report, "rotated root tamper authority holds", tamper["authority"] == w.HOLD_INCOMPLETE, tamper)

    tail = missing_rotation_tail_fails_closed()
    report["missing_rotation_tail"] = tail
    check(report, "missing rotated root tail is incomplete", tail["status"].get("status") == w.HISTORY_INCOMPLETE, tail)

    crash = crash_then_exact_recovery()
    report["crash_recovery"] = crash
    check(report, "checkpoint-before-activation fault injected", isinstance(crash["rotation_error"], str) and "checkpoint-before-outcome-authority-activation" in crash["rotation_error"], crash)
    check(report, "crash window holds commit history", crash["held_status"].get("status") == w.HISTORY_INCOMPLETE, crash)
    check(report, "crash window authority holds", crash["held_authority"] == w.HOLD_INCOMPLETE, crash)
    check(report, "wrong successor recovery rejected", isinstance(crash["wrong_recovery_error"], str) and "successor-credential-mismatch" in crash["wrong_recovery_error"], crash)
    check(report, "wrong recovery does not mutate live binding", crash["unchanged_after_wrong"], crash)
    check(report, "exact successor recovery succeeds", crash["recovered"] == "RECOVERED_ROTATION_ACTIVATION", crash)
    check(report, "recovered commit history valid", crash["settled_status"].get("status") == w.HISTORY_VALID, crash)
    check(report, "recovered authority settles after witness sync", crash["authority"].startswith("AUTHORITATIVE"), crash)

    historical = outcomes_survive_rotation_lineage()
    report["historical_outcomes_across_rotation"] = historical
    check(report, "pre-rotation bad sibling rejected", historical["reject1"] == "TRANSITION_DELTA_HOLD", historical)
    check(report, "pre-rotation genuine sibling commits", historical["good1"] == "COMMITTED", historical)
    check(report, "rotation with retained old rejection history commits", historical["rotation_result"] == "COMMITTED_ROTATED", historical)
    check(report, "post-rotation bad sibling rejected", historical["reject2"] == "TRANSITION_DELTA_HOLD", historical)
    check(report, "post-rotation genuine sibling commits", historical["good2"] == "COMMITTED", historical)
    check(report, "two rejection outcomes retained", historical["outcome_count"] == 2, historical)
    check(report, "outcomes retain exact old then new authority identities", historical["outcome_authority_ids"] == [historical["first_id"], historical["second_id"]], historical)
    check(report, "cross-rotation rejection history stays valid", historical["status"].get("status") == w.HISTORY_VALID, historical)
    check(report, "cross-rotation authority settles", historical["authority"].startswith("AUTHORITATIVE"), historical)

    forged = forged_predecessor_authorization_rejected()
    report["forged_predecessor_authorization"] = forged
    check(report, "successor cannot self-authorize rotation", isinstance(forged["error"], str) and "predecessor-authentication-failed" in forged["error"], forged)

    report["truth_boundary"] = {
        "same_process_keyring": True,
        "historical_hmac_secrets_retained": True,
        "bootstrap_root_choice_still_configuration_boundary": True,
        "whole_modeled_domain_rollback_counterexample_preserved": True,
        "pre_wave117_migration_claimed": False,
        "os_process_independence_claimed": False,
        "device_or_provider_independence_claimed": False,
        "performance_or_energy_win_claimed": False,
        "retained_incremental_dormant_compute_win_claimed": False,
        "synthetic_scaling_run": False,
        "real_axm_monolith_performance_run": False,
        "merge_or_canon_promotion": False,
    }
    report["total"] = len(report["controls"])
    report["passed"] = report["total"] - report["failed"]

    text = json.dumps(report, sort_keys=True, indent=2)
    print(text)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
