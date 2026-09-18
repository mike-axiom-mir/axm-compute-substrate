from __future__ import annotations

import gc
import hashlib
import json
import math
import os
import platform
import statistics
import time
from pathlib import Path
from typing import Any

try:
    import psutil
except Exception:  # pragma: no cover - optional evidence surface
    psutil = None

SCHEMA = "axm.flowing-compute-receipt/v0.1"
ENVELOPE_SCHEMA = "axm.retained-state-envelope/v0.1"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        while True:
            part = fh.read(chunk)
            if not part:
                break
            h.update(part)
    return h.hexdigest()


def file_identity(path: Path, role: str = "source") -> dict[str, Any]:
    path = Path(path).resolve()
    st = path.stat()
    return {
        "role": role,
        "path": str(path),
        "bytes": st.st_size,
        "sha256": sha256_file(path),
        "generation_token": {"size": st.st_size, "mtime_ns": st.st_mtime_ns},
    }


def source_set_identity(items: list[dict[str, Any]], inline: dict[str, Any] | None = None) -> dict[str, Any]:
    inline = inline or {}
    normalized = {
        "files": [
            {"role": i["role"], "path": i["path"], "bytes": i["bytes"], "sha256": i["sha256"]}
            for i in items
        ],
        "inline": inline,
    }
    return {
        "files": items,
        "inline": inline,
        "set_sha256": sha256_bytes(canonical_bytes(normalized)),
        "identity_strength": "sha256-content-identity",
    }



def make_retained_envelope(state_payload: Any, source_identity: dict[str, Any], producer: str, semantic_contract: str) -> dict[str, Any]:
    if not source_identity.get("set_sha256"):
        raise ValueError("source identity requires set_sha256")
    payload_bytes = canonical_bytes(state_payload)
    envelope = {
        "schema": ENVELOPE_SCHEMA,
        "producer": producer,
        "semantic_contract": semantic_contract,
        "source_set_sha256": source_identity["set_sha256"],
        "state_payload": state_payload,
        "state_payload_sha256": sha256_bytes(payload_bytes),
        "state_payload_bytes": len(payload_bytes),
    }
    envelope["envelope_sha256"] = sha256_bytes(canonical_bytes(envelope))
    return envelope


def validate_retained_envelope(envelope: dict[str, Any], current_source_identity: dict[str, Any]) -> Any:
    if envelope.get("schema") != ENVELOPE_SCHEMA:
        raise ValueError("unsupported retained-state envelope schema")
    if envelope.get("source_set_sha256") != current_source_identity.get("set_sha256"):
        raise ValueError("retained state is stale for current source generation")
    payload = envelope.get("state_payload")
    payload_bytes = canonical_bytes(payload)
    if sha256_bytes(payload_bytes) != envelope.get("state_payload_sha256"):
        raise ValueError("retained state payload integrity mismatch")
    if len(payload_bytes) != int(envelope.get("state_payload_bytes", -1)):
        raise ValueError("retained state payload byte count mismatch")
    return payload

def _rss() -> int | None:
    if psutil is None:
        return None
    return int(psutil.Process(os.getpid()).memory_info().rss)


def _median(rows: list[dict[str, Any]], field: str) -> float:
    return float(statistics.median([int(r[field]) for r in rows]))


def _percent_saved(cold: float, flow: float) -> float | None:
    if cold <= 0:
        return None
    return (cold - flow) / cold * 100.0


def _ratio(cold: float, flow: float) -> float | None:
    if flow <= 0:
        return None
    return cold / flow


def run_receipt(adapter: Any, trials: int = 3) -> dict[str, Any]:
    """Run a generic cold-vs-retained-state comparison.

    Adapter contract:
      id, title, units, setup_boundary_complete
      source_files() -> list[(Path, role)]
      inline_source_identity() -> JSON-able dict (optional)
      cold() -> JSON-able output evidence
      setup() -> retained state
      flow(state) -> JSON-able output evidence
      retained_state(state) -> dict (optional)
      freshness_contract() -> dict (optional)

    Timings intentionally exclude receipt hashing/bookkeeping. Flow total includes
    setup + service. Exact output-equivalence is mandatory.
    """
    if trials < 1:
        raise ValueError("trials must be >= 1")
    units = int(adapter.units)
    if units < 1:
        raise ValueError("adapter.units must be >= 1")

    files = [file_identity(Path(p), role) for p, role in adapter.source_files()]
    inline = adapter.inline_source_identity() if hasattr(adapter, "inline_source_identity") else {}
    source = source_set_identity(files, inline)
    rows: list[dict[str, Any]] = []
    reference_digest: str | None = None
    retained_observation: dict[str, Any] = {}

    for idx in range(trials):
        order = ["cold", "flow"] if idx % 2 == 0 else ["flow", "cold"]
        row: dict[str, Any] = {"trial": idx + 1, "order": order}
        for mode in order:
            gc.collect()
            before_rss = _rss()
            if mode == "cold":
                c0 = time.process_time_ns(); w0 = time.perf_counter_ns()
                output = adapter.cold()
                cpu = time.process_time_ns() - c0; wall = time.perf_counter_ns() - w0
                after_rss = _rss()
                row[mode] = {
                    "cpu_ns": cpu,
                    "wall_ns": wall,
                    "rss_before": before_rss,
                    "rss_after": after_rss,
                }
            else:
                total_c0 = time.process_time_ns(); total_w0 = time.perf_counter_ns()
                setup_c0 = time.process_time_ns(); setup_w0 = time.perf_counter_ns()
                state = adapter.setup()
                setup_cpu = time.process_time_ns() - setup_c0
                setup_wall = time.perf_counter_ns() - setup_w0
                rss_after_setup = _rss()
                service_c0 = time.process_time_ns(); service_w0 = time.perf_counter_ns()
                output = adapter.flow(state)
                service_cpu = time.process_time_ns() - service_c0
                service_wall = time.perf_counter_ns() - service_w0
                total_cpu = time.process_time_ns() - total_c0
                total_wall = time.perf_counter_ns() - total_w0
                after_rss = _rss()
                retained_observation = adapter.retained_state(state) if hasattr(adapter, "retained_state") else {}
                row[mode] = {
                    "cpu_ns": total_cpu,
                    "wall_ns": total_wall,
                    "setup_cpu_ns": setup_cpu,
                    "setup_wall_ns": setup_wall,
                    "service_cpu_ns": service_cpu,
                    "service_wall_ns": service_wall,
                    "rss_before": before_rss,
                    "rss_after_setup": rss_after_setup,
                    "rss_after_service": after_rss,
                }
                del state

            digest = sha256_bytes(canonical_bytes(output))
            row[mode]["output_sha256"] = digest
            if reference_digest is None:
                reference_digest = digest
            if digest != reference_digest:
                raise RuntimeError(f"output equivalence failed in trial {idx + 1} mode {mode}")
            del output
        rows.append(row)

    cold = [r["cold"] for r in rows]
    flow = [r["flow"] for r in rows]
    cold_cpu = _median(cold, "cpu_ns")
    cold_wall = _median(cold, "wall_ns")
    flow_cpu = _median(flow, "cpu_ns")
    flow_wall = _median(flow, "wall_ns")
    setup_cpu = _median(flow, "setup_cpu_ns")
    service_cpu = _median(flow, "service_cpu_ns")

    cold_per_unit = cold_cpu / units
    service_per_unit = service_cpu / units
    boundary_complete = bool(getattr(adapter, "setup_boundary_complete", False))
    break_even = None
    if boundary_complete and cold_per_unit > service_per_unit:
        break_even = max(1, int(math.ceil(setup_cpu / (cold_per_unit - service_per_unit))))

    freshness = adapter.freshness_contract() if hasattr(adapter, "freshness_contract") else {
        "mode": "not-declared",
        "checked_during_probe": False,
    }

    receipt = {
        "schema": SCHEMA,
        "receipt_id": f"{adapter.id}-{source['set_sha256'][:12]}",
        "subject": {
            "id": adapter.id,
            "title": adapter.title,
            "units": units,
            "trials": trials,
            "host": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "machine": platform.machine(),
            },
        },
        "source_identity": source,
        "equivalence": {
            "contract": getattr(adapter, "equivalence_contract", "exact canonical output evidence"),
            "passed": True,
            "output_sha256": reference_digest,
        },
        "cold": {
            "cpu_median_ns": cold_cpu,
            "wall_median_ns": cold_wall,
            "cpu_per_unit_ns": cold_per_unit,
        },
        "flowing": {
            "cpu_median_ns": flow_cpu,
            "wall_median_ns": flow_wall,
            "setup_cpu_median_ns": setup_cpu,
            "service_cpu_median_ns": service_cpu,
            "service_cpu_per_unit_ns": service_per_unit,
            "setup_boundary_complete": boundary_complete,
            "retained_state": retained_observation,
            "reuse_count": units,
        },
        "freshness": freshness,
        "derived": {
            "cpu_saved_percent_vs_cold": _percent_saved(cold_cpu, flow_cpu),
            "useful_yield_multiplier_vs_cold": _ratio(cold_cpu, flow_cpu),
            "estimated_setup_break_even_units": break_even,
            "estimate_withheld_reason": None if break_even is not None else (
                "setup boundary is incomplete/lazy" if not boundary_complete else "flow service cost is not below cold per-unit cost"
            ),
        },
        "trials": rows,
        "truth": {
            "same_output_required": True,
            "source_generation_named": True,
            "timing_excludes_receipt_hashing_and_evidence_serialization": True,
            "cpu_time_is_not_direct_energy_measurement": True,
            "positive_yield_does_not_mean_compute_or_energy_from_nothing": True,
            "single_host_result": True,
            "generalization_not_proven": True,
        },
    }
    receipt["receipt_sha256"] = sha256_bytes(canonical_bytes(receipt))
    return receipt


def validate_receipt(receipt: dict[str, Any]) -> None:
    if receipt.get("schema") != SCHEMA:
        raise ValueError("unsupported receipt schema")
    if not receipt.get("equivalence", {}).get("passed"):
        raise ValueError("receipt does not prove equivalent output")
    if not receipt.get("source_identity", {}).get("set_sha256"):
        raise ValueError("receipt lacks source identity")
    cold = float(receipt.get("cold", {}).get("cpu_median_ns", 0))
    flow = float(receipt.get("flowing", {}).get("cpu_median_ns", 0))
    if cold <= 0 or flow <= 0:
        raise ValueError("receipt lacks positive measured CPU timings")


def write_receipt(path: Path, receipt: dict[str, Any]) -> Path:
    validate_receipt(receipt)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
