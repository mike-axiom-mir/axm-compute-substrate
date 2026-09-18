#!/usr/bin/env python3
"""Wave 120 reference-safe rotation-prepare rollback self-test."""
from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy

import AXM_FLOWING_COMPUTE_ROTATION_PREPARE_TRANSACTION as w
import AXM_FLOWING_COMPUTE_CRASH_RECOVERABLE_ROTATION_LINEAGE as w119
import AXM_FLOWING_COMPUTE_CRASH_RECOVERABLE_ROTATION_LINEAGE_SELFTEST as t119


def check(report: dict, name: str, ok: bool, detail=None) -> None:
    report["controls"].append({"name": name, "ok": bool(ok), "detail": detail})
    if not ok:
        report["failed"] += 1


def compact_bytes(store: dict, keys: set[str]) -> int:
    return sum(
        len(json.dumps(store[key], sort_keys=True, separators=(",", ":")).encode("utf-8"))
        for key in keys
    )


def prepared_world(label: str):
    world = t119.new_world()
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring, label
    )
    verdict = w.authority(rt, st, boot, services, rs, ts, cs, certificate_domain, bs, keyring)
    if not verdict.startswith("AUTHORITATIVE"):
        raise RuntimeError(f"prepared-world-not-authoritative:{verdict}")
    return world


def failure_growth(module, attempts: int, label: str, *, prevalidated_predecessor: bool = False) -> dict:
    """Measure retained candidate growth across failed public prepares.

    The exact verifier reproduction and the bounded 16-attempt Wave 120 repair control execute the
    full predecessor authority path each time. The 1/10/100/1000 structural scaling controls may use
    a predecessor that was validated once before the loop; prepare_rotation still executes its real
    root/envelope creation, anchor/lineage checks, lower-prepare boundary, and cleanup. This keeps the
    scaling probe about retained object/byte growth rather than repeatedly benchmarking authority.
    """
    world = prepared_world(label)
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    roots = st[w.w117.OUTCOME_ROOT_STORE]
    envelopes = st[w.w117.ENVELOPE_STORE]
    base_roots = set(roots)
    base_envelopes = set(envelopes)
    base_transitions = set(ts)
    base_bindings = set(bs)
    original_prepare = module.w114.prepare
    original_authority = module.authority

    baseline_verdict = original_authority(
        rt, st, boot, services, rs, ts, cs, certificate_domain, bs, keyring
    )
    if not baseline_verdict.startswith("AUTHORITATIVE"):
        raise RuntimeError(f"failure-growth-baseline-not-authoritative:{baseline_verdict}")

    def fail(*args, **kwargs):
        raise RuntimeError("injected-wave120-lower-prepare-failure")

    errors = []
    module.w114.prepare = fail
    if prevalidated_predecessor:
        module.authority = lambda *args, **kwargs: baseline_verdict
    try:
        for i in range(attempts):
            successor = module.new_outcome_authority_domain()
            target = hashlib.sha256(f"{label}-{i}".encode()).hexdigest()
            try:
                module.prepare_rotation(
                    rt, st, priv, boot, services, rs, ts, cs, certificate_domain, bs,
                    keyring, successor, target,
                )
            except Exception as exc:
                errors.append(f"{type(exc).__name__}:{exc}")
            else:
                errors.append("NO_ERROR")
    finally:
        module.w114.prepare = original_prepare
        module.authority = original_authority

    orphan_roots = set(roots) - base_roots
    orphan_envelopes = set(envelopes) - base_envelopes
    return {
        "attempts": attempts,
        "scaling_mode": (
            "synthetic-prevalidated-predecessor-structural-storage-only"
            if prevalidated_predecessor else "full-public-authority-path"
        ),
        "errors_exact": all(x == "RuntimeError:injected-wave120-lower-prepare-failure" for x in errors),
        "root_growth": len(orphan_roots),
        "envelope_growth": len(orphan_envelopes),
        "orphan_compact_json_bytes": compact_bytes(roots, orphan_roots) + compact_bytes(envelopes, orphan_envelopes),
        "transition_growth": len(set(ts) - base_transitions),
        "binding_growth": len(set(bs) - base_bindings),
        "authority_after": original_authority(
            rt, st, boot, services, rs, ts, cs, certificate_domain, bs, keyring
        ),
    }


def fault_boundary(flag: str) -> dict:
    world = prepared_world(f"wave120-{flag}")
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    roots = st[w.w117.OUTCOME_ROOT_STORE]
    envelopes = st[w.w117.ENVELOPE_STORE]
    before = (len(roots), len(envelopes), len(ts), len(bs))
    successor = w.new_outcome_authority_domain()
    kwargs = {flag: True}
    error = None
    try:
        w.prepare_rotation(
            rt, st, priv, boot, services, rs, ts, cs, certificate_domain, bs,
            keyring, successor, hashlib.sha256(flag.encode()).hexdigest(), **kwargs,
        )
    except Exception as exc:
        error = f"{type(exc).__name__}:{exc}"
    after = (len(roots), len(envelopes), len(ts), len(bs))
    return {"flag": flag, "error": error, "before": before, "after": after}


def same_candidate_retry() -> dict:
    world = prepared_world("wave120-same-candidate")
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    roots = st[w.w117.OUTCOME_ROOT_STORE]
    envelopes = st[w.w117.ENVELOPE_STORE]
    baseline = (len(roots), len(envelopes), len(ts), len(bs))
    successor = w.new_outcome_authority_domain()
    target = hashlib.sha256(b"wave120-same-candidate-target").hexdigest()
    original = w.w114.prepare

    def fail(*args, **kwargs):
        raise RuntimeError("injected-wave120-same-candidate-first-failure")

    first_error = None
    w.w114.prepare = fail
    try:
        w.prepare_rotation(
            rt, st, priv, boot, services, rs, ts, cs, certificate_domain, bs,
            keyring, successor, target,
        )
    except Exception as exc:
        first_error = f"{type(exc).__name__}:{exc}"
    finally:
        w.w114.prepare = original
    after_failure = (len(roots), len(envelopes), len(ts), len(bs))
    retry = w.prepare_rotation(
        rt, st, priv, boot, services, rs, ts, cs, certificate_domain, bs,
        keyring, successor, target,
    )
    after_retry = (len(roots), len(envelopes), len(ts), len(bs))
    return {
        "first_error": first_error,
        "baseline": baseline,
        "after_failure": after_failure,
        "retry_is_tuple": isinstance(retry, tuple),
        "after_retry": after_retry,
    }


def preexisting_exact_candidate_survives_failure() -> dict:
    world = prepared_world("wave120-preexisting-candidate")
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    _binding, current_envelope, current_root, _status, _lineage = w.w118._current_anchor(
        rt, st, boot, rs, bs, keyring
    )
    successor = w.new_outcome_authority_domain()
    target = hashlib.sha256(b"wave120-preexisting-target").hexdigest()
    root = w.w118._seal_rotated_root(current_root, keyring.current, successor)
    root_sha, root_created = w._put_exact_rotated_root(st, root)
    envelope = w.w117._seal_envelope(target, root_sha)
    envelope_sha, envelope_created = w._put_exact_envelope(st, envelope)
    before_root = deepcopy(st[w.w117.OUTCOME_ROOT_STORE][root_sha])
    before_envelope = deepcopy(st[w.w117.ENVELOPE_STORE][envelope_sha])
    original = w.w114.prepare

    def fail(*args, **kwargs):
        raise RuntimeError("injected-wave120-preexisting-candidate-failure")

    error = None
    w.w114.prepare = fail
    try:
        w.prepare_rotation(
            rt, st, priv, boot, services, rs, ts, cs, certificate_domain, bs,
            keyring, successor, target,
        )
    except Exception as exc:
        error = f"{type(exc).__name__}:{exc}"
    finally:
        w.w114.prepare = original
    return {
        "setup_created_root": root_created,
        "setup_created_envelope": envelope_created,
        "error": error,
        "root_preserved": st[w.w117.OUTCOME_ROOT_STORE].get(root_sha) == before_root,
        "envelope_preserved": st[w.w117.ENVELOPE_STORE].get(envelope_sha) == before_envelope,
        "authority_after": w.authority(
            rt, st, boot, services, rs, ts, cs, certificate_domain, bs, keyring
        ),
    }


def partial_lower_reference_preserves_candidate() -> dict:
    world = prepared_world("wave120-partial-lower-ref")
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    roots = st[w.w117.OUTCOME_ROOT_STORE]
    envelopes = st[w.w117.ENVELOPE_STORE]
    base_root_keys = set(roots)
    base_envelope_keys = set(envelopes)
    original = w.w114.prepare
    observed = {}

    def partial(*args, **kwargs):
        lower_binding_store = args[9]
        envelope_sha = args[10]
        observed["envelope_sha"] = envelope_sha
        lower_binding_store["wave120-partial-binding-reference"] = {
            "user_app_state_sha": envelope_sha,
            "verifier_only_partial": True,
        }
        raise RuntimeError("injected-wave120-partial-lower-write")

    error = None
    w.w114.prepare = partial
    try:
        w.prepare_rotation(
            rt, st, priv, boot, services, rs, ts, cs, certificate_domain, bs,
            keyring, w.new_outcome_authority_domain(),
            hashlib.sha256(b"wave120-partial-ref-target").hexdigest(),
        )
    except Exception as exc:
        error = f"{type(exc).__name__}:{exc}"
    finally:
        w.w114.prepare = original

    new_roots = set(roots) - base_root_keys
    new_envelopes = set(envelopes) - base_envelope_keys
    return {
        "error": error,
        "new_root_count": len(new_roots),
        "new_envelope_count": len(new_envelopes),
        "binding_reference_present": "wave120-partial-binding-reference" in bs,
        "referenced_envelope_preserved": observed.get("envelope_sha") in envelopes,
    }


def lower_success_then_fault_preserves_referenced_evidence() -> dict:
    world = prepared_world("wave120-post-lower-fault")
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    base_roots = set(st[w.w117.OUTCOME_ROOT_STORE])
    base_envelopes = set(st[w.w117.ENVELOPE_STORE])
    error = None
    try:
        w.prepare_rotation(
            rt, st, priv, boot, services, rs, ts, cs, certificate_domain, bs,
            keyring, w.new_outcome_authority_domain(),
            hashlib.sha256(b"wave120-post-lower-target").hexdigest(),
            fault_after_lower_prepare_before_sync=True,
        )
    except Exception as exc:
        error = f"{type(exc).__name__}:{exc}"
    new_roots = set(st[w.w117.OUTCOME_ROOT_STORE]) - base_roots
    new_envelopes = set(st[w.w117.ENVELOPE_STORE]) - base_envelopes
    referenced = any(
        isinstance(body, dict) and body.get("user_app_state_sha") in new_envelopes
        for body in bs.values()
    )
    return {
        "error": error,
        "new_root_count": len(new_roots),
        "new_envelope_count": len(new_envelopes),
        "lower_binding_references_new_envelope": referenced,
    }


def clean_rotation_still_commits() -> dict:
    world = prepared_world("wave120-clean-rotation")
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world
    successor = w.new_outcome_authority_domain()
    prepared = w.prepare_rotation(
        rt, st, priv, boot, services, rs, ts, cs, certificate_domain, bs, keyring, successor
    )
    link_sha = prepared[2]["authority_sha"]
    transition_sha = prepared[3]
    result = w.commit_rotation(rt, st, boot, rs, ts, link_sha, transition_sha, bs, keyring, successor)
    state = w.commit_status_state(st, boot, rt, rs, bs, ts, keyring)
    cert, verdict = t119.settle(world)
    return {
        "prepare_tuple_len": len(prepared),
        "commit_result": result,
        "status": state,
        "certificate": cert,
        "authority": verdict,
        "current_is_successor": keyring.current.authority_id == successor.authority_id,
    }


def run() -> dict:
    report = {
        "wave": 120,
        "scope": "same-process exception rollback + retained-state storage hygiene only",
        "source": w.SRC,
        "controls": [],
        "failed": 0,
        "modeled_failure_scaling": [],
    }

    old = failure_growth(w119, 16, "wave120-reproduce-wave119")
    check(report, "unchanged Wave119 verifier-44 orphan growth reproduced",
          old["errors_exact"] and old["root_growth"] == 16 and old["envelope_growth"] == 16
          and old["transition_growth"] == 0 and old["binding_growth"] == 0, old)

    fixed = failure_growth(w, 16, "wave120-fixed-wave119")
    check(report, "Wave120 failed fresh rotations leave zero unreferenced root/envelope growth",
          fixed["errors_exact"] and fixed["root_growth"] == 0 and fixed["envelope_growth"] == 0
          and fixed["orphan_compact_json_bytes"] == 0 and fixed["transition_growth"] == 0
          and fixed["binding_growth"] == 0 and fixed["authority_after"].startswith("AUTHORITATIVE"), fixed)

    for attempts in (1, 10, 100, 1000):
        scaled = failure_growth(
            w, attempts, f"wave120-modeled-storage-scale-{attempts}", prevalidated_predecessor=True
        )
        report["modeled_failure_scaling"].append(scaled)
        check(report, f"synthetic modeled {attempts} failed unique rotations add zero orphan bytes",
              scaled["scaling_mode"] == "synthetic-prevalidated-predecessor-structural-storage-only"
              and scaled["errors_exact"] and scaled["root_growth"] == 0
              and scaled["envelope_growth"] == 0 and scaled["orphan_compact_json_bytes"] == 0,
              scaled)

    root_fault = fault_boundary("fault_after_root_write")
    check(report, "fault immediately after candidate root write rolls back exact new root",
          root_fault["error"] == "RuntimeError:injected-wave120-fault-after-root-write"
          and root_fault["after"] == root_fault["before"], root_fault)

    envelope_fault = fault_boundary("fault_after_envelope_write")
    check(report, "fault immediately after candidate envelope write rolls back exact new envelope and root",
          envelope_fault["error"] == "RuntimeError:injected-wave120-fault-after-envelope-write"
          and envelope_fault["after"] == envelope_fault["before"], envelope_fault)

    retry = same_candidate_retry()
    check(report, "same exact candidate can retry after unreferenced failed prepare",
          retry["first_error"] is not None and retry["after_failure"] == retry["baseline"]
          and retry["retry_is_tuple"], retry)

    preexisting = preexisting_exact_candidate_survives_failure()
    check(report, "pre-existing exact candidate objects are never deleted by failed retry cleanup",
          preexisting["error"] is not None and preexisting["root_preserved"]
          and preexisting["envelope_preserved"] and preexisting["authority_after"].startswith("AUTHORITATIVE"),
          preexisting)

    partial = partial_lower_reference_preserves_candidate()
    check(report, "partial lower binding reference prevents unsafe candidate deletion",
          partial["error"] == "RuntimeError:injected-wave120-partial-lower-write"
          and partial["new_root_count"] == 1 and partial["new_envelope_count"] == 1
          and partial["binding_reference_present"] and partial["referenced_envelope_preserved"], partial)

    post_lower = lower_success_then_fault_preserves_referenced_evidence()
    check(report, "fault after successful lower prepare preserves now-referenced root/envelope evidence",
          post_lower["error"] == "RuntimeError:injected-wave120-fault-after-lower-prepare-before-sync"
          and post_lower["new_root_count"] == 1 and post_lower["new_envelope_count"] == 1
          and post_lower["lower_binding_references_new_envelope"], post_lower)

    clean = clean_rotation_still_commits()
    check(report, "clean Wave120 rotation prepare/commit still settles VALID and authoritative",
          clean["commit_result"] == "COMMITTED_ROTATED" and clean["status"].get("status") == w.HISTORY_VALID
          and clean["authority"].startswith("AUTHORITATIVE") and clean["current_is_successor"], clean)

    report["passed"] = len(report["controls"]) - report["failed"]
    report["truth_boundary"] = {
        "modeled_failure_scaling_is_timing_benchmark": False,
        "modeled_failure_scaling_uses_prevalidated_predecessor": True,
        "energy_claim": False,
        "retained_incremental_dormant_compute_win_claim": False,
        "process_or_power_loss_atomicity_claim": False,
        "whole_domain_rollback_counterexample_removed": False,
        "note": "1/10/100/1000 scaling is explicitly synthetic structural object/byte accounting with a once-prevalidated predecessor; exact verifier reproduction and bounded repair controls keep the full public authority path",
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
