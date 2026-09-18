#!/usr/bin/env python3
"""Wave 134 adversarial self-test: recoverable atomic bootstrap publication."""
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
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ATOMIC_RECOVERY as w134

SCRIPT = Path(__file__).resolve()
ENV_UID = t132.ENV_UID
STAGES = [
    "temp_created",
    "partial_write",
    "full_write_pre_fsync",
    "post_fsync_pre_close",
    "post_close_pre_replace",
    "post_replace_pre_dir_fsync",
]


def rid(name: str) -> str:
    return hashlib.sha256(("AXM-W134-" + name).encode()).hexdigest()


def parse(cp) -> dict:
    lines = cp.stdout.strip().splitlines()
    if not lines:
        return {"ok": False, "error": f"missing-json:{cp.returncode}:{cp.stderr[-1000:]}"}
    try:
        return json.loads(lines[-1])
    except Exception:
        return {"ok": False, "error": f"json-parse:{cp.stdout[-1000:]}"}


def child_rotate(anchor: Path, witness: Path, rotation_id: str,
                 target: str | None, fault_after: str | None, marker: Path | None) -> int:
    try:
        out = w134.rotate_response_key(
            anchor, witness, rotation_id,
            atomic_fault_target=target,
            atomic_fault_after=fault_after,
            atomic_fault_marker=marker,
        )
    except BaseException as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 3
    print(json.dumps({"ok": True, "result": out}, sort_keys=True))
    return 0


def child_bootstrap(anchor: Path, witness: Path) -> int:
    try:
        out = w134.ensure_rotation_bootstrap(anchor, witness)
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


def child_legacy_cut(anchor: Path, witness: Path, target_name: str, marker: Path) -> int:
    real_replace = os.replace

    def hooked_replace(src, dst, *args, **kwargs):
        srcp, dstp = Path(src), Path(dst)
        if dstp.name == target_name and srcp.name.startswith(target_name + ".tmp-"):
            fd = os.open(str(marker), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
            try:
                payload = json.dumps({
                    "pid": os.getpid(), "src": str(srcp), "dst": str(dstp),
                    "src_size": srcp.stat().st_size,
                }, sort_keys=True).encode() + b"\n"
                os.write(fd, payload); os.fsync(fd)
            finally:
                os.close(fd)
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


def child_seed(anchor: Path, witness: Path, kind: str) -> int:
    try:
        authority_uid, specs = w134._expected_bootstrap(anchor, witness)
        rd = anchor / w132.ROT_DIR
        if not rd.exists():
            rd.mkdir(mode=0o700)
            os.chown(rd, authority_uid, authority_uid)
            os.chmod(rd, 0o700)
            w._fsync_dir(anchor)
        target, data, mode = specs[w133.BOOTSTRAP_INTENT]
        made: list[str] = []
        if kind == "multi-legacy-exact":
            for suffix in ("seed-a", "seed-b"):
                p = target.with_name(target.name + ".tmp-" + suffix)
                p.write_bytes(data); os.chown(p, authority_uid, authority_uid); os.chmod(p, mode)
                made.append(str(p))
        elif kind == "legacy-wrong":
            p = target.with_name(target.name + ".tmp-seed-wrong")
            p.write_bytes(b"wrong-wave134-bytes\n")
            os.chown(p, authority_uid, authority_uid); os.chmod(p, mode); made.append(str(p))
        elif kind == "stage-wrong":
            p = w134._stage_path(target, data, mode)
            p.write_bytes(b"not-a-prefix-of-the-intended-bootstrap\n")
            os.chown(p, authority_uid, authority_uid); os.chmod(p, mode); made.append(str(p))
        elif kind == "foreign-exact":
            p = target.with_name(target.name + ".tmp-seed-foreign")
            p.write_bytes(data); os.chown(p, authority_uid, authority_uid); os.chmod(p, mode); made.append(str(p))
        else:
            raise ValueError("unknown-seed-kind")
        w._fsync_dir(target.parent)
        print(json.dumps({"ok": True, "paths": made, "target": str(target)}, sort_keys=True))
        return 0
    except BaseException as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 3


def setup(base: Path, name: str, anchor_uid: int, worker_uid: int):
    return t132.setup_case(base, name, anchor_uid, worker_uid)


def run_as(anchor_uid: int, worker_uid: int, args: list[str], check: bool = True):
    return t132.run_as(
        anchor_uid, t132.pycmd(str(SCRIPT), *args),
        extra_env={ENV_UID: str(worker_uid)}, check=check,
    )


def popen_as(anchor_uid: int, worker_uid: int, args: list[str]):
    return t132.popen_as(
        anchor_uid, t132.pycmd(str(SCRIPT), *args),
        extra_env={ENV_UID: str(worker_uid)},
    )


def wait_marker(marker: Path, proc, timeout: float = 15.0) -> dict:
    return t132.wait_json(marker, proc, timeout)


def kill_fault(anchor_uid: int, worker_uid: int, anchor: Path, witness: Path,
               rotation_id: str, target: str, stage: str, marker: Path) -> None:
    proc = popen_as(anchor_uid, worker_uid, [
        "--child-rotate", str(anchor), str(witness), rotation_id,
        "--atomic-target", target, "--atomic-fault-after", stage,
        "--fault-marker", str(marker),
    ])
    try:
        wait_marker(marker, proc)
        os.kill(proc.pid, signal.SIGKILL)
        proc.wait(timeout=5)
    finally:
        if proc.poll() is None:
            os.kill(proc.pid, signal.SIGKILL); proc.wait(timeout=5)


def kill_legacy(anchor_uid: int, worker_uid: int, anchor: Path, witness: Path,
                target: str, marker: Path) -> None:
    proc = popen_as(anchor_uid, worker_uid, [
        "--child-legacy-cut", str(anchor), str(witness), target, str(marker),
    ])
    try:
        wait_marker(marker, proc)
        os.kill(proc.pid, signal.SIGKILL)
        proc.wait(timeout=5)
    finally:
        if proc.poll() is None:
            os.kill(proc.pid, signal.SIGKILL); proc.wait(timeout=5)


def residue_for(anchor: Path, witness: Path) -> list[str]:
    residue: list[str] = []
    for parent in (anchor / w132.ROT_DIR, witness):
        if not parent.exists():
            continue
        for p in parent.iterdir():
            if ".tmp-" in p.name or ".axm-stage-" in p.name:
                residue.append(str(p))
    return sorted(residue)


def run_suite(worker_uid: int, anchor_uid: int, report_path: Path | None) -> int:
    if os.geteuid() != 0:
        raise PermissionError("wave134-selftest-requires-root-orchestrator")
    if worker_uid == anchor_uid:
        raise ValueError("worker-and-anchor-uid-must-differ")
    results: list[dict] = []
    base = Path(tempfile.mkdtemp(prefix="axm-w134-atomic-recovery-"))
    os.chmod(base, 0o777)

    witness, anchor, _, _ = setup(base, "legacy-pr58", anchor_uid, worker_uid)
    marker = base / "legacy-pr58.marker"
    kill_legacy(anchor_uid, worker_uid, anchor, witness, w133.BOOTSTRAP_INTENT, marker)
    rd = anchor / w132.ROT_DIR
    legacy_before = sorted(p.name for p in rd.glob(w133.BOOTSTRAP_INTENT + ".tmp-*"))
    recovered = parse(run_as(anchor_uid, worker_uid, [
        "--child-rotate", str(anchor), str(witness), rid("legacy-pr58")
    ]))
    results.append({
        "name": "wave133_exact_fsynced_legacy_temp_is_recovered_without_manual_delete",
        "ok": (
            len(legacy_before) == 1 and recovered.get("ok") is True and
            recovered.get("result", {}).get("seq") == 1 and not residue_for(anchor, witness)
        ),
        "detail": {"legacy_before": legacy_before, "seq": recovered.get("result", {}).get("seq"),
                   "residue_after": residue_for(anchor, witness)},
    })

    for stage in STAGES:
        witness, anchor, _, _ = setup(base, "cut-" + stage, anchor_uid, worker_uid)
        marker = base / ("cut-" + stage + ".marker")
        rotation_id = rid("cut-" + stage)
        kill_fault(anchor_uid, worker_uid, anchor, witness, rotation_id,
                   w133.BOOTSTRAP_INTENT, stage, marker)
        first = parse(run_as(anchor_uid, worker_uid, [
            "--child-rotate", str(anchor), str(witness), rotation_id
        ]))
        second = parse(run_as(anchor_uid, worker_uid, [
            "--child-rotate", str(anchor), str(witness), rotation_id
        ]))
        res = residue_for(anchor, witness)
        results.append({
            "name": f"sigkill_at_atomic_{stage}_resumes_exact_bootstrap_and_rotation",
            "ok": (
                first.get("ok") is True and second.get("ok") is True and
                first.get("result", {}).get("seq") == 1 and
                second.get("result", {}).get("seq") == 1 and
                second.get("result", {}).get("idempotent") is True and not res
            ),
            "detail": {"seq": first.get("result", {}).get("seq"),
                       "retry_idempotent": second.get("result", {}).get("idempotent"),
                       "residue_after": res},
        })

    witness, anchor, _, _ = setup(base, "witness-lineage-cut", anchor_uid, worker_uid)
    marker = base / "witness-lineage-cut.marker"
    rotation_id = rid("witness-lineage-cut")
    kill_fault(anchor_uid, worker_uid, anchor, witness, rotation_id,
               w132.WITNESS_LINEAGE, "post_close_pre_replace", marker)
    recovered = parse(run_as(anchor_uid, worker_uid, [
        "--child-rotate", str(anchor), str(witness), rotation_id
    ]))
    res = residue_for(anchor, witness)
    results.append({
        "name": "witness_lineage_atomic_temp_is_recovered_and_not_silently_retained",
        "ok": recovered.get("ok") is True and recovered.get("result", {}).get("seq") == 1 and not res,
        "detail": {"seq": recovered.get("result", {}).get("seq"), "residue_after": res},
    })

    witness, anchor, _, _ = setup(base, "multi-legacy", anchor_uid, worker_uid)
    seeded = parse(run_as(anchor_uid, worker_uid, [
        "--child-seed", str(anchor), str(witness), "multi-legacy-exact"
    ]))
    recovered = parse(run_as(anchor_uid, worker_uid, [
        "--child-rotate", str(anchor), str(witness), rid("multi-legacy")
    ]))
    results.append({
        "name": "multiple_identical_authority_owned_legacy_temps_deduplicate_safely",
        "ok": seeded.get("ok") is True and recovered.get("ok") is True and
              recovered.get("result", {}).get("seq") == 1 and not residue_for(anchor, witness),
        "detail": {"seeded": seeded.get("paths"), "residue_after": residue_for(anchor, witness)},
    })

    witness, anchor, _, _ = setup(base, "wrong-legacy", anchor_uid, worker_uid)
    seeded = parse(run_as(anchor_uid, worker_uid, [
        "--child-seed", str(anchor), str(witness), "legacy-wrong"
    ]))
    before = Path(seeded["paths"][0]).read_bytes() if seeded.get("ok") else b""
    cp = run_as(anchor_uid, worker_uid, ["--child-bootstrap", str(anchor), str(witness)], check=False)
    after = Path(seeded["paths"][0]).read_bytes() if seeded.get("ok") and Path(seeded["paths"][0]).exists() else b""
    results.append({
        "name": "wrong_byte_legacy_temp_fails_closed_and_is_retained",
        "ok": seeded.get("ok") is True and cp.returncode != 0 and before == after and bool(after),
        "detail": {"returncode": cp.returncode, "error": parse(cp).get("error")},
    })

    witness, anchor, _, _ = setup(base, "wrong-stage", anchor_uid, worker_uid)
    seeded = parse(run_as(anchor_uid, worker_uid, [
        "--child-seed", str(anchor), str(witness), "stage-wrong"
    ]))
    p = Path(seeded["paths"][0])
    before = p.read_bytes()
    cp = run_as(anchor_uid, worker_uid, ["--child-bootstrap", str(anchor), str(witness)], check=False)
    results.append({
        "name": "content_bound_stage_with_nonprefix_bytes_fails_closed_and_is_retained",
        "ok": cp.returncode != 0 and p.exists() and p.read_bytes() == before,
        "detail": {"returncode": cp.returncode, "error": parse(cp).get("error")},
    })

    witness, anchor, _, _ = setup(base, "foreign-exact", anchor_uid, worker_uid)
    seeded = parse(run_as(anchor_uid, worker_uid, [
        "--child-seed", str(anchor), str(witness), "foreign-exact"
    ]))
    foreign = Path(seeded["paths"][0])
    os.chown(foreign, worker_uid, worker_uid)
    before = foreign.read_bytes()
    cp = run_as(anchor_uid, worker_uid, ["--child-bootstrap", str(anchor), str(witness)], check=False)
    results.append({
        "name": "foreign_owner_exact_byte_lookalike_fails_closed_and_is_retained",
        "ok": cp.returncode != 0 and foreign.exists() and foreign.read_bytes() == before and foreign.stat().st_uid == worker_uid,
        "detail": {"returncode": cp.returncode, "error": parse(cp).get("error"), "owner": foreign.stat().st_uid},
    })

    passed = sum(bool(r["ok"]) for r in results)
    report = {
        "schema": "axm.flowing-compute.wave134-recoverable-atomic-bootstrap-selftest.v1",
        "mode": "optimized" if sys.flags.optimize else "normal",
        "worker_uid": worker_uid,
        "anchor_uid": anchor_uid,
        "passed": passed,
        "total": len(results),
        "results": results,
        "truth_boundary": (
            "same-host Linux/process/filesystem recovery for Wave-133 rotation-bootstrap publication only. "
            "Legacy random temps are recoverable only when authority owner/mode and complete intended bytes match; "
            "new deterministic stages resume only exact prefixes of content-bound intended bytes. Foreign owner, "
            "wrong bytes, and unrelated stages fail closed and remain visible. This does not prove rotation-transaction "
            "atomic helper recovery, validation-to-service inode stability, user-namespace identity, copied-key "
            "cross-host uniqueness, root/kernel or authority-UID compromise resistance, whole-domain rollback, "
            "hardware custody, performance/energy/retained/incremental/dormant-compute, throughput/scaling, provider "
            "independence, or physical finality."
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
    ap.add_argument("--child-bootstrap", nargs=2, metavar=("ANCHOR", "WITNESS"))
    ap.add_argument("--child-validate", nargs=2, metavar=("ANCHOR", "WITNESS"))
    ap.add_argument("--child-legacy-cut", nargs=4, metavar=("ANCHOR", "WITNESS", "TARGET", "MARKER"))
    ap.add_argument("--child-seed", nargs=3, metavar=("ANCHOR", "WITNESS", "KIND"))
    ap.add_argument("--atomic-target")
    ap.add_argument("--atomic-fault-after", choices=STAGES)
    ap.add_argument("--fault-marker")
    ns = ap.parse_args()
    if ns.child_rotate:
        a, wi, ri = ns.child_rotate
        return child_rotate(Path(a), Path(wi), ri, ns.atomic_target, ns.atomic_fault_after,
                            Path(ns.fault_marker) if ns.fault_marker else None)
    if ns.child_bootstrap:
        a, wi = ns.child_bootstrap
        return child_bootstrap(Path(a), Path(wi))
    if ns.child_validate:
        a, wi = ns.child_validate
        return child_validate(Path(a), Path(wi))
    if ns.child_legacy_cut:
        a, wi, target, marker = ns.child_legacy_cut
        return child_legacy_cut(Path(a), Path(wi), target, Path(marker))
    if ns.child_seed:
        a, wi, kind = ns.child_seed
        return child_seed(Path(a), Path(wi), kind)
    if ns.worker_uid is None or ns.anchor_uid is None:
        ap.error("--worker-uid and --anchor-uid required")
    return run_suite(ns.worker_uid, ns.anchor_uid, Path(ns.report) if ns.report else None)


if __name__ == "__main__":
    raise SystemExit(main())
