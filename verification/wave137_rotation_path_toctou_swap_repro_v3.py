#!/usr/bin/env python3
"""Corrected Wave 137 pathname TOCTOU verifier using one mutable ancestor.

DRAFT / NON-CANON.

The first two verifier attempts tried to move individual authority-owned anchor
entries across per-case parents and were blocked by fixture permissions before
Wave 137 was attacked. This version keeps those false-negative attempts intact
and uses the already-explicit worker-writable top-level test parent instead.
It swaps the complete genuine endpoint case (anchor + witness together) at the
single path component above both stores. The authority-owned anchor/witness
stores and their production permissions are not modified by the worker.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import wave137_rotation_path_toctou_swap_repro as base

SCRIPT = Path(__file__).resolve()
base.SCRIPT = SCRIPT


def case_swap(a_anchor: Path, a_witness: Path, b_anchor: Path, b_witness: Path,
              phase: str) -> int:
    a_case = a_anchor.parent
    b_case = b_anchor.parent
    if a_witness.parent != a_case or b_witness.parent != b_case:
        raise ValueError("verifier-case-layout-mismatch")
    a_saved = a_case.with_name(a_case.name + ".validated-original")

    if phase == "enter":
        a_case.rename(a_saved)
        b_case.rename(a_case)
    elif phase == "restore":
        a_case.rename(b_case)
        a_saved.rename(a_case)
    else:
        raise ValueError("unknown-swap-phase")

    st = a_case.parent.stat()
    print(json.dumps({
        "ok": True,
        "phase": phase,
        "uid": os.getuid(),
        "euid": os.geteuid(),
        "capeff": base.capeff(),
        "mutable_parent": str(a_case.parent),
        "mutable_parent_mode": oct(st.st_mode & 0o7777),
        "mutable_parent_uid": st.st_uid,
    }, sort_keys=True))
    return 0


base.child_swap = case_swap

if __name__ == "__main__":
    raise SystemExit(base.main())
