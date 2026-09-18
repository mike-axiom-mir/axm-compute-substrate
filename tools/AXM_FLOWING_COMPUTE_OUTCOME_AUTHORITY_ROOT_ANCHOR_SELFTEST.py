#!/usr/bin/env python3
"""Wave 117 checkpoint-anchored outcome-authority-root positive/negative self-test."""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

import AXM_FLOWING_COMPUTE_OUTCOME_AUTHORITY_ROOT_ANCHOR as w
import AXM_FLOWING_COMPUTE_AUTHENTICATED_REJECTION_OUTCOME as w116
import AXM_FLOWING_COMPUTE_AUTHENTICATED_REJECTION_OUTCOME_SELFTEST as s116
import AXM_FLOWING_COMPUTE_PREVALIDATED_COMMIT_DECISION as w115
import AXM_FLOWING_COMPUTE_REMOTE_REGISTRY_MONOTONICITY as w100
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w104

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
    certificate_domain = w104.new_certificate_witness_domain()
    bs = {}
    outcome_domain = w.new_outcome_authority_domain()
    w.adopt_genesis(
        rt, st, boot, services, rs, ts, cs, certificate_domain, bs, outcome_domain
    )
    return st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, outcome_domain


def resealed_variant(original: dict, **changes) -> dict:
    body = deepcopy(original)
    body.update(changes)
    body["transition_sha"] = ""
    return w100._seal(body, "transition_sha")


def prepare_bad_sibling(world, app_hex="c1"):
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


def settle(world) -> tuple[str, str]:
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, outcome_domain = world
    for slot in q.REMOTE_IDS:
        result = w.publish(rt, st, boot, services, tokens, rs, slot)
        if result not in ("APPENDED", "ALREADY_CURRENT"):
            raise RuntimeError(f"unexpected publish result {slot}: {result}")
    cert_result, _cert = w.certify_and_sync(
        rt, st, boot, services, rs, cs, certificate_domain
    )
    authority = w.authority(
        rt, st, boot, services, rs, ts, cs, certificate_domain, bs, outcome_domain
    )
    return cert_result, authority


def reproduce_verifier41_against_wave116() -> dict:
    world = s116.new_world()
    (
        st,
        priv,
        boot,
        rt,
        services,
        tokens,
        rs,
        ts,
        cs,
        certificate_domain,
        bs,
        original_domain,
    ) = world
    link, genuine_sha, bad_sha = s116.prepare_bad_sibling(world, "d1")
    first = w116.commit(
        rt, st, boot, rs, ts, link["authority_sha"], bad_sha, bs, original_domain
    )
    raw_before = w115._rejection_rows(st, ts) or []
    substitute = w116.new_outcome_authority_domain()
    raw_body = raw_before[0][1]
    contradictory = "TRANSITION_GENERATION_HOLD"
    replacement_raw = w115._seal_rejection({
        "schema": w115.REJECTION_SCHEMA,
        "seq": 1,
        "predecessor_rejection_sha": None,
        "authority_sha": raw_body["authority_sha"],
        "transition_sha": raw_body["transition_sha"],
        "checkpoint_sha": raw_body["checkpoint_sha"],
        "lower_result": contradictory,
        "rejection_sha": "",
    })
    st[w115.REJECTION_STORE] = {replacement_raw["rejection_sha"]: replacement_raw}
    st[w116.OUTCOME_BINDING] = w116._seal_binding(substitute.authority_id)
    replacement_outcome = w116._seal_outcome({
        "schema": w116.OUTCOME_SCHEMA,
        "seq": 1,
        "predecessor_outcome_sha": None,
        "rejection_sha": replacement_raw["rejection_sha"],
        "authority_sha": replacement_raw["authority_sha"],
        "transition_sha": replacement_raw["transition_sha"],
        "checkpoint_sha": replacement_raw["checkpoint_sha"],
        "lower_result": contradictory,
        "outcome_authority_id": substitute.authority_id,
        "outcome_auth_tag": "",
        "outcome_sha": "",
    }, substitute)
    st[w116.OUTCOME_STORE] = {replacement_outcome["outcome_sha"]: replacement_outcome}
    good = w116.commit(
        rt, st, boot, rs, ts, link["authority_sha"], genuine_sha, bs, substitute
    )
    for slot in q.REMOTE_IDS:
        w116.publish(rt, st, boot, services, tokens, rs, slot)
    w116.certify_and_sync(rt, st, boot, services, rs, cs, certificate_domain)
    final_status = w116.commit_status_state(st, boot, rt, rs, bs, ts, substitute)
    final_authority = w116.authority(
        rt, st, boot, services, rs, ts, cs, certificate_domain, bs, substitute
    )
    reproduced = (
        first == "TRANSITION_DELTA_HOLD"
        and good == "COMMITTED"
        and final_status.get("status") == w116.HISTORY_VALID
        and final_authority.startswith("AUTHORITATIVE")
        and final_status.get("outcome_authority_id") == substitute.authority_id
    )
    return {
        "reproduced": reproduced,
        "first": first,
        "good": good,
        "status": final_status,
        "authority": final_authority,
        "original_authority_id": original_domain.authority_id,
        "substitute_authority_id": substitute.authority_id,
    }


def verifier41_attack_fails_closed() -> dict:
    world = new_world()
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, original_domain = world
    link, genuine_sha, bad_sha = prepare_bad_sibling(world, "d2")
    first = w.commit(
        rt, st, boot, rs, ts, link["authority_sha"], bad_sha, bs, original_domain
    )
    raw_before = w115._rejection_rows(st, ts) or []
    raw_body = raw_before[0][1]
    substitute = w.new_outcome_authority_domain()
    replacement_raw = w115._seal_rejection({
        "schema": w115.REJECTION_SCHEMA,
        "seq": 1,
        "predecessor_rejection_sha": None,
        "authority_sha": raw_body["authority_sha"],
        "transition_sha": raw_body["transition_sha"],
        "checkpoint_sha": raw_body["checkpoint_sha"],
        "lower_result": "TRANSITION_GENERATION_HOLD",
        "rejection_sha": "",
    })
    st[w115.REJECTION_STORE] = {replacement_raw["rejection_sha"]: replacement_raw}
    st[w116.OUTCOME_BINDING] = w116._seal_binding(substitute.authority_id)
    replacement_outcome = w116._seal_outcome({
        "schema": w116.OUTCOME_SCHEMA,
        "seq": 1,
        "predecessor_outcome_sha": None,
        "rejection_sha": replacement_raw["rejection_sha"],
        "authority_sha": replacement_raw["authority_sha"],
        "transition_sha": replacement_raw["transition_sha"],
        "checkpoint_sha": replacement_raw["checkpoint_sha"],
        "lower_result": replacement_raw["lower_result"],
        "outcome_authority_id": substitute.authority_id,
        "outcome_auth_tag": "",
        "outcome_sha": "",
    }, substitute)
    st[w116.OUTCOME_STORE] = {replacement_outcome["outcome_sha"]: replacement_outcome}

    substituted_status = w.commit_status_state(st, boot, rt, rs, bs, ts, substitute)
    substituted_authority = w.authority(
        rt, st, boot, services, rs, ts, cs, certificate_domain, bs, substitute
    )
    original_status = w.commit_status_state(st, boot, rt, rs, bs, ts, original_domain)
    commit_error = None
    try:
        w.commit(rt, st, boot, rs, ts, link["authority_sha"], genuine_sha, bs, substitute)
    except Exception as exc:
        commit_error = f"{type(exc).__name__}:{exc}"
    return {
        "first": first,
        "substituted_status": substituted_status,
        "substituted_authority": substituted_authority,
        "original_status_after_mutable_rewrite": original_status,
        "substitute_commit_error": commit_error,
        "original_authority_id": original_domain.authority_id,
        "substitute_authority_id": substitute.authority_id,
    }


def normal_reject_then_genuine_commit() -> dict:
    world = new_world()
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, domain = world
    link, genuine_sha, bad_sha = prepare_bad_sibling(world, "d3")
    bad = w.commit(rt, st, boot, rs, ts, link["authority_sha"], bad_sha, bs, domain)
    good = w.commit(rt, st, boot, rs, ts, link["authority_sha"], genuine_sha, bs, domain)
    cert_result, authority = settle(world)
    status = w.commit_status_state(st, boot, rt, rs, bs, ts, domain)
    current, envelope, root, local_status = w._current_anchor(rt, st, boot, rs, bs, domain)
    return {
        "bad": bad,
        "good": good,
        "cert_result": cert_result,
        "authority": authority,
        "status": status,
        "current_binding_seq": current["seq"],
        "local_status": local_status,
        "root_sha": root["root_sha"],
        "root_authority_id": root["outcome_authority_id"],
        "user_app_state_sha": envelope["user_app_state_sha"],
    }


def root_body_tamper_fails_closed() -> dict:
    world = new_world()
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, domain = world
    _binding, envelope, root, _status = w._current_anchor(rt, st, boot, rs, bs, domain)
    tampered = deepcopy(root)
    tampered["outcome_authority_id"] = "f" * 64
    st[w.OUTCOME_ROOT_STORE][root["root_sha"]] = tampered
    status = w.commit_status_state(st, boot, rt, rs, bs, ts, domain)
    authority = w.authority(rt, st, boot, services, rs, ts, cs, certificate_domain, bs, domain)
    return {"status": status, "authority": authority}


def root_store_replacement_fails_closed() -> dict:
    world = new_world()
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, domain = world
    substitute = w.new_outcome_authority_domain()
    replacement = w._seal_root(substitute.authority_id)
    st[w.OUTCOME_ROOT_STORE] = {replacement["root_sha"]: replacement}
    status = w.commit_status_state(st, boot, rt, rs, bs, ts, substitute)
    return {"status": status}


def envelope_tamper_fails_closed() -> dict:
    world = new_world()
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, domain = world
    _binding, envelope, root, _status = w._current_anchor(rt, st, boot, rs, bs, domain)
    tampered = deepcopy(envelope)
    tampered["user_app_state_sha"] = "e" * 64
    st[w.ENVELOPE_STORE][envelope["envelope_sha"]] = tampered
    status = w.commit_status_state(st, boot, rt, rs, bs, ts, domain)
    return {"status": status}


def two_epoch_app_evolution_preserves_root() -> dict:
    world = new_world()
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, domain = world
    first = w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, domain, "wave117-e1"
    )
    second = w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, domain, "wave117-e2"
    )
    current, envelope, root, status = w._current_anchor(rt, st, boot, rs, bs, domain)
    binding_head, bindings = w.w105.verify_binding_chain(bs, rs, current["binding_sha"])
    envelope_roots = []
    for binding in bindings:
        env = w._get_envelope(st, binding["user_app_state_sha"])
        envelope_roots.append(env["outcome_root_sha"])
    return {
        "first_commit_status": first[-1].get("status"),
        "second_commit_status": second[-1].get("status"),
        "current_binding_seq": current["seq"],
        "anchor_status": status,
        "binding_count": len(bindings),
        "distinct_root_count": len(set(envelope_roots)),
        "root_sha": root["root_sha"],
        "authority": w.authority(
            rt, st, boot, services, rs, ts, cs, certificate_domain, bs, domain
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out")
    args = parser.parse_args()
    report = {
        "schema": "axm.flowing-compute.wave117.selftest/v1",
        "wave": 117,
        "source": w.SRC,
        "controls": [],
        "failed": 0,
    }

    baseline = reproduce_verifier41_against_wave116()
    report["verifier41_wave116_reproduction"] = baseline
    check(report, "verifier41 reproduces against unchanged Wave 116", baseline["reproduced"], baseline)

    attack = verifier41_attack_fails_closed()
    report["verifier41_wave117_attack"] = attack
    check(report, "Wave 117 rejects substituted outcome root", attack["substituted_status"].get("status") == w.HISTORY_INCOMPLETE, attack)
    check(report, "substitution reason names checkpoint anchor", "checkpoint-anchored-outcome-authority-credential-substitution" in attack["substituted_status"].get("reason", ""), attack)
    check(report, "substituted authority holds", attack["substituted_authority"] == w.HOLD_INCOMPLETE, attack)
    check(report, "substitute cannot commit genuine sibling", isinstance(attack["substitute_commit_error"], str) and "checkpoint-anchored" in attack["substitute_commit_error"], attack)
    check(report, "old credential also detects rewritten mutable binding", attack["original_status_after_mutable_rewrite"].get("status") == w.HISTORY_INCOMPLETE, attack)

    normal = normal_reject_then_genuine_commit()
    report["normal_reject_then_genuine_commit"] = normal
    check(report, "stable bad sibling still rejected", normal["bad"] == "TRANSITION_DELTA_HOLD", normal)
    check(report, "genuine sibling still commits", normal["good"] == "COMMITTED", normal)
    check(report, "normal history remains valid", normal["status"].get("status") == w.HISTORY_VALID, normal)
    check(report, "normal authority remains authoritative", normal["authority"].startswith("AUTHORITATIVE"), normal)
    check(report, "checkpoint anchor names exact credential", normal["root_authority_id"] == normal["status"].get("checkpoint_anchored_outcome_authority_id"), normal)

    tamper = root_body_tamper_fails_closed()
    report["root_body_tamper"] = tamper
    check(report, "root-body tamper fails history", tamper["status"].get("status") == w.HISTORY_INCOMPLETE, tamper)
    check(report, "root-body tamper holds authority", tamper["authority"] == w.HOLD_INCOMPLETE, tamper)

    replacement = root_store_replacement_fails_closed()
    report["root_store_replacement"] = replacement
    check(report, "root-store replacement without checkpoint rewrite fails", replacement["status"].get("status") == w.HISTORY_INCOMPLETE, replacement)
    check(report, "root-store replacement reason names missing anchored root", "checkpoint-anchored-outcome-root-body-missing" in replacement["status"].get("reason", ""), replacement)

    envelope = envelope_tamper_fails_closed()
    report["envelope_tamper"] = envelope
    check(report, "envelope tamper fails history", envelope["status"].get("status") == w.HISTORY_INCOMPLETE, envelope)
    check(report, "envelope tamper reason names seal mismatch", "outcome-root-envelope-seal-mismatch" in envelope["status"].get("reason", ""), envelope)

    evolution = two_epoch_app_evolution_preserves_root()
    report["two_epoch_evolution"] = evolution
    check(report, "epoch1 settles valid", evolution["first_commit_status"] == w.HISTORY_VALID, evolution)
    check(report, "epoch2 settles valid", evolution["second_commit_status"] == w.HISTORY_VALID, evolution)
    check(report, "binding chain reaches genesis plus two epochs", evolution["binding_count"] == 3 and evolution["current_binding_seq"] == 2, evolution)
    check(report, "all retained checkpoints resolve one exact outcome root", evolution["distinct_root_count"] == 1, evolution)
    check(report, "two-epoch authority remains authoritative", evolution["authority"].startswith("AUTHORITATIVE"), evolution)

    report["passed"] = len(report["controls"]) - report["failed"]
    report["total"] = len(report["controls"])
    report["truth_boundary"] = {
        "same_modeled_python_failure_domain": True,
        "checkpoint_anchor_closes_verifier41_binding_substitution": True,
        "signer_rotation_supported": False,
        "migration_of_existing_wave116_worlds_proved": False,
        "os_process_independence_proved": False,
        "power_loss_atomicity_proved": False,
        "physical_or_provider_independence_proved": False,
        "whole_modeled_domain_rollback_counterexample_inherited": True,
        "real_axm_or_monolith_workload_run": False,
        "synthetic_scaling_run": False,
        "performance_claim": False,
        "energy_claim": False,
        "retained_incremental_dormant_compute_claim": False,
        "next_gate": "old-root-authorized outcome-signer rotation with append-only lineage, then separate-process durable witness",
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
