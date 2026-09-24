#!/usr/bin/env python3
"""AXM Flowing Compute Wave 135: recoverable current-key rotation publication.

Experimental lane only / NON-CANON / no automatic merge.

Wave 134 closed recoverable atomic publication for rotation bootstrap only.
Independent verifier PR #59 then reproduced the explicitly open next gate:
repeated SIGKILL immediately before the older random-temp replacement of the
live response private key retained multiple complete historical private-key
temp files even after later rotations validated successfully.

Wave 135 repairs that concrete post-pending key-publication boundary without
rewriting Wave 132/134. Once a Wave-132 pending transaction is already durable,
replacement of the live authority key, live authority public key, witness
verifier/binding, final rotation state, and generated public-key file is routed
through deterministic content-bound staging. Exact legacy random temps are
adopted/deduplicated only when authority owner/mode and complete bytes match the
already-durable intended bytes. Wrong-byte, foreign-owner, unrelated-stage, or
ambiguous residue fails closed and remains visible.

Important boundary: creation of the pending transaction itself, append-style
lineage writes, cleanup crash cuts, validation-to-service pathname identity,
and copied genuine keys across namespaces/hosts remain unproved. This wave is
not a performance, energy, retained/incremental/dormant-compute, throughput, or
scaling result.
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS as w
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_AUTHENTICATED_ANCHOR as protocol
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_AUTHORITY_BOUNDARY as w130
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_ROTATION as w132
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ATOMIC_RECOVERY as w134

SOURCE = {
    "wave134_evidence_head": "0f326221584e45723e8a9855f4d8fad5635711ac",
    "wave134_exact_green_source": "20abcb846a48709dba4ba345380a1782f3fa83c8",
    "verifier_pr": 59,
    "verifier_ci_tested_head": "12e96da5486c4bf5372feb2cc7bcac75478655e4",
    "verifier_ci_run": 35328632211,
    "verifier_artifact_sha256": "36b87d111c3e060370b58dab4ba6e355c8ba23d0550d14be09ee8ff04dc3663c",
}

ATOMIC_FAULT_STAGES = set(w134.ATOMIC_FAULT_STAGES)


def _stage_path(path: Path, data: bytes, mode: int) -> Path:
    identity = w.canonical({
        "schema": "axm.flowing-compute.wave135-rotation-stage.v1",
        "target_name": path.name,
        "mode": mode,
        "length": len(data),
        "sha256": w.sha256_hex(data),
    })
    return path.with_name(path.name + ".axm-w135-stage-" + w.sha256_hex(identity)[:32])


def _legacy_candidates(path: Path) -> list[Path]:
    return sorted(p for p in path.parent.glob(path.name + ".tmp-*") if p.exists())


def _stage_candidates(path: Path) -> list[Path]:
    return sorted(p for p in path.parent.glob(path.name + ".axm-w135-stage-*") if p.exists())


def _assert_candidate(path: Path, authority_uid: int, mode: int) -> None:
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode):
        raise PermissionError(f"wave135-candidate-not-regular:{path.name}")
    if st.st_uid != authority_uid:
        raise PermissionError(f"wave135-candidate-owner-mismatch:{path.name}")
    if stat.S_IMODE(st.st_mode) != mode:
        raise PermissionError(f"wave135-candidate-mode-mismatch:{path.name}")


def _pause(stage: str, fault_after: str | None, marker: str | Path | None) -> None:
    if fault_after is None:
        return
    if fault_after not in ATOMIC_FAULT_STAGES:
        raise ValueError("wave135-unknown-atomic-fault-stage")
    if stage != fault_after:
        return
    w134._pause(stage, fault_after, marker)


def _replace_from_stage(stage: Path, path: Path, data: bytes, authority_uid: int, mode: int,
                        fault_after: str | None, fault_marker: str | Path | None) -> None:
    _assert_candidate(stage, authority_uid, mode)
    staged = stage.read_bytes()
    if not data.startswith(staged):
        raise ValueError(f"wave135-stage-temp-mismatch:{stage.name}")
    fd = os.open(str(stage), os.O_WRONLY | os.O_TRUNC)
    try:
        w134._write_all(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    _pause("post_close_pre_replace", fault_after, fault_marker)
    os.replace(stage, path)
    os.chmod(path, mode)
    _pause("post_replace_pre_dir_fsync", fault_after, fault_marker)
    w._fsync_dir(path.parent)


def recoverable_atomic_replace(path: str | Path, data: bytes, authority_uid: int,
                               mode: int = 0o600, *,
                               fault_after: str | None = None,
                               fault_marker: str | Path | None = None) -> None:
    """Replace a caller-prevalidated current value with exact intended bytes.

    The caller must already have validated that the existing final value is an
    allowed predecessor/current value. This helper adds only crash-resumable
    publication and strict residue handling; it does not widen authority.
    """
    p = Path(path)
    expected_stage = _stage_path(p, data, mode)
    legacy = _legacy_candidates(p)
    stages = _stage_candidates(p)
    for q in stages:
        if q != expected_stage:
            raise RuntimeError(f"wave135-unrelated-stage-candidate:{q.name}")
    for q in legacy:
        _assert_candidate(q, authority_uid, mode)
        if q.read_bytes() != data:
            raise ValueError(f"wave135-legacy-temp-mismatch:{q.name}")
    for q in stages:
        _assert_candidate(q, authority_uid, mode)
        if not data.startswith(q.read_bytes()):
            raise ValueError(f"wave135-stage-temp-mismatch:{q.name}")

    if p.exists():
        st = p.lstat()
        if not stat.S_ISREG(st.st_mode):
            raise PermissionError(f"wave135-target-not-regular:{p.name}")
        if st.st_uid != authority_uid or stat.S_IMODE(st.st_mode) != mode:
            raise PermissionError(f"wave135-target-boundary-invalid:{p.name}")
        if p.read_bytes() == data:
            for q in [*legacy, *stages]:
                q.unlink()
            if legacy or stages:
                w._fsync_dir(p.parent)
            return

    if legacy:
        chosen = legacy[0]
        _pause("post_close_pre_replace", fault_after, fault_marker)
        os.replace(chosen, p)
        os.chmod(p, mode)
        for q in legacy[1:]:
            q.unlink()
        for q in stages:
            q.unlink()
        _pause("post_replace_pre_dir_fsync", fault_after, fault_marker)
        w._fsync_dir(p.parent)
        return

    if stages:
        _replace_from_stage(expected_stage, p, data, authority_uid, mode,
                            fault_after, fault_marker)
        return

    fd = os.open(str(expected_stage), os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    closed = False
    try:
        _assert_candidate(expected_stage, authority_uid, mode)
        _pause("temp_created", fault_after, fault_marker)
        split = len(data) // 2
        if data and split == 0:
            split = 1
        if split:
            w134._write_all(fd, data[:split])
        _pause("partial_write", fault_after, fault_marker)
        if split < len(data):
            w134._write_all(fd, data[split:])
        _pause("full_write_pre_fsync", fault_after, fault_marker)
        os.fsync(fd)
        _pause("post_fsync_pre_close", fault_after, fault_marker)
        os.close(fd)
        closed = True
        _pause("post_close_pre_replace", fault_after, fault_marker)
        os.replace(expected_stage, p)
        os.chmod(p, mode)
        _pause("post_replace_pre_dir_fsync", fault_after, fault_marker)
        w._fsync_dir(p.parent)
    finally:
        if not closed:
            try:
                os.close(fd)
            except OSError:
                pass


def _target_paths(anchor_dir: Path, witness_dir: Path) -> set[Path]:
    return {
        anchor_dir / protocol.PRIVATE_KEY,
        anchor_dir / protocol.PUBLIC_KEY,
        witness_dir / protocol.WITNESS_PUBLIC_KEY,
        witness_dir / protocol.WITNESS_BINDING,
        anchor_dir / w132.ROT_DIR / w132.STATE,
    }


def _rotation_residue(anchor_dir: Path, witness_dir: Path) -> list[str]:
    residue: list[str] = []
    rd = anchor_dir / w132.ROT_DIR
    targets = list(_target_paths(anchor_dir, witness_dir))
    if rd.exists():
        targets.extend(p for p in rd.glob("public-*.pem"))
    for p in targets:
        residue.extend(str(q) for q in _legacy_candidates(p))
        residue.extend(str(q) for q in _stage_candidates(p))
    return sorted(set(residue))


def _patched_rotation(anchor_dir: Path, witness_dir: Path, rotation_id: str, *,
                      atomic_fault_target: str | None,
                      atomic_fault_after: str | None,
                      atomic_fault_marker: str | Path | None) -> dict:
    authority_uid, _ = w130._assert_separate_authority_uid()
    rd = anchor_dir / w132.ROT_DIR
    known = _target_paths(anchor_dir, witness_dir)
    original = w._atomic_write

    def patched(path, data: bytes, mode: int = 0o600):
        p = Path(path)
        fault = atomic_fault_after if atomic_fault_target == p.name else None
        marker = atomic_fault_marker if fault is not None else None
        if p in known:
            return recoverable_atomic_replace(
                p, data, authority_uid, mode,
                fault_after=fault, fault_marker=marker,
            )
        if p.parent == rd and p.name.startswith("public-") and p.name.endswith(".pem"):
            if p.exists():
                _assert_candidate(p, authority_uid, mode)
                if p.read_bytes() != data:
                    raise ValueError(f"wave135-existing-generation-mismatch:{p.name}")
                return None
            return w134.recoverable_atomic_write(
                p, data, authority_uid, mode,
                fault_after=fault, fault_marker=marker,
            )
        return original(path, data, mode)

    w._atomic_write = patched
    try:
        return w132.rotate_response_key(anchor_dir, witness_dir, rotation_id)
    finally:
        w._atomic_write = original


def rotate_response_key(anchor_dir: str | Path, witness_dir: str | Path, rotation_id: str, *,
                        atomic_fault_target: str | None = None,
                        atomic_fault_after: str | None = None,
                        atomic_fault_marker: str | Path | None = None) -> dict:
    ad, wd = Path(anchor_dir), Path(witness_dir)
    w134.ensure_rotation_bootstrap(ad, wd)
    if atomic_fault_after is not None and atomic_fault_target is None:
        raise ValueError("wave135-atomic-fault-target-required")
    out = _patched_rotation(
        ad, wd, rotation_id,
        atomic_fault_target=atomic_fault_target,
        atomic_fault_after=atomic_fault_after,
        atomic_fault_marker=atomic_fault_marker,
    )
    residue = _rotation_residue(ad, wd)
    if residue:
        raise RuntimeError("wave135-rotation-publication-residue:" + ",".join(residue))
    return {**out, "wave135_recoverable_rotation_publication": True}


def validate_rotation_state(anchor_dir: str | Path, witness_dir: str | Path) -> dict:
    ad, wd = Path(anchor_dir), Path(witness_dir)
    boot = w134.ensure_rotation_bootstrap(ad, wd)
    out = w132.validate_rotation_state(ad, wd)
    residue = _rotation_residue(ad, wd)
    if residue:
        raise RuntimeError("wave135-rotation-publication-residue:" + ",".join(residue))
    return {**out, "wave134_bootstrap": boot, "wave135_recoverable_rotation_publication": True}


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="AXM Flowing Compute Wave 135 recoverable rotation publication")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("rotate")
    r.add_argument("anchor_dir")
    r.add_argument("witness_dir")
    r.add_argument("rotation_id")
    r.add_argument("--atomic-fault-target")
    r.add_argument("--atomic-fault-after", choices=sorted(ATOMIC_FAULT_STAGES))
    r.add_argument("--atomic-fault-marker")
    v = sub.add_parser("validate")
    v.add_argument("anchor_dir")
    v.add_argument("witness_dir")
    args = p.parse_args()
    if args.cmd == "rotate":
        out = rotate_response_key(
            args.anchor_dir, args.witness_dir, args.rotation_id,
            atomic_fault_target=args.atomic_fault_target,
            atomic_fault_after=args.atomic_fault_after,
            atomic_fault_marker=args.atomic_fault_marker,
        )
    else:
        out = validate_rotation_state(args.anchor_dir, args.witness_dir)
    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
