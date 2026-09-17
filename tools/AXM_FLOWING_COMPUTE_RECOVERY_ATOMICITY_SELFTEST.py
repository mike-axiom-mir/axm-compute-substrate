#!/usr/bin/env python3
"""Wave 113 exact-API positive/negative self-test.

Reproduces verifier PR #37 against unchanged Wave 112, then requires Wave 113 to reject the same
semantic-prefix damage before mutation, refuse false ALREADY_COMMITTED, roll back injected recovery
write failures, and still recover the documented clean one-row crash state.
"""
from __future__ import annotations

import argparse
import json
from copy import deepcopy

import AXM_FLOWING_COMPUTE_RECOVERY_ATOMICITY as w
import AXM_FLOWING_COMPUTE_RECOVERABLE_TRANSITION_PROVENANCE as w112
import AXM_FLOWING_COMPUTE_TRANSITION_PROVENANCE_LEDGER as w111
import AXM_FLOWING_COMPUTE_TRANSITION_EVIDENCE_GUARD as w110
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w104

q = w.q
g = w.g


def check(report: dict, name: str, ok: bool, detail=None):
    report["controls"].append({"name": name, "ok": bool(ok), "detail": detail})
    if not ok:
        report["failed"] += 1


def new_world():
    st, priv, boot, rt, services, tokens, rs = q.fixture()
    ts = {}
    cs = g.new_certificate_store()
    domain = w104.new_certificate_witness_domain()
    bs = {}
    w.adopt_genesis(rt, st, boot, services, rs, ts, cs, domain, bs)
    return st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs


def lower_commit_after_one_epoch():
    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world()
    _cp1, _use1, link1, tr1, _body1, _cert1, _certbody1 = w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs,
        "wave113-e1",
    )
    cp2, use2, link2, tr2, body2 = w.prepare(
        rt, st, priv, boot, services, rs, ts, cs, domain, bs,
        target_user_app_state_sha="73" * 32,
    )
    lower = w110.commit(rt, st, boot, rs, ts, link2["authority_sha"], tr2, bs)
    return (st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs,
            link1, tr1, cp2, use2, link2, tr2, body2, lower)


def damage_first_provenance(st: dict) -> tuple[str, str]:
    rows = w111._provenance_rows(st)
    assert rows is not None and len(rows) == 1
    original_sha, original = rows[0]
    damaged = deepcopy(original)
    damaged["target_state_sha"] = "0" * 64
    damaged_sha = w111._sha(damaged)
    pstore = st[w.PROVENANCE_STORE]
    del pstore[original_sha]
    pstore[damaged_sha] = damaged
    return original_sha, damaged_sha


def reproduce_wave112_verifier37() -> dict:
    (st, _priv, boot, rt, services, _tokens, rs, ts, cs, domain, bs,
     _link1, _tr1, _cp2, _use2, link2, tr2, _body2, lower) = lower_commit_after_one_epoch()
    damage_first_provenance(st)
    pstore = st[w.PROVENANCE_STORE]
    before = deepcopy(pstore)
    first_error = None
    first_result = None
    try:
        first_result = w112.commit(rt, st, boot, rs, ts, link2["authority_sha"], tr2, bs)
    except Exception as exc:
        first_error = f"{type(exc).__name__}:{exc}"
    mutated = pstore != before
    second_error = None
    second_result = None
    try:
        second_result = w112.commit(rt, st, boot, rs, ts, link2["authority_sha"], tr2, bs)
    except Exception as exc:
        second_error = f"{type(exc).__name__}:{exc}"
    state = w112.commit_status_state(st, boot, rt, rs, bs, ts)
    authority = w112.authority(rt, st, boot, services, rs, ts, cs, domain, bs)
    return {
        "lower_commit": lower,
        "first_result": first_result,
        "first_error": first_error,
        "mutated_after_failed_retry": mutated,
        "second_result": second_result,
        "second_error": second_error,
        "status": state.get("status"),
        "authority": authority,
        "reproduced": (
            lower == "COMMITTED"
            and first_result is None
            and isinstance(first_error, str)
            and "recovery did not settle exact committed history" in first_error
            and mutated
            and second_result == "ALREADY_COMMITTED"
            and state.get("status") == w112.HISTORY_INCOMPLETE
            and authority == w112.HOLD_INCOMPLETE
        ),
    }


def damaged_prefix_rejected_without_mutation() -> dict:
    (st, _priv, boot, rt, services, _tokens, rs, ts, cs, domain, bs,
     _link1, _tr1, _cp2, _use2, link2, tr2, _body2, lower) = lower_commit_after_one_epoch()
    original_sha, damaged_sha = damage_first_provenance(st)
    pstore = st[w.PROVENANCE_STORE]
    before = deepcopy(pstore)
    error = None
    result = None
    try:
        result = w.commit(rt, st, boot, rs, ts, link2["authority_sha"], tr2, bs)
    except Exception as exc:
        error = f"{type(exc).__name__}:{exc}"
    after = deepcopy(pstore)
    state = w.commit_status_state(st, boot, rt, rs, bs, ts)
    authority = w.authority(rt, st, boot, services, rs, ts, cs, domain, bs)
    return {
        "lower_commit": lower,
        "original_epoch1_provenance_sha": original_sha,
        "damaged_epoch1_provenance_sha": damaged_sha,
        "result": result,
        "error": error,
        "store_unchanged": before == after,
        "status": state.get("status"),
        "authority": authority,
    }


def false_already_committed_rejected() -> dict:
    (st, _priv, boot, rt, services, _tokens, rs, ts, cs, domain, bs,
     _link1, _tr1, _cp2, _use2, link2, tr2, _body2, _lower) = lower_commit_after_one_epoch()
    damage_first_provenance(st)
    marker = w111._append_provenance(
        st, boot, rs, ts, link2["authority_sha"], tr2
    )
    pstore = st[w.PROVENANCE_STORE]
    before = deepcopy(pstore)
    error = None
    result = None
    try:
        result = w.commit(rt, st, boot, rs, ts, link2["authority_sha"], tr2, bs)
    except Exception as exc:
        error = f"{type(exc).__name__}:{exc}"
    state = w.commit_status_state(st, boot, rt, rs, bs, ts)
    authority = w.authority(rt, st, boot, services, rs, ts, cs, domain, bs)
    return {
        "manual_target_append": marker,
        "result": result,
        "error": error,
        "store_unchanged": pstore == before,
        "status": state.get("status"),
        "authority": authority,
    }


def clean_recovery() -> dict:
    (st, _priv, boot, rt, services, tokens, rs, ts, cs, domain, bs,
     _link1, _tr1, _cp2, _use2, link2, tr2, _body2, lower) = lower_commit_after_one_epoch()
    before = w.commit_status_state(st, boot, rt, rs, bs, ts)
    recovered = w.commit(rt, st, boot, rs, ts, link2["authority_sha"], tr2, bs)
    after = w.commit_status_state(st, boot, rt, rs, bs, ts)
    repeated = w.commit(rt, st, boot, rs, ts, link2["authority_sha"], tr2, bs)
    for slot in q.REMOTE_IDS:
        w.publish(rt, st, boot, services, tokens, rs, slot)
    w.certify_and_sync(rt, st, boot, services, rs, cs, domain)
    final_authority = w.authority(rt, st, boot, services, rs, ts, cs, domain, bs)
    return {
        "lower_commit": lower,
        "before": before.get("status"),
        "recovered": recovered,
        "after": after.get("status"),
        "repeated": repeated,
        "final_authority": final_authority,
    }


def injected_after_append_rollback() -> dict:
    (st, _priv, boot, rt, _services, _tokens, rs, ts, _cs, _domain, bs,
     _link1, _tr1, _cp2, _use2, link2, tr2, _body2, _lower) = lower_commit_after_one_epoch()
    pstore = st[w.PROVENANCE_STORE]
    before = deepcopy(pstore)
    error = None
    try:
        w._recover_missing_trailing_provenance(
            st, boot, rt, rs, ts, bs, link2["authority_sha"], tr2,
            fault_after_append=True,
        )
    except Exception as exc:
        error = f"{type(exc).__name__}:{exc}"
    after_fault = deepcopy(pstore)
    held = w.commit_status_state(st, boot, rt, rs, bs, ts)
    recovered = w.commit(rt, st, boot, rs, ts, link2["authority_sha"], tr2, bs)
    final = w.commit_status_state(st, boot, rt, rs, bs, ts)
    return {
        "error": error,
        "store_rolled_back_exactly": before == after_fault,
        "status_after_fault": held.get("status"),
        "later_exact_recovery": recovered,
        "final_status": final.get("status"),
    }


def injected_partial_append_exception_rollback() -> dict:
    (st, _priv, boot, rt, _services, _tokens, rs, ts, _cs, _domain, bs,
     _link1, _tr1, _cp2, _use2, link2, tr2, _body2, _lower) = lower_commit_after_one_epoch()
    pstore = st[w.PROVENANCE_STORE]
    before = deepcopy(pstore)
    original = w111._append_provenance

    def partial_then_raise(*args, **kwargs):
        pstore["f" * 64] = {"injected_partial_write": True}
        raise RuntimeError("injected-wave113-partial-append-failure")

    error = None
    try:
        w111._append_provenance = partial_then_raise
        w.commit(rt, st, boot, rs, ts, link2["authority_sha"], tr2, bs)
    except Exception as exc:
        error = f"{type(exc).__name__}:{exc}"
    finally:
        w111._append_provenance = original

    after_fault = deepcopy(pstore)
    held = w.commit_status_state(st, boot, rt, rs, bs, ts)
    recovered = w.commit(rt, st, boot, rs, ts, link2["authority_sha"], tr2, bs)
    final = w.commit_status_state(st, boot, rt, rs, bs, ts)
    return {
        "error": error,
        "store_rolled_back_exactly": before == after_fault,
        "status_after_fault": held.get("status"),
        "later_exact_recovery": recovered,
        "final_status": final.get("status"),
    }


def mismatched_transition_no_mutation() -> dict:
    (st, _priv, boot, rt, _services, _tokens, rs, ts, _cs, _domain, bs,
     _link1, _tr1, _cp2, _use2, link2, tr2, _body2, _lower) = lower_commit_after_one_epoch()
    pstore = st[w.PROVENANCE_STORE]
    before = deepcopy(pstore)
    wrong = "e" * 64 if tr2 != "e" * 64 else "d" * 64
    error = None
    try:
        w.commit(rt, st, boot, rs, ts, link2["authority_sha"], wrong, bs)
    except Exception as exc:
        error = f"{type(exc).__name__}:{exc}"
    return {
        "error": error,
        "store_unchanged": pstore == before,
        "status": w.commit_status_state(st, boot, rt, rs, bs, ts).get("status"),
    }


def whole_domain_rollback_counterexample() -> dict:
    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world()
    w.advance_all(st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs, "wave113-rb-e1")
    snap_st = deepcopy(st)
    snap_rt = deepcopy(rt)
    snap_services = deepcopy(services)
    snap_ts = deepcopy(ts)
    snap_cs = deepcopy(cs)
    snap_bs = deepcopy(bs)
    snap_disks = domain.disk_snapshots()
    w.advance_all(st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs, "wave113-rb-e2")
    domain.restore_disks(snap_disks)
    authority = w.authority(
        snap_rt, snap_st, boot, snap_services, rs, snap_ts, snap_cs, domain, snap_bs
    )
    return {
        "authority": authority,
        "boundary": "whole modeled failure domain rollback still erases every newer fact",
    }


def run() -> dict:
    report = {
        "schema": "axm.flowing-compute.wave113.recovery-atomicity-selftest/v1",
        "truth_boundary": {
            "same_modeled_python_failure_domain": True,
            "in_memory_transactional_rollback_only": True,
            "power_or_process_crash_atomicity_claim": False,
            "independent_durable_commit_witness_claim": False,
            "wall_clock_performance_claim": False,
            "energy_claim": False,
            "retained_incremental_dormant_compute_claim": False,
            "os_process_device_network_provider_independence_claim": False,
        },
        "controls": [],
        "failed": 0,
    }

    old = reproduce_wave112_verifier37()
    report["verifier37_wave112_reproduction"] = old
    check(report, "wave112-verifier37-failure-reproduced", old["reproduced"], old)

    damaged = damaged_prefix_rejected_without_mutation()
    report["damaged_prefix_preflight"] = damaged
    check(report, "damaged-prefix-rejected-before-recovery-write", damaged["result"] is None and isinstance(damaged["error"], str) and "recovery-prefix-target-state-mismatch" in damaged["error"], damaged)
    check(report, "damaged-prefix-failed-retry-does-not-mutate-provenance", damaged["store_unchanged"], damaged)
    check(report, "damaged-prefix-remains-held", damaged["status"] == w.HISTORY_INCOMPLETE and damaged["authority"] == w.HOLD_INCOMPLETE, damaged)

    false_already = false_already_committed_rejected()
    report["false_already_committed_guard"] = false_already
    check(report, "already-committed-requires-full-valid-history", false_already["result"] is None and isinstance(false_already["error"], str) and "already-committed-provenance-present-but-history-not-valid" in false_already["error"], false_already)
    check(report, "invalid-already-committed-check-is-read-only", false_already["store_unchanged"], false_already)
    check(report, "invalid-complete-provenance-still-holds", false_already["status"] == w.HISTORY_INCOMPLETE and false_already["authority"] == w.HOLD_INCOMPLETE, false_already)

    clean = clean_recovery()
    report["clean_recovery"] = clean
    check(report, "clean-lower-commit-crash-starts-held", clean["lower_commit"] == "COMMITTED" and clean["before"] == w.HISTORY_INCOMPLETE, clean)
    check(report, "clean-exact-recovery-succeeds", clean["recovered"] == "COMMITTED_RECOVERED_PROVENANCE_ATOMIC" and clean["after"] == w.HISTORY_VALID, clean)
    check(report, "clean-retry-idempotent-only-after-valid", clean["repeated"] == "ALREADY_COMMITTED", clean)
    check(report, "clean-recovered-world-can-be-authoritative", clean["final_authority"].startswith("AUTHORITATIVE"), clean)

    injected = injected_after_append_rollback()
    report["fault_after_append"] = injected
    check(report, "fault-after-append-is-surfaced", isinstance(injected["error"], str) and "injected-wave113-fault-after-provenance-append" in injected["error"], injected)
    check(report, "fault-after-append-restores-exact-store", injected["store_rolled_back_exactly"], injected)
    check(report, "fault-after-append-leaves-history-held-not-falsely-closed", injected["status_after_fault"] == w.HISTORY_INCOMPLETE, injected)
    check(report, "retry-after-rolled-back-fault-can-recover", injected["later_exact_recovery"] == "COMMITTED_RECOVERED_PROVENANCE_ATOMIC" and injected["final_status"] == w.HISTORY_VALID, injected)

    partial = injected_partial_append_exception_rollback()
    report["fault_during_append"] = partial
    check(report, "partial-append-exception-is-surfaced", isinstance(partial["error"], str) and "injected-wave113-partial-append-failure" in partial["error"], partial)
    check(report, "partial-append-exception-restores-exact-store", partial["store_rolled_back_exactly"], partial)
    check(report, "partial-append-fault-leaves-history-held", partial["status_after_fault"] == w.HISTORY_INCOMPLETE, partial)
    check(report, "retry-after-partial-append-fault-can-recover", partial["later_exact_recovery"] == "COMMITTED_RECOVERED_PROVENANCE_ATOMIC" and partial["final_status"] == w.HISTORY_VALID, partial)

    mismatch = mismatched_transition_no_mutation()
    report["mismatched_transition"] = mismatch
    check(report, "mismatched-transition-rejected", isinstance(mismatch["error"], str) and "recovery-transition-sha-does-not-match-lower-committed-evidence" in mismatch["error"], mismatch)
    check(report, "mismatched-transition-retry-does-not-mutate", mismatch["store_unchanged"] and mismatch["status"] == w.HISTORY_INCOMPLETE, mismatch)

    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world()
    first = w.advance_all(st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs, "wave113-normal-e1")
    second = w.advance_all(st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs, "wave113-normal-e2")
    normal_state = w.commit_status_state(st, boot, rt, rs, bs, ts)
    check(report, "normal-two-epoch-history-valid", normal_state.get("status") == w.HISTORY_VALID, normal_state)
    check(report, "old-exact-retry-idempotent-while-full-history-valid", w.commit(rt, st, boot, rs, ts, first[2]["authority_sha"], first[3], bs) == "ALREADY_COMMITTED")
    check(report, "latest-exact-retry-idempotent-while-full-history-valid", w.commit(rt, st, boot, rs, ts, second[2]["authority_sha"], second[3], bs) == "ALREADY_COMMITTED")

    rollback = whole_domain_rollback_counterexample()
    report["preserved_counterexample"] = rollback
    check(report, "whole-domain-rollback-counterexample-still-visible", rollback["authority"].startswith("AUTHORITATIVE"), rollback)

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
        with open(args.json_out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
