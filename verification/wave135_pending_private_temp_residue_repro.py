#!/usr/bin/env python3
"""Independent Wave 135 verifier: pending-private crash residue amplification.

NON-CANON verifier lane. Builder files remain unchanged.

Wave 135 bounds residue for post-pending current-key publication. Its receipt
explicitly leaves pending-transaction creation open. This reproducer cuts the
unchanged pending_private.pem random-temp publication after a complete private
key has been written+fsynced and immediately before os.replace(). Repeating the
same requested rotation forces fresh key generation while pending.json is still
absent, so distinct complete private-key temps can accumulate outside Wave 135's
current-publication residue scan. The test then completes two legitimate Wave
135 rotations and checks whether validation still reports sequence 2 while the
abandoned private-key temps remain.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import sys
import tempfile
import time
from pathlib import Path

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS as w
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_AUTHENTICATED_ANCHOR as protocol
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_INIT_RECOVERY as w131
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_ROTATION as w132
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_ROTATION_SELFTEST as t132
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ROTATION_PUBLICATION_RECOVERY as w135

SCRIPT = Path(__file__).resolve()
ENV_UID = t132.ENV_UID
CUTS = 10


def rid(name: str) -> str:
    return hashlib.sha256(("AXM-W135-VERIFIER-PENDING-" + name).encode()).hexdigest()


def parse(cp) -> dict:
    lines = cp.stdout.strip().splitlines()
    if not lines:
        return {"ok": False, "error": f"missing-json:{cp.returncode}:{cp.stderr[-1000:]}"}
    try:
        return json.loads(lines[-1])
    except Exception:
        return {"ok": False, "error": f"json-parse:{cp.stdout[-1000:]}"}


def run_as(anchor_uid: int, worker_uid: int, args: list[str], check: bool = True):
    return t132.run_as(
        anchor_uid,
        t132.pycmd(str(SCRIPT), *args),
        extra_env={ENV_UID: str(worker_uid)},
        check=check,
        timeout=60.0,
    )


def popen_as(anchor_uid: int, worker_uid: int, args: list[str]):
    return t132.popen_as(
        anchor_uid,
        t132.pycmd(str(SCRIPT), *args),
        extra_env={ENV_UID: str(worker_uid)},
    )


def wait_json(path: Path, proc, timeout: float = 20.0) -> dict:
    return t132.wait_json(path, proc, timeout)


def child_cut(anchor: Path, witness: Path, rotation_id: str, marker: Path) -> int:
    """Pause only at pending_private.pem random-temp -> final replace."""
    real_replace = os.replace
    target = anchor / w132.ROT_DIR / w132.PENDING_PRIVATE

    def hooked_replace(src, dst, *args, **kwargs):
        srcp, dstp = Path(src), Path(dst)
        if dstp == target and srcp.name.startswith(w132.PENDING_PRIVATE + ".tmp-"):
            private = srcp.read_bytes()
            public = w131._response_public_from_private(private)
            payload = {
                "pid": os.getpid(),
                "src": str(srcp),
                "dst": str(dstp),
                "src_size": len(private),
                "src_sha256": w.sha256_hex(private),
                "derived_public_fingerprint": protocol._public_fingerprint(public),
                "pending_json_exists": (anchor / w132.ROT_DIR / w132.PENDING).exists(),
            }
            fd = os.open(str(marker), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
            try:
                os.write(fd, w.canonical(payload) + b"\n")
                os.fsync(fd)
            finally:
                os.close(fd)
            w._fsync_dir(marker.parent)
            while True:
                time.sleep(1)
        return real_replace(src, dst, *args, **kwargs)

    os.replace = hooked_replace
    try:
        out = w135.rotate_response_key(anchor, witness, rotation_id)
    except BaseException as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 3
    print(json.dumps({"ok": True, "result": out}, sort_keys=True))
    return 0


def child_rotate(anchor: Path, witness: Path, rotation_id: str) -> int:
    try:
        out = w135.rotate_response_key(anchor, witness, rotation_id)
    except BaseException as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 3
    print(json.dumps({"ok": True, "result": out}, sort_keys=True))
    return 0


def child_validate(anchor: Path, witness: Path) -> int:
    try:
        out = w135.validate_rotation_state(anchor, witness)
    except BaseException as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 3
    print(json.dumps({"ok": True, "result": out}, sort_keys=True))
    return 0


def kill_pending_private(anchor_uid: int, worker_uid: int, anchor: Path, witness: Path,
                         rotation_id: str, marker: Path) -> dict:
    proc = popen_as(anchor_uid, worker_uid, [
        "--child-cut", str(anchor), str(witness), rotation_id, str(marker)
    ])
    try:
        observed = wait_json(marker, proc)
        os.kill(proc.pid, signal.SIGKILL)
        proc.wait(timeout=5)
        return observed
    finally:
        if proc.poll() is None:
            os.kill(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5)


def pending_private_temps(anchor: Path) -> list[Path]:
    rd = anchor / w132.ROT_DIR
    return sorted(rd.glob(w132.PENDING_PRIVATE + ".tmp-*"))


def describe_temps(anchor: Path) -> list[dict]:
    out = []
    for p in pending_private_temps(anchor):
        private = p.read_bytes()
        public = w131._response_public_from_private(private)
        out.append({
            "path": str(p),
            "size": len(private),
            "sha256": w.sha256_hex(private),
            "mode": oct(p.stat().st_mode & 0o777),
            "uid": p.stat().st_uid,
            "derived_public_fingerprint": protocol._public_fingerprint(public),
        })
    return out


def run_suite(worker_uid: int, anchor_uid: int, report_path: Path | None) -> int:
    if os.geteuid() != 0:
        raise PermissionError("wave135-verifier-requires-root-orchestrator")
    if worker_uid == anchor_uid:
        raise ValueError("worker-and-anchor-uid-must-differ")

    base = Path(tempfile.mkdtemp(prefix="axm-w135-verifier-pending-private-"))
    os.chmod(base, 0o777)
    witness, anchor, _, _ = t132.setup_case(base, "pending-private", anchor_uid, worker_uid)

    rotation1 = rid("rotation-1")
    cuts: list[dict] = []
    counts: list[int] = []
    for i in range(CUTS):
        marker = base / f"pending-private-cut-{i}.json"
        obs = kill_pending_private(anchor_uid, worker_uid, anchor, witness, rotation1, marker)
        cuts.append({**obs, "src_exists_after_kill": Path(obs["src"]).exists()})
        counts.append(len(pending_private_temps(anchor)))

    before = describe_temps(anchor)
    unique_hashes_before = len({x["sha256"] for x in before})
    unique_publics_before = len({x["derived_public_fingerprint"] for x in before})
    total_secret_bytes_before = sum(x["size"] for x in before)
    pending_json_absent_after_cuts = not (anchor / w132.ROT_DIR / w132.PENDING).exists()

    first = parse(run_as(anchor_uid, worker_uid, [
        "--child-rotate", str(anchor), str(witness), rotation1
    ]))
    after_first = describe_temps(anchor)
    first_validate = parse(run_as(anchor_uid, worker_uid, [
        "--child-validate", str(anchor), str(witness)
    ]))

    rotation2 = rid("rotation-2")
    second = parse(run_as(anchor_uid, worker_uid, [
        "--child-rotate", str(anchor), str(witness), rotation2
    ]))
    after_second = describe_temps(anchor)
    final_validate = parse(run_as(anchor_uid, worker_uid, [
        "--child-validate", str(anchor), str(witness)
    ]))

    current_public = (anchor / protocol.PUBLIC_KEY).read_bytes()
    current_fp = protocol._public_fingerprint(current_public)
    orphan_publics = {x["derived_public_fingerprint"] for x in after_second}

    failure_reproduced = (
        counts == list(range(1, CUTS + 1))
        and len(before) == CUTS
        and unique_hashes_before == CUTS
        and unique_publics_before == CUTS
        and all(x["uid"] == anchor_uid and x["mode"] == "0o600" for x in before)
        and pending_json_absent_after_cuts
        and first.get("ok") is True
        and first.get("result", {}).get("seq") == 1
        and first_validate.get("ok") is True
        and len(after_first) == CUTS
        and second.get("ok") is True
        and second.get("result", {}).get("seq") == 2
        and len(after_second) == CUTS
        and final_validate.get("ok") is True
        and final_validate.get("result", {}).get("seq") == 2
        and current_fp not in orphan_publics
    )

    report = {
        "schema": "axm.flowing-compute.wave135-independent-pending-private-temp-residue-verifier.v1",
        "mode": "optimized" if sys.flags.optimize else "normal",
        "verdict": (
            "FAIL_PENDING_PRIVATE_SIGKILL_RETRIES_ACCUMULATE_DISTINCT_SECRET_TEMPS_UNSEEN_BY_WAVE135_VALIDATOR"
            if failure_reproduced else "NOT_REPRODUCED"
        ),
        "builder_evidence_head_challenged": "e486f7fd1383115f020f2c6d047ee2c63d91c6d7",
        "builder_exact_green_source": "03cfcd0ceab3884796c28ed5d25fa8cc0f3b2c71",
        "cuts": cuts,
        "residue_counts_after_each_kill": counts,
        "pending_private_temps_before_clean_retry": before,
        "unique_private_hashes_before": unique_hashes_before,
        "unique_derived_public_fingerprints_before": unique_publics_before,
        "total_secret_bytes_before": total_secret_bytes_before,
        "pending_json_absent_after_all_cuts": pending_json_absent_after_cuts,
        "rotation1": first,
        "validation_after_rotation1": first_validate,
        "residue_after_rotation1": after_first,
        "rotation2": second,
        "final_validation": final_validate,
        "residue_after_rotation2": after_second,
        "current_public_fingerprint": current_fp,
        "checks": {
            "ten_cuts_grow_residue_one_for_one": counts == list(range(1, CUTS + 1)),
            "ten_complete_private_temps_retained": len(before) == CUTS,
            "ten_distinct_private_keys_generated": unique_hashes_before == CUTS,
            "authority_owned_mode_0600": bool(before) and all(
                x["uid"] == anchor_uid and x["mode"] == "0o600" for x in before
            ),
            "pending_transaction_never_became_durable_during_cuts": pending_json_absent_after_cuts,
            "rotation1_completed_and_validator_green": (
                first.get("ok") is True and first.get("result", {}).get("seq") == 1
                and first_validate.get("ok") is True
            ),
            "residue_survives_rotation1": len(after_first) == CUTS,
            "rotation2_completed": second.get("ok") is True and second.get("result", {}).get("seq") == 2,
            "residue_survives_rotation2": len(after_second) == CUTS,
            "wave135_validator_reports_seq2_despite_pending_secret_residue": (
                final_validate.get("ok") is True and final_validate.get("result", {}).get("seq") == 2
            ),
            "retained_abandoned_keys_are_not_current_key": current_fp not in orphan_publics,
        },
        "truth_boundary": (
            "Same-host Linux SIGKILL at the explicitly unproved pending-transaction creation boundary: after a full "
            "pending_private.pem random temp is written and fsynced but before its os.replace. This does not falsify "
            "Wave 135's bounded post-pending current-key publication repair. It demonstrates that repeated exact "
            "rotation retries can still accumulate distinct complete authority-owned abandoned successor private-key "
            "temps one-for-one, and the Wave 135 residue scan/validator does not include them after later valid rotations. "
            "No worker read of the 0700 authority directory, no signature/key forgery, no stale-authority acceptance, "
            "no root/kernel or authority-UID compromise, and no performance/energy/retained-compute claim is asserted."
        ),
    }
    if report_path:
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if failure_reproduced else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker-uid", type=int)
    ap.add_argument("--anchor-uid", type=int)
    ap.add_argument("--report")
    ap.add_argument("--child-cut", nargs=4, metavar=("ANCHOR", "WITNESS", "RID", "MARKER"))
    ap.add_argument("--child-rotate", nargs=3, metavar=("ANCHOR", "WITNESS", "RID"))
    ap.add_argument("--child-validate", nargs=2, metavar=("ANCHOR", "WITNESS"))
    ns = ap.parse_args()
    if ns.child_cut:
        a, wi, ri, marker = ns.child_cut
        return child_cut(Path(a), Path(wi), ri, Path(marker))
    if ns.child_rotate:
        a, wi, ri = ns.child_rotate
        return child_rotate(Path(a), Path(wi), ri)
    if ns.child_validate:
        a, wi = ns.child_validate
        return child_validate(Path(a), Path(wi))
    if ns.worker_uid is None or ns.anchor_uid is None:
        ap.error("--worker-uid and --anchor-uid required")
    return run_suite(ns.worker_uid, ns.anchor_uid, Path(ns.report) if ns.report else None)


if __name__ == "__main__":
    raise SystemExit(main())
