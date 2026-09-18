#!/usr/bin/env python3
"""Wave 121 staged rotation-prepare publication atomicity self-test."""
from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy

import AXM_FLOWING_COMPUTE_ROTATION_PREPARE_PUBLICATION_ATOMICITY as w
import AXM_FLOWING_COMPUTE_ROTATION_PREPARE_TRANSACTION as w120
import AXM_FLOWING_COMPUTE_ROTATION_PREPARE_TRANSACTION_SELFTEST as t120
import AXM_FLOWING_COMPUTE_CRASH_RECOVERABLE_ROTATION_LINEAGE_SELFTEST as t119


def check(report: dict, name: str, ok: bool, detail=None) -> None:
    report["controls"].append({"name": name, "ok": bool(ok), "detail": detail})
    if not ok:
        report["failed"] += 1


def prepared_world(label: str):
    return t120.prepared_world(label)


def reproduce_wave120_pr45() -> dict:
    world = prepared_world("wave121-reproduce-wave120-pr45")
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    roots = st[w.w117.OUTCOME_ROOT_STORE]
    envelopes = st[w.w117.ENVELOPE_STORE]
    base_roots = set(roots)
    base_envelopes = set(envelopes)
    base_transitions = set(ts)
    base_bindings = set(bs)
    successor = w.new_outcome_authority_domain()
    target = hashlib.sha256(b"wave121-verifier45-reproduction-target").hexdigest()

    first_error = None
    try:
        w120.prepare_rotation(
            rt, st, priv, boot, services, rs, ts, cs, certificate_domain, bs,
            keyring, successor, target,
            fault_after_lower_prepare_before_sync=True,
        )
    except Exception as exc:
        first_error = f"{type(exc).__name__}:{exc}"

    new_roots = set(roots) - base_roots
    new_envelopes = set(envelopes) - base_envelopes
    new_transitions = set(ts) - base_transitions
    new_bindings = set(bs) - base_bindings
    referencing = [
        key for key, body in bs.items()
        if isinstance(body, dict) and body.get("user_app_state_sha") in new_envelopes
    ]
    status = w120.commit_status_state(st, boot, rt, rs, bs, ts, keyring)
    verdict = w120.authority(
        rt, st, boot, services, rs, ts, cs, certificate_domain, bs, keyring
    )
    retry_error = None
    retry = None
    try:
        retry = w120.prepare_rotation(
            rt, st, priv, boot, services, rs, ts, cs, certificate_domain, bs,
            keyring, successor, target,
        )
    except Exception as exc:
        retry_error = f"{type(exc).__name__}:{exc}"
    return {
        "first_error": first_error,
        "new_root_count": len(new_roots),
        "new_envelope_count": len(new_envelopes),
        "new_transition_count": len(new_transitions),
        "new_binding_count": len(new_bindings),
        "binding_references_new_envelope": bool(referencing),
        "status": status,
        "authority": verdict,
        "retry_is_none": retry is None,
        "retry_error": retry_error,
    }


def publication_fault(flag: str, expected_error: str) -> dict:
    world = prepared_world(f"wave121-{flag}")
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    before_st = deepcopy(st)
    before_priv = deepcopy(priv)
    before_ts = deepcopy(ts)
    before_bs = deepcopy(bs)
    successor = w.new_outcome_authority_domain()
    target = hashlib.sha256(f"wave121-{flag}-target".encode()).hexdigest()

    error = None
    try:
        w.prepare_rotation(
            rt, st, priv, boot, services, rs, ts, cs, certificate_domain, bs,
            keyring, successor, target, **{flag: True},
        )
    except Exception as exc:
        error = f"{type(exc).__name__}:{exc}"

    exact_rollback = st == before_st and priv == before_priv and ts == before_ts and bs == before_bs
    verdict_after_fault = w.authority(
        rt, st, boot, services, rs, ts, cs, certificate_domain, bs, keyring
    )
    retry_error = None
    retry = None
    try:
        retry = w.prepare_rotation(
            rt, st, priv, boot, services, rs, ts, cs, certificate_domain, bs,
            keyring, successor, target,
        )
    except Exception as exc:
        retry_error = f"{type(exc).__name__}:{exc}"

    return {
        "flag": flag,
        "error": error,
        "expected_error": expected_error,
        "exact_public_rollback": exact_rollback,
        "authority_after_fault": verdict_after_fault,
        "retry_is_tuple": isinstance(retry, tuple),
        "retry_error": retry_error,
    }


def lower_partial_mutation_is_staged() -> dict:
    world = prepared_world("wave121-stage-lower-partial-mutation")
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    before_st = deepcopy(st)
    before_priv = deepcopy(priv)
    before_ts = deepcopy(ts)
    before_bs = deepcopy(bs)
    original = w.w114.prepare

    def partial(*args, **kwargs):
        staged_st = args[1]
        staged_priv = args[2]
        staged_transition_store = args[6]
        staged_binding_store = args[9]
        staged_st["wave121-verifier-only-partial"] = {"staged": True}
        first_private = next(iter(staged_priv))
        staged_priv[first_private]["wave121-verifier-only"] = True
        staged_transition_store["wave121-verifier-only-transition"] = {"staged": True}
        staged_binding_store["wave121-verifier-only-binding"] = {"staged": True}
        raise RuntimeError("injected-wave121-lower-partial-mutation")

    error = None
    w.w114.prepare = partial
    try:
        w.prepare_rotation(
            rt, st, priv, boot, services, rs, ts, cs, certificate_domain, bs,
            keyring, w.new_outcome_authority_domain(),
            hashlib.sha256(b"wave121-partial-lower-target").hexdigest(),
        )
    except Exception as exc:
        error = f"{type(exc).__name__}:{exc}"
    finally:
        w.w114.prepare = original

    verdict = w.authority(
        rt, st, boot, services, rs, ts, cs, certificate_domain, bs, keyring
    )
    return {
        "error": error,
        "public_st_unchanged": st == before_st,
        "public_priv_unchanged": priv == before_priv,
        "public_transition_store_unchanged": ts == before_ts,
        "public_binding_store_unchanged": bs == before_bs,
        "authority_after": verdict,
    }


def clean_rotation() -> dict:
    world = prepared_world("wave121-clean-rotation")
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    before_ts = set(ts)
    before_bs = set(bs)
    before_c = set(st.get("C", {}))
    before_u = set(st.get("U", {}))
    before_l = set(st.get("L", {}))
    before_roots = set(st[w.w117.OUTCOME_ROOT_STORE])
    before_envelopes = set(st[w.w117.ENVELOPE_STORE])
    successor = w.new_outcome_authority_domain()
    prepared = w.prepare_rotation(
        rt, st, priv, boot, services, rs, ts, cs, certificate_domain, bs, keyring, successor
    )
    cp, use, link, transition_sha, binding, root, envelope = prepared
    exact_published = (
        set(ts) - before_ts == {transition_sha}
        and set(bs) - before_bs == {binding["binding_sha"]}
        and set(st["C"]) - before_c == {cp["checkpoint_sha"]}
        and set(st["U"]) - before_u == {use["use_sha"]}
        and set(st["L"]) - before_l == {link["authority_sha"]}
        and set(st[w.w117.OUTCOME_ROOT_STORE]) - before_roots == {root["root_sha"]}
        and set(st[w.w117.ENVELOPE_STORE]) - before_envelopes == {envelope["envelope_sha"]}
        and bs[binding["binding_sha"]] == binding
        and binding["user_app_state_sha"] == envelope["envelope_sha"]
    )
    commit_result = w.commit_rotation(
        rt, st, boot, rs, ts, link["authority_sha"], transition_sha, bs, keyring, successor
    )
    state = w.commit_status_state(st, boot, rt, rs, bs, ts, keyring)
    cert, verdict = t119.settle(world)
    return {
        "prepare_tuple_len": len(prepared),
        "exact_published": exact_published,
        "commit_result": commit_result,
        "status": state,
        "certificate": cert,
        "authority": verdict,
        "current_is_successor": keyring.current.authority_id == successor.authority_id,
    }


def run() -> dict:
    report = {
        "wave": 121,
        "scope": "staged prepare + same-process exact rollback across caller-visible prepare publication",
        "source": w.SRC,
        "controls": [],
        "failed": 0,
    }

    old = reproduce_wave120_pr45()
    check(
        report,
        "unchanged Wave120 verifier-45 post-lower/pre-sync transition-loss reproduced",
        old["first_error"] == "RuntimeError:injected-wave120-fault-after-lower-prepare-before-sync"
        and old["new_root_count"] == 1 and old["new_envelope_count"] == 1
        and old["new_transition_count"] == 0 and old["new_binding_count"] >= 1
        and old["binding_references_new_envelope"] and not old["authority"].startswith("AUTHORITATIVE")
        and old["retry_is_none"] and old["retry_error"] is not None,
        old,
    )

    staged_partial = lower_partial_mutation_is_staged()
    check(
        report,
        "arbitrary lower partial writes stay staged when lower prepare raises",
        staged_partial["error"] == "RuntimeError:injected-wave121-lower-partial-mutation"
        and staged_partial["public_st_unchanged"] and staged_partial["public_priv_unchanged"]
        and staged_partial["public_transition_store_unchanged"]
        and staged_partial["public_binding_store_unchanged"]
        and staged_partial["authority_after"].startswith("AUTHORITATIVE"),
        staged_partial,
    )

    faults = [
        ("fault_after_lower_prepare_before_publish", "RuntimeError:injected-wave121-fault-after-lower-prepare-before-publish"),
        ("fault_after_transition_publish", "RuntimeError:injected-wave121-fault-after-transition-publish"),
        ("fault_after_retained_state_publish", "RuntimeError:injected-wave121-fault-after-retained-state-publish"),
        ("fault_after_binding_publish", "RuntimeError:injected-wave121-fault-after-binding-publish"),
        ("fault_after_private_state_publish", "RuntimeError:injected-wave121-fault-after-private-state-publish"),
    ]
    for flag, expected in faults:
        result = publication_fault(flag, expected)
        check(
            report,
            f"{flag} restores exact public prepare state and exact retry succeeds",
            result["error"] == expected and result["exact_public_rollback"]
            and result["authority_after_fault"].startswith("AUTHORITATIVE")
            and result["retry_is_tuple"] and result["retry_error"] is None,
            result,
        )

    clean = clean_rotation()
    check(
        report,
        "clean Wave121 publishes exact prepared identities then commits/settles",
        clean["prepare_tuple_len"] == 7 and clean["exact_published"]
        and clean["commit_result"] == "COMMITTED_ROTATED"
        and clean["status"].get("status") == w.HISTORY_VALID
        and clean["authority"].startswith("AUTHORITATIVE")
        and clean["current_is_successor"],
        clean,
    )

    report["passed"] = len(report["controls"]) - report["failed"]
    report["truth_boundary"] = {
        "stale_authority_accepted_by_verifier45_reproduction": False,
        "same_process_exception_rollback_claim": True,
        "os_process_or_power_loss_atomicity_claim": False,
        "multiwrite_hard_kill_counterexample_removed": False,
        "whole_domain_rollback_counterexample_removed": False,
        "synthetic_scaling_run": False,
        "real_axm_or_monolith_performance_run": False,
        "timing_or_energy_claim": False,
        "retained_incremental_dormant_compute_win_claim": False,
        "note": "Wave121 closes the reproduced caller-visible post-lower/pre-sync exception hole by staging exact evidence. A hard kill during multi-write publication is intentionally left for the next gate.",
    }
    if report["failed"]:
        raise AssertionError(json.dumps(report, sort_keys=True))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out")
    args = parser.parse_args()
    report = run()
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")


if __name__ == "__main__":
    main()
