from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ENVELOPE_SCHEMA = "axm.flowing-compute-dormant-state/v0.1"
RECEIPT_SCHEMA = "axm.flowing-compute-dormant-resume-receipt/v0.1"
VALIDATION_MODES = {"trusted_content_id", "stat_token", "rehash"}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: str | Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        while True:
            part = fh.read(chunk)
            if not part:
                break
            h.update(part)
    return h.hexdigest()


def generation_token(path: str | Path) -> dict[str, int]:
    st = Path(path).stat()
    return {"bytes": int(st.st_size), "mtime_ns": int(st.st_mtime_ns)}


def make_envelope(*, source_path: str | Path, state_payload: Any, semantic_contract: str, producer: str) -> dict[str, Any]:
    source = Path(source_path)
    payload_bytes = canonical_bytes(state_payload)
    value = {
        "schema": ENVELOPE_SCHEMA,
        "semantic_contract": semantic_contract,
        "producer": producer,
        "source": {
            "path_hint": source.name,
            "sha256": sha256_file(source),
            "generation_token": generation_token(source),
        },
        "state_payload": state_payload,
        "state_payload_sha256": sha256_bytes(payload_bytes),
        "state_payload_bytes": len(payload_bytes),
        "truth": {
            "state_is_derived_not_source": True,
            "trusted_content_id_requires_external_immutable_generation_identity": True,
            "stat_token_is_not_cryptographic_identity": True,
        },
    }
    value["envelope_sha256"] = sha256_bytes(canonical_bytes(value))
    return value


def validate_envelope(value: dict[str, Any]) -> None:
    if value.get("schema") != ENVELOPE_SCHEMA:
        raise ValueError("unsupported dormant-state envelope schema")
    stored = value.get("envelope_sha256")
    body = dict(value)
    body.pop("envelope_sha256", None)
    if sha256_bytes(canonical_bytes(body)) != stored:
        raise ValueError("dormant-state envelope integrity mismatch")
    payload_bytes = canonical_bytes(value.get("state_payload"))
    if sha256_bytes(payload_bytes) != value.get("state_payload_sha256"):
        raise ValueError("dormant-state payload integrity mismatch")
    if len(payload_bytes) != int(value.get("state_payload_bytes", -1)):
        raise ValueError("dormant-state payload byte count mismatch")


def resume(*, envelope: dict[str, Any], source_path: str | Path, validation_mode: str, trusted_source_sha256: str | None = None) -> tuple[Any, dict[str, Any]]:
    validate_envelope(envelope)
    if validation_mode not in VALIDATION_MODES:
        raise ValueError("unsupported validation mode")
    source = Path(source_path)
    expected_sha = envelope["source"]["sha256"]
    checked_bytes = 0
    identity_strength = "unknown"
    if validation_mode == "trusted_content_id":
        if not trusted_source_sha256:
            raise ValueError("trusted_content_id requires externally established source SHA-256")
        if trusted_source_sha256 != expected_sha:
            raise ValueError("trusted source generation mismatch")
        identity_strength = "external-content-addressed-generation"
    elif validation_mode == "stat_token":
        if generation_token(source) != envelope["source"]["generation_token"]:
            raise ValueError("source generation token mismatch")
        identity_strength = "freshness-token-only"
    else:
        checked_bytes = source.stat().st_size
        if sha256_file(source) != expected_sha:
            raise ValueError("source content hash mismatch")
        identity_strength = "sha256-content-identity"
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "semantic_contract": envelope["semantic_contract"],
        "source_sha256": expected_sha,
        "validation_mode": validation_mode,
        "identity_strength": identity_strength,
        "source_bytes_rehashed": checked_bytes,
        "state_payload_sha256": envelope["state_payload_sha256"],
        "state_payload_bytes": envelope["state_payload_bytes"],
        "resume_allowed": True,
        "truth": {
            "resume_does_not_prove_source_semantics": True,
            "stat_token_can_miss_adversarial_same_token_changes": True,
            "trusted_mode_depends_on_external_package_generation_proof": True,
            "rehash_mode_reads_entire_source": True,
        },
    }
    receipt["receipt_sha256"] = sha256_bytes(canonical_bytes(receipt))
    return envelope["state_payload"], receipt
