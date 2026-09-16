#!/usr/bin/env python3
"""Independent Wave 87 counterexample.

This verifier does not modify builder code. It exercises the published Wave 87 API
and contrasts two ways to stop after one witness has advanced:

1. the intended full-membership crash path; and
2. calling commit_prepared() with a reduced runtime witness map.

The second path currently publishes the primary pointer even though the prepared
commit-set names three witnesses and only one witness advanced.
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

import AXM_FLOWING_COMPUTE_WITNESS_COMMIT_SET as wave87  # noqa: E402


def setup(root: Path):
    primary = wave87.Primary(root / "primary")
    witnesses = wave87.witness_map(root / "witnesses")
    commit_sets = wave87.ObjectStore(root / "commit_sets", "commit_set_sha256")
    genesis = wave87.initialize(primary, witnesses)
    return primary, witnesses, commit_sets, genesis


def run_full_membership_crash_control() -> dict:
    with tempfile.TemporaryDirectory(prefix="axm-wave87-verifier-control-") as tmp:
        primary, witnesses, commit_sets, _ = setup(Path(tmp))
        _, commit_set = wave87.prepare_transition(
            primary=primary,
            witnesses=witnesses,
            commit_sets=commit_sets,
            target_retention_sha256=wave87.W83_DROP_RETENTION_SHA,
            note="verifier full-membership crash control",
        )
        result = wave87.commit_prepared(
            primary=primary,
            witnesses=witnesses,
            commit_sets=commit_sets,
            commit_set=commit_set,
            crash_after_witness_count=1,
        )
        status = wave87.recovery_status(
            primary=primary, witnesses=witnesses, commit_sets=commit_sets
        )
        heads = {wid: witnesses[wid].head()["anchor_epoch"] for wid in sorted(witnesses)}
        return {
            "commit_result": result,
            "primary_epoch": primary.current()["commit_epoch"],
            "witness_epochs": heads,
            "recovery_status": status["status"],
            "commit_set_witness_ids": commit_set["witness_ids"],
        }


def run_reduced_runtime_map_counterexample() -> dict:
    with tempfile.TemporaryDirectory(prefix="axm-wave87-verifier-counterexample-") as tmp:
        primary, witnesses, commit_sets, _ = setup(Path(tmp))
        _, commit_set = wave87.prepare_transition(
            primary=primary,
            witnesses=witnesses,
            commit_sets=commit_sets,
            target_retention_sha256=wave87.W83_DROP_RETENTION_SHA,
            note="verifier reduced-runtime-map counterexample",
        )

        # The prepared commit-set explicitly names all three witnesses.
        assert commit_set["witness_ids"] == ["witness-a", "witness-b", "witness-c"]

        # Adversarial caller supplies only one member to commit_prepared().
        reduced = {"witness-a": witnesses["witness-a"]}
        result = wave87.commit_prepared(
            primary=primary,
            witnesses=reduced,
            commit_sets=commit_sets,
            commit_set=commit_set,
        )

        full_status = wave87.recovery_status(
            primary=primary, witnesses=witnesses, commit_sets=commit_sets
        )
        heads = {wid: witnesses[wid].head()["anchor_epoch"] for wid in sorted(witnesses)}
        return {
            "commit_result": result,
            "primary_epoch": primary.current()["commit_epoch"],
            "witness_epochs": heads,
            "full_membership_recovery_status": full_status["status"],
            "commit_set_witness_ids": commit_set["witness_ids"],
            "runtime_witness_ids_given_to_commit_prepared": sorted(reduced),
        }


def main() -> None:
    control = run_full_membership_crash_control()
    counterexample = run_reduced_runtime_map_counterexample()

    # Intended crash semantics: after one witness write, primary must remain old and
    # the exact commit-set is recoverable.
    assert control["primary_epoch"] == 0, control
    assert control["witness_epochs"] == {
        "witness-a": 1,
        "witness-b": 0,
        "witness-c": 0,
    }, control
    assert control["recovery_status"] == "PARTIAL_COMMIT_SET_RECOVERABLE", control

    # Counterexample: same 1/3 witness advancement, but the helper publishes primary.
    assert counterexample["commit_result"]["status"] == "COMMITTED", counterexample
    assert counterexample["primary_epoch"] == 1, counterexample
    assert counterexample["witness_epochs"] == {
        "witness-a": 1,
        "witness-b": 0,
        "witness-c": 0,
    }, counterexample
    assert counterexample["full_membership_recovery_status"] == "NO_RECOVERABLE_COMMIT_SET_HOLD", counterexample

    print(json.dumps({
        "verdict": "FAIL_PARTIAL_PUBLISH_VIA_REDUCED_RUNTIME_WITNESS_MAP",
        "control": control,
        "counterexample": counterexample,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
