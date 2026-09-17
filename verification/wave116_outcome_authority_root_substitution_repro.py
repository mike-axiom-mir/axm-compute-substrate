#!/usr/bin/env python3
"""Independent adversarial reproducer for Wave 116 outcome-authority root substitution.

This does not forge the original HMAC credential. It replaces only the Wave-116 outcome binding,
raw rejection row, and authenticated outcome row with a fresh internally valid credential/history,
while leaving the lower runtime/authority/certificate/transition substrate intact.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import AXM_FLOWING_COMPUTE_AUTHENTICATED_REJECTION_OUTCOME as w
import AXM_FLOWING_COMPUTE_AUTHENTICATED_REJECTION_OUTCOME_SELFTEST as s
import AXM_FLOWING_COMPUTE_PREVALIDATED_COMMIT_DECISION as w115


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out")
    args = parser.parse_args()

    world = s.new_world()
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
        original_outcome_domain,
    ) = world

    link, genuine_sha, bad_sha = s.prepare_bad_sibling(world, "c1")
    first = w.commit(
        rt,
        st,
        boot,
        rs,
        ts,
        link["authority_sha"],
        bad_sha,
        bs,
        original_outcome_domain,
    )
    repeated_actual = w115._prevalidate_lower_commit(
        rt,
        st,
        boot,
        rs,
        ts,
        link["authority_sha"],
        bad_sha,
        bs,
    )

    raw_before = w115._rejection_rows(st, ts) or []
    outcomes_before = w._outcome_rows(st, original_outcome_domain) or []
    assert len(raw_before) == 1 and len(outcomes_before) == 1
    _raw_sha, raw_body = raw_before[0]

    substitute = w.new_outcome_authority_domain()
    substitute_before = w.commit_status_state(st, boot, rt, rs, bs, ts, substitute)

    contradictory_result = "TRANSITION_GENERATION_HOLD"
    if contradictory_result == repeated_actual:
        contradictory_result = "TRANSITION_CHECKPOINT_HOLD"

    replacement_raw = w115._seal_rejection(
        {
            "schema": w115.REJECTION_SCHEMA,
            "seq": 1,
            "predecessor_rejection_sha": None,
            "authority_sha": raw_body["authority_sha"],
            "transition_sha": raw_body["transition_sha"],
            "checkpoint_sha": raw_body["checkpoint_sha"],
            "lower_result": contradictory_result,
            "rejection_sha": "",
        }
    )
    st[w115.REJECTION_STORE] = {
        replacement_raw["rejection_sha"]: replacement_raw,
    }

    st[w.OUTCOME_BINDING] = w._seal_binding(substitute.authority_id)
    replacement_outcome = w._seal_outcome(
        {
            "schema": w.OUTCOME_SCHEMA,
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
        },
        substitute,
    )
    st[w.OUTCOME_STORE] = {
        replacement_outcome["outcome_sha"]: replacement_outcome,
    }

    old_domain_after = w.commit_status_state(
        st, boot, rt, rs, bs, ts, original_outcome_domain
    )
    substituted_status_before_good = w.commit_status_state(
        st, boot, rt, rs, bs, ts, substitute
    )
    substituted_authority_before_good = w.authority(
        rt,
        st,
        boot,
        services,
        rs,
        ts,
        cs,
        certificate_domain,
        bs,
        substitute,
    )

    good = w.commit(
        rt,
        st,
        boot,
        rs,
        ts,
        link["authority_sha"],
        genuine_sha,
        bs,
        substitute,
    )
    for slot in w.q.REMOTE_IDS:
        published = w.publish(rt, st, boot, services, tokens, rs, slot)
        if published not in ("APPENDED", "ALREADY_CURRENT"):
            raise RuntimeError(f"unexpected publish result {slot}: {published}")
    cert_result, _cert_body = w.certify_and_sync(
        rt,
        st,
        boot,
        services,
        rs,
        cs,
        certificate_domain,
    )
    final_status = w.commit_status_state(st, boot, rt, rs, bs, ts, substitute)
    final_authority = w.authority(
        rt,
        st,
        boot,
        services,
        rs,
        ts,
        cs,
        certificate_domain,
        bs,
        substitute,
    )

    raw_after = w115._rejection_rows(st, ts) or []
    outcomes_after = w._outcome_rows(st, substitute) or []

    reproduced = (
        first == "TRANSITION_DELTA_HOLD"
        and repeated_actual == "TRANSITION_DELTA_HOLD"
        and contradictory_result != repeated_actual
        and substitute_before.get("status") == w.HISTORY_INCOMPLETE
        and old_domain_after.get("status") == w.HISTORY_INCOMPLETE
        and substituted_status_before_good.get("status") in (w.HISTORY_NONE, w.HISTORY_VALID)
        and substituted_authority_before_good.startswith("AUTHORITATIVE")
        and good == "COMMITTED"
        and final_status.get("status") == w.HISTORY_VALID
        and final_status.get("outcome_authority_id") == substitute.authority_id
        and final_authority.startswith("AUTHORITATIVE")
        and len(raw_after) == 1
        and raw_after[0][1]["lower_result"] == contradictory_result
        and len(outcomes_after) == 1
        and outcomes_after[0][1]["lower_result"] == contradictory_result
        and outcomes_after[0][1]["outcome_authority_id"] == substitute.authority_id
    )

    report = {
        "schema": "axm.flowing-compute.verifier.wave116.outcome-authority-root-substitution/v1",
        "verdict": (
            "FAIL_OUTCOME_AUTHORITY_ROOT_SUBSTITUTION_ACCEPTS_RESEALED_CONTRADICTORY_HISTORY"
            if reproduced
            else "NOT_REPRODUCED"
        ),
        "reproduced": reproduced,
        "builder_source": {
            "head_observed": "fc9d6b0f88d9acbfb1ff5b5fcbb2a4a50de5224b",
            "exact_tested_source": "b47136f228679ef72130d5e043e56743d00257f8",
            "tool_blob": "9b3459d84766cea56e293d4cdf573d8457c51b8f",
        },
        "actual_semantic_result": repeated_actual,
        "replacement_claimed_result": contradictory_result,
        "initial_reject_result": first,
        "original_outcome_authority_id": original_outcome_domain.authority_id,
        "substitute_outcome_authority_id": substitute.authority_id,
        "substitute_before_binding_rewrite": substitute_before,
        "old_domain_after_binding_rewrite": old_domain_after,
        "substituted_status_before_good_commit": substituted_status_before_good,
        "substituted_authority_before_good_commit": substituted_authority_before_good,
        "genuine_sibling_commit": good,
        "certificate_result": cert_result,
        "final_status": final_status,
        "final_authority": final_authority,
        "raw_rows_after": len(raw_after),
        "outcome_rows_after": len(outcomes_after),
        "boundary": {
            "forged_original_hmac": False,
            "hash_collision": False,
            "lower_runtime_rewritten_for_root_substitution": False,
            "certificate_domain_replaced": False,
            "certificate_store_replaced": False,
            "transition_store_replaced": False,
            "wave116_binding_replaced": True,
            "wave115_raw_rejection_row_replaced": True,
            "wave116_outcome_row_replaced": True,
            "stale_authority_takeover_claim": False,
            "performance_or_energy_claim": False,
        },
    }

    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.json_out:
        path = Path(args.json_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    return 0 if reproduced else 1


if __name__ == "__main__":
    raise SystemExit(main())
