#!/usr/bin/env python3
"""Independent verifier for AXM Flowing Compute Wave 122.

This lane does not modify builder evidence or promote CANON. It probes two things:
1. the claimed single-same-process-BaseException rollback boundary at a *mid-write* cut
   (after the destination dict is cleared, before replacement data is installed), including
   KeyboardInterrupt, SystemExit, and GeneratorExit;
2. the explicitly unproved repeated-termination-during-rollback boundary, to preserve the
   exact failure shape rather than silently extrapolating Wave 122 beyond its claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy

import AXM_FLOWING_COMPUTE_TERMINATION_EXCEPTION_ROLLBACK as w
import AXM_FLOWING_COMPUTE_ROTATION_PREPARE_PUBLICATION_ATOMICITY_SELFTEST as t121


def prepared_world(label: str):
    return t121.prepared_world(label)


def safe_authority(world) -> dict:
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    try:
        value = w.authority(rt, st, boot, services, rs, ts, cs, certificate_domain, bs, keyring)
        return {"value": value, "error": None}
    except BaseException as exc:
        return {"value": None, "error": f"{type(exc).__name__}:{exc}"}


def midwrite_case(exception_type, call_index: int) -> dict:
    label = exception_type.__name__.lower()
    world = prepared_world(f"verifier-wave122-midwrite-{label}-{call_index}")
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    before_st = deepcopy(st)
    before_priv = deepcopy(priv)
    before_ts = deepcopy(ts)
    before_bs = deepcopy(bs)
    successor = w.new_outcome_authority_domain()
    target = hashlib.sha256(f"verifier-wave122-midwrite-{label}-{call_index}".encode()).hexdigest()

    original = w._publish_replace
    calls = 0

    def cutting_replace(dst: dict, src: dict) -> None:
        nonlocal calls
        calls += 1
        if calls == call_index:
            # Stronger cut than the builder suite: publication has mutated the destination
            # (cleared it), but the replacement body has not been installed yet.
            dict.clear(dst)
            raise exception_type(f"verifier-midwrite-{label}-{call_index}")
        original(dst, src)

    caught = None
    w._publish_replace = cutting_replace
    try:
        w.prepare_rotation(
            rt, st, priv, boot, services, rs, ts, cs, certificate_domain, bs,
            keyring, successor, target,
        )
    except BaseException as exc:
        caught = f"{type(exc).__name__}:{exc}"
    finally:
        w._publish_replace = original

    exact_rollback = (
        st == before_st and priv == before_priv and ts == before_ts and bs == before_bs
    )
    after_authority = safe_authority(world)

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
        "publication_call_index": call_index,
        "caught": caught,
        "publish_calls": calls,
        "exact_public_value_rollback": exact_rollback,
        "authority_after": after_authority,
        "retry_succeeded": isinstance(retry, tuple),
        "retry_error": retry_error,
    }


def repeated_termination_during_rollback() -> dict:
    world = prepared_world("verifier-wave122-repeated-termination-during-rollback")
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    before_st = deepcopy(st)
    before_priv = deepcopy(priv)
    before_ts = deepcopy(ts)
    before_bs = deepcopy(bs)
    successor = w.new_outcome_authority_domain()
    target = hashlib.sha256(b"verifier-wave122-repeated-termination-target").hexdigest()

    original_publish = w._publish_replace
    original_restore = w._restore_exact
    publish_calls = 0
    restore_calls = 0

    def first_termination(dst: dict, src: dict) -> None:
        nonlocal publish_calls
        original_publish(dst, src)
        publish_calls += 1
        if publish_calls == 4:
            raise KeyboardInterrupt("verifier-first-termination-after-fourth-publication")

    def second_termination(dst: dict, src: dict) -> None:
        nonlocal restore_calls
        original_restore(dst, src)
        restore_calls += 1
        if restore_calls == 1:
            raise SystemExit("verifier-second-termination-during-rollback")

    caught = None
    w._publish_replace = first_termination
    w._restore_exact = second_termination
    try:
        w.prepare_rotation(
            rt, st, priv, boot, services, rs, ts, cs, certificate_domain, bs,
            keyring, successor, target,
        )
    except BaseException as exc:
        caught = f"{type(exc).__name__}:{exc}"
    finally:
        w._publish_replace = original_publish
        w._restore_exact = original_restore

    status = None
    status_error = None
    try:
        status = w.commit_status_state(st, boot, rt, rs, bs, ts, keyring)
    except BaseException as exc:
        status_error = f"{type(exc).__name__}:{exc}"

    after_authority = safe_authority(world)
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
        "caught": caught,
        "publication_calls_before_first_termination": publish_calls,
        "restore_calls_before_second_termination": restore_calls,
        "transition_store_restored": ts == before_ts,
        "retained_state_restored": st == before_st,
        "binding_store_restored": bs == before_bs,
        "private_state_restored": priv == before_priv,
        "commit_status": status,
        "commit_status_error": status_error,
        "authority_after": after_authority,
        "retry_succeeded": isinstance(retry, tuple),
        "retry_error": retry_error,
    }


def run() -> dict:
    cases = []
    contract_failures = []
    for exception_type in (KeyboardInterrupt, SystemExit, GeneratorExit):
        for call_index in range(1, 5):
            result = midwrite_case(exception_type, call_index)
            cases.append(result)
            expected_caught = (
                f"{exception_type.__name__}:verifier-midwrite-"
                f"{exception_type.__name__.lower()}-{call_index}"
            )
            ok = (
                result["caught"] == expected_caught
                and result["exact_public_value_rollback"]
                and result["authority_after"]["error"] is None
                and isinstance(result["authority_after"]["value"], str)
                and result["authority_after"]["value"].startswith("AUTHORITATIVE")
                and result["retry_succeeded"]
                and result["retry_error"] is None
            )
            if not ok:
                contract_failures.append({"case": result, "expected_caught": expected_caught})

    repeated = repeated_termination_during_rollback()
    report = {
        "schema": "axm.flowing-compute.verifier-wave122-midwrite/v1",
        "builder_head": "41f1719b48aace2c5db5ae68cadb9ccbce14970d",
        "builder_tested_source": "5ebe63488494c6767637b82407be8675d1fcca52",
        "wave122_tool_blob": "78df9135f97e568e64ef37b83d743d6475a8adee",
        "single_exception_midwrite_cases": cases,
        "single_exception_contract_failures": contract_failures,
        "single_exception_contract_survived": not contract_failures,
        "repeated_termination_boundary": repeated,
        "truth_boundary": {
            "tests_same_process_python_only": True,
            "midwrite_destination_clear_before_replacement_tested": True,
            "keyboardinterrupt_tested": True,
            "systemexit_tested": True,
            "generatorexit_tested": True,
            "repeated_termination_during_rollback_tested": True,
            "hard_kill_or_power_loss_tested": False,
            "separate_process_or_store_tested": False,
            "performance_or_energy_claim": False,
            "retained_incremental_dormant_compute_claim": False,
            "auto_merge_or_canon": False,
        },
    }
    if contract_failures:
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
