#!/usr/bin/env python3
"""AXM Flowing Compute Wave 137: strict rotation-namespace provenance.

Experimental lane only / NON-CANON / no automatic merge.

Wave 136 made the on-host response-key rotation transaction crash-recoverable,
but its stable validator intentionally ignored unrelated files in the
authority-owned response_rotation directory. That left a provenance gap:
stale future generation files, unrelated authority-owned files, or foreign-
owned lookalike recovery files could coexist with a state Wave 136 reported as
valid.

Wave 137 closes only that namespace-integrity boundary. Before rotation it
checks that every artifact in response_rotation belongs to the exact known
bootstrap/lineage/state/generation namespace or to a narrowly recognized
in-flight recovery target. Stable validation additionally requires the exact
namespace implied by signed lineage. Unknown, stale-future, wrong-owner,
wrong-mode, non-regular, and unrelated recovery artifacts fail closed and are
left visible; they are never silently deleted or adopted.

This does not claim protection from the authority UID, root/kernel compromise,
validation-to-service inode substitution after this check, user namespaces,
cross-host copied-key uniqueness, whole-domain rollback, hardware key custody,
provider independence, physical finality, or any speed, energy,
retained/incremental/dormant-compute, throughput, or scaling result.
"""
from __future__ import annotations

import re
import stat
from pathlib import Path

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_AUTHORITY_BOUNDARY as w130
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_ROTATION as w132
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ROTATION_BOOTSTRAP_RECOVERY as w133
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ATOMIC_RECOVERY as w134
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ROTATION_TRANSACTION_RECOVERY as w136

SOURCE = {
    "wave136_evidence_head": "411bd123b193eca34f44bec1ff3d9d9af32247c5",
    "wave136_tool_blob": "47fe034330c808b48ee39f64f70b07778b533372",
    "wave136_selftest_blob": "589934e3b476ee7f9e661558255e3a43df7d3c49",
}

GENERATION_RE = re.compile(r"^public-(\d{6})\.pem$")
STABLE_FIXED = {
    w133.BOOTSTRAP_INTENT,
    w133.BOOTSTRAP_READY,
    w132.LINEAGE,
    w132.STATE,
}
PENDING_NAMES = set(w136.PENDING_TARGETS)
RECOVERY_MARKERS = (
    ".axm-w135-stage-",  # Wave 135/136 deterministic recoverable publication.
    ".axm-stage-",       # Wave 134 bootstrap publication staging.
    ".tmp-",             # Older exact legacy temp candidates.
)


def _recovery_base(name: str) -> str | None:
    for marker in RECOVERY_MARKERS:
        if marker in name:
            return name.split(marker, 1)[0]
    return None


def _generation_index(name: str) -> int | None:
    m = GENERATION_RE.fullmatch(name)
    return int(m.group(1)) if m else None


def _assert_private_regular(path: Path, authority_uid: int) -> None:
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode):
        raise PermissionError(f"wave137-rotation-artifact-not-regular:{path.name}")
    if st.st_uid != authority_uid:
        raise PermissionError(f"wave137-rotation-artifact-owner-mismatch:{path.name}")
    if stat.S_IMODE(st.st_mode) != 0o600:
        raise PermissionError(f"wave137-rotation-artifact-mode-mismatch:{path.name}")


def _scan_rotation_namespace(anchor_dir: str | Path, *, stable: bool) -> dict:
    ad = Path(anchor_dir)
    authority_uid, _ = w130._assert_separate_authority_uid()
    rd = ad / w132.ROT_DIR
    st = rd.stat()
    if not stat.S_ISDIR(st.st_mode):
        raise PermissionError("wave137-rotation-dir-not-directory")
    if st.st_uid != authority_uid or stat.S_IMODE(st.st_mode) != 0o700:
        raise PermissionError("wave137-rotation-dir-boundary-invalid")

    lineage_path = rd / w132.LINEAGE
    rows = w132._read_jsonl(lineage_path)
    seq = len(rows)

    names = sorted(p.name for p in rd.iterdir())
    pending_official = any(name in PENDING_NAMES for name in names)
    pending_recovery = any(
        (_recovery_base(name) in PENDING_NAMES)
        for name in names
        if _recovery_base(name) is not None
    )
    transaction_active = pending_official or pending_recovery

    unknown: list[str] = []
    stale_generations: list[str] = []
    disallowed_recovery: list[str] = []

    for name in names:
        path = rd / name
        _assert_private_regular(path, authority_uid)

        if name in STABLE_FIXED or name in PENDING_NAMES:
            if stable and name in PENDING_NAMES:
                disallowed_recovery.append(name)
            continue

        generation = _generation_index(name)
        if generation is not None:
            if generation > seq:
                stale_generations.append(name)
            continue

        base = _recovery_base(name)
        if base is None:
            unknown.append(name)
            continue

        base_generation = _generation_index(base)
        if base in PENDING_NAMES:
            if stable:
                disallowed_recovery.append(name)
            continue
        if transaction_active and base in {w132.LINEAGE, w132.STATE}:
            continue
        if transaction_active and base_generation is not None and base_generation == seq:
            continue

        disallowed_recovery.append(name)

    if unknown:
        raise RuntimeError("wave137-unexpected-rotation-artifact:" + ",".join(unknown))
    if stale_generations:
        raise RuntimeError("wave137-stale-future-generation:" + ",".join(stale_generations))
    if disallowed_recovery:
        raise RuntimeError("wave137-unrelated-recovery-artifact:" + ",".join(disallowed_recovery))

    present_generations = {
        idx for name in names if (idx := _generation_index(name)) is not None
    }
    if stable:
        expected = set(range(seq + 1))
        missing = sorted(expected - present_generations)
        if missing:
            raise RuntimeError(
                "wave137-missing-generation:" + ",".join(f"{x:06d}" for x in missing)
            )

    return {
        "seq": seq,
        "artifact_count": len(names),
        "transaction_active": transaction_active,
        "strict_rotation_namespace": True,
    }


def rotate_response_key(anchor_dir: str | Path, witness_dir: str | Path,
                        rotation_id: str, **kwargs) -> dict:
    ad, wd = Path(anchor_dir), Path(witness_dir)
    w134.ensure_rotation_bootstrap(ad, wd)
    preflight = _scan_rotation_namespace(ad, stable=False)
    out = w136.rotate_response_key(ad, wd, rotation_id, **kwargs)
    verified = validate_rotation_state(ad, wd)
    return {
        **out,
        "wave137_preflight_artifact_count": preflight["artifact_count"],
        "wave137_strict_rotation_namespace": verified["strict_rotation_namespace"],
    }


def validate_rotation_state(anchor_dir: str | Path, witness_dir: str | Path) -> dict:
    ad, wd = Path(anchor_dir), Path(witness_dir)
    out = w136.validate_rotation_state(ad, wd)
    namespace = _scan_rotation_namespace(ad, stable=True)
    return {
        **out,
        **namespace,
        "wave137_strict_rotation_namespace": True,
    }


def main() -> int:
    import argparse
    import json

    p = argparse.ArgumentParser(
        description="AXM Flowing Compute Wave 137 strict rotation namespace"
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("rotate")
    r.add_argument("anchor_dir")
    r.add_argument("witness_dir")
    r.add_argument("rotation_id")
    v = sub.add_parser("validate")
    v.add_argument("anchor_dir")
    v.add_argument("witness_dir")
    args = p.parse_args()

    if args.cmd == "rotate":
        out = rotate_response_key(args.anchor_dir, args.witness_dir, args.rotation_id)
    else:
        out = validate_rotation_state(args.anchor_dir, args.witness_dir)
    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
