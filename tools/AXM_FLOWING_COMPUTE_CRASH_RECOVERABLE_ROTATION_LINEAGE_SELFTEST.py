#!/usr/bin/env python3
"""Wave 119 crash-recoverable bootstrap + rotation lineage self-test."""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

import AXM_FLOWING_COMPUTE_CRASH_RECOVERABLE_ROTATION_LINEAGE as w
import AXM_FLOWING_COMPUTE_OUTCOME_AUTHORITY_ROTATION_LINEAGE as w118
import AXM_FLOWING_COMPUTE_OUTCOME_AUTHORITY_ROTATION_LINEAGE_SELFTEST as t118
import AXM_FLOWING_COMPUTE_OUTCOME_AUTHORITY_ROOT_ANCHOR as w117

q = w.q
g = w.g


def check(report: dict, name: str, ok: bool, detail=None) -> None:
    report["controls"].append({"name": name, "ok": bool(ok), "detail": detail})
    if not ok:
        report["failed"] += 1


def fresh_raw():
    st, priv, boot, rt, services, tokens, rs = q.fixture()
    ts = {}
    cs = g.new_certificate_store()
    certificate_domain = w.w104.new_certificate_witness_domain()
    bs = {}
    initial = w.new_outcome_authority_domain()
    keyring = w.new_outcome_authority_keyring(initial)
    return st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring


def new_world():
    world = fresh_raw()
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    w.adopt_genesis(rt, st, boot, services, rs, ts, cs, certificate_domain, bs, keyring)
    return world


def settle(world) -> tuple[str, str]:
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    for slot in q.REMOTE_IDS:
        result = w.publish(rt, st, boot, services, tokens, rs, slot)
        if result not in ("APPENDED", "ALREADY_CURRENT"):
            raise RuntimeError(f"unexpected publish result {slot}: {result}")
    cert_result, _ = w.certify_and_sync(rt, st, boot, services, rs, cs, certificate_domain)
    verdict = w.authority(rt, st, boot, services, rs, ts, cs, certificate_domain, bs, keyring)
    return cert_result, verdict


def bootstrap_prefix_retry(mode: str) -> dict:
    world = fresh_raw()
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    original = rt["app_state_sha"]
    root = w117._seal_root(keyring.current.authority_id)
    root_sha = w117._put_root(st, root)
    envelope_sha = None
    if mode == "root-envelope":
        envelope = w117._seal_envelope(original, root_sha)
        envelope_sha = w117._put_envelope(st, envelope)
    result = w.adopt_genesis(rt, st, boot, services, rs, ts, cs, certificate_domain, bs, keyring)
    state = w.commit_status_state(st, boot, rt, rs, bs, ts, keyring)
    second = w.adopt_genesis(rt, st, boot, services, rs, ts, cs, certificate_domain, bs, keyring)
    return {
        "mode": mode,
        "result": result,
        "second": second,
        "status": state,
        "root_count": len(st[w117.OUTCOME_ROOT_STORE]),
        "envelope_count": len(st[w117.ENVELOPE_STORE]),
        "root_sha": root_sha,
        "prefix_envelope_sha": envelope_sha,
        "runtime_app_state_sha": rt["app_state_sha"],
    }


def reproduce_wave117_bootstrap_retry_failure() -> dict:
    world = fresh_raw()
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    root = w117._seal_root(keyring.current.authority_id)
    w117._put_root(st, root)
    error = None
    try:
        w117.adopt_genesis(rt, st, boot, services, rs, ts, cs, certificate_domain, bs, keyring.current)
    except Exception as exc:
        error = f"{type(exc).__name__}:{exc}"
    return {"error": error, "binding_count": len(bs), "transition_count": len(ts)}


def bad_bootstrap_prefix_fails_closed() -> dict:
    world = fresh_raw()
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    other = w.new_outcome_authority_domain()
    wrong = w117._seal_root(other.authority_id)
    w117._put_root(st, wrong)
    before = deepcopy(st[w117.OUTCOME_ROOT_STORE])
    error = None
    try:
        w.adopt_genesis(rt, st, boot, services, rs, ts, cs, certificate_domain, bs, keyring)
    except Exception as exc:
        error = f"{type(exc).__name__}:{exc}"
    return {
        "error": error,
        "root_unchanged": st[w117.OUTCOME_ROOT_STORE] == before,
        "binding_count": len(bs),
        "transition_count": len(ts),
        "lower_outcome_binding_present": w.w116.OUTCOME_BINDING in st,
    }


def prepare_rotation(world):
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring,
        "wave119-pre-rotation",
    )
    successor = w.new_outcome_authority_domain()
    prepared = w.prepare_rotation(
        rt, st, priv, boot, services, rs, ts, cs, certificate_domain, bs, keyring, successor
    )
    link = prepared[2]
    transition_sha = prepared[3]
    return successor, prepared, link["authority_sha"], transition_sha


def crash_before_provenance(world) -> dict:
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    successor, prepared, link_sha, transition_sha = prepare_rotation(world)
    original_append = w.w111._append_provenance

    def boom(*args, **kwargs):
        raise RuntimeError("injected-wave119-verifier-crash-after-lower-commit-before-provenance")

    error = None
    w.w111._append_provenance = boom
    try:
        w.commit_rotation(rt, st, boot, rs, ts, link_sha, transition_sha, bs, keyring, successor)
    except Exception as exc:
        error = f"{type(exc).__name__}:{exc}"
    finally:
        w.w111._append_provenance = original_append

    return {
        "world": world,
        "successor": successor,
        "prepared": prepared,
        "link_sha": link_sha,
        "transition_sha": transition_sha,
        "error": error,
        "status_after_crash": w.commit_status_state(st, boot, rt, rs, bs, ts, keyring),
        "live_authority_after_crash": keyring.current.authority_id,
    }


def reproduce_wave118_rotation_retry_failure() -> dict:
    world = t118.new_world()
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    w118.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring,
        "wave119-repro-wave118-pre",
    )
    successor = w118.new_outcome_authority_domain()
    prepared = w118.prepare_rotation(
        rt, st, priv, boot, services, rs, ts, cs, certificate_domain, bs, keyring, successor
    )
    link_sha = prepared[2]["authority_sha"]
    transition_sha = prepared[3]
    original_append = w118.w111._append_provenance

    def boom(*args, **kwargs):
        raise RuntimeError("injected-wave119-wave118-repro")

    first_error = None
    w118.w111._append_provenance = boom
    try:
        w118.commit_rotation(rt, st, boot, rs, ts, link_sha, transition_sha, bs, keyring, successor)
    except Exception as exc:
        first_error = f"{type(exc).__name__}:{exc}"
    finally:
        w118.w111._append_provenance = original_append

    retry_error = None
    try:
        w118.commit_rotation(rt, st, boot, rs, ts, link_sha, transition_sha, bs, keyring, successor)
    except Exception as exc:
        retry_error = f"{type(exc).__name__}:{exc}"
    state = w118.commit_status_state(st, boot, rt, rs, bs, ts, keyring)
    return {"first_error": first_error, "retry_error": retry_error, "status": state}


def wave119_retry_repairs_rotation() -> dict:
    crash = crash_before_provenance(new_world())
    world = crash["world"]
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    result = w.commit_rotation(
        rt, st, boot, rs, ts, crash["link_sha"], crash["transition_sha"], bs, keyring, crash["successor"]
    )
    state = w.commit_status_state(st, boot, rt, rs, bs, ts, keyring)
    second = w.commit_rotation(
        rt, st, boot, rs, ts, crash["link_sha"], crash["transition_sha"], bs, keyring, crash["successor"]
    )
    return {
        "crash_error": crash["error"],
        "crash_status": crash["status_after_crash"],
        "retry_result": result,
        "second_retry": second,
        "final_status": state,
        "current_authority_id": keyring.current.authority_id,
        "successor_id": crash["successor"].authority_id,
    }


def explicit_recovery_repairs_rotation() -> dict:
    crash = crash_before_provenance(new_world())
    world = crash["world"]
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    result = w.recover_rotation_commit(
        rt, st, boot, rs, ts, crash["link_sha"], crash["transition_sha"], bs, keyring, crash["successor"]
    )
    state = w.commit_status_state(st, boot, rt, rs, bs, ts, keyring)
    return {"result": result, "status": state, "current": keyring.current.authority_id}


def wrong_successor_fails_without_mutation() -> dict:
    crash = crash_before_provenance(new_world())
    world = crash["world"]
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    before_prov = deepcopy(st.get(w.w111.PROVENANCE_STORE))
    before_binding = deepcopy(st.get(w.w116.OUTCOME_BINDING))
    before_current = keyring.current.authority_id
    wrong = w.new_outcome_authority_domain()
    error = None
    try:
        w.recover_rotation_commit(
            rt, st, boot, rs, ts, crash["link_sha"], crash["transition_sha"], bs, keyring, wrong
        )
    except Exception as exc:
        error = f"{type(exc).__name__}:{exc}"
    return {
        "error": error,
        "provenance_unchanged": st.get(w.w111.PROVENANCE_STORE) == before_prov,
        "binding_unchanged": st.get(w.w116.OUTCOME_BINDING) == before_binding,
        "current_unchanged": keyring.current.authority_id == before_current,
    }


def after_provenance_before_activation_retry() -> dict:
    world = new_world()
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    successor, prepared, link_sha, transition_sha = prepare_rotation(world)
    error = None
    try:
        w.commit_rotation(
            rt, st, boot, rs, ts, link_sha, transition_sha, bs, keyring, successor,
            fault_after_checkpoint_before_activation=True,
        )
    except Exception as exc:
        error = f"{type(exc).__name__}:{exc}"
    result = w.commit_rotation(rt, st, boot, rs, ts, link_sha, transition_sha, bs, keyring, successor)
    state = w.commit_status_state(st, boot, rt, rs, bs, ts, keyring)
    return {"error": error, "retry_result": result, "status": state}


def clean_rotation() -> dict:
    world = new_world()
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    successor, prepared, link_sha, transition_sha = prepare_rotation(world)
    result = w.commit_rotation(rt, st, boot, rs, ts, link_sha, transition_sha, bs, keyring, successor)
    state = w.commit_status_state(st, boot, rt, rs, bs, ts, keyring)
    cert, verdict = settle(world)
    return {"result": result, "status": state, "certificate": cert, "authority": verdict}


def run() -> dict:
    report = {
        "wave": 119,
        "scope": "same-process crash/retry correctness only; no performance/energy/process-independence claim",
        "source": w.SRC,
        "controls": [],
        "failed": 0,
    }

    repro_boot = reproduce_wave117_bootstrap_retry_failure()
    check(report, "unchanged Wave117 exact-root bootstrap retry failure reproduced",
          repro_boot["error"] is not None and "wave117-root-anchor-state-already-present" in repro_boot["error"], repro_boot)

    root_only = bootstrap_prefix_retry("root")
    check(report, "Wave119 root-only durable prefix retry succeeds",
          root_only["status"].get("status") in (w.HISTORY_NONE, w.HISTORY_VALID), root_only)
    check(report, "Wave119 root-only retry does not duplicate root/envelope",
          root_only["root_count"] == 1 and root_only["envelope_count"] == 1, root_only)
    check(report, "Wave119 completed bootstrap is exactly idempotent",
          root_only["second"] == "ALREADY_GENESIS_ADOPTED", root_only)

    root_env = bootstrap_prefix_retry("root-envelope")
    check(report, "Wave119 root+envelope durable prefix retry succeeds",
          root_env["status"].get("status") in (w.HISTORY_NONE, w.HISTORY_VALID), root_env)
    check(report, "Wave119 root+envelope retry does not duplicate durable prefix",
          root_env["root_count"] == 1 and root_env["envelope_count"] == 1, root_env)

    bad = bad_bootstrap_prefix_fails_closed()
    check(report, "Wave119 mismatched bootstrap residue fails closed without lower adoption",
          bad["error"] is not None and bad["root_unchanged"] and not bad["lower_outcome_binding_present"]
          and bad["binding_count"] == 0 and bad["transition_count"] == 0, bad)

    repro_rot = reproduce_wave118_rotation_retry_failure()
    check(report, "unchanged Wave118 lower-commit/provenance crash reproduced",
          repro_rot["first_error"] is not None and repro_rot["status"].get("status") == w.HISTORY_INCOMPLETE, repro_rot)
    check(report, "unchanged Wave118 public retry remains blocked", repro_rot["retry_error"] is not None, repro_rot)

    repaired = wave119_retry_repairs_rotation()
    check(report, "Wave119 exact commit_rotation retry repairs missing trailing provenance",
          repaired["retry_result"] == "RECOVERED_ROTATION_COMMIT", repaired)
    check(report, "Wave119 recovered rotation settles VALID under exact successor",
          repaired["final_status"].get("status") == w.HISTORY_VALID
          and repaired["current_authority_id"] == repaired["successor_id"], repaired)
    check(report, "Wave119 settled rotation retry is idempotent",
          repaired["second_retry"] == "ALREADY_COMMITTED_ROTATED", repaired)

    explicit = explicit_recovery_repairs_rotation()
    check(report, "Wave119 explicit public recovery route repairs exact crash boundary",
          explicit["result"] == "RECOVERED_ROTATION_COMMIT"
          and explicit["status"].get("status") == w.HISTORY_VALID, explicit)

    wrong = wrong_successor_fails_without_mutation()
    check(report, "Wave119 wrong successor recovery fails before provenance/live mutation",
          wrong["error"] is not None and wrong["provenance_unchanged"]
          and wrong["binding_unchanged"] and wrong["current_unchanged"], wrong)

    late = after_provenance_before_activation_retry()
    check(report, "Wave119 retry also recovers Wave118 after-provenance activation crash",
          late["error"] is not None and late["retry_result"] == "RECOVERED_ROTATION_ACTIVATION"
          and late["status"].get("status") == w.HISTORY_VALID, late)

    clean = clean_rotation()
    check(report, "Wave119 clean rotation preserves Wave118 normal success",
          clean["result"] == "COMMITTED_ROTATED" and clean["status"].get("status") == w.HISTORY_VALID
          and str(clean["authority"]).startswith("AUTHORITATIVE"), clean)

    report["passed"] = len(report["controls"]) - report["failed"]
    report["total"] = len(report["controls"])
    report["verdict"] = "PASS" if report["failed"] == 0 else "FAIL"
    report["preserved_counterexamples"] = [
        "whole-modeled-domain rollback can still erase every newer root/decision/provenance fact",
        "bootstrap retry repair accepts only one exact generation-0 root/envelope prefix",
        "rotation repair accepts only one exact missing trailing provenance row already proven by lower commit + decision",
        "all credentials/stores remain in one Python failure domain",
    ]
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out")
    args = parser.parse_args()
    report = run()
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
