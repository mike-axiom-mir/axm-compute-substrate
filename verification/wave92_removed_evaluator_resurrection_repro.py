#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "AXM_FLOWING_COMPUTE_PREDECESSOR_AUTHORIZED_REGISTRY_TRANSITION.py"
SPEC = importlib.util.spec_from_file_location("wave92", TOOL)
assert SPEC and SPEC.loader
wave92 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = wave92
SPEC.loader.exec_module(wave92)


def main() -> None:
    E, R, T, A, x = wave92.fixture()
    r0 = x["r0"]
    original_truth_sha = x["truth0"]
    original_truth = deepcopy(E[original_truth_sha])
    assert original_truth["evaluator_id"] == "eval-truth"
    assert original_truth["predecessor_evaluator_sha256"] is None

    runtime = {
        "cur": r0["registry_sha256"],
        "w": {w: r0["registry_sha256"] for w in wave92.WIT},
    }
    assert wave92.authority(runtime, R, E) == "AUTHORITATIVE"

    # Generation 1 deliberately removes the historical eval-truth identity and
    # assigns the truth root to a different evaluator ID. This is a normal MIXED
    # transition (one REMOVE + one ADD), authorized by the current predecessor.
    bridge_id = "eval-truth-bridge"
    bridge = wave92.ev(
        bridge_id,
        ["truth"],
        wave92.td("bridge-tool"),
        wave92.td("bridge-source"),
        "bridge truth evaluator",
        None,
    )
    wave92.put(E, bridge, "evaluator_sha256")

    entries1 = dict(r0["evaluator_entries"])
    entries1.pop("eval-truth")
    entries1[bridge_id] = bridge["evaluator_sha256"]
    assign1 = dict(r0["root_assignments"])
    assign1["truth"] = bridge_id

    r1 = wave92.reg(
        1,
        r0["registry_sha256"],
        entries1,
        assign1,
        "MIXED",
        "remove original truth evaluator",
    )
    wave92.put(R, r1, "registry_sha256")
    t1 = wave92.trans(r0, r1)
    wave92.put(T, t1, "transition_sha256")
    a1 = wave92.auth(t1, r0, E)
    wave92.put(A, a1, "authorization_sha256")

    assert "eval-truth" in t1["removed_evaluator_ids"]
    assert bridge_id in t1["added_evaluator_ids"]
    assert wave92.apply(
        runtime,
        t1["transition_sha256"],
        a1["authorization_sha256"],
        E,
        R,
        T,
        A,
    ) == "COMMITTED"
    assert wave92.authority(runtime, R, E) == "AUTHORITATIVE"

    # Generation 2 re-adds the *exact old evaluator object* from generation 0.
    # Because the evaluator ID was absent in generation 1, Wave 92 classifies it
    # as ADD, not REPLACE. The ADD validator requires predecessor=None, which the
    # old genesis evaluator already has, so the historical identity is accepted.
    entries2 = dict(r1["evaluator_entries"])
    entries2.pop(bridge_id)
    entries2["eval-truth"] = original_truth_sha
    assign2 = dict(r1["root_assignments"])
    assign2["truth"] = "eval-truth"

    r2 = wave92.reg(
        2,
        r1["registry_sha256"],
        entries2,
        assign2,
        "MIXED",
        "resurrect exact historical truth evaluator",
    )
    wave92.put(R, r2, "registry_sha256")
    t2 = wave92.trans(r1, r2)
    wave92.put(T, t2, "transition_sha256")

    # The reusable semantic transition resolver accepts the resurrection.
    resolved_t2, resolved_old, resolved_new = wave92.rtrans(
        t2["transition_sha256"], T, R, E
    )
    assert resolved_t2["transition_sha256"] == t2["transition_sha256"]
    assert resolved_old["registry_sha256"] == r1["registry_sha256"]
    assert resolved_new["registry_sha256"] == r2["registry_sha256"]
    assert "eval-truth" in t2["added_evaluator_ids"]
    assert bridge_id in t2["removed_evaluator_ids"]
    assert E[original_truth_sha]["predecessor_evaluator_sha256"] is None

    a2 = wave92.auth(t2, r1, E)
    wave92.put(A, a2, "authorization_sha256")
    result2 = wave92.apply(
        runtime,
        t2["transition_sha256"],
        a2["authorization_sha256"],
        E,
        R,
        T,
        A,
    )
    assert result2 == "COMMITTED", result2
    assert wave92.authority(runtime, R, E) == "AUTHORITATIVE"
    assert R[runtime["cur"]]["evaluator_entries"]["eval-truth"] == original_truth_sha

    print(
        json.dumps(
            {
                "verdict": "FAIL_REMOVED_EVALUATOR_IDENTITY_CAN_BE_RESURRECTED_AS_ADD",
                "builder_wave92_head": "f94d563fe5339316e3362bccf988e83c950f161d",
                "control_initial_authority": "AUTHORITATIVE",
                "generation1_removed_original_evaluator": "eval-truth" in t1["removed_evaluator_ids"],
                "generation1_commit": "COMMITTED",
                "generation2_transition_classifies_historical_identity_as_add": "eval-truth" in t2["added_evaluator_ids"],
                "generation2_exact_historical_evaluator_sha256": original_truth_sha,
                "historical_evaluator_predecessor_is_none": original_truth["predecessor_evaluator_sha256"] is None,
                "semantic_transition_resolver_accepted_resurrection": True,
                "generation2_commit": result2,
                "final_authority": wave92.authority(runtime, R, E),
                "final_registry_uses_exact_generation0_evaluator_identity": R[runtime["cur"]]["evaluator_entries"]["eval-truth"] == original_truth_sha,
                "hash_collision_required": False,
                "store_key_body_substitution_required": False,
                "target_self_authorization_required": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
