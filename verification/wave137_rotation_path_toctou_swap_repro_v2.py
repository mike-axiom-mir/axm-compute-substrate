#!/usr/bin/env python3
"""Corrected wrapper for the Wave 137 pathname TOCTOU verifier.

The first verifier attempt preserved the initialized case-parent permissions and
therefore the worker could not move the second genuine authority directory into
the validated pathname. This wrapper changes only the deployment boundary under
test: after each genuine domain is initialized, its immediate parent directory
is made worker-writable (0777), matching the explicitly scoped mutable-parent
pathname-substitution boundary. Anchor/witness stores themselves remain owned
by the authority uid with their production permissions.
"""
from __future__ import annotations

import os

import wave137_rotation_path_toctou_swap_repro as base

_original_setup_case = base.t132.setup_case


def _setup_case_worker_writable_parent(base_dir, name, anchor_uid, worker_uid):
    result = _original_setup_case(base_dir, name, anchor_uid, worker_uid)
    witness, anchor, _, _ = result
    os.chmod(anchor.parent, 0o777)
    # anchor and witness share the same case parent in the production self-test fixture.
    if witness.parent != anchor.parent:
        os.chmod(witness.parent, 0o777)
    return result


base.t132.setup_case = _setup_case_worker_writable_parent

if __name__ == "__main__":
    raise SystemExit(base.main())
