#!/usr/bin/env python3
"""AXM Flowing Compute Wave 132: predecessor-authorized response-key rotation.

Experimental lane only / NON-CANON / no automatic merge.

Wave 131 made dedicated-UID anchor initialization recoverable across named
SIGKILL publication points, but a ready anchor still had no legitimate way to
change its authenticated response key: replacing response_private/public or the
witness verifier directly either breaks the Wave-131 readiness receipt or turns
rotation into an unaudited provisioning rewrite.

Wave 132 adds an explicit, predecessor-authorized rotation lineage. The old
response key signs the exact successor public key, anchor/witness identity,
sequence, previous certificate hash, and caller-supplied rotation id before any
current trust pointer is advanced. The authority and witness keep byte-exact
copies of that certificate. Rotation is performed while holding the existing
anchor credential's same-host lifetime lease, so a live old signer cannot race
this writer in the tested Linux namespace. Named post-publication SIGKILL cuts
are resumable from the exact pending transaction; mismatches fail closed.

Truth boundary: the initial Wave-131 verifier remains a bootstrap/rollback root.
This does not establish cross-host key uniqueness, protect against root/kernel or
anchor-UID compromise, make an exportable private key hardware-bound, or solve
whole-domain rollback/provider/physical finality. Rotation bootstrap itself is
not claimed crash-atomic before its first transaction metadata exists. No
speed, energy, retained/incremental/dormant-compute, throughput, or scaling
claim is made.
"""
from __future__ import annotations

import base64
import hmac
import json
import os
import stat
import time
from pathlib import Path

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS as w
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ANCHORED as w126
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_AUTHENTICATED_ANCHOR as protocol
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_CUSTODY as w128
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_AUTHORITY_BOUNDARY as w130
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_INIT_RECOVERY as w131

ROTATION_SCHEMA = "axm.flowing-compute.wave132-response-key-rotation.v1"
STATE_SCHEMA = "axm.flowing-compute.wave132-response-key-state.v1"
WITNESS_LINEAGE = "anchor_response_rotation.jsonl"
ROT_DIR = "response_rotation"
LINEAGE = "lineage.jsonl"
STATE = "state.json"
GENESIS_PUBLIC = "public-000000.pem"
PENDING = "pending.json"
PENDING_PRIVATE = "pending_private.pem"
PENDING_PUBLIC = "pending_public.pem"
PENDING_CERT = "pending_cert.json"
ZERO = "0" * 64
FAULT_STAGES = {
    "pending", "authority_lineage", "witness_lineage", "successor_public",
    "authority_key", "witness_public", "witness_binding", "state",
}
SOURCE = {
    "wave131_evidence_head": "72b6cf04e8cbd1a8fc356bb47dca103fa1e39ffe",
    "wave131_ci_run": 35317693211,
    "wave131_artifact_sha256": "7aab5f6f032d748a0961721293c5603927313b3468c1df304685038085750aea",
    "wave131_tool_blob": "494315788092d690cd305811525b98fb080a5285",
    "wave131_impl_blob": "32c804ecfe899f11528ac87346bfc6b6266afae6",
    "wave131_selftest_blob": "799e17750d7270f4119f7eccf5d06a955f7894db",
}


def _canon_file(obj: dict) -> bytes:
    return w.canonical(obj) + b"\n"


def _cert_sha(cert: dict) -> str:
    return w.sha256_hex(w.canonical(cert))


def _public_fp(data: bytes) -> str:
    return protocol._public_fingerprint(data)


def _check_rotation_id(rotation_id: str) -> None:
    if not isinstance(rotation_id, str) or len(rotation_id) != 64:
        raise ValueError("wave132-rotation-id-invalid")
    try:
        bytes.fromhex(rotation_id)
    except Exception as exc:
        raise ValueError("wave132-rotation-id-invalid") from exc


def _assert_authority_private(path: Path, authority_uid: int, mode: int = 0o600) -> None:
    st = path.stat()
    if st.st_uid != authority_uid:
        raise PermissionError(f"wave132-owner-mismatch:{path.name}")
    if stat.S_IMODE(st.st_mode) != mode:
        raise PermissionError(f"wave132-mode-mismatch:{path.name}")


def _read_exact_json(path: Path, schema: str | None = None) -> dict:
    raw = path.read_bytes()
    try:
        obj = json.loads(raw)
    except Exception as exc:
        raise ValueError(f"wave132-json-invalid:{path.name}") from exc
    if not isinstance(obj, dict) or raw != _canon_file(obj):
        raise ValueError(f"wave132-json-not-canonical:{path.name}")
    if schema is not None and obj.get("schema") != schema:
        raise ValueError(f"wave132-schema-mismatch:{path.name}")
    return obj


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    raw = path.read_bytes()
    if raw and not raw.endswith(b"\n"):
        raise ValueError(f"wave132-jsonl-truncated:{path.name}")
    rows: list[dict] = []
    for line in raw.splitlines():
        try:
            obj = json.loads(line)
        except Exception as exc:
            raise ValueError(f"wave132-jsonl-invalid:{path.name}") from exc
        if w.canonical(obj) != line:
            raise ValueError(f"wave132-jsonl-not-canonical:{path.name}")
        rows.append(obj)
    return rows


def _pause_after(stage: str, fault_after: str | None, marker: str | Path | None) -> None:
    if fault_after is None:
        return
    if fault_after not in FAULT_STAGES:
        raise ValueError("wave132-unknown-fault-stage")
    if stage != fault_after:
        return
    if marker is None:
        raise ValueError("wave132-fault-marker-required")
    w._atomic_write(Path(marker), _canon_file({"stage": stage, "pid": os.getpid()}), 0o644)
    while True:
        time.sleep(1)


def _binding(anchor_fp: str, public_pem: bytes) -> dict:
    return {
        "schema": protocol.RESPONSE_BINDING_SCHEMA,
        "anchor_credential_fingerprint": anchor_fp,
        "response_public_fingerprint": _public_fp(public_pem),
    }


def _verify_cert(cert: dict, previous_public_path: Path, expected_seq: int,
                 expected_prev: str, root: dict) -> bytes:
    expected = {
        "schema", "seq", "prev_rotation_sha", "rotation_id",
        "anchor_credential_fingerprint", "witness_credential_fingerprint",
        "witness_root_sha", "old_response_public_fingerprint",
        "new_response_public_fingerprint", "new_response_public_pem_b64",
        "signature_algorithm", "predecessor_signature",
    }
    if set(cert) != expected or cert.get("schema") != ROTATION_SCHEMA:
        raise ValueError("wave132-certificate-fields-or-schema-mismatch")
    if cert.get("seq") != expected_seq or cert.get("prev_rotation_sha") != expected_prev:
        raise ValueError("wave132-certificate-chain-position-mismatch")
    _check_rotation_id(str(cert.get("rotation_id", "")))
    for key in (
        "anchor_credential_fingerprint", "witness_credential_fingerprint", "witness_root_sha"
    ):
        if cert.get(key) != root[key]:
            raise ValueError(f"wave132-certificate-identity-mismatch:{key}")
    previous_public = previous_public_path.read_bytes()
    if cert.get("old_response_public_fingerprint") != _public_fp(previous_public):
        raise ValueError("wave132-certificate-predecessor-fingerprint-mismatch")
    try:
        new_public = base64.b64decode(cert["new_response_public_pem_b64"], validate=True)
    except Exception as exc:
        raise ValueError("wave132-certificate-successor-public-invalid") from exc
    if b"BEGIN PUBLIC KEY" not in new_public or cert.get("new_response_public_fingerprint") != _public_fp(new_public):
        raise ValueError("wave132-certificate-successor-fingerprint-mismatch")
    if cert.get("signature_algorithm") != w128.SIGNATURE_ALGORITHM:
        raise ValueError("wave132-certificate-signature-algorithm-mismatch")
    unsigned = {k: cert[k] for k in (
        "schema", "seq", "prev_rotation_sha", "rotation_id",
        "anchor_credential_fingerprint", "witness_credential_fingerprint",
        "witness_root_sha", "old_response_public_fingerprint",
        "new_response_public_fingerprint", "new_response_public_pem_b64",
    )}
    if not w128._verify_memfd(previous_public_path, w.canonical(unsigned), cert["predecessor_signature"]):
        raise PermissionError("wave132-predecessor-signature-invalid")
    return new_public


def _state_for(seq: int, head: str, current_fp: str, rotation_id: str | None) -> dict:
    return {
        "schema": STATE_SCHEMA,
        "seq": seq,
        "head_rotation_sha": head,
        "current_response_public_fingerprint": current_fp,
        "last_rotation_id": rotation_id,
    }


def _ensure_bootstrap(anchor_dir: Path, witness_dir: Path) -> None:
    rd = anchor_dir / ROT_DIR
    if rd.exists():
        return
    base = w131.validate_initialized_anchor(anchor_dir)
    authority_uid, _ = w130._assert_separate_authority_uid()
    rd.mkdir(mode=0o700)
    os.chown(rd, authority_uid, authority_uid)
    os.chmod(rd, 0o700)
    current_public = (anchor_dir / protocol.PUBLIC_KEY).read_bytes()
    if _public_fp(current_public) != base["response_public_fingerprint"]:
        raise ValueError("wave132-bootstrap-public-mismatch")
    w._atomic_write(rd / GENESIS_PUBLIC, current_public, 0o600)
    w._atomic_write(rd / LINEAGE, b"", 0o600)
    witness_lineage = witness_dir / WITNESS_LINEAGE
    if witness_lineage.exists() and witness_lineage.read_bytes() != b"":
        raise RuntimeError("wave132-bootstrap-witness-lineage-not-empty")
    if not witness_lineage.exists():
        w._atomic_write(witness_lineage, b"", 0o600)
    w._atomic_write(
        rd / STATE,
        _canon_file(_state_for(0, ZERO, _public_fp(current_public), None)),
        0o600,
    )


def validate_authority_rotation_state(anchor_dir: str | Path) -> dict:
    """Validate the authority-owned half without needing worker-store access."""
    ad = Path(anchor_dir)
    authority_uid, worker_uid = w130._assert_separate_authority_uid()
    rd = ad / ROT_DIR
    if not rd.is_dir():
        raise RuntimeError("wave132-rotation-metadata-missing")
    if rd.stat().st_uid != authority_uid or stat.S_IMODE(rd.stat().st_mode) != 0o700:
        raise PermissionError("wave132-rotation-dir-boundary-invalid")

    root, anchor_secret, witness_secret = w126.load_anchor_identity(ad)
    w126.load_anchor_ledger(ad, root, anchor_secret, witness_secret)
    manifest = w131._load_json_exact(ad / w131.MANIFEST, w131.MANIFEST_SCHEMA)
    genesis_path = rd / GENESIS_PUBLIC
    _assert_authority_private(genesis_path, authority_uid)
    genesis = genesis_path.read_bytes()
    initial_ready = w131._load_json_exact(ad / w131.READY, w131.READY_SCHEMA)
    expected_initial = w131._ready_for(manifest, root, genesis)
    if not hmac.compare_digest(_canon_file(initial_ready), _canon_file(expected_initial)):
        raise ValueError("wave132-wave131-genesis-readiness-mismatch")

    authority_rows = _read_jsonl(rd / LINEAGE)
    prev_sha = ZERO
    prev_public_path = genesis_path
    current_public = genesis
    seen_ids: set[str] = set()
    for seq, cert in enumerate(authority_rows, 1):
        new_public = _verify_cert(cert, prev_public_path, seq, prev_sha, root)
        rid = cert["rotation_id"]
        if rid in seen_ids:
            raise ValueError("wave132-rotation-id-reused")
        seen_ids.add(rid)
        generation_path = rd / f"public-{seq:06d}.pem"
        _assert_authority_private(generation_path, authority_uid)
        if generation_path.read_bytes() != new_public:
            raise ValueError("wave132-generation-public-mismatch")
        prev_public_path = generation_path
        current_public = new_public
        prev_sha = _cert_sha(cert)

    current_public_path = ad / protocol.PUBLIC_KEY
    current_private_path = ad / protocol.PRIVATE_KEY
    _assert_authority_private(current_public_path, authority_uid)
    _assert_authority_private(current_private_path, authority_uid)
    if current_public_path.read_bytes() != current_public:
        raise ValueError("wave132-current-authority-public-mismatch")
    derived = w131._response_public_from_private(current_private_path.read_bytes())
    if derived != current_public:
        raise ValueError("wave132-current-authority-keypair-mismatch")

    state = _read_exact_json(rd / STATE, STATE_SCHEMA)
    expected_state = _state_for(
        len(authority_rows), prev_sha, _public_fp(current_public),
        authority_rows[-1]["rotation_id"] if authority_rows else None,
    )
    if state != expected_state:
        raise ValueError("wave132-state-lineage-mismatch")
    boundary = w130.durable_key_boundary_status(ad)
    return {
        "root": root,
        "authority_rows": authority_rows,
        "seq": len(authority_rows),
        "head_rotation_sha": prev_sha,
        "current_public": current_public,
        "current_response_public_fingerprint": _public_fp(current_public),
        "last_rotation_id": expected_state["last_rotation_id"],
        "authority_uid": authority_uid,
        "forbidden_worker_uid": worker_uid,
        "wave130_durable_key_boundary": boundary,
    }


def validate_rotation_state(anchor_dir: str | Path, witness_dir: str | Path) -> dict:
    wd = Path(witness_dir)
    authority = validate_authority_rotation_state(anchor_dir)
    root = authority["root"]
    authority_rows = authority["authority_rows"]
    witness_rows = _read_jsonl(wd / WITNESS_LINEAGE)
    if authority_rows != witness_rows:
        raise ValueError("wave132-authority-witness-lineage-mismatch")
    current_public = authority["current_public"]
    witness_public = (wd / protocol.WITNESS_PUBLIC_KEY).read_bytes()
    if witness_public != current_public:
        raise ValueError("wave132-current-witness-public-mismatch")
    binding = w131._load_json_exact(wd / protocol.WITNESS_BINDING, protocol.RESPONSE_BINDING_SCHEMA)
    if binding != _binding(root["anchor_credential_fingerprint"], current_public):
        raise ValueError("wave132-current-witness-binding-mismatch")
    return {k: v for k, v in authority.items() if k not in {"root", "authority_rows", "current_public"}} | {
        "root": root,
    }


def _load_pending(rd: Path, root: dict, rotation_id: str) -> tuple[dict, bytes, bytes, dict]:
    pending = _read_exact_json(rd / PENDING, ROTATION_SCHEMA)
    if pending.get("kind") != "pending" or pending.get("rotation_id") != rotation_id:
        raise ValueError("wave132-pending-rotation-id-mismatch")
    seq = pending.get("seq")
    if not isinstance(seq, int) or seq < 1:
        raise ValueError("wave132-pending-seq-invalid")
    private = (rd / PENDING_PRIVATE).read_bytes()
    public = (rd / PENDING_PUBLIC).read_bytes()
    if w131._response_public_from_private(private) != public:
        raise ValueError("wave132-pending-keypair-mismatch")
    if pending.get("new_response_public_fingerprint") != _public_fp(public):
        raise ValueError("wave132-pending-public-fingerprint-mismatch")
    cert = _read_exact_json(rd / PENDING_CERT, ROTATION_SCHEMA)
    if cert.get("rotation_id") != rotation_id or cert.get("seq") != seq:
        raise ValueError("wave132-pending-certificate-mismatch")
    return pending, private, public, cert


def _append_exact_once(path: Path, cert: dict, seq: int) -> None:
    rows = _read_jsonl(path)
    if len(rows) == seq:
        if rows[-1] != cert:
            raise ValueError(f"wave132-existing-lineage-entry-mismatch:{path.name}")
        return
    if len(rows) != seq - 1:
        raise ValueError(f"wave132-lineage-position-mismatch:{path.name}")
    w._append_fsync(path, w.canonical(cert) + b"\n")


def _write_or_match(path: Path, data: bytes, mode: int = 0o600) -> None:
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"wave132-existing-artifact-mismatch:{path.name}")
        return
    w._atomic_write(path, data, mode)


def rotate_response_key(anchor_dir: str | Path, witness_dir: str | Path,
                        rotation_id: str, *,
                        fault_after: str | None = None,
                        fault_marker: str | Path | None = None) -> dict:
    """Rotate once, or exactly resume/retry the same requested rotation id."""
    _check_rotation_id(rotation_id)
    ad, wd = Path(anchor_dir), Path(witness_dir)
    _ensure_bootstrap(ad, wd)
    rd = ad / ROT_DIR
    root, _, _ = w126.load_anchor_identity(ad)

    lease = w126._acquire_anchor_lease(root["anchor_credential_fingerprint"])
    try:
        pending_path = rd / PENDING
        if not pending_path.exists():
            current = validate_rotation_state(ad, wd)
            if current["last_rotation_id"] == rotation_id:
                return {**current, "idempotent": True, "rotation_id": rotation_id}
            seq = current["seq"] + 1
            prev_sha = current["head_rotation_sha"]
            old_public_path = rd / f"public-{seq - 1:06d}.pem"
            old_public = old_public_path.read_bytes()
            private, public = w128._generate_response_keypair_memfd()
            pending = {
                "schema": ROTATION_SCHEMA,
                "kind": "pending",
                "seq": seq,
                "prev_rotation_sha": prev_sha,
                "rotation_id": rotation_id,
                "anchor_credential_fingerprint": root["anchor_credential_fingerprint"],
                "witness_credential_fingerprint": root["witness_credential_fingerprint"],
                "witness_root_sha": root["witness_root_sha"],
                "old_response_public_fingerprint": _public_fp(old_public),
                "new_response_public_fingerprint": _public_fp(public),
            }
            unsigned = {
                "schema": ROTATION_SCHEMA,
                "seq": seq,
                "prev_rotation_sha": prev_sha,
                "rotation_id": rotation_id,
                "anchor_credential_fingerprint": root["anchor_credential_fingerprint"],
                "witness_credential_fingerprint": root["witness_credential_fingerprint"],
                "witness_root_sha": root["witness_root_sha"],
                "old_response_public_fingerprint": _public_fp(old_public),
                "new_response_public_fingerprint": _public_fp(public),
                "new_response_public_pem_b64": base64.b64encode(public).decode("ascii"),
            }
            signature = w128._sign_memfd(ad / protocol.PRIVATE_KEY, w.canonical(unsigned))
            cert = {
                **unsigned,
                "signature_algorithm": w128.SIGNATURE_ALGORITHM,
                "predecessor_signature": signature,
            }
            w._atomic_write(rd / PENDING_PRIVATE, private, 0o600)
            w._atomic_write(rd / PENDING_PUBLIC, public, 0o600)
            w._atomic_write(rd / PENDING_CERT, _canon_file(cert), 0o600)
            w._atomic_write(pending_path, _canon_file(pending), 0o600)
        pending, private, public, cert = _load_pending(rd, root, rotation_id)
        seq = pending["seq"]
        old_public_path = rd / f"public-{seq - 1:06d}.pem"
        expected_new = _verify_cert(cert, old_public_path, seq, pending["prev_rotation_sha"], root)
        if expected_new != public:
            raise ValueError("wave132-pending-successor-public-mismatch")
        _pause_after("pending", fault_after, fault_marker)

        _append_exact_once(rd / LINEAGE, cert, seq)
        _pause_after("authority_lineage", fault_after, fault_marker)
        _append_exact_once(wd / WITNESS_LINEAGE, cert, seq)
        _pause_after("witness_lineage", fault_after, fault_marker)

        generation = rd / f"public-{seq:06d}.pem"
        _write_or_match(generation, public)
        _pause_after("successor_public", fault_after, fault_marker)

        cur_pub = (ad / protocol.PUBLIC_KEY).read_bytes()
        old_pub = old_public_path.read_bytes()
        if cur_pub not in (old_pub, public):
            raise ValueError("wave132-authority-current-public-ambiguous")
        if cur_pub == old_pub:
            w._atomic_write(ad / protocol.PRIVATE_KEY, private, 0o600)
            w._atomic_write(ad / protocol.PUBLIC_KEY, public, 0o600)
        else:
            if w131._response_public_from_private((ad / protocol.PRIVATE_KEY).read_bytes()) != public:
                raise ValueError("wave132-authority-current-private-ambiguous")
        _pause_after("authority_key", fault_after, fault_marker)

        witness_public_path = wd / protocol.WITNESS_PUBLIC_KEY
        witness_public = witness_public_path.read_bytes()
        if witness_public not in (old_pub, public):
            raise ValueError("wave132-witness-current-public-ambiguous")
        if witness_public == old_pub:
            w._atomic_write(witness_public_path, public, 0o600)
        _pause_after("witness_public", fault_after, fault_marker)

        new_binding = _binding(root["anchor_credential_fingerprint"], public)
        binding_path = wd / protocol.WITNESS_BINDING
        current_binding = _read_exact_json(binding_path, protocol.RESPONSE_BINDING_SCHEMA)
        old_binding = _binding(root["anchor_credential_fingerprint"], old_pub)
        if current_binding not in (old_binding, new_binding):
            raise ValueError("wave132-witness-binding-ambiguous")
        if current_binding == old_binding:
            w._atomic_write(binding_path, _canon_file(new_binding), 0o600)
        _pause_after("witness_binding", fault_after, fault_marker)

        next_state = _state_for(seq, _cert_sha(cert), _public_fp(public), rotation_id)
        state_path = rd / STATE
        existing_state = _read_exact_json(state_path, STATE_SCHEMA)
        old_state = _state_for(seq - 1, pending["prev_rotation_sha"], _public_fp(old_pub),
                               None if seq == 1 else _read_jsonl(rd / LINEAGE)[seq - 2]["rotation_id"])
        if existing_state not in (old_state, next_state):
            raise ValueError("wave132-state-ambiguous")
        if existing_state == old_state:
            w._atomic_write(state_path, _canon_file(next_state), 0o600)
        _pause_after("state", fault_after, fault_marker)

        for name in (PENDING, PENDING_CERT, PENDING_PUBLIC, PENDING_PRIVATE):
            try:
                (rd / name).unlink()
            except FileNotFoundError:
                pass
        w._fsync_dir(rd)
        final = validate_rotation_state(ad, wd)
        return {**final, "idempotent": False, "rotation_id": rotation_id}
    finally:
        lease.close()


def serve_anchor(anchor_dir: str | Path, witness_dir: str | Path,
                 socket_path: str | Path, ready_file: str | Path | None = None,
                 error_file: str | Path | None = None,
                 allow_fault: bool = False) -> int:
    """Serve only after the authority-owned signed rotation lineage is valid."""
    try:
        validate_authority_rotation_state(anchor_dir)
    except BaseException as exc:
        w126._write_error(error_file, exc)
        return 2
    return w130._wave129_serve_anchor(
        anchor_dir, socket_path, ready_file, error_file, allow_fault
    )


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="AXM Flowing Compute Wave 132 response-key rotation")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("rotate")
    r.add_argument("anchor_dir")
    r.add_argument("witness_dir")
    r.add_argument("rotation_id")
    r.add_argument("--fault-after", choices=sorted(FAULT_STAGES))
    r.add_argument("--fault-marker")
    v = sub.add_parser("validate")
    v.add_argument("anchor_dir")
    v.add_argument("witness_dir")
    args = p.parse_args()
    if args.cmd == "rotate":
        out = rotate_response_key(
            args.anchor_dir, args.witness_dir, args.rotation_id,
            fault_after=args.fault_after, fault_marker=args.fault_marker,
        )
    else:
        out = validate_rotation_state(args.anchor_dir, args.witness_dir)
    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
