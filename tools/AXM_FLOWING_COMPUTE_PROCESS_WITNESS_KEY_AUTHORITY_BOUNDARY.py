#!/usr/bin/env python3
"""AXM Flowing Compute Wave 130: dedicated-UID durable key authority boundary.

Experimental lane only / NON-CANON / no automatic merge.

Independent verifier PR #54 showed that Wave 129's response_private.pem remains
ordinary mode-0600 storage owned by the same Unix uid as ordinary worker
processes. 0600 protects against other uids, not against another process with
the same uid. Such a worker can therefore read the durable private key directly
without ptrace, /proc memory access, capability abuse, or signature forgery.

Wave 130 does not pretend file permissions can solve same-uid isolation. It
makes the durable response-key owner an explicit authority boundary: anchor
initialization and serving must run as a different Unix uid than the declared
worker uid, the anchor directory is private (0700) before any key generation,
and response_private.pem must remain owner-only (0600) and owned by the anchor
service uid. The already-authenticated Wave-127/128/129 protocol remains the
wire boundary, so workers receive only signed responses plus the pinned public
verifier; they do not receive a generic signing oracle.

Truth boundary: this establishes only the tested Unix-uid/process separation.
Root/kernel compromise, an attacker running as the anchor uid, ACL/LSM policy
that grants equivalent access, copied genuine credentials on another host,
whole-domain rollback, hardware/non-exportable-key custody, and physical or
provider finality remain open. Interrupted initialization recovery and identity
rotation are also still separate gates. No speed, energy, retained,
incremental, dormant-compute, throughput, or scaling claim is made.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_LIFECYCLE as _base129
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_AUTHENTICATED_ANCHOR as _protocol
from AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_LIFECYCLE import *  # noqa: F401,F403

FORBIDDEN_WORKER_UID_ENV = "AXM_W130_FORBIDDEN_WORKER_UID"
PRIVATE_KEY = "response_private.pem"
PUBLIC_KEY = "response_public.pem"

SOURCE = {
    "wave129_evidence_head": "f0afa88d8e03404b4a985a91b3efc62d1cec000f",
    "wave129_tested_source_commit": "d0bab11db00abf9c635d3827b0138f28cbb19fde",
    "wave129_key_lifecycle_tool_blob": "643b747762e904cd07efcccc36036fb7cba8b4f4",
    "verifier_pr": 54,
    "verifier_tested_head": "ece88c7181355c834ead613b59e5e3a2fd14bdac",
    "verifier_ci_run": 35310042572,
    "verifier_artifact_sha256": "a43586a2b6a7a0f1c43aac80f93014c628567b2a960734dc350e48e1f58930c7",
}

_wave129_initialize_anchor_dir = _base129.initialize_anchor_dir
_wave129_serve_anchor = _protocol.serve_anchor


def _forbidden_worker_uid() -> int:
    raw = os.environ.get(FORBIDDEN_WORKER_UID_ENV)
    if raw is None or not raw.strip():
        raise RuntimeError("wave130-forbidden-worker-uid-required")
    try:
        uid = int(raw, 10)
    except ValueError as exc:
        raise RuntimeError("wave130-forbidden-worker-uid-invalid") from exc
    if uid < 0:
        raise RuntimeError("wave130-forbidden-worker-uid-invalid")
    return uid


def _assert_separate_authority_uid() -> tuple[int, int]:
    worker_uid = _forbidden_worker_uid()
    authority_uid = os.geteuid()
    if authority_uid == worker_uid:
        raise PermissionError("wave130-anchor-authority-must-use-different-uid")
    return authority_uid, worker_uid


def _prepare_private_anchor_dir(anchor_dir: str | Path) -> Path:
    authority_uid, _ = _assert_separate_authority_uid()
    ad = Path(anchor_dir)
    if not ad.exists():
        ad.mkdir(parents=True, mode=0o700)
    st = ad.stat()
    if not stat.S_ISDIR(st.st_mode):
        raise ValueError("wave130-anchor-store-not-directory")
    if st.st_uid != authority_uid:
        raise PermissionError("wave130-anchor-store-owner-mismatch")
    os.chmod(ad, 0o700)
    mode = stat.S_IMODE(ad.stat().st_mode)
    if mode != 0o700:
        raise PermissionError("wave130-anchor-store-mode-mismatch")
    # Do not silently reinterpret partially initialized state. Recovery is a
    # later explicit gate; a non-empty pre-init directory must be inspected.
    if any(ad.iterdir()):
        raise RuntimeError("wave130-anchor-store-not-empty-requires-explicit-recovery")
    return ad


def durable_key_boundary_status(anchor_dir: str | Path) -> dict:
    authority_uid, worker_uid = _assert_separate_authority_uid()
    ad = Path(anchor_dir)
    private = ad / PRIVATE_KEY
    public = ad / PUBLIC_KEY
    ad_st = ad.stat()
    private_st = private.stat()
    public_st = public.stat()
    status = {
        "schema": "axm.flowing-compute.wave130-durable-key-boundary.v1",
        "authority_uid": authority_uid,
        "forbidden_worker_uid": worker_uid,
        "separate_uid": authority_uid != worker_uid,
        "anchor_dir_owner_uid": ad_st.st_uid,
        "anchor_dir_mode": oct(stat.S_IMODE(ad_st.st_mode)),
        "private_key_owner_uid": private_st.st_uid,
        "private_key_mode": oct(stat.S_IMODE(private_st.st_mode)),
        "public_key_owner_uid": public_st.st_uid,
    }
    if ad_st.st_uid != authority_uid or stat.S_IMODE(ad_st.st_mode) != 0o700:
        raise PermissionError("wave130-anchor-store-boundary-invalid")
    if private_st.st_uid != authority_uid or stat.S_IMODE(private_st.st_mode) != 0o600:
        raise PermissionError("wave130-private-key-boundary-invalid")
    return status


def initialize_anchor_dir(anchor_dir: str | Path, witness_dir: str | Path,
                          anchor_id: str = "wave130-anchor") -> dict:
    """Initialize inside a private dedicated-uid directory from byte zero."""
    ad = _prepare_private_anchor_dir(anchor_dir)
    root = _wave129_initialize_anchor_dir(ad, witness_dir, anchor_id)
    os.chmod(ad, 0o700)
    os.chmod(ad / PRIVATE_KEY, 0o600)
    boundary = durable_key_boundary_status(ad)
    return {**root, "wave130_durable_key_boundary": boundary}


def serve_anchor(anchor_dir: str | Path, socket_path: str | Path,
                 ready_file: str | Path | None = None,
                 error_file: str | Path | None = None,
                 allow_fault: bool = False) -> int:
    """Refuse service unless durable key ownership is a distinct uid boundary."""
    durable_key_boundary_status(anchor_dir)
    return _wave129_serve_anchor(
        anchor_dir, socket_path, ready_file, error_file, allow_fault
    )


# The shared protocol parser resolves these globals at runtime.
_protocol.initialize_anchor_dir = initialize_anchor_dir
_protocol.serve_anchor = serve_anchor
_base129.initialize_anchor_dir = initialize_anchor_dir


def __getattr__(name: str):
    return getattr(_base129, name)


def main() -> int:
    return _protocol.main()


if __name__ == "__main__":
    raise SystemExit(main())
