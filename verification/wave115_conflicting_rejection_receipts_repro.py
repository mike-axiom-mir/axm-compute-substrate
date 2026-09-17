#!/usr/bin/env python3
"""Independent Wave 115 adversarial reproducer.

Challenge: Wave 115 verifies each rejection receipt independently but does not require a unique
terminal outcome per transition identity. A second correctly sealed append-only row for the exact
same transition can claim a different stable lower result and still pass rejection-chain
verification. The committed world can then return VALID/AUTHORITATIVE while the rejection ledger
contains mutually contradictory exact-outcome evidence.

This does not forge a hash, alter the builder code, delete prior evidence, or claim stale-authority
takeover. It tests the evidence/provenance boundary of the new rejection ledger.
"""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

import AXM_FLOWING_COMPUTE_PREVALIDATED_COMMIT_DECISION as w
import AXM_FLOWING_COMPUTE_REMOTE_REGISTRY_MONOTONICITY as w100
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w104

q = w.q
g = w.g

VERDICT = "FAIL_CONTRADICTORY_REJECTION_OUTCOMES_ACCEPTED_AS_VALID_HISTORY"


def new_world():
    st, priv, boot, rt, services, tokens, rs = q.fixture()
    ts = {}
    cs = g.new_certificate_store()
    domain = w104.new_certificate_witness_domain()
    bs = {}
    w.adopt_genesis(rt, st, boot, services, rs, ts, cs, domain, bs)
    return st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs


def resealed_variant(original: dict, **changes) -> dict:
    body = deepcopy(original)
    body.update(changes)
    body["transition_sha"] = ""
    return w100._seal(body, "transition_sha")


def run() -> dict:
    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world()

    cp, use, link, genuine_sha, _body = w.prepare(
        rt,
        st,
        priv,
        boot,
        services,
        rs,
        ts,
        cs,
        domain,
        bs,
        target_user_app_state_sha="a1" * 32,
    )
    genuine = deepcopy(ts[genuine_sha])
    bad = resealed_variant(
        genuine,
        transition_kind=(
            "CREDENTIAL_ROTATION" if genuine["transition_kind"] == "SAME" else "SAME"
        ),
    )
    bad_sha = w100.put_transition(ts, bad)

    first_result = w.commit(
        rt, st, boot, rs, ts, link["authority_sha"], bad_sha, bs
    )
    first_rows = w._rejection_rows(st, ts) or []
    if len(first_rows) != 1:
        raise RuntimeError(f"expected one legitimate rejection row, got {len(first_rows)}")
    first_sha, first_body = first_rows[0]

    # Re-run the lower semantic probe before adding the adversarial row. The exact transition still
    # deterministically returns DELTA_HOLD, so a later GENERATION_HOLD receipt for this same SHA is
    # factually contradictory rather than merely another observation.
    repeated_actual = w._prevalidate_lower_commit(
        rt,
        st,
        boot,
        rs,
        ts,
        link["authority_sha"],
        bad_sha,
        bs,
    )

    contradictory = w._seal_rejection(
        {
            "schema": w.REJECTION_SCHEMA,
            "seq": 2,
            "predecessor_rejection_sha": first_sha,
            "authority_sha": first_body["authority_sha"],
            "transition_sha": bad_sha,
            "checkpoint_sha": first_body["checkpoint_sha"],
            "lower_result": "TRANSITION_GENERATION_HOLD",
            "rejection_sha": "",
        }
    )
    contradictory_sha = contradictory["rejection_sha"]
    st[w.REJECTION_STORE][contradictory_sha] = contradictory

    verification_error = None
    try:
        rows_after = w._rejection_rows(st, ts) or []
    except Exception as exc:
        rows_after = []
        verification_error = f"{type(exc).__name__}:{exc}"

    same_transition_results = [
        body["lower_result"]
        for _sha, body in rows_after
        if body.get("transition_sha") == bad_sha
    ]
    contradiction_accepted = (
        verification_error is None
        and len(rows_after) == 2
        and sorted(same_transition_results)
        == sorted(["TRANSITION_DELTA_HOLD", "TRANSITION_GENERATION_HOLD"])
    )

    genuine_result = w.commit(
        rt, st, boot, rs, ts, link["authority_sha"], genuine_sha, bs
    )
    for slot in q.REMOTE_IDS:
        pub = w.publish(rt, st, boot, services, tokens, rs, slot)
        if pub not in ("APPENDED", "ALREADY_CURRENT"):
            raise RuntimeError(f"publish failed for {slot}: {pub}")
    w.certify_and_sync(rt, st, boot, services, rs, cs, domain)

    status = w.commit_status_state(st, boot, rt, rs, bs, ts)
    authority = w.authority(rt, st, boot, services, rs, ts, cs, domain, bs)

    reproduced = (
        first_result == "TRANSITION_DELTA_HOLD"
        and repeated_actual == "TRANSITION_DELTA_HOLD"
        and contradiction_accepted
        and genuine_result == "COMMITTED"
        and status.get("status") == w.HISTORY_VALID
        and authority.startswith("AUTHORITATIVE")
    )

    return {
        "schema": "axm.flowing-compute.wave115.adversarial-verification/v1",
        "builder_tested_source": "ad03fc8582a8ac6d8b294c494fa8b2fabb142dc6",
        "builder_head_at_verification_start": "8f183d61e9874fd821ec2c03c222f13711d7b8ff",
        "verdict": VERDICT if reproduced else "NOT_REPRODUCED",
        "reproduced": reproduced,
        "first_public_rejection_result": first_result,
        "repeated_actual_lower_result": repeated_actual,
        "genuine_transition_sha": genuine_sha,
        "rejected_transition_sha": bad_sha,
        "legitimate_rejection_sha": first_sha,
        "adversarial_conflicting_rejection_sha": contradictory_sha,
        "accepted_rejection_rows": len(rows_after),
        "same_transition_claimed_results": same_transition_results,
        "rejection_verification_error": verification_error,
        "genuine_commit_result": genuine_result,
        "final_history_status": status.get("status"),
        "final_history_reason": status.get("reason"),
        "final_rejected_transition_count": status.get("rejected_transition_count"),
        "final_authority": authority,
        "severity_boundary": {
            "stale_authority_takeover_demonstrated": False,
            "hash_collision_or_hash_forgery_used": False,
            "existing_evidence_rewritten_or_deleted": False,
            "builder_files_modified": False,
            "failure_class": "rejection-ledger provenance integrity / contradictory terminal outcome acceptance",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out")
    args = parser.parse_args()
    report = run()
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.json_out:
        path = Path(args.json_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    return 0 if report["reproduced"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
