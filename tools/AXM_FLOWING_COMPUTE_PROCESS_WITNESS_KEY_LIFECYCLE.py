#!/usr/bin/env python3
"""AXM Flowing Compute Wave 129: protect the full response-key init lifecycle.

Experimental lane only / NON-CANON / no automatic merge.

Wave 128 removed globally discoverable private-key helper files and made the
long-lived anchor plus crypto children non-dumpable before secret-key access.
Independent verifier PR #53 then found a narrower lifecycle hole: the ordinary
Python process running initialize_anchor_dir() was still dumpable while the
fresh response private PEM existed in its heap immediately before persistence.
A same-UID direct parent without CAP_SYS_PTRACE could recover that exact key
through /proc/<pid>/mem and reopen signed socket substitution.

Wave 129 keeps the Wave-128 cryptographic protocol and durable layout unchanged.
It closes only that custody gap: initialization must become non-dumpable before
anchor initialization, key generation, or private-key bytes can enter Python
memory. The existing Wave-128 non-dumpable crypto-child and memfd signing path
remain in force. Failure to establish the Linux non-dumpable boundary fails
closed rather than silently continuing with weaker custody.

This is not a hostile-kernel/root boundary, does not prevent an actor that can
read the anchor store itself from reading response_private.pem, and does not
create cross-host uniqueness. A copied genuine key in another host/namespace,
whole-domain rollback, hardware-backed custody, power/device failure, and
physical/provider finality remain open. No performance, energy, retained,
incremental, dormant-compute, throughput, or scaling claim is made.
"""
from __future__ import annotations

import ctypes
from pathlib import Path

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_CUSTODY as _base128
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_AUTHENTICATED_ANCHOR as _protocol
from AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_CUSTODY import *  # noqa: F401,F403

PR_GET_DUMPABLE = 3

SOURCE = {
    "wave128_evidence_head": "f3e6c9bb775a9fec8204342e5d0bffff54ea42cb",
    "wave128_tested_source_commit": "a84f80672a2c54c02ad89479ec4c7c091a93f1d3",
    "wave128_key_custody_tool_blob": "c77cd2fc5b56848d1c88218a60d17d9df9c0d6bd",
    "verifier_pr": 53,
    "verifier_tested_head": "a06cc52793a41a5635e9b9aa23c0a1dcdd3b60ea",
    "verifier_ci_run": 35306142204,
    "verifier_artifact_sha256": "fb9f915e763b7df9917192c22c4c1fe4cf9b0ca48b1a191ce73ed8dd9079a0f0",
}

# Capture the Wave-127 initializer after importing Wave 128. Its global crypto
# hooks have already been replaced by the Wave-128 memfd/non-dumpable versions.
_original_initialize_anchor_dir = _protocol.initialize_anchor_dir


def _get_dumpable() -> int:
    libc = ctypes.CDLL(None, use_errno=True)
    rc = libc.prctl(PR_GET_DUMPABLE, 0, 0, 0, 0)
    if rc < 0:
        err = ctypes.get_errno()
        raise OSError(err, "prctl(PR_GET_DUMPABLE) failed")
    return int(rc)


def _enter_initializer_custody_boundary() -> None:
    """Establish and verify non-dumpable custody before any secret generation."""
    _base128._set_dumpable_disabled()
    if _get_dumpable() != 0:
        raise RuntimeError("wave129-initializer-remained-dumpable")


def initialize_anchor_dir(anchor_dir: str | Path, witness_dir: str | Path,
                          anchor_id: str = "wave129-anchor") -> dict:
    """Run the unchanged Wave-128 init path inside a non-dumpable process."""
    _enter_initializer_custody_boundary()
    return _original_initialize_anchor_dir(anchor_dir, witness_dir, anchor_id)


# Wave-128's CLI delegates to the Wave-127 protocol module, so patch the exact
# initializer symbol that CLI dispatch resolves. Also expose the fixed function
# through the imported Wave-128 module for callers that retain that module.
_protocol.initialize_anchor_dir = initialize_anchor_dir
_base128.initialize_anchor_dir = initialize_anchor_dir


def __getattr__(name: str):
    return getattr(_base128, name)


def main() -> int:
    # Wave-128 already installed the memfd signing/verification + non-dumpable
    # serving hooks into this shared protocol module. The only Wave-129 change
    # above is the initializer entry boundary.
    return _protocol.main()


if __name__ == "__main__":
    raise SystemExit(main())
