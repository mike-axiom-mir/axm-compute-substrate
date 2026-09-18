#!/usr/bin/env python3
"""Wave 135 adversarial self-test: recoverable current-key rotation publication."""
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
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_ROTATION as w132
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_ROTATION_SELFTEST as t132
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ATOMIC_RECOVERY as w134
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ROTATION_PUBLICATION_RECOVERY as w135

SCRIPT = Path(__file__).resolve()
ENV_UID = t132.ENV_UID
CUT_STAGE = "post_close_pre_replace"


def rid(name: str) -> str:
    return hashlib.sha256(("AXM-W135-" + name).encode()).hexdigest()


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


def child_w134_cut(anchor: Path, witness: Path, rotation_id: str, marker: Path) -> int:
    """Reproduce PR #59's predecessor random-temp cut exactly enough for repair control."""
    real_replace = os.replace

    def hooked_replace(src, dst, *args, **kwargs):
        srcp, dstp = Path(src), Path(dst)
        if dstp.name == protocol.PRIVATE_KEY and srcp.name.startswith(protocol.PRIVATE_KEY + ".tmp-"):
            payload = {
                "pid": os.getpid(),
                "src": str(srcp),
                "dst": str(dstp),
                "sha256": w.sha256_hex(srcp.read_bytes()),
                "size": srcp.stat().st_size,
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


def child_rotate(anchor: Path, witness: Path, rotation_id: str,
                 target: str | None, stage: str | None, marker: Path | None) -> int:
    try:
        out = w135.rotate_response_key(
            anchor, witness, rotation_id,
            atomic_fault_target=target,
            atomic_fault_after=stage,
            atomic_fault_marker=marker,
        )
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


def kill_child(proc, marker: Path) -> dict:
    try:
        observed = wait_json(marker, proc)
        os.kill(proc.pid, signal.SIGKILL)
        proc.wait(timeout=5)
        return observed
    finally:
        if proc.poll() is None:
            os.kill(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5)


def kill_w134(anchor_uid: int, worker_uid: int, anchor: Path, witness: Path,
              rotation_id: str, marker: Path) -> dict:
    proc = popen_as(anchor_uid, worker_uid, [
        "--child-w134-cut", str(anchor), str(witness), rotation_id, str(marker),
    ])
    return kill_child(proc, marker)


def kill_w135(anchor_uid: int, worker_uid: int, anchor: Path, witness: Path,
              rotation_id: str, marker: Path) -> dict:
    proc = popen_as(anchor_uid, worker_uid, [
        "--child-rotate", str(anchor), str(witness), rotation_id,
        "--atomic-target", protocol.PRIVATE_KEY,
        "--atomic-fault-after", CUT_STAGE,
        "--fault-marker", str(marker),
    ])
    return kill_child(proc, marker)


def current_private_residue(anchor: Path) -> list[Path]:
    target = anchor / protocol.PRIVATE_KEY
    return sorted([
        *w135._legacy_candidates(target),
        *w135._stage_candidates(target),
    ])


def setup(base: Path, name: str, anchor_uid: int, worker_uid: int):
    return t132.setup_case(base, name, anchor_uid, worker_uid)


def run_suite(worker_uid: int, anchor_uid: int, report_path: Path | None) -> int:
    if os.geteuid() != 0:
        raise PermissionError("wave135-selftest-requires-root-orchestrator")
    if worker_uid == anchor_uid:
        raise ValueError("worker-and-anchor-uid-must-differ")

    base = Path(tempfile.mkdtemp(prefix="axm-w135-rotation-publication-"))
    os.chmod(base, 0o777)
    results: list[dict] = []

    witness, anchor, _, _ = setup(base, "pr59-repair", anchor_uid, worker_uid)
    rotation1 = rid("pr59-rotation-1")
    cuts = []
    for i in range(3):
        marker = base / f"pr59-cut-{i}.json"
        cuts.append(kill_w134(anchor_uid, worker_uid, anchor, witness, rotation1, marker))
    old_residue = current_private_residue(anchor)
    old_hashes = [w.sha256_hex(p.read_bytes()) for p in old_residue]
    repaired = parse(run_as(anchor_uid, worker_uid, [
        "--child-rotate", str(anchor), str(witness), rotation1,
    ]))
    after_repair = current_private_residue(anchor)
    rotation2 = rid("pr59-rotation-2")
    advanced = parse(run_as(anchor_uid, worker_uid, [
        "--child-rotate", str(anchor), str(witness), rotation2,
    ]))
    final_check = parse(run_as(anchor_uid, worker_uid, [
        "--child-validate", str(anchor), str(witness),
    ]))
    results.append({
        "name": "pr59_historical_private_temp_amplification_is_recovered_and_removed",
        "ok": (
            len(old_residue) >= 3 and len(set(old_hashes)) == 1 and
            repaired.get("ok") is True and repaired.get("result", {}).get("seq") == 1 and
            not after_repair and advanced.get("ok") is True and
            advanced.get("result", {}).get("seq") == 2 and
            not current_private_residue(anchor) and final_check.get("ok") is True and
            final_check.get("result", {}).get("seq") == 2
        ),
        "detail": {
            "old_residue_count": len(old_residue),
            "old_hashes_unique": len(set(old_hashes)),
            "seq_after_repair": repaired.get("result", {}).get("seq"),
            "seq_after_second_rotation": advanced.get("result", {}).get("seq"),
            "final_residue": [str(p) for p in current_private_residue(anchor)],
        },
    })

    witness, anchor, _, _ = setup(base, "ten-cuts", anchor_uid, worker_uid)
    rotation = rid("ten-cuts")
    counts = []
    paths = []
    for i in range(10):
        marker = base / f"ten-cut-{i}.json"
        kill_w135(anchor_uid, worker_uid, anchor, witness, rotation, marker)
        residue = current_private_residue(anchor)
        counts.append(len(residue))
        paths.append([p.name for p in residue])
    recovered = parse(run_as(anchor_uid, worker_uid, [
        "--child-rotate", str(anchor), str(witness), rotation,
    ]))
    retry = parse(run_as(anchor_uid, worker_uid, [
        "--child-rotate", str(anchor), str(witness), rotation,
    ]))
    results.append({
        "name": "ten_repeated_private_replace_sigkills_reuse_one_stage_then_recover",
        "ok": (
            counts == [1] * 10 and len({tuple(x) for x in paths}) == 1 and
            recovered.get("ok") is True and recovered.get("result", {}).get("seq") == 1 and
            retry.get("ok") is True and retry.get("result", {}).get("seq") == 1 and
            retry.get("result", {}).get("idempotent") is True and
            not current_private_residue(anchor)
        ),
        "detail": {
            "residue_counts": counts,
            "unique_stage_paths": len({tuple(x) for x in paths}),
            "seq": recovered.get("result", {}).get("seq"),
            "idempotent": retry.get("result", {}).get("idempotent"),
        },
    })

    witness, anchor, _, _ = setup(base, "wrong-stage", anchor_uid, worker_uid)
    rotation = rid("wrong-stage")
    marker = base / "wrong-stage-cut.json"
    kill_w135(anchor_uid, worker_uid, anchor, witness, rotation, marker)
    stage = current_private_residue(anchor)[0]
    original_stage = stage.read_bytes()
    stage.write_bytes(b"wrong-wave135-private-stage\n")
    os.chown(stage, anchor_uid, anchor_uid)
    os.chmod(stage, 0o600)
    cp = run_as(anchor_uid, worker_uid, [
        "--child-rotate", str(anchor), str(witness), rotation,
    ], check=False)
    results.append({
        "name": "wrong_byte_private_stage_fails_closed_and_is_retained",
        "ok": (
            cp.returncode != 0 and stage.exists() and
            stage.read_bytes() == b"wrong-wave135-private-stage\n" and
            original_stage != stage.read_bytes()
        ),
        "detail": {"returncode": cp.returncode, "error": parse(cp).get("error")},
    })

    witness, anchor, _, _ = setup(base, "foreign-stage", anchor_uid, worker_uid)
    rotation = rid("foreign-stage")
    marker = base / "foreign-stage-cut.json"
    kill_w135(anchor_uid, worker_uid, anchor, witness, rotation, marker)
    stage = current_private_residue(anchor)[0]
    stage_bytes = stage.read_bytes()
    os.chown(stage, worker_uid, worker_uid)
    cp = run_as(anchor_uid, worker_uid, [
        "--child-rotate", str(anchor), str(witness), rotation,
    ], check=False)
    results.append({
        "name": "foreign_owner_exact_private_stage_fails_closed_and_is_retained",
        "ok": (
            cp.returncode != 0 and stage.exists() and stage.read_bytes() == stage_bytes and
            stage.stat().st_uid == worker_uid
        ),
        "detail": {"returncode": cp.returncode, "error": parse(cp).get("error"),
                   "owner": stage.stat().st_uid},
    })

    witness, anchor, _, _ = setup(base, "clean-two", anchor_uid, worker_uid)
    one = parse(run_as(anchor_uid, worker_uid, [
        "--child-rotate", str(anchor), str(witness), rid("clean-one"),
    ]))
    two = parse(run_as(anchor_uid, worker_uid, [
        "--child-rotate", str(anchor), str(witness), rid("clean-two"),
    ]))
    final = parse(run_as(anchor_uid, worker_uid, [
        "--child-validate", str(anchor), str(witness),
    ]))
    results.append({
        "name": "clean_two_rotation_lineage_remains_valid",
        "ok": (
            one.get("ok") is True and one.get("result", {}).get("seq") == 1 and
            two.get("ok") is True and two.get("result", {}).get("seq") == 2 and
            final.get("ok") is True and final.get("result", {}).get("seq") == 2 and
            not current_private_residue(anchor)
        ),
        "detail": {"seq1": one.get("result", {}).get("seq"),
                   "seq2": two.get("result", {}).get("seq")},
    })

    passed = sum(bool(r["ok"]) for r in results)
    report = {
        "schema": "axm.flowing-compute.wave135-recoverable-rotation-publication-selftest.v1",
        "mode": "optimized" if sys.flags.optimize else "normal",
        "worker_uid": worker_uid,
        "anchor_uid": anchor_uid,
        "passed": passed,
        "total": len(results),
        "results": results,
        "truth_boundary": (
            "same-host Linux/process/filesystem recovery for the post-pending Wave-132 current-key publication "
            "boundary challenged by verifier PR #59. The test proves bounded recovery/deduplication for exact "
            "authority-owned historical response-private temps and deterministic current-key stages, including ten "
            "repeated SIGKILLs. Wrong-byte and foreign-owner stages fail closed and remain visible. Pending-transaction "
            "creation, append-style lineage internal cuts, cleanup cuts, validation-to-service object identity, user "
            "namespace aliasing, copied genuine keys across hosts, root/kernel or authority-UID compromise, whole-domain "
            "rollback, hardware custody, performance/energy/retained/incremental/dormant-compute, throughput/scaling, "
            "provider independence and physical finality remain unproved."
        ),
    }
    if report_path:
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if passed == len(results) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker-uid", type=int)
    ap.add_argument("--anchor-uid", type=int)
    ap.add_argument("--report")
    ap.add_argument("--child-w134-cut", nargs=4, metavar=("ANCHOR", "WITNESS", "RID", "MARKER"))
    ap.add_argument("--child-rotate", nargs=3, metavar=("ANCHOR", "WITNESS", "RID"))
    ap.add_argument("--child-validate", nargs=2, metavar=("ANCHOR", "WITNESS"))
    ap.add_argument("--atomic-target")
    ap.add_argument("--atomic-fault-after", choices=sorted(w135.ATOMIC_FAULT_STAGES))
    ap.add_argument("--fault-marker")
    ns = ap.parse_args()
    if ns.child_w134_cut:
        a, wi, ri, marker = ns.child_w134_cut
        return child_w134_cut(Path(a), Path(wi), ri, Path(marker))
    if ns.child_rotate:
        a, wi, ri = ns.child_rotate
        return child_rotate(
            Path(a), Path(wi), ri, ns.atomic_target, ns.atomic_fault_after,
            Path(ns.fault_marker) if ns.fault_marker else None,
        )
    if ns.child_validate:
        a, wi = ns.child_validate
        return child_validate(Path(a), Path(wi))
    if ns.worker_uid is None or ns.anchor_uid is None:
        ap.error("--worker-uid and --anchor-uid required")
    return run_suite(ns.worker_uid, ns.anchor_uid, Path(ns.report) if ns.report else None)


if __name__ == "__main__":
    raise SystemExit(main())
