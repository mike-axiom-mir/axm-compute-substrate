#!/usr/bin/env python3
"""Independent Wave 89 adversarial reproducer.

Exercises the published Wave 89 API without modifying builder code.

The Wave 89 authorization binds the target membership SHA and target witness IDs
as separate exact fields, but `validate_reconfiguration()` does not resolve the
target membership object or prove that those IDs are the IDs named by that
membership SHA. A fully content-valid/rehashed reconfiguration + authorization
can therefore publish a current membership identity for A/B/D while the modeled
runtime witness set is A/B/E.

A second check shows `recover()` returns CONSISTENT_TARGET solely from the
current pointer/membership pair once the target is published, even if the exact
authorization receipt has been deleted and witness heads contradict the target
membership object.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS = REPO_ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import AXM_FLOWING_COMPUTE_WITNESS_MEMBERSHIP_AUTH as wave89  # noqa: E402


def make_runtime(old_m: dict, old_p: dict) -> wave89.Runtime:
    return wave89.Runtime(
        old_p["pointer_sha256"],
        old_m["membership_sha256"],
        {wid: "PREDECESSOR" for wid in old_m["witness_ids"]},
    )


def legitimate_control() -> dict:
    old_m, old_p, target_m, _target_p, reconfig = wave89.fixture()
    ev = wave89.test_root_evaluations(reconfig)
    auth = wave89.make_authorization(reconfig, ev, label="verifier legitimate control")

    with tempfile.TemporaryDirectory(prefix="axm-wave89-verifier-control-") as tmp:
        store = wave89.AuthStore(Path(tmp) / "auth")
        aid = store.put(auth)
        rt = make_runtime(old_m, old_p)
        out = wave89.apply_step(rt, reconfig, store, aid)
        return {
            "status": out["status"],
            "target_membership_ids": target_m["witness_ids"],
            "runtime_witness_ids": sorted(rt.witness_heads),
            "target_membership_sha256": target_m["membership_sha256"],
            "runtime_current_membership_sha256": rt.current_membership_sha256,
        }


def forge_target_set(reconfig: dict) -> dict:
    forged = dict(reconfig)
    # Keep the exact target membership SHA/pointer from the legitimate fixture,
    # whose membership body says A/B/D. Only change the reconfiguration's
    # declared target witness set to A/B/E and reseal all derived set fields.
    forged["target_witness_ids"] = ["witness-a", "witness-b", "witness-e"]
    forged["retained_witness_ids"] = ["witness-a", "witness-b"]
    forged["added_witness_ids"] = ["witness-e"]
    forged["removed_witness_ids"] = ["witness-c"]
    forged["transition_kind"] = "REPLACE"
    forged["reconfiguration_sha256"] = ""
    forged = wave89.seal(forged, "reconfiguration_sha256")

    # Exact published Wave 89 validator currently accepts this even though the
    # target membership object says A/B/D, not A/B/E.
    wave89.validate_reconfiguration(forged)
    return forged


def counterexample() -> dict:
    old_m, old_p, target_m, target_p, legitimate = wave89.fixture()
    forged = forge_target_set(legitimate)

    ev = wave89.test_root_evaluations(forged)
    auth = wave89.make_authorization(
        forged,
        ev,
        label="verifier cross-object target mismatch: structurally valid Wave89 authorization",
    )
    decision = wave89.validate_authorization(auth, forged)

    with tempfile.TemporaryDirectory(prefix="axm-wave89-verifier-attack-") as tmp:
        store = wave89.AuthStore(Path(tmp) / "auth")
        aid = store.put(auth)
        rt = make_runtime(old_m, old_p)
        out = wave89.apply_step(rt, forged, store, aid)

        runtime_ids_after_commit = sorted(rt.witness_heads)
        target_ids_from_membership_body = target_m["witness_ids"]

        # Remove the exact authorization receipt. Because primary pointer +
        # membership already match the target fields, recover() fast-paths to
        # CONSISTENT_TARGET without resolving authorization or witness heads.
        store.path_for(aid).unlink()
        recovery = wave89.recover(rt, forged, store, aid)

        return {
            "authorization_decision": decision,
            "commit_status": out["status"],
            "legitimate_target_membership_sha256": target_m["membership_sha256"],
            "legitimate_target_pointer_sha256": target_p["pointer_sha256"],
            "target_ids_from_membership_body": target_ids_from_membership_body,
            "forged_reconfiguration_target_ids": forged["target_witness_ids"],
            "runtime_current_membership_sha256": rt.current_membership_sha256,
            "runtime_current_pointer_sha256": rt.current_pointer_sha256,
            "runtime_witness_ids_after_commit": runtime_ids_after_commit,
            "authorization_receipt_present_during_recovery": store.path_for(aid).exists(),
            "recovery_status_without_receipt": recovery["status"],
        }


def main() -> None:
    control = legitimate_control()
    attack = counterexample()

    assert control["status"] == "COMMITTED", control
    assert control["target_membership_ids"] == ["witness-a", "witness-b", "witness-d"], control
    assert control["runtime_witness_ids"] == control["target_membership_ids"], control
    assert control["runtime_current_membership_sha256"] == control["target_membership_sha256"], control

    # Primary failure: Wave89's own validator + root-evaluation helper +
    # authorization validator accept a reconfiguration whose target witness set
    # contradicts the exact target membership object it references.
    assert attack["authorization_decision"] == "ALLOW", attack
    assert attack["commit_status"] == "COMMITTED", attack
    assert attack["target_ids_from_membership_body"] == ["witness-a", "witness-b", "witness-d"], attack
    assert attack["forged_reconfiguration_target_ids"] == ["witness-a", "witness-b", "witness-e"], attack
    assert attack["runtime_current_membership_sha256"] == attack["legitimate_target_membership_sha256"], attack
    assert attack["runtime_current_pointer_sha256"] == attack["legitimate_target_pointer_sha256"], attack
    assert attack["runtime_witness_ids_after_commit"] == ["witness-a", "witness-b", "witness-e"], attack
    assert attack["runtime_witness_ids_after_commit"] != attack["target_ids_from_membership_body"], attack

    # Secondary failure: after publication, recovery declares the target
    # consistent without the exact authorization receipt and without verifying
    # witness heads against the target membership body.
    assert attack["authorization_receipt_present_during_recovery"] is False, attack
    assert attack["recovery_status_without_receipt"] == "CONSISTENT_TARGET", attack

    print(json.dumps({
        "verdict": "FAIL_AUTHORIZED_RECONFIGURATION_CAN_COMMIT_WITNESS_SET_THAT_CONTRADICTS_TARGET_MEMBERSHIP_OBJECT",
        "control": control,
        "counterexample": attack,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
