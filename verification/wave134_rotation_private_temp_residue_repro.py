#!/usr/bin/env python3
"""Independent Wave 134 verifier: stale private-key temp retention in rotation path.

NON-CANON verifier lane. Builder files remain unchanged.

Wave 134 repairs atomic bootstrap publication, but rotate_response_key() still
hands the full Wave 132 rotation transaction to the older random-temp
_atomic_write helper. This reproducer SIGKILLs the authority process after a
new response_private.pem temp has been fully written+fsync'd and immediately
before os.replace(). It repeats the exact rotation, completes it, advances to a
second rotation, then checks whether historical private-key temp copies remain
while Wave 134 validation still reports the state as valid.
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
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ATOMIC_RECOVERY as w134

SCRIPT = Path(__file__).resolve()
ENV_UID = t132.ENV_UID


def rid(name: str) -> str:
    return hashlib.sha256(("AXM-W134-VERIFIER-" + name).encode()).hexdigest()


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
    real_replace = os.replace

    def hooked_replace(src, dst, *args, **kwargs):
        srcp, dstp = Path(src), Path(dst)
        if (
            dstp.name == protocol.PRIVATE_KEY
            and srcp.name.startswith(protocol.PRIVATE_KEY + ".tmp-")
        ):
            private = srcp.read_bytes()
            public = w131._response_public_from_private(private)
            payload = {
                "pid": os.getpid(),
                "src": str(srcp),
                "dst": str(dstp),
                "src_size": len(private),
                "src_sha256": w.sha256_hex(private),
                "derived_public_fingerprint": protocol._public_fingerprint(public),
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
        out = w134.rotate_response_key(anchor, witness, rotation_id)
    except BaseException as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 3
    print(json.dumps({"ok": True, "result": out}, sort_keys=True))
    return 0


def child_rotate(anchor: Path, witness: Path, rotation_id: str) -> int:
    try:
        out = w134.rotate_response_key(anchor, witness, rotation_id)
    except BaseException as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 3
    print(json.dumps({"ok": True, "result": out}, sort_keys=True))
    return 0


def child_validate(anchor: Path, witness: Path) -> int:
    try:
        out = w134.validate_rotation_state(anchor, witness)
    except BaseException as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 3
    print(json.dumps({"ok": True, "result": out}, sort_keys=True))
    return 0


def kill_private_replace(anchor_uid: int, worker_uid: int, anchor: Path, witness: Path,
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


def run_suite(worker_uid: int, anchor_uid: int, report_path: Path | None) -> int:
    if os.geteuid() != 0:
        raise PermissionError("wave134-verifier-requires-root-orchestrator")
    if worker_uid == anchor_uid:
        raise ValueError("worker-and-anchor-uid-must-differ")

    base = Path(tempfile.mkdtemp(prefix="axm-w134-verifier-private-temp-"))
    os.chmod(base, 0o777)
    witness, anchor, _, _ = t132.setup_case(base, "private-temp", anchor_uid, worker_uid)

    rotation1 = rid("rotation-1")
    cuts: list[dict] = []
    for i in range(3):
        marker = base / f"cut-{i}.json"
        obs = kill_private_replace(anchor_uid, worker_uid, anchor, witness, rotation1, marker)
        src = Path(obs["src"])
        cuts.append({**obs, "exists_after_kill": src.exists()})

    orphan_paths = sorted(anchor.glob(protocol.PRIVATE_KEY + ".tmp-*"))
    orphan_before = []
    for p in orphan_paths:
        private = p.read_bytes()
        orphan_before.append({
            "path": str(p),
            "size": len(private),
            "sha256": w.sha256_hex(private),
            "mode": oct(p.stat().st_mode & 0o777),
            "uid": p.stat().st_uid,
            "derived_public_fingerprint": protocol._public_fingerprint(
                w131._response_public_from_private(private)
            ),
        })

    first = parse(run_as(anchor_uid, worker_uid, [
        "--child-rotate", str(anchor), str(witness), rotation1
    ]))
    after_first_validate = parse(run_as(anchor_uid, worker_uid, [
        "--child-validate", str(anchor), str(witness)
    ]))

    seq1_public = (anchor / w132.ROT_DIR / "public-000001.pem").read_bytes()
    seq1_fp = protocol._public_fingerprint(seq1_public)

    rotation2 = rid("rotation-2")
    second = parse(run_as(anchor_uid, worker_uid, [
        "--child-rotate", str(anchor), str(witness), rotation2
    ]))
    final_validate = parse(run_as(anchor_uid, worker_uid, [
        "--child-validate", str(anchor), str(witness)
    ]))

    current_public = (anchor / protocol.PUBLIC_KEY).read_bytes()
    current_fp = protocol._public_fingerprint(current_public)
    orphan_after_paths = sorted(anchor.glob(protocol.PRIVATE_KEY + ".tmp-*"))
    orphan_after = []
    for p in orphan_after_paths:
        private = p.read_bytes()
        orphan_after.append({
            "path": str(p),
            "size": len(private),
            "sha256": w.sha256_hex(private),
            "mode": oct(p.stat().st_mode & 0o777),
            "uid": p.stat().st_uid,
            "derived_public_fingerprint": protocol._public_fingerprint(
                w131._response_public_from_private(private)
            ),
        })

    same_secret = len({x["sha256"] for x in orphan_before}) == 1 if orphan_before else False
    historical_match = bool(orphan_after) and all(
        x["derived_public_fingerprint"] == seq1_fp for x in orphan_after
    )
    current_advanced = current_fp != seq1_fp
    validation_ignores_residue = (
        final_validate.get("ok") is True
        and final_validate.get("result", {}).get("seq") == 2
    )

    failure_reproduced = (
        len(orphan_before) >= 3
        and all(x["uid"] == anchor_uid and x["mode"] == "0o600" for x in orphan_before)
        and same_secret
        and first.get("ok") is True
        and first.get("result", {}).get("seq") == 1
        and after_first_validate.get("ok") is True
        and len(orphan_after) >= 3
        and historical_match
        and second.get("ok") is True
        and second.get("result", {}).get("seq") == 2
        and current_advanced
        and validation_ignores_residue
    )

    report = {
        "schema": "axm.flowing-compute.wave134-independent-private-temp-residue-verifier.v1",
        "mode": "optimized" if sys.flags.optimize else "normal",
        "verdict": (
            "FAIL_ROTATION_PRIVATE_KEY_ATOMIC_KILLS_RETAIN_HISTORICAL_SECRET_TEMPS"
            if failure_reproduced else "NOT_REPRODUCED"
        ),
        "builder_head_challenged": "0f326221584e45723e8a9855f4d8fad5635711ac",
        "builder_exact_green_source": "20abcb846a48709dba4ba345380a1782f3fa83c8",
        "cuts": cuts,
        "orphan_before_clean_retry": orphan_before,
        "rotation1": first,
        "validation_after_rotation1": after_first_validate,
        "seq1_public_fingerprint": seq1_fp,
        "rotation2": second,
        "final_validation": final_validate,
        "current_public_fingerprint": current_fp,
        "orphan_after_rotation2": orphan_after,
        "checks": {
            "three_or_more_private_temps_accumulated": len(orphan_before) >= 3,
            "orphan_owner_mode_are_authority_0600": bool(orphan_before) and all(
                x["uid"] == anchor_uid and x["mode"] == "0o600" for x in orphan_before
            ),
            "repeated_exact_retry_retained_same_private_secret": same_secret,
            "rotation1_completed": first.get("ok") is True and first.get("result", {}).get("seq") == 1,
            "rotation2_completed": second.get("ok") is True and second.get("result", {}).get("seq") == 2,
            "historical_seq1_private_key_still_present_after_seq2": historical_match,
            "current_key_advanced_beyond_seq1": current_advanced,
            "wave134_validation_reports_seq2_despite_secret_residue": validation_ignores_residue,
        },
        "truth_boundary": (
            "Same-host Linux SIGKILL immediately before the unchanged Wave-132 random-temp os.replace for "
            "response_private.pem. This does not falsify Wave 134's stated bootstrap-only atomic recovery. "
            "It demonstrates that the next full-rotation gate can retain multiple authority-owned historical "
            "private-key temp files while the normal Wave-134 validator still reports the rotation state valid. "
            "No worker read of the 0700 authority directory, no signature/key forgery, no stale authority acceptance, "
            "no performance/energy claim, and no root/kernel or authority-UID compromise is asserted."
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
