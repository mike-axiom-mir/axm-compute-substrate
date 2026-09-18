#!/usr/bin/env python3
"""Independent Wave 133 verifier: SIGKILL inside the shared atomic-write helper.

NON-CANON verifier lane only. Builder files are not modified.

Wave 133 explicitly tests kills *after* named publication boundaries. This
reproducer widens the cut one step into the production `_atomic_write`: after
the exact temp file has been written+fsync'd and the helper is about to call
`os.replace`, but before the replace occurs. We intercept only `os.replace` to
make that natural instant observable, then the parent sends a real SIGKILL.
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
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_ROTATION as w132
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_ROTATION_SELFTEST as t132
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ROTATION_BOOTSTRAP_RECOVERY as w133

SCRIPT = Path(__file__).resolve()
ENV_UID = t132.ENV_UID


def rid(name: str) -> str:
    return hashlib.sha256(("AXM-W133-ATOMIC-TEMP-" + name).encode()).hexdigest()


def parse(cp) -> dict:
    try:
        return json.loads(cp.stdout)
    except Exception:
        return {"ok": False, "parse_error": cp.stdout[-1000:]}


def child_cut(anchor: Path, witness: Path, target_name: str, marker: Path) -> int:
    real_replace = os.replace

    def hooked_replace(src, dst, *args, **kwargs):
        srcp, dstp = Path(src), Path(dst)
        if dstp.name == target_name and srcp.name.startswith(target_name + ".tmp-"):
            marker.write_text(json.dumps({
                "pid": os.getpid(),
                "src": str(srcp),
                "dst": str(dstp),
                "src_exists": srcp.exists(),
                "src_size": srcp.stat().st_size if srcp.exists() else None,
            }, sort_keys=True) + "\n")
            with marker.open("rb") as fh:
                os.fsync(fh.fileno())
            while True:
                time.sleep(1)
        return real_replace(src, dst, *args, **kwargs)

    os.replace = hooked_replace
    try:
        out = w133.ensure_rotation_bootstrap(anchor, witness)
    except BaseException as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 3
    print(json.dumps({"ok": True, "result": out}, sort_keys=True))
    return 0


def child_bootstrap(anchor: Path, witness: Path) -> int:
    try:
        out = w133.ensure_rotation_bootstrap(anchor, witness)
    except BaseException as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 3
    print(json.dumps({"ok": True, "result": out}, sort_keys=True))
    return 0


def child_rotate(anchor: Path, witness: Path, rotation_id: str) -> int:
    try:
        out = w133.rotate_response_key(anchor, witness, rotation_id)
    except BaseException as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 3
    print(json.dumps({"ok": True, "result": out}, sort_keys=True))
    return 0


def wait_marker(marker: Path, proc, timeout: float = 10.0) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        if marker.exists():
            return json.loads(marker.read_text())
        if proc.poll() is not None:
            raise RuntimeError(f"child-exited-before-marker:{proc.returncode}:{proc.stdout.read()[-1000:]}")
        time.sleep(0.01)
    raise TimeoutError(f"marker-timeout:{marker}")


def kill_before_replace(anchor_uid: int, worker_uid: int, anchor: Path, witness: Path,
                        target_name: str, marker: Path) -> dict:
    proc = t132.popen_as(
        anchor_uid,
        t132.pycmd(str(SCRIPT), "--child-cut", str(anchor), str(witness), target_name, str(marker)),
        extra_env={ENV_UID: str(worker_uid)},
    )
    try:
        observed = wait_marker(marker, proc)
        os.kill(proc.pid, signal.SIGKILL)
        proc.wait(timeout=5)
        return {**observed, "returncode": proc.returncode}
    finally:
        if proc.poll() is None:
            os.kill(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5)


def run_as(anchor_uid: int, worker_uid: int, args: list[str], check: bool = True):
    return t132.run_as(
        anchor_uid,
        t132.pycmd(str(SCRIPT), *args),
        extra_env={ENV_UID: str(worker_uid)},
        check=check,
    )


def setup(base: Path, name: str, anchor_uid: int, worker_uid: int):
    return t132.setup_case(base, name, anchor_uid, worker_uid)


def run_suite(worker_uid: int, anchor_uid: int, report_path: Path | None) -> int:
    if os.geteuid() != 0:
        raise PermissionError("wave133-atomic-temp-verifier-requires-root-orchestrator")
    if worker_uid == anchor_uid:
        raise ValueError("worker-and-anchor-uid-must-differ")

    results: list[dict] = []
    base = Path(tempfile.mkdtemp(prefix="axm-w133-atomic-temp-verifier-"))
    os.chmod(base, 0o777)

    # Case A: kill after production temp write+fsync for bootstrap.json but
    # before os.replace. The stale temp lives *inside* response_rotation.
    witness, anchor, _, _ = setup(base, "intent-cut", anchor_uid, worker_uid)
    marker = base / "intent-cut.marker"
    cut = kill_before_replace(anchor_uid, worker_uid, anchor, witness, w133.BOOTSTRAP_INTENT, marker)
    rd = anchor / w132.ROT_DIR
    intent_temps = sorted(p for p in rd.glob(w133.BOOTSTRAP_INTENT + ".tmp-*") if p.is_file())
    temp_before = intent_temps[0].read_bytes() if len(intent_temps) == 1 else b""
    retry1 = run_as(anchor_uid, worker_uid, ["--child-bootstrap", str(anchor), str(witness)], check=False)
    retry2 = run_as(anchor_uid, worker_uid, ["--child-bootstrap", str(anchor), str(witness)], check=False)
    retry1_obj, retry2_obj = parse(retry1), parse(retry2)
    temp_still = len(intent_temps) == 1 and intent_temps[0].exists() and intent_temps[0].read_bytes() == temp_before
    blocked = (
        cut.get("src_exists") is True and cut.get("returncode") == -signal.SIGKILL and
        len(intent_temps) == 1 and not (rd / w133.BOOTSTRAP_INTENT).exists() and
        retry1.returncode != 0 and retry2.returncode != 0 and temp_still and
        "wave133-unexpected-pre-ready-artifacts" in str(retry1_obj.get("error", "")) and
        "wave133-unexpected-pre-ready-artifacts" in str(retry2_obj.get("error", ""))
    )
    results.append({
        "name": "sigkill_inside_atomic_write_before_bootstrap_intent_replace_blocks_exact_retry",
        "ok": blocked,
        "detail": {
            "cut": cut,
            "temp_names": [p.name for p in intent_temps],
            "temp_sha256": hashlib.sha256(temp_before).hexdigest() if temp_before else None,
            "retry1_returncode": retry1.returncode,
            "retry1": retry1_obj,
            "retry2_returncode": retry2.returncode,
            "retry2": retry2_obj,
            "temp_persisted_unchanged": temp_still,
        },
    })

    # Diagnostic only: removing exactly the orphan helper temp restores the
    # same untouched Wave-133 bootstrap and rotation path. This localizes the
    # liveness loss to stale atomic-helper residue rather than missing authority.
    if len(intent_temps) == 1:
        intent_temps[0].unlink()
        w._fsync_dir(rd)
    repaired = run_as(anchor_uid, worker_uid, ["--child-rotate", str(anchor), str(witness), rid("intent-cut")], check=False)
    repaired_obj = parse(repaired)
    results.append({
        "name": "manual_removal_of_only_orphan_temp_restores_exact_authorized_rotation",
        "ok": repaired.returncode == 0 and repaired_obj.get("ok") is True and repaired_obj.get("result", {}).get("seq") == 1,
        "detail": {"returncode": repaired.returncode, "result": repaired_obj},
    })

    # Case B: same natural cut for the witness-lineage bootstrap write. The
    # orphan temp lives outside response_rotation, so Wave 133 retries past it;
    # successful recovery leaves the stale authority-owned file resident.
    witness2, anchor2, _, _ = setup(base, "witness-lineage-cut", anchor_uid, worker_uid)
    marker2 = base / "witness-lineage-cut.marker"
    cut2 = kill_before_replace(anchor_uid, worker_uid, anchor2, witness2, w132.WITNESS_LINEAGE, marker2)
    witness_temps = sorted(p for p in witness2.glob(w132.WITNESS_LINEAGE + ".tmp-*") if p.is_file())
    stale_before = witness_temps[0].read_bytes() if len(witness_temps) == 1 else b""
    recover2 = run_as(anchor_uid, worker_uid, ["--child-rotate", str(anchor2), str(witness2), rid("witness-lineage-cut")], check=False)
    recover2_obj = parse(recover2)
    stale_after = (
        len(witness_temps) == 1 and witness_temps[0].exists() and
        witness_temps[0].read_bytes() == stale_before
    )
    results.append({
        "name": "witness_lineage_atomic_temp_is_silently_retained_after_successful_retry",
        "ok": (
            cut2.get("src_exists") is True and cut2.get("returncode") == -signal.SIGKILL and
            len(witness_temps) == 1 and recover2.returncode == 0 and recover2_obj.get("ok") is True and
            recover2_obj.get("result", {}).get("seq") == 1 and stale_after
        ),
        "detail": {
            "cut": cut2,
            "temp_names": [p.name for p in witness_temps],
            "temp_sha256": hashlib.sha256(stale_before).hexdigest() if stale_before else None,
            "retry_returncode": recover2.returncode,
            "retry": recover2_obj,
            "orphan_persisted_after_success": stale_after,
        },
    })

    passed = sum(bool(r["ok"]) for r in results)
    report = {
        "schema": "axm.flowing-compute.wave133-atomic-temp-kill-verifier.v1",
        "mode": "optimized" if sys.flags.optimize else "normal",
        "builder_wave133_tool_blob": "934dad194c800bcf768bdac918fe02fbe8449495",
        "shared_atomic_write_tool_blob": "2e87f9416d8ec0d9d04b46e842ac2d7a1a9e0f08",
        "worker_uid": worker_uid,
        "anchor_uid": anchor_uid,
        "passed": passed,
        "total": len(results),
        "results": results,
        "verdict": (
            "FAIL_EXACT_RETRY_AFTER_SIGKILL_BEFORE_ATOMIC_REPLACE_IS_BLOCKED_BY_OWN_STALE_TEMP; "
            "separate witness-lineage cut also shows accepted retained temp residue"
        ),
        "truth_boundary": (
            "same-host Linux/process/filesystem verifier at the production atomic-write pre-replace boundary. "
            "The helper writes+fsyncs the exact temp bytes; verifier delays only os.replace so a real SIGKILL "
            "can land at that natural instant. This is outside Wave 133's stated named post-publication kill claim, "
            "so it is a bounded next-gate failure, not a reclassification of the 12/12 builder suite. No root/kernel "
            "compromise, authority-key forgery, cross-host uniqueness, performance, energy, retained/incremental/"
            "dormant-compute win, provider independence, or physical-finality claim is made."
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
    ap.add_argument("--child-cut", nargs=4, metavar=("ANCHOR", "WITNESS", "TARGET", "MARKER"))
    ap.add_argument("--child-bootstrap", nargs=2, metavar=("ANCHOR", "WITNESS"))
    ap.add_argument("--child-rotate", nargs=3, metavar=("ANCHOR", "WITNESS", "RID"))
    ns = ap.parse_args()
    if ns.child_cut:
        a, wi, target, marker = ns.child_cut
        return child_cut(Path(a), Path(wi), target, Path(marker))
    if ns.child_bootstrap:
        a, wi = ns.child_bootstrap
        return child_bootstrap(Path(a), Path(wi))
    if ns.child_rotate:
        a, wi, rotation_id = ns.child_rotate
        return child_rotate(Path(a), Path(wi), rotation_id)
    if ns.worker_uid is None or ns.anchor_uid is None:
        ap.error("--worker-uid and --anchor-uid required")
    return run_suite(ns.worker_uid, ns.anchor_uid, Path(ns.report) if ns.report else None)


if __name__ == "__main__":
    raise SystemExit(main())
