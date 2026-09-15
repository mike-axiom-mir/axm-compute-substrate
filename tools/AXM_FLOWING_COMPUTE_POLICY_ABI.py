from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REGISTRY_SCHEMA = "axm.flowing-compute-policy-registry/v0.2"
PROFILE_SCHEMA = "axm.flowing-compute-policy-profile/v0.1"
SUPPORTED_EVALUATORS = {"linear_cpu_models_v1", "retained_work_fraction_v1"}
SUPPORTED_DOMAINS = {"nearest_observed_surface_v1", "range_v1", "allowed_totals_v1", "unbounded_structural_v1"}


def _read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_registry(path: str | Path) -> dict[str, Any]:
    value = _read_json(path)
    if value.get("schema") != REGISTRY_SCHEMA:
        raise ValueError("unsupported policy registry schema")
    seen_contracts: set[str] = set()
    for item in value.get("profiles", []):
        contract_id = str(item.get("contract_id") or "")
        evaluator_kind = str(item.get("evaluator_kind") or "")
        profile_path = str(item.get("profile_path") or "")
        if not contract_id or not profile_path:
            raise ValueError("profile registration missing contract_id/profile_path")
        if contract_id in seen_contracts:
            raise ValueError("duplicate policy contract_id: " + contract_id)
        if evaluator_kind not in SUPPORTED_EVALUATORS:
            raise ValueError("unsupported evaluator_kind: " + evaluator_kind)
        seen_contracts.add(contract_id)
    return value


def resolve_registration(registry: dict[str,Any], contract_id: str) -> dict[str,Any]:
    matches = [item for item in registry.get("profiles", []) if item.get("contract_id") == contract_id]
    if len(matches) != 1:
        raise ValueError("HOLD: no unique exact policy registration for contract_id=" + contract_id)
    return matches[0]


def load_bound_profile(registry_path: str | Path, contract_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    registry_path = Path(registry_path)
    registry = load_registry(registry_path)
    registration = resolve_registration(registry, contract_id)
    profile = _read_json(registry_path.parent.parent / registration["profile_path"])
    if profile.get("schema") != PROFILE_SCHEMA:
        raise ValueError("unsupported policy profile schema")
    expected_profile_id = registration.get("profile_id")
    if expected_profile_id and profile.get("profile_id") != expected_profile_id:
        raise ValueError("policy profile_id mismatch")
    declared_contract = profile.get("contract_id")
    if declared_contract is not None and declared_contract != contract_id:
        raise ValueError("policy profile contract mismatch")
    return registration, profile


def _check_domain(registration: dict[str, Any], features: dict[str, float]) -> dict[str, Any]:
    domain = registration.get("domain") or {"kind": "unbounded_structural_v1"}
    kind = domain.get("kind")
    if kind not in SUPPORTED_DOMAINS:
        raise ValueError("HOLD: unsupported policy domain kind=" + str(kind))
    if kind == "unbounded_structural_v1":
        return {"kind": kind, "inside": True}
    if kind == "range_v1":
        for name, bounds in (domain.get("features") or {}).items():
            value = float(features[name])
            lo = float(bounds["min"])
            hi = float(bounds["max"])
            if value < lo or value > hi:
                raise ValueError(f"HOLD: feature {name}={value} outside measured range [{lo},{hi}]")
        return {"kind": kind, "inside": True}
    if kind == "allowed_totals_v1":
        total_name = str(domain.get("total_feature") or "total_work_units")
        total = float(features[total_name])
        allowed = [float(x) for x in domain.get("allowed_totals", [])]
        if total not in allowed:
            raise ValueError(f"HOLD: {total_name}={total} not in measured totals {allowed}")
        return {"kind": kind, "inside": True}
    if kind == "nearest_observed_surface_v1":
        feature_order = list(domain.get("feature_order") or [])
        points = list(domain.get("points") or [])
        max_delta = domain.get("max_abs_delta") or {}
        if not feature_order or not points:
            raise ValueError("HOLD: observed-surface domain lacks points")
        nearest = None
        nearest_score = None
        for point in points:
            deltas = {name: abs(float(features[name]) - float(point[name])) for name in feature_order}
            score = sum(deltas[name] / max(float(max_delta.get(name, 0.0)), 1e-12) for name in feature_order)
            if nearest_score is None or score < nearest_score:
                nearest_score = score
                nearest = {"point": point, "deltas": deltas}
        assert nearest is not None
        outside = [name for name in feature_order if nearest["deltas"][name] > float(max_delta.get(name, 0.0))]
        if outside:
            raise ValueError("HOLD: feature combination outside measured surface; nearest=" + json.dumps(nearest, sort_keys=True))
        return {"kind": kind, "inside": True, "nearest_observation": nearest}
    raise ValueError("HOLD: unsupported policy domain")


def _validate_feature_shape(required: list[str], features: dict[str, float]) -> None:
    missing = [name for name in required if name not in features]
    extra = [name for name in features if name not in required]
    if missing or extra:
        raise ValueError(f"feature contract mismatch missing={missing} extra={extra}")
    for name in required:
        value = float(features[name])
        if value < 0:
            raise ValueError("policy features must be non-negative")


def _linear_cost(model: dict[str, Any], features: dict[str, float]) -> float:
    total = float(model.get("intercept", 0.0))
    for name, value in features.items():
        total += float(model.get(name, 0.0)) * float(value)
    return total


def _decide_linear(profile: dict[str, Any], features: dict[str, float]) -> dict[str, Any]:
    required = list(profile.get("features") or [])
    _validate_feature_shape(required, features)
    models = profile.get("models") or {}
    global_cpu = _linear_cost(models.get("global_cpu_ns") or {}, features)
    incremental_cpu = _linear_cost(models.get("incremental_cpu_ns") or {}, features)
    if global_cpu <= 0 or incremental_cpu <= 0:
        raise ValueError("policy predicted non-positive CPU")
    advantage = (global_cpu - incremental_cpu) / global_cpu * 100.0
    band = float(profile.get("uncertainty_band_percent", 0.0))
    return {
        "decision": "incremental" if incremental_cpu < global_cpu else "global",
        "confidence": "uncertain" if abs(advantage) <= band else "clear",
        "predicted_global_cpu_ns": global_cpu,
        "predicted_incremental_cpu_ns": incremental_cpu,
        "predicted_incremental_advantage_percent": advantage,
        "uncertainty_band_percent": band,
    }


def _decide_retained_fraction(profile: dict[str, Any], features: dict[str, float]) -> dict[str, Any]:
    required = list(profile.get("features") or [])
    _validate_feature_shape(required, features)
    affected = float(features["affected_work_units"])
    total = float(features["total_work_units"])
    if total <= 0:
        raise ValueError("total_work_units must be positive")
    if affected > total:
        raise ValueError("affected_work_units cannot exceed total_work_units")
    invalidated_fraction = affected / total
    decision = "global" if affected >= total else "incremental"
    confidence = "uncertain" if affected >= total else "clear"
    return {
        "decision": decision,
        "confidence": confidence,
        "predicted_global_cpu_ns": None,
        "predicted_incremental_cpu_ns": None,
        "predicted_incremental_advantage_percent": None,
        "uncertainty_band_percent": float(profile.get("uncertainty_band_percent", 0.0)),
        "invalidated_fraction": invalidated_fraction,
    }


def decide(registry_path: str | Path, *, contract_id: str, features: dict[str, float]) -> dict[str, Any]:
    registration, profile = load_bound_profile(registry_path, contract_id)
    domain_evidence = _check_domain(registration, features)
    evaluator_kind = registration["evaluator_kind"]
    if evaluator_kind == "linear_cpu_models_v1":
        body = _decide_linear(profile, features)
    elif evaluator_kind == "retained_work_fraction_v1":
        body = _decide_retained_fraction(profile, features)
    else:
        raise ValueError("HOLD: unsupported evaluator_kind=" + str(evaluator_kind))
    return {
        "contract_id": contract_id,
        "profile_id": profile.get("profile_id"),
        "evaluator_kind": evaluator_kind,
        "features": features,
        "domain_evidence": domain_evidence,
        **body,
        "truth": {
            "exact_contract_binding": True,
            "profile_shape_not_forced_into_one_model_family": True,
            "prediction_not_proof": True,
            "equivalent_output_still_required": True,
            "unknown_contract_is_hold": True,
        },
    }
