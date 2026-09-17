#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "AXM_FLOWING_COMPUTE_CURRENT_REGISTRY_AUTHORITY.py"
SPEC = importlib.util.spec_from_file_location("wave91", TOOL)
assert SPEC and SPEC.loader
wave91 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = wave91
SPEC.loader.exec_module(wave91)


def auth_for_lookup_key(
    lookup_registry_sha256: str,
    body: dict,
    reconfiguration_sha256: str,
) -> dict:
    rows = {}
    for root in wave91.ROOTS:
        rows[root] = {
            "root": root,
            "verdict": "PASS",
            "registry_sha256": lookup_registry_sha256,
            "evaluator_id": body["root_evaluator_ids"][root],
        }
    return wave91.seal(
        {
            "schema": wave91.SCHEMA_AUTH,
            "reconfiguration_sha256": reconfiguration_sha256,
            "evaluator_registry_sha256": lookup_registry_sha256,
            "evaluations": rows,
            "test_only": True,
            "authorization_sha256": "",
        },
        "authorization_sha256",
    )


def main() -> None:
    reconfig = wave91.text_digest("wave91-verifier-reconfiguration")

    base_ids = {root: f"base-{root}-evaluator" for root in wave91.ROOTS}
    base = wave91.make_registry(0, None, base_ids, "control current registry")
    base_sha = base["registry_sha256"]
    runtime = wave91.Runtime(
        base_sha,
        {w: base_sha for w in wave91.WITNESSES},
    )

    # Control: exact lookup key -> exact body behaves as intended.
    control_store = {base_sha: base}
    control_auth = wave91.make_auth(base, reconfig)
    control_state = wave91.current_authority(runtime, control_store)
    control_decision = wave91.validate_current(
        control_auth, reconfig, runtime, control_store
    )
    assert control_state["status"] == "AUTHORITATIVE", control_state
    assert control_decision == "ALLOW", control_decision

    # Adversarial body: independently sealed, different identity and evaluator set.
    substituted_ids = {
        root: f"substituted-{root}-evaluator" for root in wave91.ROOTS
    }
    substituted = wave91.make_registry(
        0,
        None,
        substituted_ids,
        "adversarial body under another registry key",
    )
    substituted_sha = substituted["registry_sha256"]
    assert substituted_sha != base_sha
    wave91.validate_registry(substituted)

    # Attack: the content-addressed mapping key remains the exact current pointer A,
    # but the body stored under A is the separately valid registry B.
    # current_authority() validates B's internal seal but never checks that B's
    # self-hash equals the lookup key/current pointer A.
    substituted_store = {base_sha: substituted}
    attack_state = wave91.current_authority(runtime, substituted_store)
    assert attack_state["status"] == "AUTHORITATIVE", attack_state
    assert attack_state["registry_sha256"] == base_sha
    assert substituted["registry_sha256"] == substituted_sha
    assert substituted["registry_sha256"] != base_sha

    # Build a normally sealed authorization whose external registry identity is A,
    # while its evaluator rows match the substituted body B found under key A.
    # validate_structural()/validate_current() likewise do not assert
    # store[key]['registry_sha256'] == key, so the substituted evaluators authorize.
    attack_auth = auth_for_lookup_key(base_sha, substituted, reconfig)
    attack_decision = wave91.validate_current(
        attack_auth, reconfig, runtime, substituted_store
    )
    assert attack_decision == "ALLOW", attack_decision

    # Negative control: if the key is actually absent, Wave 91 correctly HOLDs.
    missing_state = wave91.current_authority(runtime, {})
    assert missing_state["status"] == "HOLD", missing_state

    print(
        json.dumps(
            {
                "verdict": "FAIL_CURRENT_REGISTRY_KEY_BODY_IDENTITY_NOT_ENFORCED",
                "control_exact_key_body_state": control_state["status"],
                "control_exact_key_body_authorization": control_decision,
                "pointer_and_witness_registry_sha256": base_sha,
                "substituted_body_registry_sha256": substituted_sha,
                "substituted_body_differs_from_pointer": substituted_sha != base_sha,
                "authority_status_under_substituted_body": attack_state["status"],
                "authorization_under_substituted_evaluators": attack_decision,
                "missing_key_still_holds": missing_state["status"] == "HOLD",
                "already_disclosed_unguarded_transition_required": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
