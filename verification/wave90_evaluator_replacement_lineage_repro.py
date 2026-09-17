#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "AXM_FLOWING_COMPUTE_EVALUATOR_PROVENANCE.py"
SPEC = importlib.util.spec_from_file_location("wave90", TOOL)
assert SPEC and SPEC.loader
wave90 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = wave90
SPEC.loader.exec_module(wave90)


def make_assignments(evaluator_id: str) -> dict[str, str]:
    return {root: evaluator_id for root in wave90.REQUIRED_ROOTS}


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="axm-wave90-verifier-") as td:
        root = Path(td)
        evaluators = wave90.CASStore(root / "evaluators", "evaluator_sha256")
        registries = wave90.CASStore(root / "registries", "registry_sha256")

        # Control: a correctly linked replacement works.
        old = wave90.make_evaluator(
            "eval-main",
            list(wave90.REQUIRED_ROOTS),
            wave90.text_sha("old-tool"),
            wave90.text_sha("old-source"),
            label="control old evaluator",
        )
        old_sha = evaluators.put(old)
        old_registry = wave90.make_registry(
            0,
            {"eval-main": old_sha},
            make_assignments("eval-main"),
            None,
            "GENESIS",
        )
        registries.put(old_registry)
        wave90.validate_registry(old_registry, evaluators)

        good = wave90.make_evaluator(
            "eval-main",
            list(wave90.REQUIRED_ROOTS),
            wave90.text_sha("good-new-tool"),
            wave90.text_sha("good-new-source"),
            label="control correctly linked replacement",
            predecessor_evaluator_sha256=old_sha,
        )
        good_sha = evaluators.put(good)
        good_registry = wave90.make_registry(
            1,
            {"eval-main": good_sha},
            make_assignments("eval-main"),
            old_registry["registry_sha256"],
            "REPLACE",
        )
        registries.put(good_registry)
        good_transition = wave90.make_registry_transition(old_registry, good_registry)
        wave90.validate_registry_transition(good_transition, old_registry, good_registry)
        assert good["predecessor_evaluator_sha256"] == old_sha

        # Attack: replacement changes the evaluator body but carries NO predecessor evaluator.
        # The reusable registry/transition validators still accept it, and the normal runtime
        # handoff can make it the fully current witnessed registry.
        bad = wave90.make_evaluator(
            "eval-main",
            list(wave90.REQUIRED_ROOTS),
            wave90.text_sha("bad-new-tool"),
            wave90.text_sha("bad-new-source"),
            label="adversarial replacement with missing evaluator predecessor",
            predecessor_evaluator_sha256=None,
        )
        bad_sha = evaluators.put(bad)
        bad_registry = wave90.make_registry(
            1,
            {"eval-main": bad_sha},
            make_assignments("eval-main"),
            old_registry["registry_sha256"],
            "REPLACE",
        )
        registries.put(bad_registry)

        wave90.validate_registry(bad_registry, evaluators)
        bad_transition = wave90.make_registry_transition(old_registry, bad_registry)
        wave90.validate_registry_transition(bad_transition, old_registry, bad_registry)
        assert bad["predecessor_evaluator_sha256"] is None
        assert bad_transition["replaced_evaluator_ids"] == ["eval-main"]

        runtime = wave90.RegistryRuntime(
            old_registry["registry_sha256"],
            {wid: old_registry["registry_sha256"] for wid in wave90.WITNESSES},
        )
        commit = wave90.apply_registry_transition(
            runtime,
            bad_transition,
            old_registry,
            bad_registry,
        )
        assert commit["status"] == "COMMITTED", commit
        status = wave90.registry_view_status(runtime)
        assert status["status"] == "CONSISTENT", status
        assert runtime.current_registry_sha256 == bad_registry["registry_sha256"]

        # This deliberately avoids Wave 90's already-disclosed prepared/stored-registry
        # authority gap: the adversarial registry is now the model's current witnessed registry.
        reconfiguration_sha = "a" * 64
        authorization = wave90.make_authorization(
            reconfiguration_sha,
            bad_registry,
            evaluators,
        )
        decision = wave90.validate_authorization(
            authorization,
            reconfiguration_sha,
            registries,
            evaluators,
        )
        assert decision == "ALLOW", decision

        # A second malformed replacement may point at an unrelated-looking digest; this is
        # also accepted because replacement lineage is not checked against the old entry.
        wrong_pred = wave90.make_evaluator(
            "eval-main",
            list(wave90.REQUIRED_ROOTS),
            wave90.text_sha("wrong-pred-tool"),
            wave90.text_sha("wrong-pred-source"),
            label="adversarial replacement with unrelated predecessor",
            predecessor_evaluator_sha256="f" * 64,
        )
        wrong_pred_sha = evaluators.put(wrong_pred)
        wrong_pred_registry = wave90.make_registry(
            1,
            {"eval-main": wrong_pred_sha},
            make_assignments("eval-main"),
            old_registry["registry_sha256"],
            "REPLACE",
        )
        registries.put(wrong_pred_registry)
        wave90.validate_registry(wrong_pred_registry, evaluators)
        wrong_pred_transition = wave90.make_registry_transition(old_registry, wrong_pred_registry)
        wave90.validate_registry_transition(wrong_pred_transition, old_registry, wrong_pred_registry)
        assert wrong_pred["predecessor_evaluator_sha256"] == "f" * 64

        print(json.dumps({
            "verdict": "FAIL_REPLACEMENT_EVALUATOR_PREDECESSOR_NOT_ENFORCED",
            "control_correct_predecessor": good["predecessor_evaluator_sha256"] == old_sha,
            "missing_predecessor_registry_validated": True,
            "missing_predecessor_transition_validated": True,
            "missing_predecessor_committed_as_current": commit["status"] == "COMMITTED",
            "current_registry_witness_status": status["status"],
            "authorization_after_current_commit": decision,
            "wrong_predecessor_digest_transition_validated": True,
            "already_disclosed_prepared_registry_gap_required": False,
        }, sort_keys=True))


if __name__ == "__main__":
    main()
