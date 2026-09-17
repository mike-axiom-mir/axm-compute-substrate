#!/usr/bin/env python3
"""Wave 115 focused exact rejection-identity check.

This intentionally closes a coverage gap in the broader Wave 115 self-test: a rejection receipt
must name the exact rejected transition SHA, not merely exist with the right verdict.
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


def run() -> dict:
    st, priv, boot, rt, services, tokens, rs = q.fixture()
    ts = {}
    cs = g.new_certificate_store()
    domain = w104.new_certificate_witness_domain()
    bs = {}
    w.adopt_genesis(rt, st, boot, services, rs, ts, cs, domain, bs)

    cp, use, link, genuine_sha, _body = w.prepare(
        rt, st, priv, boot, services, rs, ts, cs, domain, bs,
        target_user_app_state_sha="91" * 32,
    )
    bad = deepcopy(ts[genuine_sha])
    bad["transition_kind"] = (
        "CREDENTIAL_ROTATION" if bad["transition_kind"] == "SAME" else "SAME"
    )
    bad["transition_sha"] = ""
    bad = w100._seal(bad, "transition_sha")
    bad_sha = w100.put_transition(ts, bad)

    decisions_before = deepcopy(st[w.DECISION_STORE])
    bad_result = w.commit(rt, st, boot, rs, ts, link["authority_sha"], bad_sha, bs)
    rejections = w._rejection_rows(st, ts) or []
    receipt = rejections[0][1] if len(rejections) == 1 else {}

    genuine_result = w.commit(rt, st, boot, rs, ts, link["authority_sha"], genuine_sha, bs)
    decisions = w._decision_rows(st) or []
    bound = [d for _sha, d in decisions if d.get("authority_sha") == link["authority_sha"]]

    controls = {
        "bad_semantic_transition_rejected": bad_result == "TRANSITION_DELTA_HOLD",
        "bad_transition_did_not_write_commit_decision": st[w.DECISION_STORE] != decisions_before and len(bound) == 1 and bound[0].get("transition_sha") == genuine_sha,
        "exactly_one_rejection_receipt": len(rejections) == 1,
        "rejection_receipt_binds_exact_bad_sha": receipt.get("transition_sha") == bad_sha,
        "rejection_receipt_binds_same_authority": receipt.get("authority_sha") == link["authority_sha"],
        "rejection_receipt_preserves_exact_lower_result": receipt.get("lower_result") == bad_result,
        "raw_bad_transition_is_preserved": bad_sha in ts and ts[bad_sha] == bad,
        "genuine_retry_commits": genuine_result == "COMMITTED",
        "commit_decision_binds_genuine_not_bad": len(bound) == 1 and bound[0].get("transition_sha") == genuine_sha and bound[0].get("transition_sha") != bad_sha,
    }
    failed = [name for name, ok in controls.items() if not ok]
    return {
        "schema": "axm.flowing-compute.wave115.rejection-identity-selftest/v1",
        "genuine_transition_sha": genuine_sha,
        "rejected_transition_sha": bad_sha,
        "rejection_receipt_transition_sha": receipt.get("transition_sha"),
        "commit_decision_transition_sha": bound[0].get("transition_sha") if len(bound) == 1 else None,
        "bad_result": bad_result,
        "genuine_result": genuine_result,
        "controls": controls,
        "passed": len(controls) - len(failed),
        "total": len(controls),
        "failed": failed,
        "verdict": "PASS" if not failed else "FAIL",
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
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
