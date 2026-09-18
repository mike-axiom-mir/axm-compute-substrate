#!/usr/bin/env python3
"""Independent verifier for Wave 137 lineage-stage compatibility.

NON-CANON / verifier-only. This does not modify builder implementation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_ROTATION as w132
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_ROTATION_SELFTEST as t132
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ROTATION_TRANSACTION_RECOVERY as w136
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ROTATION_TRANSACTION_RECOVERY_SELFTEST as t136
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ROTATION_NAMESPACE as w137

SCRIPT = Path(__file__).resolve()
ENV_UID = t132.ENV_UID


def rid() -> str:
    return hashlib.sha256(b"AXM-VERIFIER-W137-GENUINE-LINEAGE-RECOVERY-STAGE").hexdigest()


def parse(cp) -> dict:
    lines = cp.stdout.strip().splitlines()
    if not lines:
        return {"ok": False, "error": f"missing-json:{cp.returncode}:{cp.stderr[-1200:]}"}
    try:
        return json.loads(lines[-1])
    except Exception:
        return {"ok": False, "error": f"json-parse:{cp.stdout[-1200:]}:{cp.stderr[-1200:]}"}


def run_child(anchor_uid: int, worker_uid: int, mode: str, anchor: Path, witness: Path, rotation: str):
    return t132.run_as(
        anchor_uid,
        t132.pycmd(str(SCRIPT), f"--child-{mode}", str(anchor), str(witness), rotation),
        extra_env={ENV_UID: str(worker_uid)},
        check=False,
        timeout=90.0,
    )


def child(anchor: Path, witness: Path, rotation: str, predecessor: bool) -> int:
    try:
        fn = w136.rotate_response_key if predecessor else w137.rotate_response_key
        out = fn(anchor, witness, rotation)
        print(json.dumps({"ok": True, "result": out}, sort_keys=True))
        return 0
    except BaseException as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 3


def run_suite(worker_uid: int, anchor_uid: int, report_path: Path | None) -> int:
    if os.geteuid() != 0:
        raise PermissionError("verifier-requires-root-orchestrator")
    if worker_uid == anchor_uid:
        raise ValueError("worker-and-anchor-uid-must-differ")

    base = Path(tempfile.mkdtemp(prefix="axm-v-w137-lineage-stage-"))
    os.chmod(base, 0o777)
    witness, anchor, _, _ = t132.setup_case(base, "case", anchor_uid, worker_uid)
    rotation = rid()
    marker = base / "cut.json"

    # Create a genuine Wave-136 authority-lineage partial replacement using its
    # production crash helper. This is predecessor-produced recovery residue,
    # not verifier-invented garbage.
    t136.kill_at(
        anchor_uid, worker_uid, anchor, witness, rotation, marker,
        target="authority_lineage", stage="partial_write",
    )

    rd = anchor / w132.ROT_DIR
    residues = sorted(p.name for p in rd.glob("lineage.jsonl.axm-w135-stage-*"))
    lineage_before = (rd / w132.LINEAGE).read_bytes()

    strict_cp = run_child(anchor_uid, worker_uid, "strict", anchor, witness, rotation)
    strict = parse(strict_cp)
    lineage_after_strict = (rd / w132.LINEAGE).read_bytes()
    residues_after_strict = sorted(p.name for p in rd.glob("lineage.jsonl.axm-w135-stage-*"))

    # Control: unchanged Wave 136 must be able to resume the exact state Wave 137 rejected.
    predecessor_cp = run_child(anchor_uid, worker_uid, "predecessor", anchor, witness, rotation)
    predecessor = parse(predecessor_cp)
    residues_after_predecessor = sorted(p.name for p in rd.glob("lineage.jsonl.axm-w135-stage-*"))

    final_cp = t132.run_as(
        anchor_uid,
        t132.pycmd(str(SCRIPT), "--child-validate", str(anchor), str(witness), rotation),
        extra_env={ENV_UID: str(worker_uid)},
        check=False,
        timeout=90.0,
    )
    final = parse(final_cp)

    expected_error = "wave137-unexpected-rotation-artifact:lineage.jsonl.axm-w135-stage-"
    failed = (
        len(residues) == 1
        and strict_cp.returncode != 0
        and expected_error in strict.get("error", "")
        and lineage_after_strict == lineage_before
        and residues_after_strict == residues
        and predecessor_cp.returncode == 0
        and predecessor.get("ok") is True
        and predecessor.get("result", {}).get("seq") == 1
        and not residues_after_predecessor
        and final_cp.returncode == 0
        and final.get("ok") is True
        and final.get("result", {}).get("seq") == 1
    )

    report = {
        "schema": "axm.flowing-compute.verifier.wave137-lineage-stage-regression.v1",
        "mode": "optimized" if sys.flags.optimize else "normal",
        "builder_head": "e6ac6962c6ee1e4b5e6023daa999838873644f56",
        "verdict": (
            "FAIL_WAVE137_REJECTS_GENUINE_WAVE136_LINEAGE_RECOVERY_STAGE"
            if failed else "VERIFIER_DID_NOT_REPRODUCE_EXPECTED_FAILURE"
        ),
        "reproduced": failed,
        "residue_before": residues,
        "strict_returncode": strict_cp.returncode,
        "strict_error": strict.get("error"),
        "strict_left_lineage_unchanged": lineage_after_strict == lineage_before,
        "strict_retained_residue": residues_after_strict == residues,
        "wave136_control_returncode": predecessor_cp.returncode,
        "wave136_control_seq": predecessor.get("result", {}).get("seq"),
        "residue_after_wave136_control": residues_after_predecessor,
        "wave137_validate_after_wave136_recovery": final,
        "truth_boundary": (
            "Same-host Linux recovery-namespace compatibility only. The residue is generated by "
            "the unchanged Wave-136 authority-lineage partial-write path. No authority key, ledger, "
            "certificate, or signed lineage is forged or rewritten by the verifier. This is a "
            "fail-closed liveness/regression failure, not stale-authority acceptance and not a "
            "speed, energy, retained/incremental/dormant-compute, cross-host, or physical-finality result."
        ),
    }
    if report_path:
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if failed else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker-uid", type=int)
    ap.add_argument("--anchor-uid", type=int)
    ap.add_argument("--report")
    ap.add_argument("--child-strict", nargs=3, metavar=("ANCHOR", "WITNESS", "RID"))
    ap.add_argument("--child-predecessor", nargs=3, metavar=("ANCHOR", "WITNESS", "RID"))
    ap.add_argument("--child-validate", nargs=3, metavar=("ANCHOR", "WITNESS", "RID"))
    args = ap.parse_args()

    if args.child_strict:
        a, w, r = args.child_strict
        return child(Path(a), Path(w), r, False)
    if args.child_predecessor:
        a, w, r = args.child_predecessor
        return child(Path(a), Path(w), r, True)
    if args.child_validate:
        a, w, _ = args.child_validate
        try:
            out = w137.validate_rotation_state(Path(a), Path(w))
            print(json.dumps({"ok": True, "result": out}, sort_keys=True))
            return 0
        except BaseException as exc:
            print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
            return 3
    if args.worker_uid is None or args.anchor_uid is None:
        ap.error("--worker-uid and --anchor-uid are required")
    return run_suite(args.worker_uid, args.anchor_uid, Path(args.report) if args.report else None)


if __name__ == "__main__":
    raise SystemExit(main())
