#!/usr/bin/env python3
"""Independent Wave 137 verifier: validation->rotation->validation pathname swap.

DRAFT / NON-CANON. This does not modify builder implementation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_ROTATION_SELFTEST as t132
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ROTATION_NAMESPACE as w137

SCRIPT = Path(__file__).resolve()
ENV_UID = t132.ENV_UID


def rid(name: str) -> str:
    return hashlib.sha256(("AXM-VERIFIER-W137-TOCTOU-" + name).encode()).hexdigest()


def parse(cp) -> dict:
    lines = cp.stdout.strip().splitlines()
    if not lines:
        return {"ok": False, "error": f"missing-json:{cp.returncode}:{cp.stderr[-1200:]}"}
    try:
        return json.loads(lines[-1])
    except Exception:
        return {"ok": False, "error": f"json-parse:{cp.stdout[-1200:]}:{cp.stderr[-1200:]}"}


def wait_file(path: Path, timeout: float = 30.0) -> None:
    end = time.time() + timeout
    while time.time() < end:
        if path.exists():
            return
        time.sleep(0.02)
    raise TimeoutError(f"timeout-waiting:{path}")


def touch(path: Path) -> None:
    path.write_text("go\n")


def capeff() -> str:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("CapEff:"):
            return line.split(":", 1)[1].strip()
    return "unknown"


def child_swap(a_anchor: Path, a_witness: Path, b_anchor: Path, b_witness: Path,
               phase: str) -> int:
    a_anchor_saved = a_anchor.with_name(a_anchor.name + ".validated-original")
    a_witness_saved = a_witness.with_name(a_witness.name + ".validated-original")
    if phase == "enter":
        a_anchor.rename(a_anchor_saved)
        a_witness.rename(a_witness_saved)
        b_anchor.rename(a_anchor)
        b_witness.rename(a_witness)
    elif phase == "restore":
        a_anchor.rename(b_anchor)
        a_witness.rename(b_witness)
        a_anchor_saved.rename(a_anchor)
        a_witness_saved.rename(a_witness)
    else:
        raise ValueError("unknown-swap-phase")
    print(json.dumps({
        "ok": True,
        "phase": phase,
        "uid": os.getuid(),
        "euid": os.geteuid(),
        "capeff": capeff(),
    }, sort_keys=True))
    return 0


def child_raced_rotate(anchor: Path, witness: Path, rotation_id: str,
                       before_marker: Path, before_continue: Path,
                       after_marker: Path, after_continue: Path) -> int:
    original = w137.w136.rotate_response_key

    def wrapped(ad, wd, rid_value, **kwargs):
        before_marker.write_text(json.dumps({"stage": "after-wave137-preflight"}) + "\n")
        wait_file(before_continue)
        out = original(ad, wd, rid_value, **kwargs)
        after_marker.write_text(json.dumps({"stage": "after-wave136-rotation"}) + "\n")
        wait_file(after_continue)
        return out

    w137.w136.rotate_response_key = wrapped
    try:
        out = w137.rotate_response_key(anchor, witness, rotation_id)
    except BaseException as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 3
    print(json.dumps({"ok": True, "result": out}, sort_keys=True))
    return 0


def child_validate(anchor: Path, witness: Path) -> int:
    try:
        out = w137.validate_rotation_state(anchor, witness)
    except BaseException as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 3
    print(json.dumps({"ok": True, "result": out}, sort_keys=True))
    return 0


def run_suite(worker_uid: int, anchor_uid: int, report_path: Path | None) -> int:
    if os.geteuid() != 0:
        raise PermissionError("verifier-requires-root-orchestrator")
    if worker_uid == anchor_uid:
        raise ValueError("worker-and-anchor-uid-must-differ")

    base = Path(tempfile.mkdtemp(prefix="axm-w137-toctou-verifier-"))
    os.chmod(base, 0o777)
    witness_a, anchor_a, _, init_a = t132.setup_case(base, "domain-a", anchor_uid, worker_uid)
    witness_b, anchor_b, _, init_b = t132.setup_case(base, "domain-b", anchor_uid, worker_uid)

    before_marker = base / "after-preflight.json"
    before_continue = base / "continue-into-lower"
    after_marker = base / "after-lower.json"
    after_continue = base / "continue-to-final-validate"
    rotation_id = rid("swap")

    proc = t132.popen_as(
        anchor_uid,
        t132.pycmd(
            str(SCRIPT), "--child-raced-rotate", str(anchor_a), str(witness_a), rotation_id,
            str(before_marker), str(before_continue), str(after_marker), str(after_continue),
        ),
        extra_env={ENV_UID: str(worker_uid)},
    )

    try:
        wait_file(before_marker)
        enter = t132.run_as(
            worker_uid,
            t132.pycmd(
                str(SCRIPT), "--child-swap", str(anchor_a), str(witness_a),
                str(anchor_b), str(witness_b), "enter",
            ),
            check=True,
        )
        touch(before_continue)

        wait_file(after_marker)
        restore = t132.run_as(
            worker_uid,
            t132.pycmd(
                str(SCRIPT), "--child-swap", str(anchor_a), str(witness_a),
                str(anchor_b), str(witness_b), "restore",
            ),
            check=True,
        )
        touch(after_continue)

        stdout, stderr = proc.communicate(timeout=45)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)

    raced = parse(type("CP", (), {"stdout": stdout, "stderr": stderr, "returncode": proc.returncode})())
    va = parse(t132.run_as(
        anchor_uid,
        t132.pycmd(str(SCRIPT), "--child-validate", str(anchor_a), str(witness_a)),
        extra_env={ENV_UID: str(worker_uid)},
        check=True,
    ))
    vb = parse(t132.run_as(
        anchor_uid,
        t132.pycmd(str(SCRIPT), "--child-validate", str(anchor_b), str(witness_b)),
        extra_env={ENV_UID: str(worker_uid)},
        check=True,
    ))
    enter_j = parse(enter)
    restore_j = parse(restore)

    rr = raced.get("result", {})
    ar = va.get("result", {})
    br = vb.get("result", {})

    reproduced = (
        raced.get("ok") is True and proc.returncode == 0 and
        rr.get("seq") == 1 and rr.get("rotation_id") == rotation_id and
        rr.get("wave137_strict_rotation_namespace") is True and
        va.get("ok") is True and ar.get("seq") == 0 and ar.get("last_rotation_id") is None and
        vb.get("ok") is True and br.get("seq") == 1 and br.get("last_rotation_id") == rotation_id and
        enter_j.get("uid") == worker_uid and enter_j.get("euid") == worker_uid and
        restore_j.get("uid") == worker_uid and restore_j.get("euid") == worker_uid
    )

    report = {
        "schema": "axm.flowing-compute.verifier.wave137-path-toctou.v1",
        "mode": "optimized" if sys.flags.optimize else "normal",
        "verdict": (
            "FAIL_WAVE137_ROTATE_REPORTS_SUCCESS_FOR_VALIDATED_A_WHILE_ROTATING_SWAPPED_B"
            if reproduced else "NOT_REPRODUCED"
        ),
        "reproduced": reproduced,
        "worker_uid": worker_uid,
        "anchor_uid": anchor_uid,
        "worker_enter": enter_j,
        "worker_restore": restore_j,
        "domain_a_initial_response_fp": init_a.get("response_public_fingerprint"),
        "domain_b_initial_response_fp": init_b.get("response_public_fingerprint"),
        "returned_rotation": rr,
        "post_return_domain_a": ar,
        "post_return_domain_b": br,
        "truth_boundary": (
            "Same-host pathname TOCTOU counterexample in a deployment where the ordinary worker can "
            "rename the parent directory entries for anchor+witness domains. The worker subprocess "
            "only renames directory entries and does not read authority-owned stores or private keys. "
            "Wave 137 preflight validates domain A, lower Wave 136 mutates substituted genuine domain B, "
            "then domain A is restored before Wave 137 final validation. This is not a cryptographic "
            "forgery, authority-UID/root/kernel compromise, performance/energy result, cross-host "
            "uniqueness result, or physical-finality claim."
        ),
    }
    if report_path:
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if reproduced else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker-uid", type=int)
    ap.add_argument("--anchor-uid", type=int)
    ap.add_argument("--report")
    ap.add_argument("--child-swap", nargs=5, metavar=("A_ANCHOR", "A_WITNESS", "B_ANCHOR", "B_WITNESS", "PHASE"))
    ap.add_argument("--child-raced-rotate", nargs=7, metavar=("ANCHOR", "WITNESS", "RID", "BEFORE_MARKER", "BEFORE_CONTINUE", "AFTER_MARKER", "AFTER_CONTINUE"))
    ap.add_argument("--child-validate", nargs=2, metavar=("ANCHOR", "WITNESS"))
    args = ap.parse_args()

    if args.child_swap:
        aa, aw, ba, bw, phase = args.child_swap
        return child_swap(Path(aa), Path(aw), Path(ba), Path(bw), phase)
    if args.child_raced_rotate:
        a, w, r, bm, bc, am, ac = args.child_raced_rotate
        return child_raced_rotate(Path(a), Path(w), r, Path(bm), Path(bc), Path(am), Path(ac))
    if args.child_validate:
        a, w = args.child_validate
        return child_validate(Path(a), Path(w))
    if args.worker_uid is None or args.anchor_uid is None:
        ap.error("--worker-uid and --anchor-uid required")
    return run_suite(args.worker_uid, args.anchor_uid, Path(args.report) if args.report else None)


if __name__ == "__main__":
    raise SystemExit(main())
