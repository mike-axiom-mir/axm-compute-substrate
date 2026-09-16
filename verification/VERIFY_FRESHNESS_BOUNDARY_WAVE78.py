from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import AXM_FLOWING_COMPUTE_FRESHNESS_BOUND_GENERATION as fg
import AXM_FLOWING_COMPUTE_VERIFICATION_FRESHNESS as vf


def verdict(callable_):
    try:
        callable_()
        return "ACCEPTED"
    except Exception as exc:
        return "REJECTED:" + type(exc).__name__ + ":" + str(exc)


def rehash_freshness(state):
    body = {k: v for k, v in state.items() if k != "state_sha256"}
    state["state_sha256"] = vf.digest(body)


def rehash_pointer(pointer):
    body = {k: v for k, v in pointer.items() if k != "pointer_sha256"}
    pointer["pointer_sha256"] = fg.digest(body)


def main():
    s0 = vf.start(
        contract_id="mesh",
        artifact_sha256="a" * 64,
        artifact_bytes=15137,
        proof_sha256="b" * 64,
        audited_sequence=0,
    )
    s1 = vf.advance(
        state=s0,
        sequence=1,
        mode="carried_immutable_proof",
        artifact_sha256="a" * 64,
        proof_sha256="b" * 64,
    )["state"]
    p1 = fg.make_pointer(
        sequence=1,
        generation_sha256="c" * 64,
        freshness={"mesh": s1},
    )

    results = {}
    results["baseline_valid_pointer"] = verdict(lambda: fg.validate_pointer(p1))

    outer_only = copy.deepcopy(p1)
    outer_only["freshness"]["mesh"]["last_strong_audit_sequence"] = 1
    rehash_pointer(outer_only)
    results["outer_only_rehash_nested_tamper"] = verdict(
        lambda: fg.validate_pointer(outer_only)
    )

    full_rehash = copy.deepcopy(p1)
    row = full_rehash["freshness"]["mesh"]
    row["last_strong_audit_sequence"] = 1
    row["carried_generations_since_audit"] = 0
    row["cumulative_bytes_not_rehashed"] = 0
    rehash_freshness(row)
    rehash_pointer(full_rehash)
    results["nested_plus_outer_rehash_forgery"] = verdict(
        lambda: fg.validate_pointer(full_rehash)
    )

    fake_audit = vf.advance(
        state=s0,
        sequence=1,
        mode="audited_reuse",
        artifact_sha256="a" * 64,
        proof_sha256="b" * 64,
    )["state"]
    fake_audit_pointer = fg.make_pointer(
        sequence=1,
        generation_sha256="c" * 64,
        freshness={"mesh": fake_audit},
    )
    results["audit_reset_without_audit_receipt"] = verdict(
        lambda: fg.validate_pointer(fake_audit_pointer)
    )

    dangling = copy.deepcopy(p1)
    dangling["generation_sha256"] = "not-a-generation-object"
    rehash_pointer(dangling)
    results["dangling_generation_identity"] = verdict(
        lambda: fg.validate_pointer(dangling)
    )

    empty = fg.make_pointer(
        sequence=999,
        generation_sha256="x",
        freshness={},
    )
    results["empty_freshness_contract_set"] = verdict(
        lambda: fg.validate_pointer(empty)
    )

    mismatch = copy.deepcopy(p1)
    mismatch["sequence"] = 2
    rehash_pointer(mismatch)
    results["freshness_sequence_mismatch"] = verdict(
        lambda: fg.validate_pointer(mismatch)
    )

    expected = {
        "baseline_valid_pointer": "ACCEPTED",
        "outer_only_rehash_nested_tamper": "REJECTED",
        "nested_plus_outer_rehash_forgery": "ACCEPTED",
        "audit_reset_without_audit_receipt": "ACCEPTED",
        "dangling_generation_identity": "ACCEPTED",
        "empty_freshness_contract_set": "ACCEPTED",
        "freshness_sequence_mismatch": "REJECTED",
    }
    normalized = {
        k: ("REJECTED" if v.startswith("REJECTED:") else v)
        for k, v in results.items()
    }
    print(json.dumps({"results": results, "expected_current_behavior": expected}, indent=2))
    if normalized != expected:
        raise SystemExit("current behavior changed; review verifier expectations")


if __name__ == "__main__":
    main()
