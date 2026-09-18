#!/usr/bin/env python3
"""AXM Flowing Compute Wave 133: exact rotation-bootstrap crash recovery.

Experimental lane only / NON-CANON / no automatic merge.

Wave 132 added predecessor-authorized response-key rotation, but its first
rotation-metadata bootstrap used an existence-only guard: once the
``response_rotation`` directory existed, bootstrap was treated as done. A hard
kill after directory creation or any early genesis publication could therefore
leave an exact legitimate anchor permanently stuck even though all intended
genesis bytes are derivable from already-validated Wave-131 identity.

Wave 133 makes only that bootstrap boundary recoverable. It records an exact
bootstrap intent bound to the Wave-131 manifest/readiness bytes and the pinned
anchor/witness identity, writes or matches each deterministic genesis artifact,
and publishes a bootstrap-ready receipt last. Missing exact artifacts may be
resumed; any mismatched artifact, unexpected pre-ready evolution, or missing
bootstrap receipt after rotation evolution fails closed. Existing bytes are
never silently rewritten to make them fit.

Truth boundary: this is same-host Linux/process/filesystem crash recovery for
rotation bootstrap. It does not provide cross-host uniqueness, root/kernel or
authority-UID resistance, hardware key custody, whole-domain rollback
resistance, provider/physical finality, or any speed/energy/retained/
incremental/dormant-compute/throughput/scaling claim.
"""
from __future__ import annotations

import json
import os
import stat
import time
from pathlib import Path

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS as w
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ANCHORED as w126
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_AUTHENTICATED_ANCHOR as protocol
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_AUTHORITY_BOUNDARY as w130
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_INIT_RECOVERY as w131
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_ROTATION as w132

BOOTSTRAP_SCHEMA = "axm.flowing-compute.wave133-rotation-bootstrap.v1"
BOOTSTRAP_READY_SCHEMA = "axm.flowing-compute.wave133-rotation-bootstrap-ready.v1"
BOOTSTRAP_INTENT = "bootstrap.json"
BOOTSTRAP_READY = "bootstrap.ready.json"
FAULT_STAGES = {
    "directory",
    "intent",
    "genesis_public",
    "authority_lineage",
    "witness_lineage",
    "state",
    "ready",
}


def _canon_file(obj: dict) -> bytes:
    return w.canonical(obj) + b"\n"


def _sha(data: bytes) -> str:
    return w.sha256_hex(data)


def _pause_after(stage: str, fault_after: str | None, marker: str | Path | None) -> None:
    if fault_after is None:
        return
    if fault_after not in FAULT_STAGES:
        raise ValueError("wave133-unknown-fault-stage")
    if stage != fault_after:
        return
    if marker is None:
        raise ValueError("wave133-fault-marker-required")
    w._atomic_write(Path(marker), _canon_file({"stage": stage, "pid": os.getpid()}), 0o644)
    while True:
        time.sleep(1)


def _read_exact_json(path: Path, schema: str, fields: set[str]) -> dict:
    raw = path.read_bytes()
    try:
        obj = json.loads(raw)
    except Exception as exc:
        raise ValueError(f"wave133-json-invalid:{path.name}") from exc
    if not isinstance(obj, dict) or raw != _canon_file(obj):
        raise ValueError(f"wave133-json-not-canonical:{path.name}")
    if obj.get("schema") != schema or set(obj) != fields:
        raise ValueError(f"wave133-json-fields-or-schema-mismatch:{path.name}")
    return obj


def _assert_file(path: Path, uid: int, mode: int = 0o600) -> None:
    st = path.stat()
    if st.st_uid != uid:
        raise PermissionError(f"wave133-owner-mismatch:{path.name}")
    if stat.S_IMODE(st.st_mode) != mode:
        raise PermissionError(f"wave133-mode-mismatch:{path.name}")


def _write_or_match(path: Path, data: bytes, uid: int, mode: int = 0o600) -> None:
    if path.exists():
        _assert_file(path, uid, mode)
        if path.read_bytes() != data:
            raise ValueError(f"wave133-existing-artifact-mismatch:{path.name}")
        return
    w._atomic_write(path, data, mode)
    _assert_file(path, uid, mode)


def _bootstrap_intent(anchor_dir: Path, root: dict, genesis_public: bytes) -> dict:
    manifest_bytes = (anchor_dir / w131.MANIFEST).read_bytes()
    ready_bytes = (anchor_dir / w131.READY).read_bytes()
    state0 = _canon_file(w132._state_for(0, w132.ZERO, protocol._public_fingerprint(genesis_public), None))
    return {
        "schema": BOOTSTRAP_SCHEMA,
        "anchor_credential_fingerprint": root["anchor_credential_fingerprint"],
        "witness_credential_fingerprint": root["witness_credential_fingerprint"],
        "witness_root_sha": root["witness_root_sha"],
        "genesis_response_public_fingerprint": protocol._public_fingerprint(genesis_public),
        "genesis_response_public_sha256": _sha(genesis_public),
        "wave131_manifest_sha256": _sha(manifest_bytes),
        "wave131_ready_sha256": _sha(ready_bytes),
        "genesis_state_sha256": _sha(state0),
    }


def _bootstrap_ready(intent: dict, genesis_public: bytes) -> dict:
    return {
        "schema": BOOTSTRAP_READY_SCHEMA,
        "bootstrap_intent_sha256": _sha(_canon_file(intent)),
        "genesis_response_public_sha256": _sha(genesis_public),
        "genesis_authority_lineage_sha256": _sha(b""),
        "genesis_witness_lineage_sha256": _sha(b""),
        "genesis_state_sha256": intent["genesis_state_sha256"],
    }


def _intent_fields() -> set[str]:
    return {
        "schema",
        "anchor_credential_fingerprint",
        "witness_credential_fingerprint",
        "witness_root_sha",
        "genesis_response_public_fingerprint",
        "genesis_response_public_sha256",
        "wave131_manifest_sha256",
        "wave131_ready_sha256",
        "genesis_state_sha256",
    }


def _ready_fields() -> set[str]:
    return {
        "schema",
        "bootstrap_intent_sha256",
        "genesis_response_public_sha256",
        "genesis_authority_lineage_sha256",
        "genesis_witness_lineage_sha256",
        "genesis_state_sha256",
    }


def _validate_bootstrap_receipt(anchor_dir: Path, witness_dir: Path) -> dict:
    authority_uid, _ = w130._assert_separate_authority_uid()
    rd = anchor_dir / w132.ROT_DIR
    if not rd.is_dir():
        raise RuntimeError("wave133-rotation-dir-missing")
    st = rd.stat()
    if st.st_uid != authority_uid or stat.S_IMODE(st.st_mode) != 0o700:
        raise PermissionError("wave133-rotation-dir-boundary-invalid")

    root, _, _ = w126.load_anchor_identity(anchor_dir)
    manifest = w131._load_json_exact(anchor_dir / w131.MANIFEST, w131.MANIFEST_SCHEMA)
    initial_ready = w131._load_json_exact(anchor_dir / w131.READY, w131.READY_SCHEMA)

    intent_path = rd / BOOTSTRAP_INTENT
    ready_path = rd / BOOTSTRAP_READY
    genesis_path = rd / w132.GENESIS_PUBLIC
    for path in (intent_path, ready_path, genesis_path):
        _assert_file(path, authority_uid)

    intent = _read_exact_json(intent_path, BOOTSTRAP_SCHEMA, _intent_fields())
    genesis = genesis_path.read_bytes()
    expected_intent = _bootstrap_intent(anchor_dir, root, genesis)
    if intent != expected_intent:
        raise ValueError("wave133-bootstrap-intent-provenance-mismatch")

    expected_initial_ready = w131._ready_for(manifest, root, genesis)
    if initial_ready != expected_initial_ready:
        raise ValueError("wave133-wave131-readiness-genesis-mismatch")

    ready = _read_exact_json(ready_path, BOOTSTRAP_READY_SCHEMA, _ready_fields())
    if ready != _bootstrap_ready(intent, genesis):
        raise ValueError("wave133-bootstrap-ready-mismatch")

    return {
        "bootstrap_intent_sha256": _sha(_canon_file(intent)),
        "genesis_response_public_fingerprint": intent["genesis_response_public_fingerprint"],
        "anchor_credential_fingerprint": root["anchor_credential_fingerprint"],
        "witness_credential_fingerprint": root["witness_credential_fingerprint"],
    }


def _pre_ready_has_evolution(rd: Path, witness_dir: Path) -> bool:
    lineage = rd / w132.LINEAGE
    witness_lineage = witness_dir / w132.WITNESS_LINEAGE
    if lineage.exists() and lineage.read_bytes() != b"":
        return True
    if witness_lineage.exists() and witness_lineage.read_bytes() != b"":
        return True
    if any((rd / name).exists() for name in (
        w132.PENDING, w132.PENDING_PRIVATE, w132.PENDING_PUBLIC, w132.PENDING_CERT
    )):
        return True
    for path in rd.glob("public-*.pem"):
        if path.name != w132.GENESIS_PUBLIC:
            return True
    return False


def ensure_rotation_bootstrap(anchor_dir: str | Path, witness_dir: str | Path, *,
                              fault_after: str | None = None,
                              fault_marker: str | Path | None = None) -> dict:
    """Create or exactly resume deterministic Wave-132 genesis metadata.

    Recovery is allowed only while no rotation evolution exists. Existing
    artifacts must byte-match the deterministic genesis derived from the
    already-validated Wave-131 identity; mismatches are retained and rejected.
    """
    ad, wd = Path(anchor_dir), Path(witness_dir)
    authority_uid, _ = w130._assert_separate_authority_uid()
    rd = ad / w132.ROT_DIR

    if rd.exists() and (rd / BOOTSTRAP_READY).exists():
        out = _validate_bootstrap_receipt(ad, wd)
        return {**out, "recovered": False, "already_ready": True}

    if rd.exists() and _pre_ready_has_evolution(rd, wd):
        raise RuntimeError("wave133-bootstrap-receipt-missing-after-evolution")

    # Before rotation evolution, Wave-131 is the exact source of bootstrap truth.
    base = w131.validate_initialized_anchor(ad)
    root, _, _ = w126.load_anchor_identity(ad)
    genesis = (ad / protocol.PUBLIC_KEY).read_bytes()
    if protocol._public_fingerprint(genesis) != base["response_public_fingerprint"]:
        raise ValueError("wave133-bootstrap-public-mismatch")
    intent = _bootstrap_intent(ad, root, genesis)
    state0 = _canon_file(w132._state_for(0, w132.ZERO, protocol._public_fingerprint(genesis), None))
    ready = _bootstrap_ready(intent, genesis)

    if not rd.exists():
        rd.mkdir(mode=0o700)
        os.chown(rd, authority_uid, authority_uid)
        os.chmod(rd, 0o700)
        w._fsync_dir(ad)
    st = rd.stat()
    if st.st_uid != authority_uid or stat.S_IMODE(st.st_mode) != 0o700:
        raise PermissionError("wave133-rotation-dir-boundary-invalid")
    _pause_after("directory", fault_after, fault_marker)

    allowed = {
        BOOTSTRAP_INTENT, BOOTSTRAP_READY, w132.GENESIS_PUBLIC,
        w132.LINEAGE, w132.STATE,
    }
    unexpected = sorted(p.name for p in rd.iterdir() if p.name not in allowed)
    if unexpected:
        raise RuntimeError("wave133-unexpected-pre-ready-artifacts:" + ",".join(unexpected))

    _write_or_match(rd / BOOTSTRAP_INTENT, _canon_file(intent), authority_uid)
    _pause_after("intent", fault_after, fault_marker)

    _write_or_match(rd / w132.GENESIS_PUBLIC, genesis, authority_uid)
    _pause_after("genesis_public", fault_after, fault_marker)

    _write_or_match(rd / w132.LINEAGE, b"", authority_uid)
    _pause_after("authority_lineage", fault_after, fault_marker)

    witness_lineage = wd / w132.WITNESS_LINEAGE
    _write_or_match(witness_lineage, b"", authority_uid)
    _pause_after("witness_lineage", fault_after, fault_marker)

    _write_or_match(rd / w132.STATE, state0, authority_uid)
    _pause_after("state", fault_after, fault_marker)

    _write_or_match(rd / BOOTSTRAP_READY, _canon_file(ready), authority_uid)
    _pause_after("ready", fault_after, fault_marker)

    out = _validate_bootstrap_receipt(ad, wd)
    baseline = w132.validate_rotation_state(ad, wd)
    if baseline["seq"] != 0 or baseline["head_rotation_sha"] != w132.ZERO:
        raise ValueError("wave133-bootstrap-baseline-not-genesis")
    return {**out, "recovered": True, "already_ready": False}


def rotate_response_key(anchor_dir: str | Path, witness_dir: str | Path,
                        rotation_id: str, *,
                        bootstrap_fault_after: str | None = None,
                        bootstrap_fault_marker: str | Path | None = None,
                        rotation_fault_after: str | None = None,
                        rotation_fault_marker: str | Path | None = None) -> dict:
    ensure_rotation_bootstrap(
        anchor_dir, witness_dir,
        fault_after=bootstrap_fault_after,
        fault_marker=bootstrap_fault_marker,
    )
    return w132.rotate_response_key(
        anchor_dir, witness_dir, rotation_id,
        fault_after=rotation_fault_after,
        fault_marker=rotation_fault_marker,
    )


def validate_rotation_state(anchor_dir: str | Path, witness_dir: str | Path) -> dict:
    boot = _validate_bootstrap_receipt(Path(anchor_dir), Path(witness_dir))
    state = w132.validate_rotation_state(anchor_dir, witness_dir)
    return {**state, "wave133_bootstrap": boot}


def serve_anchor(anchor_dir: str | Path, witness_dir: str | Path,
                 socket_path: str | Path, ready_file: str | Path | None = None,
                 error_file: str | Path | None = None,
                 allow_fault: bool = False) -> int:
    try:
        validate_rotation_state(anchor_dir, witness_dir)
    except BaseException as exc:
        w126._write_error(error_file, exc)
        return 2
    return w132.serve_anchor(anchor_dir, witness_dir, socket_path, ready_file, error_file, allow_fault)


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="AXM Flowing Compute Wave 133 rotation bootstrap recovery")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("rotate")
    r.add_argument("anchor_dir")
    r.add_argument("witness_dir")
    r.add_argument("rotation_id")
    r.add_argument("--bootstrap-fault-after", choices=sorted(FAULT_STAGES))
    r.add_argument("--bootstrap-fault-marker")
    v = sub.add_parser("validate")
    v.add_argument("anchor_dir")
    v.add_argument("witness_dir")
    b = sub.add_parser("bootstrap")
    b.add_argument("anchor_dir")
    b.add_argument("witness_dir")
    b.add_argument("--fault-after", choices=sorted(FAULT_STAGES))
    b.add_argument("--fault-marker")
    args = p.parse_args()
    if args.cmd == "rotate":
        out = rotate_response_key(
            args.anchor_dir, args.witness_dir, args.rotation_id,
            bootstrap_fault_after=args.bootstrap_fault_after,
            bootstrap_fault_marker=args.bootstrap_fault_marker,
        )
    elif args.cmd == "bootstrap":
        out = ensure_rotation_bootstrap(
            args.anchor_dir, args.witness_dir,
            fault_after=args.fault_after, fault_marker=args.fault_marker,
        )
    else:
        out = validate_rotation_state(args.anchor_dir, args.witness_dir)
    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
