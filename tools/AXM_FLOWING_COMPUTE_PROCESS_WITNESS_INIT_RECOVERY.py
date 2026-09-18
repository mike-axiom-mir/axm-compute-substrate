#!/usr/bin/env python3
"""AXM Flowing Compute Wave 131: exact-provenance crash-recoverable anchor init.

Experimental lane only / NON-CANON / no automatic merge.

Wave 130 moved the durable response private key behind a distinct Unix uid, but
it deliberately refused any non-empty partially initialized anchor directory.
That is safe, yet a hard kill during initialization can leave exact durable
identity material that is neither serveable nor retryable.

Wave 131 adds an explicit initialization transaction manifest and final readiness
receipt. Recovery is allowed only when every durable artifact that already
exists matches the exact manifest-bound witness identity, authority/worker uid
boundary, anchor id, cryptographic derivations, and response binding. Missing
artifacts may be completed from already-authenticated durable material; existing
artifacts are never silently replaced. Ambiguous, mismatched, unexpected, or
public-without-private leftovers fail closed.

A completed store must carry an exact readiness receipt before it may serve.
Hard-kill tests pause only after named durable publication points; a kill inside
_atomic_write itself can leave a temporary file and remains deliberately
fail-closed rather than being guessed away.

Fresh independent verifier PR #55 did not falsify Wave 130, but it could not run
its unprivileged user-namespace uid-alias attack because the GitHub runner's
AppArmor policy returned EPERM. Wave 131 therefore does not upgrade the uid
boundary into a host-wide or cross-namespace claim. That boundary remains open.

No speed, energy, retained/incremental/dormant-compute, throughput, scaling,
provider-finality, physical-finality, merge, or CANON claim is made.
"""
from __future__ import annotations

import hmac
import json
import os
import secrets
import stat
import time
from pathlib import Path

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS as w
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ANCHORED as w126
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_AUTHENTICATED_ANCHOR as protocol
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_CUSTODY as w128
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_LIFECYCLE as w129
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_AUTHORITY_BOUNDARY as w130
from AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_AUTHORITY_BOUNDARY import *  # noqa: F401,F403

MANIFEST = "init_manifest.json"
READY = "init_ready.json"
MANIFEST_SCHEMA = "axm.flowing-compute.wave131-init-manifest.v1"
READY_SCHEMA = "axm.flowing-compute.wave131-init-ready.v1"
PRIVATE_KEY = protocol.PRIVATE_KEY
PUBLIC_KEY = protocol.PUBLIC_KEY
WITNESS_PUBLIC_KEY = protocol.WITNESS_PUBLIC_KEY
WITNESS_BINDING = protocol.WITNESS_BINDING

FAULT_STAGES = {
    "manifest",
    "anchor_credential",
    "root",
    "response_private",
    "response_public",
    "witness_public",
    "witness_binding",
    "ready",
}

ANCHOR_INIT_FILES = {
    MANIFEST,
    READY,
    "credential.bin",
    "witness_credential.bin",
    "root.json",
    "ledger.jsonl",
    PRIVATE_KEY,
    PUBLIC_KEY,
}
ANCHOR_RUNTIME_FILES = ANCHOR_INIT_FILES | {"serve.lock"}

SOURCE = {
    "wave130_evidence_head": "08701ae0cee15007a37f0edd8d01f61f6aa2ab22",
    "wave130_tested_source_commit": "d5f3cbc678559b139d7b622ecbbacd3987fdac65",
    "wave130_tool_blob": "17241b23bc7104410ae39c4ebfa258d32cd934f1",
    "wave130_selftest_blob": "630504c9768293e7e53ef3ce91e70cb4b4f58434",
    "wave130_ci_run": 35313219079,
    "wave130_artifact_sha256": "7f73004c895df5f17f791a9a8306e3408c452a824bbe2cf40489261d0523cccd",
    "verifier_pr": 55,
    "verifier_head": "2a661f428b51a3a4f677412e8f51f3bae28a4ec9",
    "verifier_tested_head": "1e942411959d919cc627a12ebaa9c15468d758a2",
    "verifier_ci_run": 35314687612,
    "verifier_artifact_digest": "7fd7eab5f34a15d283cf3d79af879cbb67f8c7116451131279206171c0d6dbed",
    "verifier_result": "userns-alias-attempt-environment-blocked-not-falsified",
}


def _canon_file(obj: dict) -> bytes:
    return w.canonical(obj) + b"\n"


def _assert_private_path(path: Path, owner_uid: int, mode: int = 0o600) -> None:
    st = path.stat()
    if st.st_uid != owner_uid:
        raise PermissionError(f"wave131-owner-mismatch:{path.name}")
    if stat.S_IMODE(st.st_mode) != mode:
        raise PermissionError(f"wave131-mode-mismatch:{path.name}")


def _prepare_anchor_dir(anchor_dir: str | Path) -> tuple[Path, int, int]:
    authority_uid, worker_uid = w130._assert_separate_authority_uid()
    ad = Path(anchor_dir)
    if not ad.exists():
        ad.mkdir(parents=True, mode=0o700)
    st = ad.stat()
    if not stat.S_ISDIR(st.st_mode):
        raise ValueError("wave131-anchor-store-not-directory")
    if st.st_uid != authority_uid:
        raise PermissionError("wave131-anchor-store-owner-mismatch")
    os.chmod(ad, 0o700)
    if stat.S_IMODE(ad.stat().st_mode) != 0o700:
        raise PermissionError("wave131-anchor-store-mode-mismatch")
    return ad, authority_uid, worker_uid


def _reject_unexpected(ad: Path, *, runtime: bool = False) -> None:
    allowed = ANCHOR_RUNTIME_FILES if runtime else ANCHOR_INIT_FILES
    unexpected = sorted(p.name for p in ad.iterdir() if p.name not in allowed)
    if unexpected:
        raise RuntimeError("wave131-unexpected-anchor-artifact:" + ",".join(unexpected))


def _pause_after(stage: str, fault_after: str | None, fault_marker: str | Path | None) -> None:
    if fault_after is None:
        return
    if fault_after not in FAULT_STAGES:
        raise ValueError("wave131-unknown-init-fault-stage")
    if stage != fault_after:
        return
    if fault_marker is None:
        raise ValueError("wave131-fault-marker-required")
    marker = Path(fault_marker)
    w._atomic_write(marker, _canon_file({"stage": stage, "pid": os.getpid()}), 0o644)
    while True:
        time.sleep(1)


def _write_missing_exact(path: Path, data: bytes, mode: int = 0o600) -> bool:
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"wave131-existing-artifact-mismatch:{path.name}")
        if stat.S_IMODE(path.stat().st_mode) != mode:
            raise PermissionError(f"wave131-existing-artifact-mode-mismatch:{path.name}")
        return False
    w._atomic_write(path, data, mode)
    return True


def _load_json_exact(path: Path, schema: str | None = None) -> dict:
    raw = path.read_bytes()
    try:
        obj = json.loads(raw)
    except Exception as exc:
        raise ValueError(f"wave131-json-invalid:{path.name}") from exc
    if not isinstance(obj, dict):
        raise ValueError(f"wave131-json-not-object:{path.name}")
    if raw != _canon_file(obj):
        raise ValueError(f"wave131-json-not-canonical:{path.name}")
    if schema is not None and obj.get("schema") != schema:
        raise ValueError(f"wave131-schema-mismatch:{path.name}")
    return obj


def _current_witness(witness_dir: str | Path) -> tuple[dict, bytes, str]:
    root, secret = w.load_identity(witness_dir)
    return root, secret, w126._root_sha(root)


def _expected_manifest(anchor_id: str, authority_uid: int, worker_uid: int,
                       witness_root: dict, witness_root_sha: str,
                       init_id: str) -> dict:
    return {
        "schema": MANIFEST_SCHEMA,
        "init_id": init_id,
        "anchor_id": anchor_id,
        "authority_uid": authority_uid,
        "forbidden_worker_uid": worker_uid,
        "witness_credential_fingerprint": witness_root["credential_fingerprint"],
        "witness_root_sha": witness_root_sha,
    }


def _validate_manifest(manifest: dict, anchor_id: str, authority_uid: int,
                       worker_uid: int, witness_root: dict,
                       witness_root_sha: str) -> None:
    expected_keys = {
        "schema", "init_id", "anchor_id", "authority_uid",
        "forbidden_worker_uid", "witness_credential_fingerprint",
        "witness_root_sha",
    }
    if set(manifest) != expected_keys:
        raise ValueError("wave131-init-manifest-fields-mismatch")
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError("wave131-init-manifest-schema-mismatch")
    init_id = manifest.get("init_id")
    if not isinstance(init_id, str) or len(init_id) != 64:
        raise ValueError("wave131-init-id-invalid")
    try:
        bytes.fromhex(init_id)
    except Exception as exc:
        raise ValueError("wave131-init-id-invalid") from exc
    checks = {
        "anchor_id": anchor_id,
        "authority_uid": authority_uid,
        "forbidden_worker_uid": worker_uid,
        "witness_credential_fingerprint": witness_root["credential_fingerprint"],
        "witness_root_sha": witness_root_sha,
    }
    for key, expected in checks.items():
        if manifest.get(key) != expected:
            raise ValueError(f"wave131-init-manifest-provenance-mismatch:{key}")


def _root_for(anchor_id: str, anchor_secret: bytes,
              witness_root: dict, witness_root_sha: str) -> dict:
    return {
        "schema": w126.SCHEMA_ANCHOR_ROOT,
        "anchor_id": anchor_id,
        "anchor_credential_fingerprint": w126.anchor_credential_fingerprint(anchor_secret),
        "witness_credential_fingerprint": witness_root["credential_fingerprint"],
        "witness_root_sha": witness_root_sha,
    }


def _response_public_from_private(private_pem: bytes) -> bytes:
    public = w128._run_openssl_private(["pkey", "-pubout"], private_pem)
    if b"BEGIN PUBLIC KEY" not in public:
        raise ValueError("wave131-derived-response-public-key-invalid")
    return public


def _binding_for(root: dict, response_public: bytes) -> dict:
    return {
        "schema": protocol.RESPONSE_BINDING_SCHEMA,
        "anchor_credential_fingerprint": root["anchor_credential_fingerprint"],
        "response_public_fingerprint": protocol._public_fingerprint(response_public),
    }


def _ready_for(manifest: dict, root: dict, response_public: bytes) -> dict:
    return {
        "schema": READY_SCHEMA,
        "init_id": manifest["init_id"],
        "manifest_sha": w.sha256_hex(w.canonical(manifest)),
        "anchor_root_sha": w.sha256_hex(w.canonical(root)),
        "anchor_credential_fingerprint": root["anchor_credential_fingerprint"],
        "witness_credential_fingerprint": root["witness_credential_fingerprint"],
        "witness_root_sha": root["witness_root_sha"],
        "response_public_fingerprint": protocol._public_fingerprint(response_public),
        "authority_uid": manifest["authority_uid"],
        "forbidden_worker_uid": manifest["forbidden_worker_uid"],
    }


def _validate_internal_ready(anchor_dir: str | Path, *, runtime: bool = False) -> dict:
    ad, authority_uid, worker_uid = _prepare_anchor_dir(anchor_dir)
    _reject_unexpected(ad, runtime=runtime)
    manifest_path = ad / MANIFEST
    ready_path = ad / READY
    if not manifest_path.exists() or not ready_path.exists():
        raise RuntimeError("wave131-anchor-initialization-not-ready")
    _assert_private_path(manifest_path, authority_uid)
    _assert_private_path(ready_path, authority_uid)
    manifest = _load_json_exact(manifest_path, MANIFEST_SCHEMA)
    if manifest.get("authority_uid") != authority_uid or manifest.get("forbidden_worker_uid") != worker_uid:
        raise PermissionError("wave131-ready-uid-boundary-mismatch")

    root, anchor_secret, witness_secret = w126.load_anchor_identity(ad)
    if root.get("anchor_id") != manifest.get("anchor_id"):
        raise ValueError("wave131-ready-anchor-id-mismatch")
    if root.get("anchor_credential_fingerprint") != w126.anchor_credential_fingerprint(anchor_secret):
        raise ValueError("wave131-ready-anchor-secret-mismatch")
    if root.get("witness_credential_fingerprint") != w.credential_fingerprint(witness_secret):
        raise ValueError("wave131-ready-witness-secret-mismatch")
    if root.get("witness_credential_fingerprint") != manifest.get("witness_credential_fingerprint"):
        raise ValueError("wave131-ready-witness-fingerprint-mismatch")
    if root.get("witness_root_sha") != manifest.get("witness_root_sha"):
        raise ValueError("wave131-ready-witness-root-mismatch")

    private_path = ad / PRIVATE_KEY
    public_path = ad / PUBLIC_KEY
    _assert_private_path(private_path, authority_uid)
    _assert_private_path(public_path, authority_uid)
    private_pem = private_path.read_bytes()
    public_pem = public_path.read_bytes()
    if _response_public_from_private(private_pem) != public_pem:
        raise ValueError("wave131-ready-response-keypair-mismatch")

    expected_ready = _ready_for(manifest, root, public_pem)
    ready = _load_json_exact(ready_path, READY_SCHEMA)
    if not hmac.compare_digest(_canon_file(ready), _canon_file(expected_ready)):
        raise ValueError("wave131-readiness-receipt-mismatch")
    w126.load_anchor_ledger(ad, root, anchor_secret, witness_secret)
    boundary = w130.durable_key_boundary_status(ad)
    return {
        "root": root,
        "manifest": manifest,
        "ready": ready,
        "response_public_fingerprint": expected_ready["response_public_fingerprint"],
        "wave130_durable_key_boundary": boundary,
    }


def initialize_anchor_dir(anchor_dir: str | Path, witness_dir: str | Path,
                          anchor_id: str = "wave131-anchor",
                          fault_after: str | None = None,
                          fault_marker: str | Path | None = None) -> dict:
    """Create or exactly resume one anchor initialization transaction."""
    w129._enter_initializer_custody_boundary()
    ad, authority_uid, worker_uid = _prepare_anchor_dir(anchor_dir)
    wd = Path(witness_dir)
    witness_root, witness_secret, witness_root_sha = _current_witness(wd)
    _reject_unexpected(ad)

    manifest_path = ad / MANIFEST
    if manifest_path.exists():
        _assert_private_path(manifest_path, authority_uid)
        manifest = _load_json_exact(manifest_path, MANIFEST_SCHEMA)
        _validate_manifest(
            manifest, anchor_id, authority_uid, worker_uid,
            witness_root, witness_root_sha,
        )
    else:
        if any(ad.iterdir()):
            raise RuntimeError("wave131-partial-anchor-without-manifest")
        if (wd / WITNESS_PUBLIC_KEY).exists() or (wd / WITNESS_BINDING).exists():
            raise RuntimeError("wave131-witness-publication-without-init-manifest")
        manifest = _expected_manifest(
            anchor_id, authority_uid, worker_uid,
            witness_root, witness_root_sha, secrets.token_hex(32),
        )
        w._atomic_write(manifest_path, _canon_file(manifest), 0o600)
    _pause_after("manifest", fault_after, fault_marker)

    if (ad / READY).exists():
        complete = _validate_internal_ready(ad)
        _validate_manifest(
            complete["manifest"], anchor_id, authority_uid, worker_uid,
            witness_root, witness_root_sha,
        )
        binding, _ = protocol.load_response_binding(
            wd, complete["root"]["anchor_credential_fingerprint"]
        )
        if binding["response_public_fingerprint"] != complete["response_public_fingerprint"]:
            raise ValueError("wave131-ready-witness-binding-mismatch")
        return {
            **complete["root"],
            "response_public_fingerprint": complete["response_public_fingerprint"],
            "wave130_durable_key_boundary": complete["wave130_durable_key_boundary"],
            "wave131_init_recovery": {
                "schema": READY_SCHEMA,
                "init_id": complete["manifest"]["init_id"],
                "ready": True,
                "idempotent": True,
            },
        }

    credential_path = ad / "credential.bin"
    root_path = ad / "root.json"
    witness_credential_path = ad / "witness_credential.bin"
    ledger_path = ad / "ledger.jsonl"

    if credential_path.exists():
        _assert_private_path(credential_path, authority_uid)
        anchor_secret = credential_path.read_bytes()
        if len(anchor_secret) != 32:
            raise ValueError("wave131-anchor-credential-length-invalid")
    else:
        if root_path.exists():
            raise RuntimeError("wave131-root-without-anchor-credential-ambiguous")
        anchor_secret = secrets.token_bytes(32)
        w._atomic_write(credential_path, anchor_secret, 0o600)
    _pause_after("anchor_credential", fault_after, fault_marker)

    if witness_credential_path.exists():
        _assert_private_path(witness_credential_path, authority_uid)
        if witness_credential_path.read_bytes() != witness_secret:
            raise ValueError("wave131-witness-credential-leftover-mismatch")
    else:
        w._atomic_write(witness_credential_path, witness_secret, 0o600)

    root = _root_for(anchor_id, anchor_secret, witness_root, witness_root_sha)
    _write_missing_exact(root_path, _canon_file(root), 0o600)
    _assert_private_path(root_path, authority_uid)
    if ledger_path.exists():
        _assert_private_path(ledger_path, authority_uid)
        if ledger_path.read_bytes() != b"":
            raise RuntimeError("wave131-partial-init-ledger-not-empty")
    else:
        w._atomic_write(ledger_path, b"", 0o600)
    _pause_after("root", fault_after, fault_marker)

    private_path = ad / PRIVATE_KEY
    public_path = ad / PUBLIC_KEY
    witness_public_path = wd / WITNESS_PUBLIC_KEY
    witness_binding_path = wd / WITNESS_BINDING

    if private_path.exists():
        _assert_private_path(private_path, authority_uid)
        private_pem = private_path.read_bytes()
        if b"BEGIN PRIVATE KEY" not in private_pem:
            raise ValueError("wave131-response-private-key-invalid")
        derived_public = _response_public_from_private(private_pem)
    else:
        if public_path.exists() or witness_public_path.exists() or witness_binding_path.exists():
            raise RuntimeError("wave131-publication-without-response-private-key-ambiguous")
        private_pem, derived_public = w128._generate_response_keypair_memfd()
        w._atomic_write(private_path, private_pem, 0o600)
    _pause_after("response_private", fault_after, fault_marker)

    if public_path.exists():
        _assert_private_path(public_path, authority_uid)
        public_pem = public_path.read_bytes()
        if public_pem != derived_public:
            raise ValueError("wave131-response-keypair-mismatch")
    else:
        public_pem = derived_public
        w._atomic_write(public_path, public_pem, 0o600)
    _pause_after("response_public", fault_after, fault_marker)

    if witness_public_path.exists():
        if witness_public_path.read_bytes() != public_pem:
            raise ValueError("wave131-witness-public-key-leftover-mismatch")
        if stat.S_IMODE(witness_public_path.stat().st_mode) != 0o600:
            raise PermissionError("wave131-witness-public-key-mode-mismatch")
    else:
        w._atomic_write(witness_public_path, public_pem, 0o600)
    _pause_after("witness_public", fault_after, fault_marker)

    binding = _binding_for(root, public_pem)
    _write_missing_exact(witness_binding_path, _canon_file(binding), 0o600)
    _pause_after("witness_binding", fault_after, fault_marker)

    loaded_root, loaded_anchor_secret, loaded_witness_secret = w126.load_anchor_identity(ad)
    if loaded_root != root:
        raise ValueError("wave131-loaded-root-mismatch")
    if loaded_anchor_secret != anchor_secret or loaded_witness_secret != witness_secret:
        raise ValueError("wave131-loaded-credential-mismatch")
    if w126.load_anchor_ledger(ad, root, anchor_secret, witness_secret):
        raise RuntimeError("wave131-initial-ledger-not-empty")
    loaded_binding, loaded_public_path = protocol.load_response_binding(
        wd, root["anchor_credential_fingerprint"]
    )
    if loaded_binding != binding or loaded_public_path.read_bytes() != public_pem:
        raise ValueError("wave131-loaded-response-binding-mismatch")

    ready = _ready_for(manifest, root, public_pem)
    w._atomic_write(ad / READY, _canon_file(ready), 0o600)
    _pause_after("ready", fault_after, fault_marker)

    complete = _validate_internal_ready(ad)
    return {
        **root,
        "response_public_fingerprint": complete["response_public_fingerprint"],
        "wave130_durable_key_boundary": complete["wave130_durable_key_boundary"],
        "wave131_init_recovery": {
            "schema": READY_SCHEMA,
            "init_id": manifest["init_id"],
            "ready": True,
            "idempotent": False,
        },
    }


def validate_initialized_anchor(anchor_dir: str | Path) -> dict:
    """Read-only validation used by the service gate and adversarial tests."""
    w129._enter_initializer_custody_boundary()
    return _validate_internal_ready(anchor_dir, runtime=True)


def serve_anchor(anchor_dir: str | Path, socket_path: str | Path,
                 ready_file: str | Path | None = None,
                 error_file: str | Path | None = None,
                 allow_fault: bool = False) -> int:
    """Do not expose the authenticated endpoint until Wave 131 is exactly ready."""
    try:
        validate_initialized_anchor(anchor_dir)
    except BaseException as exc:
        w126._write_error(error_file, exc)
        return 2
    return w130.serve_anchor(
        anchor_dir, socket_path, ready_file, error_file, allow_fault
    )


protocol.initialize_anchor_dir = initialize_anchor_dir
protocol.serve_anchor = serve_anchor
w130.initialize_anchor_dir = initialize_anchor_dir
w130.serve_anchor = serve_anchor


def __getattr__(name: str):
    return getattr(w130, name)


def main() -> int:
    return protocol.main()


if __name__ == "__main__":
    raise SystemExit(main())
