#!/usr/bin/env python3
"""Wave 136 adversarial self-test: pending transaction, lineage, and cleanup recovery."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import sys
import tempfile
from pathlib import Path

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS as w
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_AUTHENTICATED_ANCHOR as protocol
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_ROTATION as w132
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_ROTATION_SELFTEST as t132
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ATOMIC_RECOVERY as w134
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ROTATION_PUBLICATION_RECOVERY as w135
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ROTATION_TRANSACTION_RECOVERY as w136

SCRIPT = Path(__file__).resolve()
ENV_UID = t132.ENV_UID


def rid(name: str) -> str:
    return hashlib.sha256(("AXM-W136-" + name).encode()).hexdigest()


def parse(cp) -> dict:
    lines = cp.stdout.strip().splitlines()
    if not lines:
        return {"ok": False, "error": f"missing-json:{cp.returncode}:{cp.stderr[-1200:]}"}
    try:
        return json.loads(lines[-1])
    except Exception:
        return {"ok": False, "error": f"json-parse:{cp.stdout[-1200:]}:{cp.stderr[-1200:]}"}


def run_as(anchor_uid: int, worker_uid: int, args: list[str], check: bool = True):
    return t132.run_as(
        anchor_uid,
        t132.pycmd(str(SCRIPT), *args),
        extra_env={ENV_UID: str(worker_uid)},
        check=check,
        timeout=90.0,
    )


def popen_as(anchor_uid: int, worker_uid: int, args: list[str]):
    return t132.popen_as(
        anchor_uid,
        t132.pycmd(str(SCRIPT), *args),
        extra_env={ENV_UID: str(worker_uid)},
    )


def wait_json(path: Path, proc, timeout: float = 30.0) -> dict:
    return t132.wait_json(path, proc, timeout)


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


def child_rotate(anchor: Path, witness: Path, rotation_id: str,
                 target: str | None, stage: str | None, marker: Path | None) -> int:
    try:
        out = w136.rotate_response_key(
            anchor, witness, rotation_id,
            fault_target=target,
            fault_after=stage,
            fault_marker=marker,
        )
    except BaseException as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 3
    print(json.dumps({"ok": True, "result": out}, sort_keys=True))
    return 0


def child_validate(anchor: Path, witness: Path) -> int:
    try:
        out = w136.validate_rotation_state(anchor, witness)
    except BaseException as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 3
    print(json.dumps({"ok": True, "result": out}, sort_keys=True))
    return 0


def kill_at(anchor_uid: int, worker_uid: int, anchor: Path, witness: Path,
            rotation_id: str, marker: Path, *,
            target: str | None, stage: str) -> dict:
    args = [
        "--child-rotate", str(anchor), str(witness), rotation_id,
        "--fault-after", stage,
        "--fault-marker", str(marker),
    ]
    if target is not None:
        args += ["--fault-target", target]
    proc = popen_as(anchor_uid, worker_uid, args)
    return kill_child(proc, marker)


def recover(anchor_uid: int, worker_uid: int, anchor: Path, witness: Path,
            rotation_id: str, check: bool = True):
    return run_as(anchor_uid, worker_uid, [
        "--child-rotate", str(anchor), str(witness), rotation_id,
    ], check=check)


def validate(anchor_uid: int, worker_uid: int, anchor: Path, witness: Path,
             check: bool = True):
    return run_as(anchor_uid, worker_uid, [
        "--child-validate", str(anchor), str(witness),
    ], check=check)


def setup(base: Path, name: str, anchor_uid: int, worker_uid: int):
    return t132.setup_case(base, name, anchor_uid, worker_uid)


def pending_private_residue(anchor: Path) -> list[Path]:
    p = anchor / w132.ROT_DIR / w132.PENDING_PRIVATE
    return sorted([
        *w134._legacy_candidates(p),
        *w134._stage_candidates(p),
        *w135._legacy_candidates(p),
        *w135._stage_candidates(p),
    ])


def lineage_stage_residue(path: Path) -> list[Path]:
    return sorted([
        *w135._legacy_candidates(path),
        *w135._stage_candidates(path),
    ])


def run_suite(worker_uid: int, anchor_uid: int, report_path: Path | None) -> int:
    if os.geteuid() != 0:
        raise PermissionError("wave136-selftest-requires-root-orchestrator")
    if worker_uid == anchor_uid:
        raise ValueError("worker-and-anchor-uid-must-differ")

    base = Path(tempfile.mkdtemp(prefix="axm-w136-transaction-"))
    os.chmod(base, 0o777)
    results: list[dict] = []

    for count in (1, 10, 100):
        witness, anchor, _, _ = setup(base, f"pending-private-{count}", anchor_uid, worker_uid)
        rotation = rid(f"pending-private-{count}")
        residue_counts = []
        residue_owners = []
        for i in range(count):
            marker = base / f"pending-private-{count}-{i}.json"
            kill_at(
                anchor_uid, worker_uid, anchor, witness, rotation, marker,
                target=w132.PENDING_PRIVATE, stage="partial_write",
            )
            residue = pending_private_residue(anchor)
            residue_counts.append(len(residue))
            residue_owners.append(residue[0].stat().st_uid if len(residue) == 1 else None)
        final = parse(recover(anchor_uid, worker_uid, anchor, witness, rotation))
        check = parse(validate(anchor_uid, worker_uid, anchor, witness))
        results.append({
            "name": f"pending_private_partial_sigkill_x{count}_is_bounded_then_recovers",
            "ok": (
                residue_counts == [1] * count and
                residue_owners == [anchor_uid] * count and
                final.get("ok") is True and final.get("result", {}).get("seq") == 1 and
                check.get("ok") is True and check.get("result", {}).get("seq") == 1 and
                not pending_private_residue(anchor)
            ),
            "detail": {
                "cuts": count,
                "residue_counts_unique": sorted(set(residue_counts)),
                "owners_unique": sorted(set(x for x in residue_owners if x is not None)),
                "seq": final.get("result", {}).get("seq"),
            },
        })

    witness, anchor, _, _ = setup(base, "complete-private", anchor_uid, worker_uid)
    rotation = rid("complete-private")
    marker = base / "complete-private.json"
    kill_at(
        anchor_uid, worker_uid, anchor, witness, rotation, marker,
        target=w132.PENDING_PRIVATE, stage="post_close_pre_replace",
    )
    residue = pending_private_residue(anchor)
    before = residue[0].read_bytes() if len(residue) == 1 else b""
    before_public = None
    if before:
        try:
            import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_INIT_RECOVERY as w131
            before_public = w131._response_public_from_private(before)
        except Exception:
            pass
    final = parse(recover(anchor_uid, worker_uid, anchor, witness, rotation))
    current_public = (anchor / protocol.PUBLIC_KEY).read_bytes()
    results.append({
        "name": "complete_pending_private_stage_preserves_exact_candidate",
        "ok": (
            len(residue) == 1 and before_public is not None and
            final.get("ok") is True and final.get("result", {}).get("seq") == 1 and
            current_public == before_public and not pending_private_residue(anchor)
        ),
        "detail": {
            "stage_size": len(before),
            "candidate_preserved": current_public == before_public if before_public else False,
        },
    })

    witness, anchor, _, _ = setup(base, "pending-metadata", anchor_uid, worker_uid)
    rotation = rid("pending-metadata")
    marker = base / "pending-metadata.json"
    kill_at(
        anchor_uid, worker_uid, anchor, witness, rotation, marker,
        target=w132.PENDING, stage="partial_write",
    )
    pending_path = anchor / w132.ROT_DIR / w132.PENDING
    stages = w134._stage_candidates(pending_path)
    stage_prefix = stages[0].read_bytes() if len(stages) == 1 else b""
    final = parse(recover(anchor_uid, worker_uid, anchor, witness, rotation))
    results.append({
        "name": "partial_pending_commit_recovers_same_transaction",
        "ok": (
            len(stages) == 1 and len(stage_prefix) > 0 and
            final.get("ok") is True and final.get("result", {}).get("seq") == 1 and
            not w134._stage_candidates(pending_path) and not pending_path.exists()
        ),
        "detail": {
            "partial_bytes": len(stage_prefix),
            "seq": final.get("result", {}).get("seq"),
        },
    })

    witness, anchor, _, _ = setup(base, "authority-lineage", anchor_uid, worker_uid)
    rotation = rid("authority-lineage")
    marker = base / "authority-lineage.json"
    kill_at(
        anchor_uid, worker_uid, anchor, witness, rotation, marker,
        target="authority_lineage", stage="partial_write",
    )
    auth_line = anchor / w132.ROT_DIR / w132.LINEAGE
    auth_stage = lineage_stage_residue(auth_line)
    final = parse(recover(anchor_uid, worker_uid, anchor, witness, rotation))
    results.append({
        "name": "authority_lineage_partial_replace_recovers_exact_append",
        "ok": (
            len(auth_stage) == 1 and final.get("ok") is True and
            final.get("result", {}).get("seq") == 1 and
            len(w132._read_jsonl(auth_line)) == 1 and not lineage_stage_residue(auth_line)
        ),
        "detail": {"stage_count": len(auth_stage), "seq": final.get("result", {}).get("seq")},
    })

    witness, anchor, _, _ = setup(base, "witness-lineage", anchor_uid, worker_uid)
    rotation = rid("witness-lineage")
    marker = base / "witness-lineage.json"
    kill_at(
        anchor_uid, worker_uid, anchor, witness, rotation, marker,
        target="witness_lineage", stage="partial_write",
    )
    wit_line = witness / w132.WITNESS_LINEAGE
    wit_stage = lineage_stage_residue(wit_line)
    final = parse(recover(anchor_uid, worker_uid, anchor, witness, rotation))
    results.append({
        "name": "witness_lineage_partial_replace_recovers_exact_append",
        "ok": (
            len(wit_stage) == 1 and final.get("ok") is True and
            final.get("result", {}).get("seq") == 1 and
            len(w132._read_jsonl(wit_line)) == 1 and not lineage_stage_residue(wit_line)
        ),
        "detail": {"stage_count": len(wit_stage), "seq": final.get("result", {}).get("seq")},
    })

    witness, anchor, _, _ = setup(base, "wrong-lineage", anchor_uid, worker_uid)
    rotation = rid("wrong-lineage")
    marker = base / "wrong-lineage.json"
    kill_at(
        anchor_uid, worker_uid, anchor, witness, rotation, marker,
        target="authority_lineage", stage="partial_write",
    )
    auth_line = anchor / w132.ROT_DIR / w132.LINEAGE
    residue = lineage_stage_residue(auth_line)
    stage = residue[0] if len(residue) == 1 else None
    if stage is not None:
        stage.write_bytes(b"wrong-wave136-lineage-stage\n")
        os.chown(stage, anchor_uid, anchor_uid)
        os.chmod(stage, 0o600)
    cp = recover(anchor_uid, worker_uid, anchor, witness, rotation, check=False)
    results.append({
        "name": "wrong_byte_lineage_stage_fails_closed_and_is_retained",
        "ok": (
            stage is not None and cp.returncode != 0 and stage.exists() and
            stage.read_bytes() == b"wrong-wave136-lineage-stage\n"
        ),
        "detail": {"returncode": cp.returncode, "error": parse(cp).get("error")},
    })

    cleanup_details = []
    cleanup_ok = True
    for cleanup_stage in sorted(w136.CLEANUP_STAGES):
        witness, anchor, _, _ = setup(base, cleanup_stage, anchor_uid, worker_uid)
        rotation = rid(cleanup_stage)
        marker = base / f"{cleanup_stage}.json"
        kill_at(
            anchor_uid, worker_uid, anchor, witness, rotation, marker,
            target=None, stage=cleanup_stage,
        )
        rd = anchor / w132.ROT_DIR
        before = [p.name for p in w136._all_pending_residue(rd)]
        final = parse(recover(anchor_uid, worker_uid, anchor, witness, rotation))
        after = [p.name for p in w136._all_pending_residue(rd)]
        ok = (
            final.get("ok") is True and final.get("result", {}).get("seq") == 1 and
            final.get("result", {}).get("idempotent") is True and not after
        )
        cleanup_ok = cleanup_ok and ok
        cleanup_details.append({
            "stage": cleanup_stage,
            "before": before,
            "after": after,
            "idempotent": final.get("result", {}).get("idempotent"),
        })
    results.append({
        "name": "all_postcommit_cleanup_sigkills_resume_idempotently",
        "ok": cleanup_ok,
        "detail": cleanup_details,
    })

    witness, anchor, _, _ = setup(base, "cleanup-corrupt", anchor_uid, worker_uid)
    rotation = rid("cleanup-corrupt")
    marker = base / "cleanup-corrupt.json"
    kill_at(
        anchor_uid, worker_uid, anchor, witness, rotation, marker,
        target=None, stage="cleanup_after_pending",
    )
    pp = anchor / w132.ROT_DIR / w132.PENDING_PRIVATE
    if pp.exists():
        pp.write_bytes(b"wrong-completed-pending-private\n")
        os.chown(pp, anchor_uid, anchor_uid)
        os.chmod(pp, 0o600)
    cp = recover(anchor_uid, worker_uid, anchor, witness, rotation, check=False)
    results.append({
        "name": "corrupt_postcommit_pending_residue_fails_closed_and_remains",
        "ok": (
            cp.returncode != 0 and pp.exists() and
            pp.read_bytes() == b"wrong-completed-pending-private\n"
        ),
        "detail": {"returncode": cp.returncode, "error": parse(cp).get("error")},
    })

    witness, anchor, _, _ = setup(base, "clean-two", anchor_uid, worker_uid)
    one = parse(recover(anchor_uid, worker_uid, anchor, witness, rid("clean-one")))
    two = parse(recover(anchor_uid, worker_uid, anchor, witness, rid("clean-two")))
    check = parse(validate(anchor_uid, worker_uid, anchor, witness))
    results.append({
        "name": "clean_two_rotation_lineage_remains_valid",
        "ok": (
            one.get("ok") is True and one.get("result", {}).get("seq") == 1 and
            two.get("ok") is True and two.get("result", {}).get("seq") == 2 and
            check.get("ok") is True and check.get("result", {}).get("seq") == 2 and
            not w136._all_pending_residue(anchor / w132.ROT_DIR)
        ),
        "detail": {
            "seq1": one.get("result", {}).get("seq"),
            "seq2": two.get("result", {}).get("seq"),
        },
    })

    passed = sum(bool(r["ok"]) for r in results)
    report = {
        "schema": "axm.flowing-compute.wave136-rotation-transaction-recovery-selftest.v1",
        "mode": "optimized" if sys.flags.optimize else "normal",
        "worker_uid": worker_uid,
        "anchor_uid": anchor_uid,
        "passed": passed,
        "total": len(results),
        "results": results,
        "truth_boundary": (
            "Same-host Linux/process/filesystem recovery for Wave-132 pending-transaction creation, "
            "authority/witness lineage append, and post-commit cleanup. Complete candidate bytes are "
            "preserved exactly. An incomplete private-key or certificate stage may be abandoned only "
            "before pending.json exists and while signed lineage/current trust state is still the predecessor; "
            "that is explicitly not same-candidate recovery. Wrong-byte recovery state fails closed and remains "
            "visible. Cross-host copied-key uniqueness, root/kernel or authority-UID compromise, user namespaces, "
            "whole-domain rollback, validation-to-service inode substitution, hardware custody, performance/energy/"
            "retained/incremental/dormant-compute, throughput/scaling, provider independence and physical finality "
            "remain unproved."
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
    ap.add_argument("--fault-target")
    ap.add_argument("--fault-after", choices=sorted(w136.FAULT_STAGES))
    ap.add_argument("--fault-marker")
    args = ap.parse_args()

    if args.child_rotate:
        anchor, witness, rotation = args.child_rotate
        return child_rotate(
            Path(anchor), Path(witness), rotation,
            args.fault_target,
            args.fault_after,
            Path(args.fault_marker) if args.fault_marker else None,
        )
    if args.child_validate:
        anchor, witness = args.child_validate
        return child_validate(Path(anchor), Path(witness))
    if args.worker_uid is None or args.anchor_uid is None:
        ap.error("--worker-uid and --anchor-uid are required for suite mode")
    return run_suite(
        args.worker_uid,
        args.anchor_uid,
        Path(args.report) if args.report else None,
    )


if __name__ == "__main__":
    raise SystemExit(main())
