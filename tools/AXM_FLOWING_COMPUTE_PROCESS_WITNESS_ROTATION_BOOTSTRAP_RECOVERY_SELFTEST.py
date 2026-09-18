#!/usr/bin/env python3
"""Wave 133 adversarial self-test: exact rotation-bootstrap crash recovery."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import stat
import sys
import tempfile
from pathlib import Path

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_ROTATION as w132
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_ROTATION_SELFTEST as t132
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ROTATION_BOOTSTRAP_RECOVERY as w133

SCRIPT = Path(__file__).resolve()
ENV_UID = t132.ENV_UID
STAGES = [
    "directory",
    "intent",
    "genesis_public",
    "authority_lineage",
    "witness_lineage",
    "state",
    "ready",
]


def rid(name: str) -> str:
    return hashlib.sha256(("AXM-W133-" + name).encode()).hexdigest()


def parse(cp) -> dict:
    return t132.parse(cp)


def write_owned(path: Path, data: bytes, uid: int, mode: int = 0o600) -> None:
    path.write_bytes(data)
    os.chown(path, uid, uid)
    os.chmod(path, mode)


def child_rotate(anchor: Path, witness: Path, rotation_id: str,
                 bootstrap_fault_after: str | None, marker: Path | None) -> int:
    try:
        out = w133.rotate_response_key(
            anchor, witness, rotation_id,
            bootstrap_fault_after=bootstrap_fault_after,
            bootstrap_fault_marker=marker,
        )
    except BaseException as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 3
    print(json.dumps({"ok": True, "result": out}, sort_keys=True))
    return 0


def child_validate(anchor: Path, witness: Path) -> int:
    try:
        out = w133.validate_rotation_state(anchor, witness)
    except BaseException as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 3
    print(json.dumps({"ok": True, "result": out}, sort_keys=True))
    return 0


def start_fault(anchor_uid: int, worker_uid: int, anchor: Path, witness: Path,
                rotation_id: str, stage: str, marker: Path):
    return t132.popen_as(anchor_uid, t132.pycmd(
        str(SCRIPT), "--child-rotate", str(anchor), str(witness), rotation_id,
        "--bootstrap-fault-after", stage, "--fault-marker", str(marker),
    ), extra_env={ENV_UID: str(worker_uid)})


def kill_at(anchor_uid: int, worker_uid: int, anchor: Path, witness: Path,
            rotation_id: str, stage: str, marker: Path) -> None:
    proc = start_fault(anchor_uid, worker_uid, anchor, witness, rotation_id, stage, marker)
    try:
        t132.wait_json(marker, proc)
        os.kill(proc.pid, signal.SIGKILL)
        proc.wait(timeout=4)
    finally:
        if proc.poll() is None:
            os.kill(proc.pid, signal.SIGKILL)
            proc.wait(timeout=4)


def recover(anchor_uid: int, worker_uid: int, anchor: Path, witness: Path,
            rotation_id: str, check: bool = True):
    return t132.run_as(anchor_uid, t132.pycmd(
        str(SCRIPT), "--child-rotate", str(anchor), str(witness), rotation_id,
    ), extra_env={ENV_UID: str(worker_uid)}, check=check)


def validate(anchor_uid: int, worker_uid: int, anchor: Path, witness: Path,
             check: bool = True):
    return t132.run_as(anchor_uid, t132.pycmd(
        str(SCRIPT), "--child-validate", str(anchor), str(witness),
    ), extra_env={ENV_UID: str(worker_uid)}, check=check)


def setup(base: Path, name: str, anchor_uid: int, worker_uid: int):
    return t132.setup_case(base, name, anchor_uid, worker_uid)


def run_suite(worker_uid: int, anchor_uid: int, report_path: Path | None) -> int:
    if os.geteuid() != 0:
        raise PermissionError("wave133-selftest-requires-root-orchestrator")
    if worker_uid == anchor_uid:
        raise ValueError("worker-and-anchor-uid-must-differ")

    results: list[dict] = []
    base = Path(tempfile.mkdtemp(prefix="axm-w133-bootstrap-recovery-"))
    os.chmod(base, 0o777)

    # Predecessor counterexample: Wave 132 treats directory existence as bootstrap completion.
    witness, anchor, benv, _ = setup(base, "predecessor-dir-cut", anchor_uid, worker_uid)
    rd = anchor / w132.ROT_DIR
    rd.mkdir(mode=0o700)
    os.chown(rd, anchor_uid, anchor_uid)
    os.chmod(rd, 0o700)
    old = t132.recover(anchor_uid, worker_uid, anchor, witness, rid("predecessor-dir-cut"), check=False)
    repaired = parse(recover(anchor_uid, worker_uid, anchor, witness, rid("predecessor-dir-cut")))
    results.append({
        "name": "wave132_directory_only_bootstrap_sticks_but_wave133_exactly_recovers",
        "ok": old.returncode != 0 and repaired.get("ok") is True and repaired.get("result", {}).get("seq") == 1,
        "detail": {"wave132_returncode": old.returncode, "wave133_seq": repaired.get("result", {}).get("seq")},
    })

    for stage in STAGES:
        witness, anchor, benv, _ = setup(base, f"cut-{stage}", anchor_uid, worker_uid)
        rotation_id = rid(f"cut-{stage}")
        marker = base / f"cut-{stage}.marker"
        kill_at(anchor_uid, worker_uid, anchor, witness, rotation_id, stage, marker)
        first = parse(recover(anchor_uid, worker_uid, anchor, witness, rotation_id))
        rd = anchor / w132.ROT_DIR
        intent_before = (rd / w133.BOOTSTRAP_INTENT).read_bytes()
        ready_before = (rd / w133.BOOTSTRAP_READY).read_bytes()
        second = parse(recover(anchor_uid, worker_uid, anchor, witness, rotation_id))
        checked = parse(validate(anchor_uid, worker_uid, anchor, witness))
        no_pending = not any((rd / name).exists() for name in (
            w132.PENDING, w132.PENDING_CERT, w132.PENDING_PUBLIC, w132.PENDING_PRIVATE
        ))
        ok = (
            first.get("ok") is True and second.get("ok") is True and checked.get("ok") is True and
            first.get("result", {}).get("seq") == 1 and
            second.get("result", {}).get("seq") == 1 and
            second.get("result", {}).get("idempotent") is True and
            (rd / w133.BOOTSTRAP_INTENT).read_bytes() == intent_before and
            (rd / w133.BOOTSTRAP_READY).read_bytes() == ready_before and
            no_pending
        )
        results.append({
            "name": f"sigkill_after_bootstrap_{stage}_resumes_exact_genesis_then_rotation",
            "ok": ok,
            "detail": {
                "seq": first.get("result", {}).get("seq"),
                "retry_idempotent": second.get("result", {}).get("idempotent"),
                "bootstrap_intent_sha256": hashlib.sha256(intent_before).hexdigest(),
                "bootstrap_ready_sha256": hashlib.sha256(ready_before).hexdigest(),
            },
        })

    # Mismatched exact-looking intent must be retained and rejected, never rewritten.
    witness, anchor, benv, _ = setup(base, "tampered-intent", anchor_uid, worker_uid)
    marker = base / "tampered-intent.marker"
    rotation_id = rid("tampered-intent")
    kill_at(anchor_uid, worker_uid, anchor, witness, rotation_id, "intent", marker)
    intent_path = anchor / w132.ROT_DIR / w133.BOOTSTRAP_INTENT
    tampered = json.loads(intent_path.read_text())
    tampered["witness_root_sha"] = "f" * 64
    bad_bytes = w133._canon_file(tampered)
    write_owned(intent_path, bad_bytes, anchor_uid)
    cp = recover(anchor_uid, worker_uid, anchor, witness, rotation_id, check=False)
    results.append({
        "name": "mismatched_bootstrap_intent_fails_closed_without_rewrite",
        "ok": cp.returncode != 0 and intent_path.read_bytes() == bad_bytes,
        "detail": {"returncode": cp.returncode},
    })

    # Unexpected rotation transaction bytes before bootstrap-ready are ambiguous.
    witness, anchor, benv, _ = setup(base, "unexpected-pending", anchor_uid, worker_uid)
    rd = anchor / w132.ROT_DIR
    rd.mkdir(mode=0o700)
    os.chown(rd, anchor_uid, anchor_uid)
    os.chmod(rd, 0o700)
    pending = rd / w132.PENDING
    write_owned(pending, b"{}\n", anchor_uid)
    cp = recover(anchor_uid, worker_uid, anchor, witness, rid("unexpected-pending"), check=False)
    results.append({
        "name": "unexpected_pre_ready_rotation_transaction_fails_closed",
        "ok": cp.returncode != 0 and pending.read_bytes() == b"{}\n",
        "detail": {"returncode": cp.returncode},
    })

    # Once evolution exists, deleting the bootstrap receipt cannot silently re-bootstrap history.
    witness, anchor, benv, _ = setup(base, "ready-rollback", anchor_uid, worker_uid)
    first = parse(recover(anchor_uid, worker_uid, anchor, witness, rid("ready-rollback-one")))
    ready_path = anchor / w132.ROT_DIR / w133.BOOTSTRAP_READY
    ready_path.unlink()
    w133.w._fsync_dir(anchor / w132.ROT_DIR)
    cp = recover(anchor_uid, worker_uid, anchor, witness, rid("ready-rollback-two"), check=False)
    results.append({
        "name": "bootstrap_receipt_loss_after_rotation_evolution_fails_closed",
        "ok": first.get("result", {}).get("seq") == 1 and cp.returncode != 0 and not ready_path.exists(),
        "detail": {"returncode": cp.returncode},
    })

    # Rolling mutable state back to genesis while signed lineage stays newer must fail closed.
    witness, anchor, benv, _ = setup(base, "state-rollback", anchor_uid, worker_uid)
    first = parse(recover(anchor_uid, worker_uid, anchor, witness, rid("state-rollback")))
    rd = anchor / w132.ROT_DIR
    genesis = (rd / w132.GENESIS_PUBLIC).read_bytes()
    state0 = w133._canon_file(w132._state_for(
        0, w132.ZERO, w132._public_fp(genesis), None
    ))
    state_path = rd / w132.STATE
    write_owned(state_path, state0, anchor_uid)
    cp = validate(anchor_uid, worker_uid, anchor, witness, check=False)
    results.append({
        "name": "rotation_state_rollback_against_newer_signed_lineage_fails_closed",
        "ok": first.get("result", {}).get("seq") == 1 and cp.returncode != 0 and state_path.read_bytes() == state0,
        "detail": {"returncode": cp.returncode},
    })

    passed = sum(bool(r["ok"]) for r in results)
    report = {
        "schema": "axm.flowing-compute.wave133-rotation-bootstrap-recovery-selftest.v1",
        "mode": "optimized" if sys.flags.optimize else "normal",
        "worker_uid": worker_uid,
        "anchor_uid": anchor_uid,
        "passed": passed,
        "total": len(results),
        "results": results,
        "truth_boundary": (
            "same-host deterministic Wave-132 rotation-bootstrap SIGKILL recovery only; exact missing "
            "genesis artifacts may be resumed before rotation evolution, mismatches and receipt loss after "
            "evolution fail closed. Cross-host genuine-key clones, root/kernel or authority-UID compromise, "
            "whole-domain rollback, hardware custody, performance/energy/retained/incremental/dormant-compute, "
            "throughput/scaling, provider independence and physical finality remain unproved"
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
    ap.add_argument("--child-rotate", nargs=3, metavar=("ANCHOR", "WITNESS", "RID"))
    ap.add_argument("--child-validate", nargs=2, metavar=("ANCHOR", "WITNESS"))
    ap.add_argument("--bootstrap-fault-after", choices=STAGES)
    ap.add_argument("--fault-marker")
    ns = ap.parse_args()
    if ns.child_rotate:
        a, wi, ri = ns.child_rotate
        return child_rotate(
            Path(a), Path(wi), ri, ns.bootstrap_fault_after,
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
