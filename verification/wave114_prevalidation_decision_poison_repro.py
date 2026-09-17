#!/usr/bin/env python3
"""Independent adversarial reproducer for Wave 114.

Finding: Wave 114 writes a sealed COMMIT decision before the lower Wave-100/110
transition semantics are validated. A strict-field, correctly content-addressed transition
that preserves authority/checkpoint/state/predecessor identities but lies about the registry
delta can therefore be durably decision-bound and only afterwards rejected by the lower
commit. The genuine transition for the same prepared authority is then blocked because that
authority is already bound to the rejected transition identity.

This is a liveness / evidence-integrity defect, not stale-authority acceptance.
"""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

import AXM_FLOWING_COMPUTE_EXACT_TRANSITION_DECISION as w
import AXM_FLOWING_COMPUTE_REMOTE_REGISTRY_MONOTONICITY as w100
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w104

q = w.q
g = w.g


def new_world():
    st, priv, boot, rt, services, tokens, rs = q.fixture()
    ts = {}
    cs = g.new_certificate_store()
    domain = w104.new_certificate_witness_domain()
    bs = {}
    w.adopt_genesis(rt, st, boot, services, rs, ts, cs, domain, bs)
    return st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs


def main() -> int:
    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world()

    cp, use, link, genuine_sha, body = w.prepare(
        rt, st, priv, boot, services, rs, ts, cs, domain, bs,
        target_user_app_state_sha="81" * 32,
    )
    genuine = deepcopy(ts[genuine_sha])

    # Keep the exact Wave-114 field set and all identities that _ensure_commit_decision checks,
    # but lie about the registry semantic delta. For a SAME-registry transaction, the lower
    # Wave-100 validator must reject this as TRANSITION_DELTA_HOLD.
    adversarial = deepcopy(genuine)
    adversarial["transition_kind"] = (
        "CREDENTIAL_ROTATION" if genuine["transition_kind"] == "SAME" else "SAME"
    )
    adversarial["transition_sha"] = ""
    adversarial = w100._seal(adversarial, "transition_sha")
    adversarial_sha = w100.put_transition(ts, adversarial)

    decision_before = deepcopy(st[w.DECISION_STORE])
    first_result = w.commit(
        rt, st, boot, rs, ts, link["authority_sha"], adversarial_sha, bs
    )
    decisions_after = w._decision_rows(st) or []
    bound = [
        d for _sha, d in decisions_after
        if d.get("authority_sha") == link["authority_sha"]
    ]

    status_after_bad = w.commit_status_state(st, boot, rt, rs, bs, ts)
    authority_after_bad = w.authority(
        rt, st, boot, services, rs, ts, cs, domain, bs
    )

    valid_retry_result = None
    valid_retry_error = None
    try:
        valid_retry_result = w.commit(
            rt, st, boot, rs, ts, link["authority_sha"], genuine_sha, bs
        )
    except Exception as exc:
        valid_retry_error = f"{type(exc).__name__}:{exc}"

    status_after_valid_retry = w.commit_status_state(st, boot, rt, rs, bs, ts)
    authority_after_valid_retry = w.authority(
        rt, st, boot, services, rs, ts, cs, domain, bs
    )

    exact_bad_retry = w.commit(
        rt, st, boot, rs, ts, link["authority_sha"], adversarial_sha, bs
    )

    reproduced = (
        decision_before == {}
        and adversarial_sha != genuine_sha
        and first_result == "TRANSITION_DELTA_HOLD"
        and len(bound) == 1
        and bound[0].get("decision") == "COMMIT"
        and bound[0].get("transition_sha") == adversarial_sha
        and valid_retry_result is None
        and valid_retry_error is not None
        and "decision-authority-bound-to-different-transition" in valid_retry_error
        and not authority_after_bad.startswith("AUTHORITATIVE")
        and not authority_after_valid_retry.startswith("AUTHORITATIVE")
        and exact_bad_retry == "TRANSITION_DELTA_HOLD"
    )

    report = {
        "schema": "axm.flowing-compute.verifier.wave114-prevalidation-decision-poison/v1",
        "builder_head_inspected": "e9b48d8e6b090ad73fe6f9d4443e741c308a70e6",
        "builder_tested_source": "cd946978f2c01ce719307c5bc025beccbcb1ec4f",
        "verdict": (
            "FAIL_SEMANTICALLY_INVALID_TRANSITION_IS_DURABLY_COMMIT_DECIDED_BEFORE_LOWER_VALIDATION"
            if reproduced else "NOT_REPRODUCED"
        ),
        "genuine_transition_sha": genuine_sha,
        "adversarial_transition_sha": adversarial_sha,
        "genuine_transition_kind": genuine["transition_kind"],
        "adversarial_transition_kind": adversarial["transition_kind"],
        "first_commit_result": first_result,
        "decision_count_after_rejected_commit": len(decisions_after),
        "decision_bound_transition_sha": bound[0].get("transition_sha") if len(bound) == 1 else None,
        "status_after_rejected_commit": status_after_bad.get("status"),
        "status_reason_after_rejected_commit": status_after_bad.get("reason"),
        "authority_after_rejected_commit": authority_after_bad,
        "genuine_retry_result": valid_retry_result,
        "genuine_retry_error": valid_retry_error,
        "status_after_genuine_retry": status_after_valid_retry.get("status"),
        "authority_after_genuine_retry": authority_after_valid_retry,
        "rejected_identity_retry_result": exact_bad_retry,
        "bounded_scope": {
            "stale_authority_accepted": False,
            "hash_collision_used": False,
            "credential_forgery_used": False,
            "builder_files_rewritten": False,
            "performance_or_energy_claim": False,
            "same_modeled_python_failure_domain": True,
            "finding_class": "pre-validation decision ordering / liveness / evidence integrity",
        },
        "reproduced": reproduced,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if reproduced else 1


if __name__ == "__main__":
    raise SystemExit(main())
