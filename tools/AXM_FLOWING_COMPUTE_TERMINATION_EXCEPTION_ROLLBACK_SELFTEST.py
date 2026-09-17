#!/usr/bin/env python3
"""Wave 122 same-process termination-exception rollback self-test."""
from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy

import AXM_FLOWING_COMPUTE_TERMINATION_EXCEPTION_ROLLBACK as w
import AXM_FLOWING_COMPUTE_ROTATION_PREPARE_PUBLICATION_ATOMICITY as w121
import AXM_FLOWING_COMPUTE_ROTATION_PREPARE_PUBLICATION_ATOMICITY_SELFTEST as t121
import AXM_FLOWING_COMPUTE_CRASH_RECOVERABLE_ROTATION_LINEAGE_SELFTEST as t119


def check(report: dict, name: str, ok: bool, detail=None) -> None:
    report["controls"].append({"name": name, "ok": bool(ok), "detail": detail})
    if not ok:
        report["failed"] += 1


def prepared_world(label: str):
    return t121.prepared_world(label)


def reproduce_wave121_pr46() -> dict:
    world = prepared_world("wave122-reproduce-wave121-pr46")
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    before_st = deepcopy(st)
    before_priv = deepcopy(priv)
    before_ts = deepcopy(ts)
    before_bs = deepcopy(bs)
    successor = w121.new_outcome_authority_domain()
    target = hashlib.sha256(b"wave122-reproduce-wave121-pr46-target").hexdigest()

    original = w121._replace_exact
    calls = 0

    def interrupting_replace(dst: dict, src: dict) -> None:
        nonlocal calls
        original(dst, src)
        calls += 1
        if calls == 1:
            raise KeyboardInterrupt("wave122-reproduce-pr46")

    caught = None
    w121._replace_exact = interrupting_replace
    try:
        w121.prepare_rotation(
            rt, st, priv, boot, services, rs, ts, cs, certificate_domain, bs,
            keyring, successor, target,
        )
    except BaseException as exc:
        caught = f"{type(exc).__name__}:{exc}"
    finally:
        w121._replace_exact = original

    status = w121.commit_status_state(st, boot, rt, rs, bs, ts, keyring)
    verdict = w121.authority(
        rt, st, boot, services, rs, ts, cs, certificate_domain, bs, keyring
    )
    retry = None
    retry_error = None
    try:
        retry = w121.prepare_rotation(
            rt, st, priv, boot, services, rs, ts, cs, certificate_domain, bs,
            keyring, successor, target,
        )
    except BaseException as exc:
        retry_error = f"{type(exc).__name__}:{exc}"

    return {
        "caught": caught,
        "replace_calls": calls,
        "transition_store_changed": ts != before_ts,
        "retained_state_unchanged": st == before_st,
        "binding_store_unchanged": bs == before_bs,
        "private_state_unchanged": priv == before_priv,
        "status": status,
        "authority": verdict,
        "retry_is_none": retry is None,
        "retry_error": retry_error,
    }


def lower_staged_termination() -> dict:
    world = prepared_world("wave122-lower-staged-termination")
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    before_st = deepcopy(st)
    before_priv = deepcopy(priv)
    before_ts = deepcopy(ts)
    before_bs = deepcopy(bs)
    original = w.w114.prepare

    def interrupted(*args, **kwargs):
        staged_st = args[1]
        staged_priv = args[2]
        staged_transition_store = args[6]
        staged_binding_store = args[9]
        staged_st["wave122-staged-only"] = {"x": 1}
        first_private = next(iter(staged_priv))
        staged_priv[first_private]["wave122-staged-only"] = True
        staged_transition_store["wave122-staged-only"] = {"x": 1}
        staged_binding_store["wave122-staged-only"] = {"x": 1}
        raise KeyboardInterrupt("wave122-lower-staged-interrupt")

    caught = None
    w.w114.prepare = interrupted
    try:
        w.prepare_rotation(
            rt, st, priv, boot, services, rs, ts, cs, certificate_domain, bs,
            keyring, w.new_outcome_authority_domain(),
            hashlib.sha256(b"wave122-lower-staged-target").hexdigest(),
        )
    except BaseException as exc:
        caught = f"{type(exc).__name__}:{exc}"
    finally:
        w.w114.prepare = original

    verdict = w.authority(
        rt, st, boot, services, rs, ts, cs, certificate_domain, bs, keyring
    )
    return {
        "caught": caught,
        "public_st_unchanged": st == before_st,
        "public_priv_unchanged": priv == before_priv,
        "public_transition_store_unchanged": ts == before_ts,
        "public_binding_store_unchanged": bs == before_bs,
        "authority_after": verdict,
    }


def publication_termination(exception_type, call_index: int) -> dict:
    label = exception_type.__name__.lower()
    world = prepared_world(f"wave122-{label}-call-{call_index}")
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    before_st = deepcopy(st)
    before_priv = deepcopy(priv)
    before_ts = deepcopy(ts)
    before_bs = deepcopy(bs)
    successor = w.new_outcome_authority_domain()
    target = hashlib.sha256(f"wave122-{label}-{call_index}".encode()).hexdigest()

    original = w._publish_replace
    calls = 0

    def terminating_replace(dst: dict, src: dict) -> None:
        nonlocal calls
        original(dst, src)
        calls += 1
        if calls == call_index:
            raise exception_type(f"wave122-{label}-after-publication-{call_index}")

    caught = None
    w._publish_replace = terminating_replace
    try:
        w.prepare_rotation(
            rt, st, priv, boot, services, rs, ts, cs, certificate_domain, bs,
            keyring, successor, target,
        )
    except BaseException as exc:
        caught = f"{type(exc).__name__}:{exc}"
    finally:
        w._publish_replace = original

    exact_rollback = st == before_st and priv == before_priv and ts == before_ts and bs == before_bs
    verdict = w.authority(
        rt, st, boot, services, rs, ts, cs, certificate_domain, bs, keyring
    )
    retry = None
    retry_error = None
    try:
        retry = w.prepare_rotation(
            rt, st, priv, boot, services, rs, ts, cs, certificate_domain, bs,
            keyring, successor, target,
        )
    except BaseException as exc:
        retry_error = f"{type(exc).__name__}:{exc}"

    return {
        "exception_type": exception_type.__name__,
        "call_index": call_index,
        "caught": caught,
        "publish_calls_before_fault": calls,
        "exact_public_rollback": exact_rollback,
        "authority_after_fault": verdict,
        "retry_is_tuple": isinstance(retry, tuple),
        "retry_error": retry_error,
    }


def ordinary_exception_regression() -> dict:
    world = prepared_world("wave122-runtimeerror-regression")
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    before_st = deepcopy(st)
    before_priv = deepcopy(priv)
    before_ts = deepcopy(ts)
    before_bs = deepcopy(bs)
    successor = w.new_outcome_authority_domain()
    target = hashlib.sha256(b"wave122-runtimeerror-regression").hexdigest()
    error = None
    try:
        w.prepare_rotation(
            rt, st, priv, boot, services, rs, ts, cs, certificate_domain, bs,
            keyring, successor, target, fault_after_binding_publish=True,
        )
    except Exception as exc:
        error = f"{type(exc).__name__}:{exc}"
    verdict = w.authority(
        rt, st, boot, services, rs, ts, cs, certificate_domain, bs, keyring
    )
    return {
        "error": error,
        "exact_public_rollback": st == before_st and priv == before_priv and ts == before_ts and bs == before_bs,
        "authority_after": verdict,
    }


def clean_rotation() -> dict:
    world = prepared_world("wave122-clean-rotation")
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    successor = w.new_outcome_authority_domain()
    prepared = w.prepare_rotation(
        rt, st, priv, boot, services, rs, ts, cs, certificate_domain, bs, keyring, successor
    )
    cp, use, link, transition_sha, binding, root, envelope = prepared
    commit_result = w.commit_rotation(
        rt, st, boot, rs, ts, link["authority_sha"], transition_sha, bs, keyring, successor
    )
    state = w.commit_status_state(st, boot, rt, rs, bs, ts, keyring)
    cert, verdict = t119.settle(world)
    return {
        "prepare_tuple_len": len(prepared),
        "commit_result": commit_result,
        "status": state,
        "certificate": cert,
        "authority": verdict,
        "current_is_successor": keyring.current.authority_id == successor.authority_id,
    }


def run() -> dict:
    report = {
        "wave": 122,
        "scope": "single same-process BaseException rollback after caller-visible prepare publication begins",
        "source": w.SRC,
        "controls": [],
        "failed": 0,
    }

    old = reproduce_wave121_pr46()
    check(
        report,
        "unchanged Wave121 verifier-46 KeyboardInterrupt bypass reproduced",
        old["caught"] == "KeyboardInterrupt:wave122-reproduce-pr46"
        and old["replace_calls"] == 1 and old["transition_store_changed"]
        and old["retained_state_unchanged"] and old["binding_store_unchanged"]
        and old["private_state_unchanged"] and not old["authority"].startswith("AUTHORITATIVE")
        and old["retry_is_none"] and old["retry_error"] is not None,
        old,
    )

    lower = lower_staged_termination()
    check(
        report,
        "termination during lower staged prepare never reaches public stores",
        lower["caught"] == "KeyboardInterrupt:wave122-lower-staged-interrupt"
        and lower["public_st_unchanged"] and lower["public_priv_unchanged"]
        and lower["public_transition_store_unchanged"] and lower["public_binding_store_unchanged"]
        and lower["authority_after"].startswith("AUTHORITATIVE"),
        lower,
    )

    for exception_type in (KeyboardInterrupt, SystemExit):
        for call_index in range(1, 5):
            result = publication_termination(exception_type, call_index)
            expected = f"{exception_type.__name__}:wave122-{exception_type.__name__.lower()}-after-publication-{call_index}"
            check(
                report,
                f"{exception_type.__name__} after publication write {call_index} rolls back exactly and exact retry succeeds",
                result["caught"] == expected
                and result["publish_calls_before_fault"] == call_index
                and result["exact_public_rollback"]
                and result["authority_after_fault"].startswith("AUTHORITATIVE")
                and result["retry_is_tuple"] and result["retry_error"] is None,
                result,
            )

    ordinary = ordinary_exception_regression()
    check(
        report,
        "ordinary RuntimeError publication rollback remains exact",
        ordinary["error"] == "RuntimeError:injected-wave122-fault-after-binding-publish"
        and ordinary["exact_public_rollback"]
        and ordinary["authority_after"].startswith("AUTHORITATIVE"),
        ordinary,
    )

    clean = clean_rotation()
    check(
        report,
        "clean Wave122 prepare still commits, settles, and activates exact successor",
        clean["prepare_tuple_len"] == 7
        and clean["commit_result"] == "COMMITTED_ROTATED"
        and clean["status"].get("status") == w.HISTORY_VALID
        and clean["authority"].startswith("AUTHORITATIVE")
        and clean["current_is_successor"],
        clean,
    )

    report["passed"] = len(report["controls"]) - report["failed"]
    report["truth_boundary"] = {
        "verifier46_stale_authority_accepted": False,
        "single_same_process_baseexception_rollback_claim": True,
        "keyboardinterrupt_tested": True,
        "systemexit_tested": True,
        "repeated_termination_during_rollback_tested": False,
        "hard_process_kill_or_power_loss_tested": False,
        "os_process_or_durable_store_separation_claim": False,
        "whole_domain_rollback_counterexample_removed": False,
        "synthetic_scaling_run": False,
        "real_axm_or_monolith_performance_run": False,
        "timing_or_energy_claim": False,
        "retained_incremental_dormant_compute_win_claim": False,
        "note": "Wave122 repairs verifier PR #46 for one same-process termination exception. Hard kill during multi-write publication remains the next gate and cannot be repaired by Python exception handling.",
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
