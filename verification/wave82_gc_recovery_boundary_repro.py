#!/usr/bin/env python3
"""Independent adversarial reproducer for Flowing Compute Wave 82.

Run from repository root:
    python verification/wave82_gc_recovery_boundary_repro.py

This imports the exact reusable Wave 82 model from tools/ and does not modify it.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import AXM_FLOWING_COMPUTE_RETENTION_GC_MODEL as w82  # noqa: E402


def recompute(obj: dict, hash_field: str) -> dict:
    out = copy.deepcopy(obj)
    body = dict(out)
    body.pop(hash_field, None)
    out[hash_field] = w82.dig(body)
    return out


def main() -> None:
    g0 = w82.wave81()
    drop = w82.make_drop(
        g0,
        w82.C1,
        "test-only explicit rollback-root retirement for crash-safe GC probe",
    )
    g1 = w82.evolve(
        g0,
        {w82.C3},
        {w82.C1: drop},
        "Wave82 test generation: explicitly drop old Wave80/Wave79 rollback root",
    )
    assert w82.rid(g1) == "f9cb087d701268b4f7eb660161776f37d46d312f0e46c1fbc883c46a452d3eb5"
    assert w82.reachable(g1) == {w82.B}

    # This is the same minimal sweep object used by the Wave 82 model self-test.
    sweep = {
        "retention_sha256": w82.rid(g1),
        "retention_sequence": w82.seq(g1),
    }

    expected_candidate = w82.recovery_action([w82.A], sweep, g1)

    # Counterexample 1: B is reachable under the retained C3 checkpoint, yet the
    # recovery API authorizes PURGE because it checks only retention id+sequence.
    reachable_receipt_purge = w82.recovery_action([w82.B], sweep, g1)

    # Counterexample 2: validate_ret() checks that a drop-receipt key exists for
    # each removed root, but does not resolve/validate the referenced receipt.
    forged_drop_ref = copy.deepcopy(g1)
    forged_drop_ref["drop_receipts"] = {w82.C1: "0" * 64}
    forged_drop_ref = recompute(forged_drop_ref, "retention_sha256")
    forged_drop_ref_accepted = True
    forged_drop_ref_error = None
    try:
        w82.validate_ret(forged_drop_ref, g0)
    except Exception as exc:  # pragma: no cover - should not happen on Wave82
        forged_drop_ref_accepted = False
        forged_drop_ref_error = str(exc)

    # Counterexample 3: validate_mark() does not verify schema, does not require
    # reachable_receipts == reachable(current), and does not require candidates
    # == inventory - reachable(current).  The mark can be rehashed and accepted.
    inventory = {w82.A, w82.B}
    underconstrained_mark = {
        "schema": "not-the-wave82-mark-schema",
        "retention_sha256": w82.rid(g1),
        "retention_sequence": w82.seq(g1),
        "receipt_inventory_sha256": w82.dig(sorted(inventory)),
        "reachable_receipts": [],
        "candidates": [],
        "truth": {"verifier_counterexample": True},
    }
    underconstrained_mark = recompute(underconstrained_mark, "mark_sha256")
    underconstrained_mark_accepted = True
    underconstrained_mark_error = None
    try:
        w82.validate_mark(underconstrained_mark, g1, inventory)
    except Exception as exc:  # pragma: no cover - should not happen on Wave82
        underconstrained_mark_accepted = False
        underconstrained_mark_error = str(exc)

    result = {
        "schema": "axm.flowing-compute-wave82-adversarial-verification/v0.1",
        "builder_head_tested": "d3bbccd51cebb250221e501cd64db130d483479f",
        "wave82_g1_retention_sha256": w82.rid(g1),
        "reachable_receipts_under_g1": sorted(w82.reachable(g1)),
        "baseline_unreachable_A_recovery": expected_candidate,
        "counterexamples": {
            "reachable_B_is_authorized_for_purge_by_recovery_action": {
                "status": "FAIL_BOUNDARY_CONFIRMED" if reachable_receipt_purge["action"] == "PURGE" else "NOT_REPRODUCED",
                "receipt_sha256": w82.B,
                "receipt_is_reachable_under_g1": w82.B in w82.reachable(g1),
                "recovery_result": reachable_receipt_purge,
            },
            "retention_validator_accepts_unresolved_forged_drop_receipt_reference": {
                "status": "FAIL_BOUNDARY_CONFIRMED" if forged_drop_ref_accepted else "NOT_REPRODUCED",
                "forged_reference": "0" * 64,
                "accepted": forged_drop_ref_accepted,
                "error": forged_drop_ref_error,
                "rehashed_retention_sha256": forged_drop_ref["retention_sha256"],
            },
            "mark_validator_accepts_wrong_schema_and_false_incomplete_derived_sets": {
                "status": "FAIL_BOUNDARY_CONFIRMED" if underconstrained_mark_accepted else "NOT_REPRODUCED",
                "accepted": underconstrained_mark_accepted,
                "error": underconstrained_mark_error,
                "actual_reachable": sorted(w82.reachable(g1)),
                "claimed_reachable": underconstrained_mark["reachable_receipts"],
                "expected_candidates": sorted(inventory - w82.reachable(g1)),
                "claimed_candidates": underconstrained_mark["candidates"],
                "claimed_schema": underconstrained_mark["schema"],
            },
        },
        "truth_boundary": {
            "this_tests_the_published_reusable_wave82_model": True,
            "this_does_not_claim_sha256_is_broken": True,
            "this_does_not_reread_or_reaudit_the_11255808_byte_monolith_artifact": True,
            "the_one_off_filesystem_probe_may_have_external_harness_checks_not_present_in_the_reusable_model": True,
            "no_auto_merge_or_canon_promotion": True,
        },
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
