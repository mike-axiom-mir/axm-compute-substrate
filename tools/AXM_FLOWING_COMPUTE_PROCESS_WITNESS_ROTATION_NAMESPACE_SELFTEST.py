#!/usr/bin/env python3
"""Wave 137 adversarial self-test: strict response-rotation namespace provenance."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_AUTHENTICATED_ANCHOR as protocol
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_ROTATION as w132
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_ROTATION_SELFTEST as t132
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ROTATION_TRANSACTION_RECOVERY as w136
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ROTATION_TRANSACTION_RECOVERY_SELFTEST as t136
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ROTATION_NAMESPACE as w137

SCRIPT = Path(__file__).resolve()
ENV_UID = t132.ENV_UID


def rid(name: str) -> str:
    return hashlib.sha256(("AXM-W137-" + name).encode()).hexdigest()


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


def setup(base: Path, name: str, anchor_uid: int, worker_uid: int):
    return t132.setup_case(base, name, anchor_uid, worker_uid)


def child_rotate(anchor: Path, witness: Path, rotation_id: str, predecessor: bool) -> int:
    try:
        fn = w136.rotate_response_key if predecessor else w137.rotate_response_key
        out = fn(anchor, witness, rotation_id)
    except BaseException as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 3
    print(json.dumps({"ok": True, "result": out}, sort_keys=True))
    return 0


def child_validate(anchor: Path, witness: Path, predecessor: bool) -> int:
    try:
        fn = w136.validate_rotation_state if predecessor else w137.validate_rotation_state
        out = fn(anchor, witness)
    except BaseException as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 3
    print(json.dumps({"ok": True, "result": out}, sort_keys=True))
    return 0


def rotate(anchor_uid: int, worker_uid: int, anchor: Path, witness: Path,
           rotation_id: str, *, predecessor: bool = False, check: bool = True):
    args = ["--child-rotate", str(anchor), str(witness), rotation_id]
    if predecessor:
        args.append("--predecessor")
    return run_as(anchor_uid, worker_uid, args, check=check)


def validate(anchor_uid: int, worker_uid: int, anchor: Path, witness: Path,
             *, predecessor: bool = False, check: bool = True):
    args = ["--child-validate", str(anchor), str(witness)]
    if predecessor:
        args.append("--predecessor")
    return run_as(anchor_uid, worker_uid, args, check=check)


def authority_file(path: Path, data: bytes, uid: int, mode: int = 0o600) -> None:
    path.write_bytes(data)
    os.chown(path, uid, uid)
    os.chmod(path, mode)


def run_suite(worker_uid: int, anchor_uid: int, report_path: Path | None) -> int:
    if os.geteuid() != 0:
        raise PermissionError("wave137-selftest-requires-root-orchestrator")
    if worker_uid == anchor_uid:
        raise ValueError("worker-and-anchor-uid-must-differ")

    base = Path(tempfile.mkdtemp(prefix="axm-w137-namespace-"))
    os.chmod(base, 0o777)
    results: list[dict] = []

    witness, anchor, _, _ = setup(base, "clean-two", anchor_uid, worker_uid)
    one = parse(rotate(anchor_uid, worker_uid, anchor, witness, rid("clean-one")))
    two = parse(rotate(anchor_uid, worker_uid, anchor, witness, rid("clean-two")))
    check = parse(validate(anchor_uid, worker_uid, anchor, witness))
    results.append({
        "name": "clean_two_rotations_keep_exact_namespace",
        "ok": (
            one.get("ok") is True and one.get("result", {}).get("seq") == 1 and
            two.get("ok") is True and two.get("result", {}).get("seq") == 2 and
            check.get("ok") is True and check.get("result", {}).get("seq") == 2 and
            check.get("result", {}).get("strict_rotation_namespace") is True
        ),
        "detail": {
            "seq1": one.get("result", {}).get("seq"),
            "seq2": two.get("result", {}).get("seq"),
            "artifact_count": check.get("result", {}).get("artifact_count"),
        },
    })

    witness, anchor, _, _ = setup(base, "pred-stale-generation", anchor_uid, worker_uid)
    first = parse(rotate(
        anchor_uid, worker_uid, anchor, witness, rid("pred-stale-first"), predecessor=True
    ))
    rd = anchor / w132.ROT_DIR
    stale = rd / "public-999999.pem"
    authority_file(stale, (anchor / protocol.PUBLIC_KEY).read_bytes(), anchor_uid)
    pred = parse(validate(anchor_uid, worker_uid, anchor, witness, predecessor=True))
    strict = validate(anchor_uid, worker_uid, anchor, witness, check=False)
    results.append({
        "name": "wave136_accepts_stale_future_generation_wave137_rejects_and_retains",
        "ok": (
            first.get("ok") is True and pred.get("ok") is True and
            strict.returncode != 0 and stale.exists()
        ),
        "detail": {
            "predecessor_seq": pred.get("result", {}).get("seq"),
            "strict_error": parse(strict).get("error"),
            "retained": stale.exists(),
        },
    })

    witness, anchor, _, _ = setup(base, "pred-unrelated", anchor_uid, worker_uid)
    first = parse(rotate(
        anchor_uid, worker_uid, anchor, witness, rid("pred-unrelated-first"), predecessor=True
    ))
    rd = anchor / w132.ROT_DIR
    extra = rd / "orphan-authority-note.bin"
    authority_file(extra, b"unrelated-wave137-evidence\n", anchor_uid)
    pred = parse(validate(anchor_uid, worker_uid, anchor, witness, predecessor=True))
    strict = validate(anchor_uid, worker_uid, anchor, witness, check=False)
    results.append({
        "name": "wave136_accepts_unrelated_authority_file_wave137_rejects_and_retains",
        "ok": (
            first.get("ok") is True and pred.get("ok") is True and
            strict.returncode != 0 and extra.exists()
        ),
        "detail": {
            "strict_error": parse(strict).get("error"),
            "retained": extra.exists(),
        },
    })

    witness, anchor, _, _ = setup(base, "foreign-stage", anchor_uid, worker_uid)
    first = parse(rotate(
        anchor_uid, worker_uid, anchor, witness, rid("foreign-stage-bootstrap"),
        predecessor=True,
    ))
    rd = anchor / w132.ROT_DIR
    foreign = rd / (w132.PENDING + ".axm-stage-" + "f" * 32)
    authority_file(foreign, b"{}", worker_uid)
    before_seq = len(w132._read_jsonl(rd / w132.LINEAGE))
    attempted = rotate(
        anchor_uid, worker_uid, anchor, witness, rid("foreign-stage-next"),
        check=False,
    )
    after_seq = len(w132._read_jsonl(rd / w132.LINEAGE))
    results.append({
        "name": "foreign_owner_recovery_lookalike_fails_before_rotation_and_remains",
        "ok": (
            first.get("ok") is True and attempted.returncode != 0 and foreign.exists() and
            before_seq == after_seq == 1
        ),
        "detail": {
            "error": parse(attempted).get("error"),
            "seq_before": before_seq,
            "seq_after": after_seq,
        },
    })

    witness, anchor, _, _ = setup(base, "known-pending-recovery", anchor_uid, worker_uid)
    rotation = rid("known-pending-recovery")
    marker = base / "known-pending-recovery.json"
    t136.kill_at(
        anchor_uid, worker_uid, anchor, witness, rotation, marker,
        target=w132.PENDING_PRIVATE, stage="partial_write",
    )
    recovered = parse(rotate(anchor_uid, worker_uid, anchor, witness, rotation))
    check = parse(validate(anchor_uid, worker_uid, anchor, witness))
    results.append({
        "name": "known_pending_partial_stage_remains_recoverable",
        "ok": (
            recovered.get("ok") is True and recovered.get("result", {}).get("seq") == 1 and
            check.get("ok") is True and check.get("result", {}).get("seq") == 1
        ),
        "detail": {
            "seq": recovered.get("result", {}).get("seq"),
            "strict": check.get("result", {}).get("strict_rotation_namespace"),
        },
    })

    witness, anchor, _, _ = setup(base, "known-lineage-recovery", anchor_uid, worker_uid)
    rotation = rid("known-lineage-recovery")
    marker = base / "known-lineage-recovery.json"
    t136.kill_at(
        anchor_uid, worker_uid, anchor, witness, rotation, marker,
        target="authority_lineage", stage="partial_write",
    )
    recovered = parse(rotate(anchor_uid, worker_uid, anchor, witness, rotation))
    check = parse(validate(anchor_uid, worker_uid, anchor, witness))
    results.append({
        "name": "known_lineage_partial_stage_remains_recoverable",
        "ok": (
            recovered.get("ok") is True and recovered.get("result", {}).get("seq") == 1 and
            check.get("ok") is True and check.get("result", {}).get("seq") == 1
        ),
        "detail": {
            "seq": recovered.get("result", {}).get("seq"),
            "strict": check.get("result", {}).get("strict_rotation_namespace"),
        },
    })

    witness, anchor, _, _ = setup(base, "unrelated-stage", anchor_uid, worker_uid)
    first = parse(rotate(
        anchor_uid, worker_uid, anchor, witness, rid("unrelated-stage-first")
    ))
    rd = anchor / w132.ROT_DIR
    stage = rd / (w132.STATE + ".axm-stage-" + "a" * 32)
    authority_file(stage, b"partial-but-unrelated", anchor_uid)
    cp = validate(anchor_uid, worker_uid, anchor, witness, check=False)
    results.append({
        "name": "unrelated_authority_owned_recovery_stage_fails_closed_and_remains",
        "ok": (
            first.get("ok") is True and cp.returncode != 0 and stage.exists()
        ),
        "detail": {
            "error": parse(cp).get("error"),
            "retained": stage.exists(),
        },
    })

    passed = sum(bool(r["ok"]) for r in results)
    report = {
        "schema": "axm.flowing-compute.wave137-rotation-namespace-selftest.v1",
        "mode": "optimized" if sys.flags.optimize else "normal",
        "worker_uid": worker_uid,
        "anchor_uid": anchor_uid,
        "passed": passed,
        "total": len(results),
        "results": results,
        "truth_boundary": (
            "Same-host Linux/filesystem namespace-integrity evidence for the authority-owned "
            "response_rotation directory. Stable signed state is no longer considered valid in "
            "the presence of stale future generations, unrelated files, wrong-owner lookalike "
            "stages, or unrelated recovery stages; known Wave-136 in-flight recovery targets "
            "remain resumable. Files are rejected and retained, not silently rewritten or deleted. "
            "This does not prove authority-UID/root/kernel resistance, validation-to-service inode "
            "substitution after checking, user-namespace identity, copied-key uniqueness across "
            "hosts, whole-domain rollback resistance, hardware custody, performance/energy/"
            "retained/incremental/dormant-compute, throughput/scaling, provider independence, or "
            "physical finality."
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
    ap.add_argument("--predecessor", action="store_true")
    args = ap.parse_args()

    if args.child_rotate:
        anchor, witness, rotation = args.child_rotate
        return child_rotate(Path(anchor), Path(witness), rotation, args.predecessor)
    if args.child_validate:
        anchor, witness = args.child_validate
        return child_validate(Path(anchor), Path(witness), args.predecessor)
    if args.worker_uid is None or args.anchor_uid is None:
        ap.error("--worker-uid and --anchor-uid are required for suite mode")
    return run_suite(
        args.worker_uid,
        args.anchor_uid,
        Path(args.report) if args.report else None,
    )


if __name__ == "__main__":
    raise SystemExit(main())
