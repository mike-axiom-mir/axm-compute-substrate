from __future__ import annotations

import json
import tempfile
from pathlib import Path

from AXM_FLOWING_COMPUTE_POLICY_ABI import decide, load_registry


def write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    registry = {
        "schema": "axm.flowing-compute-policy-registry/v0.2",
        "profiles": [
            {
                "contract_id": "c.linear",
                "profile_id": "linear-profile",
                "profile_path": "calibration/linear.json",
                "evaluator_kind": "linear_cpu_models_v1",
            },
            {
                "contract_id": "c.fraction",
                "profile_id": "fraction-profile",
                "profile_path": "calibration/fraction.json",
                "evaluator_kind": "retained_work_fraction_v1",
            },
        ],
    }
    write(root / "calibration/REGISTRY.json", registry)
    write(
        root / "calibration/linear.json",
        {
            "schema": "axm.flowing-compute-policy-profile/v0.1",
            "profile_id": "linear-profile",
            "contract_id": "c.linear",
            "features": ["affected"],
            "models": {
                "global_cpu_ns": {"intercept": 100.0, "affected": 1.0},
                "incremental_cpu_ns": {"intercept": 10.0, "affected": 3.0},
            },
            "uncertainty_band_percent": 1.0,
        },
    )
    write(
        root / "calibration/fraction.json",
        {
            "schema": "axm.flowing-compute-policy-profile/v0.1",
            "profile_id": "fraction-profile",
            "features": ["affected_work_units", "total_work_units"],
            "uncertainty_band_percent": 1.0,
        },
    )

    loaded = load_registry(root / "calibration/REGISTRY.json")
    assert len(loaded["profiles"]) == 2
    assert decide(root / "calibration/REGISTRY.json", contract_id="c.linear", features={"affected": 10})["decision"] == "incremental"
    assert decide(root / "calibration/REGISTRY.json", contract_id="c.linear", features={"affected": 50})["decision"] == "global"
    assert decide(root / "calibration/REGISTRY.json", contract_id="c.fraction", features={"affected_work_units": 47, "total_work_units": 48})["decision"] == "incremental"
    assert decide(root / "calibration/REGISTRY.json", contract_id="c.fraction", features={"affected_work_units": 48, "total_work_units": 48})["decision"] == "global"

    try:
        decide(root / "calibration/REGISTRY.json", contract_id="unknown", features={})
        raise AssertionError("unknown contract should HOLD")
    except ValueError as exc:
        assert "HOLD" in str(exc)

    try:
        decide(root / "calibration/REGISTRY.json", contract_id="c.fraction", features={"affected_work_units": 49, "total_work_units": 48})
        raise AssertionError("affected > total should fail")
    except ValueError:
        pass

print("Policy ABI self-test passed 7 checks.")
