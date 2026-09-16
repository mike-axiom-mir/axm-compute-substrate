#!/usr/bin/env python3
"""Independent Wave 88 adversarial reproducer.

Exercises the published Wave 88 API without modifying builder code.

Wave 88 claims every witness in the old committed membership must hand off before
membership can change. The reconfiguration validator, commit path, and recovery
path currently do not cross-check `old_witness_ids` / predecessor witness heads
against the predecessor membership object named by `predecessor_membership_sha256`.

A content-valid reconfiguration can therefore name predecessor membership A/B/C
while declaring only A/B as its old witness set. The normal commit path accepts
it, and the recovery path can finish it after only A and B move, leaving C at the
old epoch while the primary advances to a current A/B membership.
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

import AXM_FLOWING_COMPUTE_WITNESS_MEMBERSHIP_STATE as wave88  # noqa: E402


def setup(root: Path):
    return wave88.initialize(root)


def prepare_legitimate_remove(root: Path):
    primary, memberships, reconfigs, witnesses, genesis_m, genesis_p = setup(root)
    target_m, target_p, legit = wave88.prepare_reconfiguration(
        primary=primary,
        memberships=memberships,
        reconfigs=reconfigs,
        witness_dir=witnesses,
        target_witness_ids=("witness-a", "witness-b"),
        transition_kind="REMOVE",
        note="verifier legitimate remove control",
    )
    return primary, memberships, reconfigs, witnesses, genesis_m, genesis_p, target_m, target_p, legit


def forge_old_set_omission(legit: dict) -> dict:
    forged = dict(legit)
    forged["old_witness_ids"] = ["witness-a", "witness-b"]
    forged["target_witness_ids"] = ["witness-a", "witness-b"]
    forged["retained_witness_ids"] = ["witness-a", "witness-b"]
    forged["added_witness_ids"] = []
    forged["removed_witness_ids"] = []
    forged["predecessor_witness_heads"] = {
        wid: legit["predecessor_witness_heads"][wid]
        for wid in ("witness-a", "witness-b")
    }
    forged["note"] = "verifier forged reconfiguration silently omits committed old witness-c"
    forged["reconfiguration_sha256"] = ""
    forged = wave88.seal(forged, "reconfiguration_sha256")
    # This is the exact published validator. It currently accepts the omission.
    wave88.validate_reconfiguration(forged)
    return forged


def control() -> dict:
    with tempfile.TemporaryDirectory(prefix="axm-wave88-verifier-control-") as tmp:
        (
            primary,
            memberships,
            reconfigs,
            witnesses,
            genesis_m,
            _genesis_p,
            _target_m,
            _target_p,
            legit,
        ) = prepare_legitimate_remove(Path(tmp))

        assert genesis_m["witness_ids"] == ["witness-a", "witness-b", "witness-c"]
        assert legit["old_witness_ids"] == ["witness-a", "witness-b", "witness-c"]
        assert legit["removed_witness_ids"] == ["witness-c"]

        out = wave88.commit_reconfiguration(
            primary=primary,
            memberships=memberships,
            reconfigs=reconfigs,
            witness_dir=witnesses,
            r=legit,
        )
        steady = wave88.validate_steady_state(
            primary=primary,
            memberships=memberships,
            witness_dir=witnesses,
            reconfigs=reconfigs,
        )
        c = witnesses.witness("witness-c").head()
        return {
            "commit_result": out,
            "steady_status": steady["status"],
            "current_witness_ids": steady.get("witness_ids"),
            "witness_c_epoch": c["anchor_epoch"],
            "witness_c_role": c["record_role"],
            "legitimate_old_witness_ids": legit["old_witness_ids"],
            "legitimate_removed_witness_ids": legit["removed_witness_ids"],
        }


def direct_commit_counterexample() -> dict:
    with tempfile.TemporaryDirectory(prefix="axm-wave88-verifier-direct-") as tmp:
        (
            primary,
            memberships,
            reconfigs,
            witnesses,
            genesis_m,
            _genesis_p,
            _target_m,
            _target_p,
            legit,
        ) = prepare_legitimate_remove(Path(tmp))
        forged = forge_old_set_omission(legit)
        reconfigs.put(forged)

        out = wave88.commit_reconfiguration(
            primary=primary,
            memberships=memberships,
            reconfigs=reconfigs,
            witness_dir=witnesses,
            r=forged,
        )
        steady = wave88.validate_steady_state(
            primary=primary,
            memberships=memberships,
            witness_dir=witnesses,
            reconfigs=reconfigs,
        )
        c = witnesses.witness("witness-c").head()
        return {
            "commit_result": out,
            "steady_status": steady["status"],
            "current_witness_ids": steady.get("witness_ids"),
            "committed_predecessor_membership_witness_ids": genesis_m["witness_ids"],
            "forged_old_witness_ids": forged["old_witness_ids"],
            "forged_removed_witness_ids": forged["removed_witness_ids"],
            "witness_c_epoch_after_commit": c["anchor_epoch"],
            "witness_c_role_after_commit": c["record_role"],
        }


def recovery_counterexample() -> dict:
    with tempfile.TemporaryDirectory(prefix="axm-wave88-verifier-recovery-") as tmp:
        (
            primary,
            memberships,
            reconfigs,
            witnesses,
            genesis_m,
            _genesis_p,
            _target_m,
            _target_p,
            legit,
        ) = prepare_legitimate_remove(Path(tmp))
        forged = forge_old_set_omission(legit)
        reconfigs.put(forged)

        # One declared old witness moves. C remains a currently required witness,
        # but it is absent from the forged reconfiguration's old set.
        witnesses.witness("witness-a").advance_existing(forged)
        before = wave88.recovery_status(
            primary=primary,
            memberships=memberships,
            reconfigs=reconfigs,
            witness_dir=witnesses,
        )
        repaired = wave88.recovery_status(
            primary=primary,
            memberships=memberships,
            reconfigs=reconfigs,
            witness_dir=witnesses,
            repair=True,
        )
        c = witnesses.witness("witness-c").head()
        return {
            "status_before_repair": before["status"],
            "status_after_repair": repaired["status"],
            "current_witness_ids_after_repair": repaired.get("witness_ids"),
            "committed_predecessor_membership_witness_ids": genesis_m["witness_ids"],
            "forged_old_witness_ids": forged["old_witness_ids"],
            "witness_c_epoch_after_repair": c["anchor_epoch"],
            "witness_c_role_after_repair": c["record_role"],
        }


def main() -> None:
    good = control()
    direct = direct_commit_counterexample()
    recovery = recovery_counterexample()

    # Control: official preparation includes C and gives it an explicit retired
    # handoff record before current membership becomes A/B.
    assert good["commit_result"]["status"] == "COMMITTED", good
    assert good["steady_status"] == "CONSISTENT", good
    assert good["current_witness_ids"] == ["witness-a", "witness-b"], good
    assert good["witness_c_epoch"] == 1, good
    assert good["witness_c_role"] == "RETIRED", good

    # Direct attack: exact public commit helper accepts the rehashed reconfiguration
    # even though it omits C from the old set; steady-state validation then reports
    # CONSISTENT because current membership is A/B.
    assert direct["commit_result"]["status"] == "COMMITTED", direct
    assert direct["steady_status"] == "CONSISTENT", direct
    assert direct["current_witness_ids"] == ["witness-a", "witness-b"], direct
    assert direct["committed_predecessor_membership_witness_ids"] == ["witness-a", "witness-b", "witness-c"], direct
    assert direct["forged_old_witness_ids"] == ["witness-a", "witness-b"], direct
    assert direct["witness_c_epoch_after_commit"] == 0, direct
    assert direct["witness_c_role_after_commit"] == "GENESIS", direct

    # Recovery attack: after only A advances under the forged reconfiguration,
    # repair advances B and publishes A/B while C remains untouched at epoch 0.
    assert recovery["status_before_repair"] == "OLD_MEMBERSHIP_HANDOFF_PARTIAL_RECOVERABLE", recovery
    assert recovery["status_after_repair"] == "CONSISTENT", recovery
    assert recovery["current_witness_ids_after_repair"] == ["witness-a", "witness-b"], recovery
    assert recovery["witness_c_epoch_after_repair"] == 0, recovery
    assert recovery["witness_c_role_after_repair"] == "GENESIS", recovery

    print(json.dumps({
        "verdict": "FAIL_OLD_COMMITTED_WITNESS_CAN_BE_OMITTED_FROM_RECONFIGURATION",
        "control": good,
        "direct_commit_counterexample": direct,
        "recovery_counterexample": recovery,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
