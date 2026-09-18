#!/usr/bin/env python3
"""AXM Flowing Compute Wave 136: recoverable pending transaction + lineage/cleanup.

Experimental lane only / NON-CANON / no automatic merge.

Wave 135 made post-pending current-key publication recoverable, but explicitly
left three rotation-transaction boundaries open: creation of the pending
transaction itself, in-place append of authority/witness lineage, and cleanup
of the pending files after the trust pointers have advanced.

Wave 136 closes a bounded same-host version of those gaps:
- a pre-commit pending candidate may be resumed from exact complete authority-
  owned bytes, while incomplete *uncommitted* private/certificate stages may be
  abandoned only when no pending commit, no lineage advance, and no trust-pointer
  advance exists;
- authority and witness lineage append are implemented as recoverable whole-file
  replacement from the exact predecessor bytes + exact signed certificate;
- post-commit pending cleanup is resumable and idempotent after SIGKILL.

This does not claim cross-host key uniqueness, root/kernel resistance, protection
from the authority UID, user-namespace identity, whole-domain rollback resistance,
hardware key custody, provider independence, physical finality, or any speed,
energy, retained/incremental/dormant-compute, throughput, or scaling result.
"""
from __future__ import annotations

import base64
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
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_ROTATION as w132
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ATOMIC_RECOVERY as w134
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ROTATION_PUBLICATION_RECOVERY as w135

SOURCE = {
    "wave135_evidence_head": "e486f7fd1383115f020f2c6d047ee2c63d91c6d7",
    "wave135_exact_green_source": "03cfcd0ceab3884796c28ed5d25fa8cc0f3b2c71",
    "wave135_tool_blob": "88a67b9fec7b519bb68a3d530ba3e7a051c7478d",
}

PENDING_TARGETS = {
    w132.PENDING_PRIVATE,
    w132.PENDING_PUBLIC,
    w132.PENDING_CERT,
    w132.PENDING,
}
LINEAGE_TARGETS = {"authority_lineage", "witness_lineage"}
ATOMIC_FAULT_STAGES = set(w134.ATOMIC_FAULT_STAGES)
CLEANUP_STAGES = {
    "cleanup_after_pending",
    "cleanup_after_pending_cert",
    "cleanup_after_pending_public",
    "cleanup_after_pending_private",
}
FAULT_STAGES = ATOMIC_FAULT_STAGES | CLEANUP_STAGES


def _canon_file(obj: dict) -> bytes:
    return w.canonical(obj) + b"\n"


def _pause(stage: str, fault_after: str | None, marker: str | Path | None) -> None:
    if fault_after is None or stage != fault_after:
        return
    if stage not in CLEANUP_STAGES:
        raise ValueError("wave136-unknown-cleanup-fault-stage")
    if marker is None:
        raise ValueError("wave136-fault-marker-required")
    mp = Path(marker)
    mp.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(mp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(fd, _canon_file({"stage": stage, "pid": os.getpid()}))
        os.fsync(fd)
    finally:
        os.close(fd)
    w._fsync_dir(mp.parent)
    while True:
        time.sleep(1)


def _current_mode_owner(path: Path) -> tuple[int, int]:
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode):
        raise PermissionError(f"wave136-target-not-regular:{path.name}")
    return st.st_uid, stat.S_IMODE(st.st_mode)


def _pending_paths(rd: Path) -> dict[str, Path]:
    return {
        w132.PENDING_PRIVATE: rd / w132.PENDING_PRIVATE,
        w132.PENDING_PUBLIC: rd / w132.PENDING_PUBLIC,
        w132.PENDING_CERT: rd / w132.PENDING_CERT,
        w132.PENDING: rd / w132.PENDING,
    }


def _atomic_residue(path: Path) -> list[Path]:
    return sorted([
        *w134._legacy_candidates(path),
        *w134._stage_candidates(path),
        *w135._legacy_candidates(path),
        *w135._stage_candidates(path),
    ])


def _all_pending_residue(rd: Path) -> list[Path]:
    out: list[Path] = []
    for p in _pending_paths(rd).values():
        if p.exists():
            out.append(p)
        out.extend(_atomic_residue(p))
    return sorted(set(out))


def _state_is_pristine_for_new_pending(ad: Path, wd: Path, rotation_id: str) -> dict:
    current = w135.validate_rotation_state(ad, wd)
    if current.get("last_rotation_id") == rotation_id:
        return current
    return current


def _build_pending(root: dict, current: dict, old_public: bytes, public: bytes,
                   rotation_id: str) -> dict:
    return {
        "schema": w132.ROTATION_SCHEMA,
        "kind": "pending",
        "seq": current["seq"] + 1,
        "prev_rotation_sha": current["head_rotation_sha"],
        "rotation_id": rotation_id,
        "anchor_credential_fingerprint": root["anchor_credential_fingerprint"],
        "witness_credential_fingerprint": root["witness_credential_fingerprint"],
        "witness_root_sha": root["witness_root_sha"],
        "old_response_public_fingerprint": w132._public_fp(old_public),
        "new_response_public_fingerprint": w132._public_fp(public),
    }


def _build_unsigned(root: dict, pending: dict, old_public: bytes, public: bytes) -> dict:
    return {
        "schema": w132.ROTATION_SCHEMA,
        "seq": pending["seq"],
        "prev_rotation_sha": pending["prev_rotation_sha"],
        "rotation_id": pending["rotation_id"],
        "anchor_credential_fingerprint": root["anchor_credential_fingerprint"],
        "witness_credential_fingerprint": root["witness_credential_fingerprint"],
        "witness_root_sha": root["witness_root_sha"],
        "old_response_public_fingerprint": w132._public_fp(old_public),
        "new_response_public_fingerprint": w132._public_fp(public),
        "new_response_public_pem_b64": base64.b64encode(public).decode("ascii"),
    }


def _validate_candidate_private(data: bytes) -> bytes:
    try:
        public = w131._response_public_from_private(data)
    except BaseException as exc:
        raise ValueError("wave136-pending-private-incomplete-or-invalid") from exc
    if b"BEGIN PUBLIC KEY" not in public:
        raise ValueError("wave136-pending-private-derived-public-invalid")
    return public


def _stage_bytes_if_single(path: Path) -> tuple[Path | None, bytes | None]:
    stages = [*w134._stage_candidates(path), *w134._legacy_candidates(path)]
    if not stages:
        return None, None
    if len(stages) != 1:
        raise RuntimeError(f"wave136-ambiguous-pending-stage:{path.name}")
    stage = stages[0]
    return stage, stage.read_bytes()


def _abandon_uncommitted_invalid_stage(path: Path, rd: Path, ad: Path, wd: Path,
                                      rotation_id: str) -> bool:
    """Drop only an invalid pre-commit stage when no trusted transition exists.

    This is not same-candidate recovery. The candidate never became a pending
    transaction: no pending.json, no lineage row, and no current trust pointer
    advanced. The self-test records that distinction explicitly.
    """
    if (rd / w132.PENDING).exists():
        return False
    current = w135.validate_rotation_state(ad, wd)
    if current.get("last_rotation_id") == rotation_id:
        return False
    stage, data = _stage_bytes_if_single(path)
    if stage is None:
        return False
    authority_uid, _ = w130._assert_separate_authority_uid()
    w134._assert_candidate(stage, authority_uid, 0o600)
    try:
        if path.name == w132.PENDING_PRIVATE:
            _validate_candidate_private(data or b"")
            return False
        if path.name == w132.PENDING_CERT:
            obj = json.loads(data or b"")
            if isinstance(obj, dict) and (data or b"") == _canon_file(obj):
                return False
    except Exception:
        stage.unlink()
        w._fsync_dir(rd)
        return True
    return False


def _recover_or_create_pending(ad: Path, wd: Path, rotation_id: str, *,
                               fault_target: str | None,
                               fault_after: str | None,
                               fault_marker: str | Path | None) -> tuple[dict, bytes, bytes, dict]:
    rd = ad / w132.ROT_DIR
    authority_uid, _ = w130._assert_separate_authority_uid()
    root, _, _ = w126.load_anchor_identity(ad)

    pending_path = rd / w132.PENDING
    if pending_path.exists():
        return w132._load_pending(rd, root, rotation_id)

    current = _state_is_pristine_for_new_pending(ad, wd, rotation_id)
    if current.get("last_rotation_id") == rotation_id:
        raise RuntimeError("wave136-rotation-already-complete")

    seq = current["seq"] + 1
    old_public_path = rd / f"public-{seq - 1:06d}.pem"
    old_public = old_public_path.read_bytes()

    private_path = rd / w132.PENDING_PRIVATE
    public_path = rd / w132.PENDING_PUBLIC
    cert_path = rd / w132.PENDING_CERT

    # If a crash left an incomplete uncommitted private stage, it cannot define
    # a committed identity. Remove only that authority-owned stage while all
    # trusted state is still at the predecessor generation.
    _abandon_uncommitted_invalid_stage(private_path, rd, ad, wd, rotation_id)

    if private_path.exists():
        w132._assert_authority_private(private_path, authority_uid)
        private = private_path.read_bytes()
        public = _validate_candidate_private(private)
    else:
        stage, staged = _stage_bytes_if_single(private_path)
        if stage is not None:
            w134._assert_candidate(stage, authority_uid, 0o600)
            try:
                public = _validate_candidate_private(staged or b"")
                private = staged or b""
                w134.recoverable_atomic_write(private_path, private, authority_uid, 0o600)
            except ValueError:
                # It is safe to start a new pre-commit candidate only because no
                # pending commit or lineage/trust-pointer advance exists.
                stage.unlink()
                w._fsync_dir(rd)
                private, public = w128._generate_response_keypair_memfd()
        else:
            private, public = w128._generate_response_keypair_memfd()

    pending = _build_pending(root, current, old_public, public, rotation_id)
    unsigned = _build_unsigned(root, pending, old_public, public)

    # Persist the secret candidate first. If killed during a partial write,
    # restart may abandon only that still-uncommitted candidate; once complete,
    # every later pending artifact is reconstructible from it.
    if not private_path.exists():
        target_fault = fault_after if fault_target == w132.PENDING_PRIVATE else None
        w134.recoverable_atomic_write(
            private_path, private, authority_uid, 0o600,
            fault_after=target_fault,
            fault_marker=fault_marker if target_fault else None,
        )

    # Public can be reconstructed exactly from the durable private candidate.
    if public_path.exists():
        w132._assert_authority_private(public_path, authority_uid)
        if public_path.read_bytes() != public:
            raise ValueError("wave136-pending-public-mismatch")
    else:
        target_fault = fault_after if fault_target == w132.PENDING_PUBLIC else None
        w134.recoverable_atomic_write(
            public_path, public, authority_uid, 0o600,
            fault_after=target_fault,
            fault_marker=fault_marker if target_fault else None,
        )

    # A complete certificate stage may be adopted only if it is canonical and
    # verifies under the predecessor. A partial uncommitted certificate stage is
    # discarded and re-signed; pending.json is still absent at this point.
    _abandon_uncommitted_invalid_stage(cert_path, rd, ad, wd, rotation_id)
    if cert_path.exists():
        cert = w132._read_exact_json(cert_path, w132.ROTATION_SCHEMA)
    else:
        stage, staged = _stage_bytes_if_single(cert_path)
        cert = None
        if stage is not None:
            w134._assert_candidate(stage, authority_uid, 0o600)
            try:
                obj = json.loads(staged or b"")
                if not isinstance(obj, dict) or (staged or b"") != _canon_file(obj):
                    raise ValueError("not-complete")
                w132._verify_cert(obj, old_public_path, seq, current["head_rotation_sha"], root)
                if obj.get("rotation_id") != rotation_id:
                    raise ValueError("wrong-rotation")
                cert = obj
                w134.recoverable_atomic_write(cert_path, staged or b"", authority_uid, 0o600)
            except Exception:
                stage.unlink()
                w._fsync_dir(rd)
                cert = None
        if cert is None:
            signature = w128._sign_memfd(ad / protocol.PRIVATE_KEY, w.canonical(unsigned))
            cert = {
                **unsigned,
                "signature_algorithm": w128.SIGNATURE_ALGORITHM,
                "predecessor_signature": signature,
            }
            target_fault = fault_after if fault_target == w132.PENDING_CERT else None
            w134.recoverable_atomic_write(
                cert_path, _canon_file(cert), authority_uid, 0o600,
                fault_after=target_fault,
                fault_marker=fault_marker if target_fault else None,
            )

    expected_new = w132._verify_cert(
        cert, old_public_path, seq, current["head_rotation_sha"], root
    )
    if expected_new != public:
        raise ValueError("wave136-pending-cert-public-mismatch")

    # Freeze the transaction identity last. Once this exists, all recovery must
    # preserve exact private/public/certificate bytes.
    target_fault = fault_after if fault_target == w132.PENDING else None
    w134.recoverable_atomic_write(
        pending_path, _canon_file(pending), authority_uid, 0o600,
        fault_after=target_fault,
        fault_marker=fault_marker if target_fault else None,
    )
    return w132._load_pending(rd, root, rotation_id)


def _append_exact_once_recoverable(path: Path, cert: dict, seq: int, *,
                                   fault_target: str | None,
                                   target_name: str,
                                   fault_after: str | None,
                                   fault_marker: str | Path | None) -> None:
    rows = w132._read_jsonl(path)
    line = w.canonical(cert) + b"\n"
    if len(rows) == seq:
        if rows[-1] != cert:
            raise ValueError(f"wave136-existing-lineage-entry-mismatch:{path.name}")
        return
    if len(rows) != seq - 1:
        raise ValueError(f"wave136-lineage-position-mismatch:{path.name}")
    owner, mode = _current_mode_owner(path)
    old = path.read_bytes()
    expected = old + line
    target_fault = fault_after if fault_target == target_name else None
    w135.recoverable_atomic_replace(
        path, expected, owner, mode,
        fault_after=target_fault,
        fault_marker=fault_marker if target_fault else None,
    )


def _cleanup_completed_pending(rd: Path, rotation_id: str, final: dict, *,
                               fault_after: str | None,
                               fault_marker: str | Path | None) -> None:
    """Delete only residue already proven to belong to the completed rotation."""
    paths = _pending_paths(rd)
    seq = final["seq"]
    current_public = (rd / f"public-{seq:06d}.pem").read_bytes()
    lineage = w132._read_jsonl(rd / w132.LINEAGE)
    if not lineage or lineage[-1].get("rotation_id") != rotation_id:
        raise ValueError("wave136-cleanup-lineage-rotation-mismatch")
    cert = lineage[-1]

    pp = paths[w132.PENDING_PRIVATE]
    if pp.exists():
        if _validate_candidate_private(pp.read_bytes()) != current_public:
            raise ValueError("wave136-cleanup-private-mismatch")
    pub = paths[w132.PENDING_PUBLIC]
    if pub.exists() and pub.read_bytes() != current_public:
        raise ValueError("wave136-cleanup-public-mismatch")
    cp = paths[w132.PENDING_CERT]
    if cp.exists() and w132._read_exact_json(cp, w132.ROTATION_SCHEMA) != cert:
        raise ValueError("wave136-cleanup-cert-mismatch")
    pend = paths[w132.PENDING]
    if pend.exists():
        pobj = w132._read_exact_json(pend, w132.ROTATION_SCHEMA)
        if pobj.get("rotation_id") != rotation_id or pobj.get("seq") != seq:
            raise ValueError("wave136-cleanup-pending-mismatch")

    ordered = [
        (w132.PENDING, "cleanup_after_pending"),
        (w132.PENDING_CERT, "cleanup_after_pending_cert"),
        (w132.PENDING_PUBLIC, "cleanup_after_pending_public"),
        (w132.PENDING_PRIVATE, "cleanup_after_pending_private"),
    ]
    for name, stage in ordered:
        p = paths[name]
        if p.exists():
            p.unlink()
            w._fsync_dir(rd)
        _pause(stage, fault_after, fault_marker)

    residue = _all_pending_residue(rd)
    if residue:
        raise RuntimeError(
            "wave136-pending-cleanup-residue:" + ",".join(p.name for p in residue)
        )


def rotate_response_key(anchor_dir: str | Path, witness_dir: str | Path,
                        rotation_id: str, *,
                        fault_target: str | None = None,
                        fault_after: str | None = None,
                        fault_marker: str | Path | None = None) -> dict:
    """Rotate once or exactly resume/retry the same rotation id."""
    w132._check_rotation_id(rotation_id)
    if fault_after is not None and fault_target is None and fault_after not in CLEANUP_STAGES:
        raise ValueError("wave136-fault-target-required")
    if fault_after is not None and fault_after not in FAULT_STAGES:
        raise ValueError("wave136-unknown-fault-stage")

    ad, wd = Path(anchor_dir), Path(witness_dir)
    w134.ensure_rotation_bootstrap(ad, wd)
    rd = ad / w132.ROT_DIR
    root, _, _ = w126.load_anchor_identity(ad)

    lease = w126._acquire_anchor_lease(root["anchor_credential_fingerprint"])
    try:
        # A cleanup crash happens only after the full trust state is committed.
        # If exact validation already proves this rotation current, finish only
        # exact matching residue and return idempotently.
        try:
            current = w135.validate_rotation_state(ad, wd)
        except Exception:
            current = None
        if current is not None and current.get("last_rotation_id") == rotation_id:
            _cleanup_completed_pending(
                rd, rotation_id, current,
                fault_after=fault_after if fault_after in CLEANUP_STAGES else None,
                fault_marker=fault_marker,
            )
            return {
                **current,
                "idempotent": True,
                "rotation_id": rotation_id,
                "wave136_recoverable_transaction": True,
            }

        pending, private, public, cert = _recover_or_create_pending(
            ad, wd, rotation_id,
            fault_target=fault_target,
            fault_after=fault_after if fault_after in ATOMIC_FAULT_STAGES else None,
            fault_marker=fault_marker,
        )
        seq = pending["seq"]
        old_public_path = rd / f"public-{seq - 1:06d}.pem"
        expected_new = w132._verify_cert(
            cert, old_public_path, seq, pending["prev_rotation_sha"], root
        )
        if expected_new != public:
            raise ValueError("wave136-pending-successor-public-mismatch")

        _append_exact_once_recoverable(
            rd / w132.LINEAGE, cert, seq,
            fault_target=fault_target,
            target_name="authority_lineage",
            fault_after=fault_after if fault_after in ATOMIC_FAULT_STAGES else None,
            fault_marker=fault_marker,
        )
        _append_exact_once_recoverable(
            wd / w132.WITNESS_LINEAGE, cert, seq,
            fault_target=fault_target,
            target_name="witness_lineage",
            fault_after=fault_after if fault_after in ATOMIC_FAULT_STAGES else None,
            fault_marker=fault_marker,
        )

        generation = rd / f"public-{seq:06d}.pem"
        if generation.exists():
            w132._assert_authority_private(
                generation, w130._assert_separate_authority_uid()[0]
            )
            if generation.read_bytes() != public:
                raise ValueError("wave136-generation-public-mismatch")
        else:
            w134.recoverable_atomic_write(
                generation, public, w130._assert_separate_authority_uid()[0], 0o600
            )

        cur_pub = (ad / protocol.PUBLIC_KEY).read_bytes()
        old_pub = old_public_path.read_bytes()
        if cur_pub not in (old_pub, public):
            raise ValueError("wave136-authority-current-public-ambiguous")
        authority_uid, _ = w130._assert_separate_authority_uid()
        if cur_pub == old_pub:
            w135.recoverable_atomic_replace(
                ad / protocol.PRIVATE_KEY, private, authority_uid, 0o600
            )
            w135.recoverable_atomic_replace(
                ad / protocol.PUBLIC_KEY, public, authority_uid, 0o600
            )
        elif w131._response_public_from_private(
            (ad / protocol.PRIVATE_KEY).read_bytes()
        ) != public:
            raise ValueError("wave136-authority-current-private-ambiguous")

        witness_public_path = wd / protocol.WITNESS_PUBLIC_KEY
        witness_public = witness_public_path.read_bytes()
        if witness_public not in (old_pub, public):
            raise ValueError("wave136-witness-current-public-ambiguous")
        if witness_public == old_pub:
            owner, mode = _current_mode_owner(witness_public_path)
            w135.recoverable_atomic_replace(witness_public_path, public, owner, mode)

        new_binding = w132._binding(root["anchor_credential_fingerprint"], public)
        binding_path = wd / protocol.WITNESS_BINDING
        current_binding = w132._read_exact_json(
            binding_path, protocol.RESPONSE_BINDING_SCHEMA
        )
        old_binding = w132._binding(root["anchor_credential_fingerprint"], old_pub)
        if current_binding not in (old_binding, new_binding):
            raise ValueError("wave136-witness-binding-ambiguous")
        if current_binding == old_binding:
            owner, mode = _current_mode_owner(binding_path)
            w135.recoverable_atomic_replace(
                binding_path, _canon_file(new_binding), owner, mode
            )

        next_state = w132._state_for(
            seq, w132._cert_sha(cert), w132._public_fp(public), rotation_id
        )
        state_path = rd / w132.STATE
        existing_state = w132._read_exact_json(state_path, w132.STATE_SCHEMA)
        prior_rows = w132._read_jsonl(rd / w132.LINEAGE)
        old_state = w132._state_for(
            seq - 1,
            pending["prev_rotation_sha"],
            w132._public_fp(old_pub),
            None if seq == 1 else prior_rows[seq - 2]["rotation_id"],
        )
        if existing_state not in (old_state, next_state):
            raise ValueError("wave136-state-ambiguous")
        if existing_state == old_state:
            w135.recoverable_atomic_replace(
                state_path, _canon_file(next_state), authority_uid, 0o600
            )

        final = w135.validate_rotation_state(ad, wd)
        _cleanup_completed_pending(
            rd, rotation_id, final,
            fault_after=fault_after if fault_after in CLEANUP_STAGES else None,
            fault_marker=fault_marker,
        )
        return {
            **final,
            "idempotent": False,
            "rotation_id": rotation_id,
            "wave136_recoverable_transaction": True,
        }
    finally:
        lease.close()


def validate_rotation_state(anchor_dir: str | Path, witness_dir: str | Path) -> dict:
    ad, wd = Path(anchor_dir), Path(witness_dir)
    out = w135.validate_rotation_state(ad, wd)
    residue = _all_pending_residue(ad / w132.ROT_DIR)
    if residue:
        raise RuntimeError(
            "wave136-pending-residue:" + ",".join(p.name for p in residue)
        )
    return {**out, "wave136_recoverable_transaction": True}


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(
        description="AXM Flowing Compute Wave 136 recoverable rotation transaction"
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("rotate")
    r.add_argument("anchor_dir")
    r.add_argument("witness_dir")
    r.add_argument("rotation_id")
    r.add_argument("--fault-target")
    r.add_argument("--fault-after", choices=sorted(FAULT_STAGES))
    r.add_argument("--fault-marker")
    v = sub.add_parser("validate")
    v.add_argument("anchor_dir")
    v.add_argument("witness_dir")
    args = p.parse_args()

    if args.cmd == "rotate":
        out = rotate_response_key(
            args.anchor_dir,
            args.witness_dir,
            args.rotation_id,
            fault_target=args.fault_target,
            fault_after=args.fault_after,
            fault_marker=args.fault_marker,
        )
    else:
        out = validate_rotation_state(args.anchor_dir, args.witness_dir)
    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
