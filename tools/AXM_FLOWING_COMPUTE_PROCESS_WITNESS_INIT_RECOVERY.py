#!/usr/bin/env python3
"""AXM Flowing Compute Wave 131 exact-init recovery public entrypoint.

This small entrypoint keeps the original first Wave-131 candidate byte-for-byte
available as ``AXM_FLOWING_COMPUTE_PROCESS_WITNESS_INIT_RECOVERY_IMPL.py`` while
repairing one integration mistake found by the first exact-source CI run: that
candidate rebound ``w130.serve_anchor`` and then called that same rebound name,
causing recursive readiness validation instead of delegating to Wave 130's
captured Wave-129/128 authenticated server.

The recovery protocol itself is unchanged. Service now validates the Wave-131
readiness receipt, validates the Wave-130 durable UID/key boundary, and then
calls Wave 130's already-captured authenticated server implementation directly.
Experimental lane only / NON-CANON / no automatic merge.
"""
from __future__ import annotations

from pathlib import Path

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_INIT_RECOVERY_IMPL as _impl
from AXM_FLOWING_COMPUTE_PROCESS_WITNESS_INIT_RECOVERY_IMPL import *  # noqa: F401,F403

# Re-export the implementation modules used by the adversarial self-test.
w = _impl.w
w126 = _impl.w126
w128 = _impl.w128
w129 = _impl.w129
w130 = _impl.w130
protocol = _impl.protocol


def initialize_anchor_dir(anchor_dir: str | Path, witness_dir: str | Path,
                          anchor_id: str = "wave131-anchor",
                          fault_after: str | None = None,
                          fault_marker: str | Path | None = None) -> dict:
    return _impl.initialize_anchor_dir(
        anchor_dir, witness_dir, anchor_id,
        fault_after=fault_after, fault_marker=fault_marker,
    )


def validate_initialized_anchor(anchor_dir: str | Path) -> dict:
    return _impl.validate_initialized_anchor(anchor_dir)


def serve_anchor(anchor_dir: str | Path, socket_path: str | Path,
                 ready_file: str | Path | None = None,
                 error_file: str | Path | None = None,
                 allow_fault: bool = False) -> int:
    """Serve only an exact Wave-131-ready, Wave-130-bound authority store."""
    try:
        validate_initialized_anchor(anchor_dir)
        w130.durable_key_boundary_status(anchor_dir)
    except BaseException as exc:
        w126._write_error(error_file, exc)
        return 2
    # Important: do not call w130.serve_anchor here. Wave 131 deliberately
    # rebinds that shared protocol name below; Wave 130 retained this exact
    # lower authenticated server before any Wave-131 patching happened.
    return w130._wave129_serve_anchor(
        anchor_dir, socket_path, ready_file, error_file, allow_fault
    )


# The shared Wave-127 CLI resolves these globals at call time.
protocol.initialize_anchor_dir = initialize_anchor_dir
protocol.serve_anchor = serve_anchor
w130.initialize_anchor_dir = initialize_anchor_dir
w130.serve_anchor = serve_anchor


def __getattr__(name: str):
    return getattr(_impl, name)


def main() -> int:
    return protocol.main()


if __name__ == "__main__":
    raise SystemExit(main())
