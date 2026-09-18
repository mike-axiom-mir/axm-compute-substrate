#!/usr/bin/env python3
"""AXM Flowing Compute Wave 134: recoverable atomic bootstrap publication.

Experimental lane only / NON-CANON / no automatic merge.

Wave 133 made rotation bootstrap recoverable after named post-publication SIGKILL
cuts. Independent verifier PR #58 then widened the cut inside the shared
``_atomic_write`` helper: a kill after a same-directory temp file was fully
written+fsync'd but before ``os.replace`` could leave an authority-owned helper
temp that either blocked exact retry or remained as silent residue.

Wave 134 repairs only that bootstrap publication boundary. It adds a reusable
recoverable atomic writer with a deterministic content-bound stage name. A
stage owned by the authority may be resumed only when its bytes are an exact
prefix of the caller's already-known intended bytes. Legacy Wave-123-style
random temps may be adopted only when owner/mode and the *complete* bytes match
exactly. Foreign-owner, wrong-byte, unrelated-stage, or ambiguous candidates
fail closed and are retained. The final rename is followed by directory fsync.

Truth boundary: same-host Linux/process/filesystem bootstrap recovery only.
Authority-UID compromise, root/kernel compromise, rollback of the whole trust
domain, validation-to-service pathname substitution, genuine copied keys in
another namespace/host, device/provider/physical finality, and any speed,
energy, retained/incremental/dormant-compute, throughput, or scaling claim
remain outside this wave.
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
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_ROTATION as w132
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ROTATION_BOOTSTRAP_RECOVERY as w133

SOURCE = {
    "wave133_evidence_head": "be2bf60d834a4feab9e7a49f166c92a7e464684c",
    "wave133_exact_green_source": "1a6867e4ee1ddeb8010cf1115da9efe5ac246f5f",
    "verifier_pr": 58,
    "verifier_ci_tested_head": "73e8b105ce2e04b66f4305e5861e77b245f1b83c",
    "verifier_ci_run": 35323372319,
    "verifier_artifact_sha256": "0172b66828877ec78687bef4b083b2d23090b1f38aad825074f0ccd1dc8a05da",
}

ATOMIC_FAULT_STAGES = {
    "temp_created",
    "partial_write",
    "full_write_pre_fsync",
    "post_fsync_pre_close",
    "post_close_pre_replace",
    "post_replace_pre_dir_fsync",
}


def _canon_file(obj: dict) -> bytes:
    return w.canonical(obj) + b"\n"


def _pause(stage: str, fault_after: str | None, marker: str | Path | None) -> None:
    if fault_after is None:
        return
    if fault_after not in ATOMIC_FAULT_STAGES:
        raise ValueError("wave134-unknown-atomic-fault-stage")
    if stage != fault_after:
        return
    if marker is None:
        raise ValueError("wave134-atomic-fault-marker-required")
    mp = Path(marker)
    mp.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(mp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        payload = _canon_file({"stage": stage, "pid": os.getpid()})
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    w._fsync_dir(mp.parent)
    while True:
        time.sleep(1)


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    off = 0
    while off < len(view):
        n = os.write(fd, view[off:])
        if n <= 0:
            raise OSError("wave134-short-write")
        off += n


def _stage_path(path: Path, data: bytes, mode: int) -> Path:
    identity = w.canonical({
        "schema": "axm.flowing-compute.wave134-atomic-stage.v1",
        "target_name": path.name,
        "mode": mode,
        "length": len(data),
        "sha256": w.sha256_hex(data),
    })
    return path.with_name(path.name + ".axm-stage-" + w.sha256_hex(identity)[:32])


def _assert_candidate(path: Path, authority_uid: int, mode: int) -> None:
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode):
        raise PermissionError(f"wave134-candidate-not-regular:{path.name}")
    if st.st_uid != authority_uid:
        raise PermissionError(f"wave134-candidate-owner-mismatch:{path.name}")
    if stat.S_IMODE(st.st_mode) != mode:
        raise PermissionError(f"wave134-candidate-mode-mismatch:{path.name}")


def _legacy_candidates(path: Path) -> list[Path]:
    return sorted(p for p in path.parent.glob(path.name + ".tmp-*") if p.exists())


def _stage_candidates(path: Path) -> list[Path]:
    return sorted(p for p in path.parent.glob(path.name + ".axm-stage-*") if p.exists())


def _clean_or_recover_existing(path: Path, data: bytes, authority_uid: int, mode: int) -> bool:
    """Resolve only already-present final/temp state; never create a new stage.

    Returns True when the final target exists after recovery, False when there
    was no final and no recoverable candidate.
    """
    expected_stage = _stage_path(path, data, mode)
    legacy = _legacy_candidates(path)
    stages = _stage_candidates(path)
    for p in stages:
        if p != expected_stage:
            raise RuntimeError(f"wave134-unrelated-stage-candidate:{p.name}")

    if path.exists():
        _assert_candidate(path, authority_uid, mode)
        if path.read_bytes() != data:
            raise ValueError(f"wave134-existing-target-mismatch:{path.name}")
        for p in legacy:
            _assert_candidate(p, authority_uid, mode)
            if p.read_bytes() != data:
                raise ValueError(f"wave134-legacy-temp-mismatch:{p.name}")
        for p in stages:
            _assert_candidate(p, authority_uid, mode)
            staged = p.read_bytes()
            if not data.startswith(staged):
                raise ValueError(f"wave134-stage-temp-mismatch:{p.name}")
        for p in [*legacy, *stages]:
            p.unlink()
        if legacy or stages:
            w._fsync_dir(path.parent)
        return True

    exact_legacy: list[Path] = []
    for p in legacy:
        _assert_candidate(p, authority_uid, mode)
        if p.read_bytes() != data:
            raise ValueError(f"wave134-legacy-temp-mismatch:{p.name}")
        exact_legacy.append(p)

    if stages:
        p = stages[0]
        _assert_candidate(p, authority_uid, mode)
        staged = p.read_bytes()
        if not data.startswith(staged):
            raise ValueError(f"wave134-stage-temp-mismatch:{p.name}")
        if exact_legacy:
            chosen = exact_legacy[0]
            os.replace(chosen, path)
            os.chmod(path, mode)
            for q in exact_legacy[1:]:
                q.unlink()
            p.unlink()
            w._fsync_dir(path.parent)
            return True
        fd = os.open(str(p), os.O_WRONLY | os.O_TRUNC)
        try:
            _write_all(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(p, path)
        os.chmod(path, mode)
        w._fsync_dir(path.parent)
        return True

    if exact_legacy:
        chosen = exact_legacy[0]
        os.replace(chosen, path)
        os.chmod(path, mode)
        for q in exact_legacy[1:]:
            q.unlink()
        w._fsync_dir(path.parent)
        return True
    return False


def recoverable_atomic_write(path: str | Path, data: bytes, authority_uid: int, mode: int = 0o600, *,
                             fault_after: str | None = None,
                             fault_marker: str | Path | None = None) -> None:
    """Publish exact bytes with resumable, content-bound same-directory staging."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if _clean_or_recover_existing(p, data, authority_uid, mode):
        return

    stage = _stage_path(p, data, mode)
    if _legacy_candidates(p) or _stage_candidates(p):
        raise RuntimeError(f"wave134-unresolved-candidate-state:{p.name}")

    fd = os.open(str(stage), os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    closed = False
    try:
        _assert_candidate(stage, authority_uid, mode)
        _pause("temp_created", fault_after, fault_marker)
        split = len(data) // 2
        if data and split == 0:
            split = 1
        if split:
            _write_all(fd, data[:split])
        _pause("partial_write", fault_after, fault_marker)
        if split < len(data):
            _write_all(fd, data[split:])
        _pause("full_write_pre_fsync", fault_after, fault_marker)
        os.fsync(fd)
        _pause("post_fsync_pre_close", fault_after, fault_marker)
        os.close(fd)
        closed = True
        _pause("post_close_pre_replace", fault_after, fault_marker)
        os.replace(stage, p)
        os.chmod(p, mode)
        _pause("post_replace_pre_dir_fsync", fault_after, fault_marker)
        w._fsync_dir(p.parent)
    finally:
        if not closed:
            try:
                os.close(fd)
            except OSError:
                pass


def _expected_bootstrap(anchor_dir: Path, witness_dir: Path) -> tuple[int, dict[str, tuple[Path, bytes, int]]]:
    authority_uid, _ = w130._assert_separate_authority_uid()
    root, _, _ = w126.load_anchor_identity(anchor_dir)
    genesis = (anchor_dir / protocol.PUBLIC_KEY).read_bytes()
    intent = w133._bootstrap_intent(anchor_dir, root, genesis)
    state0 = _canon_file(w132._state_for(0, w132.ZERO, protocol._public_fingerprint(genesis), None))
    ready = w133._bootstrap_ready(intent, genesis)
    rd = anchor_dir / w132.ROT_DIR
    return authority_uid, {
        w133.BOOTSTRAP_INTENT: (rd / w133.BOOTSTRAP_INTENT, _canon_file(intent), 0o600),
        w132.GENESIS_PUBLIC: (rd / w132.GENESIS_PUBLIC, genesis, 0o600),
        w132.LINEAGE: (rd / w132.LINEAGE, b"", 0o600),
        w132.WITNESS_LINEAGE: (witness_dir / w132.WITNESS_LINEAGE, b"", 0o600),
        w132.STATE: (rd / w132.STATE, state0, 0o600),
        w133.BOOTSTRAP_READY: (rd / w133.BOOTSTRAP_READY, _canon_file(ready), 0o600),
    }


def _assert_no_known_residue(specs: dict[str, tuple[Path, bytes, int]]) -> None:
    residue: list[str] = []
    for _, (path, _, _) in specs.items():
        residue.extend(p.name for p in _legacy_candidates(path))
        residue.extend(p.name for p in _stage_candidates(path))
    if residue:
        raise RuntimeError("wave134-bootstrap-temp-residue:" + ",".join(sorted(residue)))


def ensure_rotation_bootstrap(anchor_dir: str | Path, witness_dir: str | Path, *,
                              atomic_fault_target: str | None = None,
                              atomic_fault_after: str | None = None,
                              atomic_fault_marker: str | Path | None = None) -> dict:
    ad, wd = Path(anchor_dir), Path(witness_dir)
    authority_uid, _ = w130._assert_separate_authority_uid()
    rd = ad / w132.ROT_DIR

    if not rd.exists():
        w133._validate_wave131_genesis_allow_rotation(ad)
        rd.mkdir(mode=0o700)
        os.chown(rd, authority_uid, authority_uid)
        os.chmod(rd, 0o700)
        w._fsync_dir(ad)
    st = rd.stat()
    if st.st_uid != authority_uid or stat.S_IMODE(st.st_mode) != 0o700:
        raise PermissionError("wave134-rotation-dir-boundary-invalid")

    w133._validate_wave131_genesis_allow_rotation(ad)
    authority_uid, specs = _expected_bootstrap(ad, wd)

    for _, (path, data, mode) in specs.items():
        _clean_or_recover_existing(path, data, authority_uid, mode)

    if (rd / w133.BOOTSTRAP_READY).exists():
        out = w133._validate_bootstrap_receipt(ad, wd)
        _assert_no_known_residue(specs)
        return {**out, "recovered": False, "already_ready": True, "wave134_atomic_recovery": True}

    if w133._pre_ready_has_evolution(rd, wd):
        raise RuntimeError("wave134-bootstrap-receipt-missing-after-evolution")

    allowed = {
        w133.BOOTSTRAP_INTENT, w133.BOOTSTRAP_READY, w132.GENESIS_PUBLIC,
        w132.LINEAGE, w132.STATE,
    }
    unexpected = sorted(p.name for p in rd.iterdir() if p.name not in allowed)
    if unexpected:
        raise RuntimeError("wave134-unexpected-pre-ready-artifacts:" + ",".join(unexpected))

    order = [
        w133.BOOTSTRAP_INTENT,
        w132.GENESIS_PUBLIC,
        w132.LINEAGE,
        w132.WITNESS_LINEAGE,
        w132.STATE,
        w133.BOOTSTRAP_READY,
    ]
    if atomic_fault_target is not None and atomic_fault_target not in specs:
        raise ValueError("wave134-unknown-atomic-fault-target")
    for name in order:
        path, data, mode = specs[name]
        recoverable_atomic_write(
            path, data, authority_uid, mode,
            fault_after=atomic_fault_after if name == atomic_fault_target else None,
            fault_marker=atomic_fault_marker if name == atomic_fault_target else None,
        )

    out = w133._validate_bootstrap_receipt(ad, wd)
    baseline = w132.validate_rotation_state(ad, wd)
    if baseline["seq"] != 0 or baseline["head_rotation_sha"] != w132.ZERO:
        raise ValueError("wave134-bootstrap-baseline-not-genesis")
    _assert_no_known_residue(specs)
    return {**out, "recovered": True, "already_ready": False, "wave134_atomic_recovery": True}


def rotate_response_key(anchor_dir: str | Path, witness_dir: str | Path, rotation_id: str, *,
                        atomic_fault_target: str | None = None,
                        atomic_fault_after: str | None = None,
                        atomic_fault_marker: str | Path | None = None) -> dict:
    ensure_rotation_bootstrap(
        anchor_dir, witness_dir,
        atomic_fault_target=atomic_fault_target,
        atomic_fault_after=atomic_fault_after,
        atomic_fault_marker=atomic_fault_marker,
    )
    return w132.rotate_response_key(anchor_dir, witness_dir, rotation_id)


def validate_rotation_state(anchor_dir: str | Path, witness_dir: str | Path) -> dict:
    boot = ensure_rotation_bootstrap(anchor_dir, witness_dir)
    state = w132.validate_rotation_state(anchor_dir, witness_dir)
    return {**state, "wave134_bootstrap": boot}


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="AXM Flowing Compute Wave 134 recoverable atomic bootstrap")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("bootstrap")
    b.add_argument("anchor_dir")
    b.add_argument("witness_dir")
    b.add_argument("--atomic-fault-target")
    b.add_argument("--atomic-fault-after", choices=sorted(ATOMIC_FAULT_STAGES))
    b.add_argument("--atomic-fault-marker")
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
    if args.cmd == "bootstrap":
        out = ensure_rotation_bootstrap(
            args.anchor_dir, args.witness_dir,
            atomic_fault_target=args.atomic_fault_target,
            atomic_fault_after=args.atomic_fault_after,
            atomic_fault_marker=args.atomic_fault_marker,
        )
    elif args.cmd == "rotate":
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
