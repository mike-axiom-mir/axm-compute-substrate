#!/usr/bin/env python3
"""Independent adversarial reproducer for Wave 112 recovery atomicity.

This imports the unchanged Wave-112 implementation and exercises a damaged-but-structurally-valid
existing provenance prefix before the documented one-row crash recovery. The verifier expects a
fail-closed recovery attempt to leave retained evidence unchanged.
"""
from __future__ import annotations

import json
from copy import deepcopy

import AXM_FLOWING_COMPUTE_RECOVERABLE_TRANSITION_PROVENANCE as w
import AXM_FLOWING_COMPUTE_TRANSITION_PROVENANCE_LEDGER as w111
import AXM_FLOWING_COMPUTE_TRANSITION_EVIDENCE_GUARD as w110
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w104

q = w.q
g = w.g

BUILDER_HEAD = "a1cf4ccb535142a63a328c4a0dadc86984deaa3b"
EXACT_TESTED_SOURCE = "1be9303bba0712869d40444f5cf1b0e878948ab7"
VERDICT = "FAIL_FAILED_RECOVERY_MUTATES_LEDGER_AND_THEN_MISREPORTS_ALREADY_COMMITTED"


def new_world():
    st, priv, boot, rt, services, tokens, rs = q.fixture()
    ts = {}
    cs = g.new_certificate_store()
    domain = w104.new_certificate_witness_domain()
    bs = {}
    w.adopt_genesis(rt, st, boot, services, rs, ts, cs, domain, bs)
    return st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs


def run() -> dict:
    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world()

    # Epoch 1 is fully accepted, including the genuine Wave-111 provenance row.
    _cp1, _use1, link1, tr1, _body1, _cert1, _certbody1 = w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs,
        "verifier-wave112-e1",
    )

    # Epoch 2 reaches the lower Wave-110 durable commit but crashes before Wave-111/112 provenance.
    cp2, use2, link2, tr2, body2 = w.prepare(
        rt, st, priv, boot, services, rs, ts, cs, domain, bs,
        target_user_app_state_sha="62" * 32,
    )
    lower = w110.commit(rt, st, boot, rs, ts, link2["authority_sha"], tr2, bs)
    if lower != "COMMITTED":
        raise AssertionError(f"expected lower commit, got {lower}")

    rows_before_damage = w111._provenance_rows(st)
    assert rows_before_damage is not None and len(rows_before_damage) == 1
    original_epoch1_sha, original_epoch1 = rows_before_damage[0]

    # Damage only an already-retained provenance semantic field, then reseal under the normal
    # content-addressed key. The row stays structurally valid: same seq, epoch, authority and chain.
    # Wave 112's public status is already HOLD/INCOMPLETE before any recovery retry.
    damaged_epoch1 = deepcopy(original_epoch1)
    damaged_epoch1["target_state_sha"] = "0" * 64
    damaged_epoch1_sha = w111._sha(damaged_epoch1)
    pstore = st[w.PROVENANCE_STORE]
    del pstore[original_epoch1_sha]
    pstore[damaged_epoch1_sha] = damaged_epoch1

    structural_rows = w111._provenance_rows(st)
    assert structural_rows is not None and len(structural_rows) == 1
    before_retry = w.commit_status_state(st, boot, rt, rs, bs, ts)
    authority_before_retry = w.authority(
        rt, st, boot, services, rs, ts, cs, domain, bs
    )
    if before_retry.get("status") != w.HISTORY_INCOMPLETE:
        raise AssertionError(f"damaged prefix should already HOLD: {before_retry}")

    provenance_keys_before_retry = sorted(pstore)
    retry_exception = None
    retry_result = None
    try:
        retry_result = w.commit(
            rt, st, boot, rs, ts,
            link2["authority_sha"], tr2, bs,
        )
    except Exception as exc:  # expected: final post-append validation rejects damaged prefix
        retry_exception = f"{type(exc).__name__}:{exc}"

    provenance_keys_after_failed_retry = sorted(pstore)
    rows_after_failed_retry = w111._provenance_rows(st)
    after_failed_retry = w.commit_status_state(st, boot, rt, rs, bs, ts)
    authority_after_failed_retry = w.authority(
        rt, st, boot, services, rs, ts, cs, domain, bs
    )

    # A second exact retry now sees the row that the failed first retry appended and reports
    # ALREADY_COMMITTED even though full Wave-112 history remains INCOMPLETE and authority HOLDs.
    second_retry_exception = None
    second_retry_result = None
    try:
        second_retry_result = w.commit(
            rt, st, boot, rs, ts,
            link2["authority_sha"], tr2, bs,
        )
    except Exception as exc:
        second_retry_exception = f"{type(exc).__name__}:{exc}"
    after_second_retry = w.commit_status_state(st, boot, rt, rs, bs, ts)
    authority_after_second_retry = w.authority(
        rt, st, boot, services, rs, ts, cs, domain, bs
    )

    mutated = provenance_keys_after_failed_retry != provenance_keys_before_retry
    appended_epoch2 = (
        rows_after_failed_retry is not None
        and len(rows_after_failed_retry) == 2
        and rows_after_failed_retry[-1][1].get("authority_sha") == link2["authority_sha"]
        and rows_after_failed_retry[-1][1].get("transition_sha") == tr2
    )
    still_held = (
        after_failed_retry.get("status") == w.HISTORY_INCOMPLETE
        and authority_after_failed_retry == w.HOLD_INCOMPLETE
    )
    misreported = (
        second_retry_result == "ALREADY_COMMITTED"
        and after_second_retry.get("status") == w.HISTORY_INCOMPLETE
        and authority_after_second_retry == w.HOLD_INCOMPLETE
    )

    reproduced = (
        retry_result is None
        and isinstance(retry_exception, str)
        and "recovery did not settle exact committed history" in retry_exception
        and mutated
        and appended_epoch2
        and still_held
        and misreported
    )
    if not reproduced:
        raise AssertionError(
            json.dumps({
                "retry_result": retry_result,
                "retry_exception": retry_exception,
                "mutated": mutated,
                "appended_epoch2": appended_epoch2,
                "still_held": still_held,
                "second_retry_result": second_retry_result,
                "second_retry_exception": second_retry_exception,
                "misreported": misreported,
                "after_failed_retry": after_failed_retry,
                "after_second_retry": after_second_retry,
            }, sort_keys=True)
        )

    return {
        "schema": "axm.flowing-compute.wave112.independent-adversarial-verifier/v1",
        "builder_head": BUILDER_HEAD,
        "exact_wave112_tested_source": EXACT_TESTED_SOURCE,
        "verdict": VERDICT,
        "severity_boundary": "recovery/evidence-integrity+liveness; no stale authority acceptance demonstrated",
        "lower_epoch2_commit": lower,
        "epoch1_authority_sha": link1["authority_sha"],
        "epoch1_transition_sha": tr1,
        "epoch2_authority_sha": link2["authority_sha"],
        "epoch2_transition_sha": tr2,
        "damaged_existing_provenance": {
            "original_sha": original_epoch1_sha,
            "replacement_sha": damaged_epoch1_sha,
            "changed_field": "target_state_sha",
            "structural_chain_still_valid": True,
        },
        "before_retry": before_retry,
        "authority_before_retry": authority_before_retry,
        "failed_exact_retry": {
            "result": retry_result,
            "exception": retry_exception,
            "provenance_keys_before": provenance_keys_before_retry,
            "provenance_keys_after": provenance_keys_after_failed_retry,
            "mutated_store": mutated,
            "appended_epoch2_provenance": appended_epoch2,
        },
        "after_failed_retry": after_failed_retry,
        "authority_after_failed_retry": authority_after_failed_retry,
        "second_exact_retry": {
            "result": second_retry_result,
            "exception": second_retry_exception,
            "history_status": after_second_retry.get("status"),
            "authority": authority_after_second_retry,
            "misreports_already_committed_while_history_incomplete": misreported,
        },
        "reproduced": reproduced,
        "truth_boundary": {
            "builder_wave112_direct_crash_recovery_case_challenged": True,
            "stale_authority_acceptance_demonstrated": False,
            "wall_clock_claim": False,
            "energy_claim": False,
            "retained_incremental_dormant_compute_claim": False,
            "same_modeled_python_failure_domain": True,
        },
        "next_gate": "validate the complete existing provenance prefix before any recovery write, stage recovery append transactionally, and return ALREADY_COMMITTED only after full Wave-112 status is VALID",
    }


def main() -> int:
    print(json.dumps(run(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
