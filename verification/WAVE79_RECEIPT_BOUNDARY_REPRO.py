from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from AXM_FLOWING_COMPUTE_AUDIT_WORK_RECEIPT import digest, perform, validate as validate_receipt
from AXM_FLOWING_COMPUTE_RECEIPT_BOUND_PARTIAL_AUDIT import advance_with_receipts
from AXM_FLOWING_COMPUTE_VERIFICATION_FRESHNESS import start


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    report: dict[str, object] = {
        "schema": "axm.flowing-compute-verifier-wave79/v0.1",
        "checks": {},
        "truth": {
            "toctou_counterexample_is_synthetic_small_artifact": True,
            "committed_wave79_receipt_is_revalidated_without_rehashing_real_11mb_artifact": True,
            "validator_hash_integrity_is_not_actor_authentication": True,
        },
    }

    # 1) Revalidate the committed Wave 79 receipt against the exact predecessor
    # freshness state derivable from the receipt's public identity fields.
    receipt_path = ROOT / "evidence" / "FLOWING_COMPUTE_AUDIT_WORK_RECEIPT_WAVE79_RECEIPT.json"
    committed_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    predecessor = start(
        contract_id=committed_receipt["contract_id"],
        artifact_sha256=committed_receipt["expected_artifact_sha256"],
        artifact_bytes=int(committed_receipt["expected_artifact_bytes"]),
        proof_sha256=committed_receipt["proof_sha256"],
        audited_sequence=int(committed_receipt["sequence"]) - 1,
    )
    assert predecessor["state_sha256"] == committed_receipt["predecessor_state_sha256"]
    validate_receipt(
        receipt=committed_receipt,
        state=predecessor,
        sequence=int(committed_receipt["sequence"]),
    )
    report["checks"]["committed_wave79_receipt_revalidates"] = "PASS"

    # 2) TOCTOU: audit exact bytes, then mutate the artifact before freshness commit.
    # The receipt remains valid and the transition resets audit age to zero because
    # transition validation does not re-read or pin the artifact at commit time.
    original = (b"AXM-W79-TOCTOU-" * 512) + b"A"
    with tempfile.TemporaryDirectory() as td:
        artifact = Path(td) / "artifact.bin"
        artifact.write_bytes(original)
        state = start(
            contract_id="axm.verifier.toctou/v0.1",
            artifact_sha256=sha256_bytes(original),
            artifact_bytes=len(original),
            proof_sha256=sha256_bytes(b"verifier-proof"),
            audited_sequence=0,
        )
        audit_receipt = perform(
            state=state,
            sequence=1,
            artifact_path=artifact,
            chunk_bytes=1024,
        )
        assert audit_receipt["status"] == "AUDIT_PASS"

        mutated = bytearray(original)
        mutated[-1] ^= 0x01
        artifact.write_bytes(mutated)
        current_sha = sha256_bytes(artifact.read_bytes())
        assert current_sha != state["artifact_sha256"]

        transition = advance_with_receipts(
            freshness={state["contract_id"]: state},
            sequence=1,
            modes={state["contract_id"]: "audited_reuse"},
            audit_receipts={state["contract_id"]: audit_receipt},
        )
        assert transition["status"] == "ADVANCED"
        next_state = transition["freshness"][state["contract_id"]]
        assert next_state["last_strong_audit_sequence"] == 1
        assert next_state["carried_generations_since_audit"] == 0

        report["checks"]["post_audit_artifact_mutation_still_allows_age_zero_commit"] = {
            "status": "COUNTEREXAMPLE_REPRODUCED",
            "receipt_status": audit_receipt["status"],
            "expected_artifact_sha256": state["artifact_sha256"],
            "current_artifact_sha256_after_mutation": current_sha,
            "transition_status": transition["status"],
            "resulting_last_strong_audit_sequence": next_state["last_strong_audit_sequence"],
        }

    # 3) Benchmark/evidence semantics: fields not used by freshness authority can be
    # made internally impossible, rehashed, and still pass receipt validation.
    impossible = copy.deepcopy(committed_receipt)
    impossible["chunk_bytes"] = 1
    impossible["chunks_read"] = 1
    impossible["audit_cpu_ns"] = -1
    impossible["audit_wall_ns"] = -1
    body = dict(impossible)
    body.pop("receipt_sha256", None)
    impossible["receipt_sha256"] = digest(body)
    validate_receipt(
        receipt=impossible,
        state=predecessor,
        sequence=int(impossible["sequence"]),
    )
    report["checks"]["semantically_impossible_measurement_metadata_rehashes_and_validates"] = {
        "status": "COUNTEREXAMPLE_REPRODUCED",
        "chunk_bytes": impossible["chunk_bytes"],
        "chunks_read": impossible["chunks_read"],
        "bytes_read": impossible["bytes_read"],
        "audit_cpu_ns": impossible["audit_cpu_ns"],
        "audit_wall_ns": impossible["audit_wall_ns"],
    }

    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
