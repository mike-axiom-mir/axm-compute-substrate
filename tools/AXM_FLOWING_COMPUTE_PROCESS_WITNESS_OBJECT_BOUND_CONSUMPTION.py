#!/usr/bin/env python3
"""AXM Flowing Compute Wave 138: bind validated filesystem objects to exact bytes.

Experimental lane only / NON-CANON / no automatic merge.

Wave 137 made the response-rotation namespace strict, but its stable validation
still returned ordinary path-backed state. A consumer that validates, then later
re-opens a current key or lineage pathname can observe a different inode/bytes
if that path is substituted in between.

Wave 138 adds a small reusable exact-object boundary for stable rotation state:
- open with O_NOFOLLOW and bind one file descriptor to regular-file metadata;
- read/validate exact bytes from that descriptor;
- compare the post-validation snapshot back to the already validated rotation
  sequence/head/current-key fingerprint;
- use bound bytes for crypto rather than re-opening the pathname.

Rejected substitutions are retained. This is deliberately not protection from
an attacker who can modify this process, authority memory, or the kernel. It is
same-host filesystem TOCTOU evidence only, and makes no performance/energy/
retained/incremental/dormant-compute, throughput, or scaling claim.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS as w
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_AUTHENTICATED_ANCHOR as protocol
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_CUSTODY as w128
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_AUTHORITY_BOUNDARY as w130
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_ROTATION as w132
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ROTATION_NAMESPACE as w137

SOURCE = {
    "wave137_evidence_head": "655c9306e457cd6ac24091e93eab9367b91d0693",
    "wave137_tool_blob": "4d95b9c509485dbfb8f46e0c0ff23357e1d1402c",
    "wave137_selftest_blob": "88f5873ced1ba3fdeca397777691e1d4ec763571",
}


@dataclass(frozen=True)
class BoundFile:
    path: str
    dev: int
    ino: int
    uid: int
    gid: int
    mode: int
    size: int
    sha256: str
    data: bytes


@dataclass(frozen=True)
class BoundRotationView:
    validated: dict
    authority_lineage: tuple[dict, ...]
    authority_lineage_file: BoundFile
    witness_lineage_file: BoundFile
    state: dict
    state_file: BoundFile
    private_file: BoundFile
    public_file: BoundFile
    witness_public_file: BoundFile


def _read_all(fd: int) -> bytes:
    chunks: list[bytes] = []
    while True:
        chunk = os.read(fd, 1024 * 1024)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def bind_file(path: str | Path, *, owner_uid: int | None = None,
              mode: int | None = None) -> BoundFile:
    """Bind exact bytes to one opened inode; future consumers use the snapshot."""
    p = Path(path)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(str(p), flags)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise PermissionError(f"wave138-bound-object-not-regular:{p.name}")
        actual_mode = stat.S_IMODE(st.st_mode)
        if owner_uid is not None and st.st_uid != owner_uid:
            raise PermissionError(f"wave138-bound-owner-mismatch:{p.name}")
        if mode is not None and actual_mode != mode:
            raise PermissionError(f"wave138-bound-mode-mismatch:{p.name}")
        data = _read_all(fd)
        if len(data) != st.st_size:
            raise RuntimeError(f"wave138-bound-size-changed-during-read:{p.name}")
        now = p.lstat()
        if now.st_dev != st.st_dev or now.st_ino != st.st_ino:
            raise RuntimeError(f"wave138-path-changed-during-bind:{p.name}")
        return BoundFile(
            path=str(p), dev=st.st_dev, ino=st.st_ino, uid=st.st_uid,
            gid=st.st_gid, mode=actual_mode, size=len(data),
            sha256=hashlib.sha256(data).hexdigest(), data=data,
        )
    finally:
        os.close(fd)


def path_still_matches(snapshot: BoundFile) -> bool:
    try:
        st = Path(snapshot.path).lstat()
    except FileNotFoundError:
        return False
    return (
        stat.S_ISREG(st.st_mode)
        and st.st_dev == snapshot.dev
        and st.st_ino == snapshot.ino
        and st.st_uid == snapshot.uid
        and stat.S_IMODE(st.st_mode) == snapshot.mode
    )


def _parse_canonical_json(snapshot: BoundFile, schema: str | None = None) -> dict:
    try:
        obj = json.loads(snapshot.data)
    except Exception as exc:
        raise ValueError(f"wave138-json-invalid:{Path(snapshot.path).name}") from exc
    if not isinstance(obj, dict) or snapshot.data != w.canonical(obj) + b"\n":
        raise ValueError(f"wave138-json-not-canonical:{Path(snapshot.path).name}")
    if schema is not None and obj.get("schema") != schema:
        raise ValueError(f"wave138-json-schema-mismatch:{Path(snapshot.path).name}")
    return obj


def _parse_canonical_jsonl(snapshot: BoundFile) -> tuple[dict, ...]:
    raw = snapshot.data
    if raw and not raw.endswith(b"\n"):
        raise ValueError(f"wave138-jsonl-truncated:{Path(snapshot.path).name}")
    rows: list[dict] = []
    for line in raw.splitlines():
        try:
            obj = json.loads(line)
        except Exception as exc:
            raise ValueError(f"wave138-jsonl-invalid:{Path(snapshot.path).name}") from exc
        if not isinstance(obj, dict) or w.canonical(obj) != line:
            raise ValueError(f"wave138-jsonl-not-canonical:{Path(snapshot.path).name}")
        rows.append(obj)
    return tuple(rows)


def _public_from_private_bytes(private_pem: bytes) -> bytes:
    public = w128._run_openssl_private(["pkey", "-pubout"], private_pem)
    if b"BEGIN PUBLIC KEY" not in public:
        raise ValueError("wave138-derived-public-invalid")
    return public


def sign_private_bytes(private_pem: bytes, payload: bytes) -> str:
    key_fd = w128._memfd_bytes("axm-wave138-bound-private", private_pem)
    try:
        signature = w128._run_openssl_private(
            ["dgst", "-sha256", "-sign", f"/proc/self/fd/{key_fd}"],
            payload, (key_fd,),
        )
        return base64.b64encode(signature).decode("ascii")
    finally:
        os.close(key_fd)


def verify_public_bytes(public_pem: bytes, payload: bytes, signature_b64: str) -> bool:
    try:
        signature = base64.b64decode(signature_b64, validate=True)
    except Exception:
        return False
    pub_fd = w128._memfd_bytes("axm-wave138-bound-public", public_pem)
    sig_fd = w128._memfd_bytes("axm-wave138-bound-signature", signature)
    try:
        cp = subprocess.run(
            [
                "openssl", "dgst", "-sha256",
                "-verify", f"/proc/self/fd/{pub_fd}",
                "-signature", f"/proc/self/fd/{sig_fd}",
            ],
            input=payload, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False, pass_fds=(pub_fd, sig_fd),
            preexec_fn=w128._child_disable_dumpable,
        )
        return cp.returncode == 0
    finally:
        os.close(sig_fd)
        os.close(pub_fd)


def bind_validated_rotation_view(anchor_dir: str | Path, witness_dir: str | Path, *,
                                 after_validation_hook: Callable[[], None] | None = None,
                                 ) -> BoundRotationView:
    """Validate Wave 137, then bind the exact stable objects consumers use."""
    ad, wd = Path(anchor_dir), Path(witness_dir)
    validated = w137.validate_rotation_state(ad, wd)
    if after_validation_hook is not None:
        after_validation_hook()

    authority_uid, _ = w130._assert_separate_authority_uid()
    rd = ad / w132.ROT_DIR

    lineage_file = bind_file(rd / w132.LINEAGE, owner_uid=authority_uid, mode=0o600)
    rows = _parse_canonical_jsonl(lineage_file)
    if len(rows) != validated["seq"]:
        raise RuntimeError("wave138-lineage-seq-mismatch")
    head = w132.ZERO if not rows else w132._cert_sha(rows[-1])
    if head != validated["head_rotation_sha"]:
        raise RuntimeError("wave138-lineage-head-mismatch")
    last_rotation = None if not rows else rows[-1].get("rotation_id")
    if last_rotation != validated["last_rotation_id"]:
        raise RuntimeError("wave138-lineage-last-rotation-mismatch")

    state_file = bind_file(rd / w132.STATE, owner_uid=authority_uid, mode=0o600)
    state = _parse_canonical_json(state_file, w132.STATE_SCHEMA)
    expected_state = w132._state_for(
        validated["seq"], validated["head_rotation_sha"],
        validated["current_response_public_fingerprint"], validated["last_rotation_id"],
    )
    if state != expected_state:
        raise RuntimeError("wave138-state-validation-snapshot-mismatch")

    public_file = bind_file(ad / protocol.PUBLIC_KEY, owner_uid=authority_uid, mode=0o600)
    if w132._public_fp(public_file.data) != validated["current_response_public_fingerprint"]:
        raise RuntimeError("wave138-current-public-validation-snapshot-mismatch")

    private_file = bind_file(ad / protocol.PRIVATE_KEY, owner_uid=authority_uid, mode=0o600)
    if _public_from_private_bytes(private_file.data) != public_file.data:
        raise RuntimeError("wave138-current-private-public-snapshot-mismatch")

    witness_lineage_path = wd / w132.WITNESS_LINEAGE
    witness_lineage_st = witness_lineage_path.lstat()
    witness_lineage_file = bind_file(
        witness_lineage_path, owner_uid=witness_lineage_st.st_uid,
        mode=stat.S_IMODE(witness_lineage_st.st_mode),
    )
    if witness_lineage_file.data != lineage_file.data:
        raise RuntimeError("wave138-authority-witness-lineage-snapshot-mismatch")

    witness_public_path = wd / protocol.WITNESS_PUBLIC_KEY
    witness_public_st = witness_public_path.lstat()
    witness_public_file = bind_file(
        witness_public_path, owner_uid=witness_public_st.st_uid,
        mode=stat.S_IMODE(witness_public_st.st_mode),
    )
    if witness_public_file.data != public_file.data:
        raise RuntimeError("wave138-authority-witness-public-snapshot-mismatch")

    return BoundRotationView(
        validated=validated, authority_lineage=rows,
        authority_lineage_file=lineage_file, witness_lineage_file=witness_lineage_file,
        state=state, state_file=state_file, private_file=private_file,
        public_file=public_file, witness_public_file=witness_public_file,
    )


def sign_from_bound_view(view: BoundRotationView, payload: bytes, *,
                         after_bind_hook: Callable[[], None] | None = None) -> str:
    if after_bind_hook is not None:
        after_bind_hook()
    signature = sign_private_bytes(view.private_file.data, payload)
    if not verify_public_bytes(view.public_file.data, payload, signature):
        raise RuntimeError("wave138-bound-signature-self-verification-failed")
    return signature


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="AXM Wave 138 exact-object binding")
    p.add_argument("anchor_dir")
    p.add_argument("witness_dir")
    args = p.parse_args()
    view = bind_validated_rotation_view(args.anchor_dir, args.witness_dir)
    print(json.dumps({
        "seq": view.validated["seq"],
        "head_rotation_sha": view.validated["head_rotation_sha"],
        "current_response_public_fingerprint":
            view.validated["current_response_public_fingerprint"],
        "authority_lineage_sha256": view.authority_lineage_file.sha256,
        "private_inode": view.private_file.ino,
        "public_inode": view.public_file.ino,
        "wave138_exact_object_binding": True,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
