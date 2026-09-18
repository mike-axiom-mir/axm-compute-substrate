#!/usr/bin/env python3
"""Independent adversarial verifier for Wave 131 readiness-gate path identity.

NON-CANON verifier lane. This does not modify builder implementation.

The attack widens only the natural boundary between Wave 131's readiness
validation and its delegation into the already-captured lower authenticated
server. A worker that can rename entries in the anchor path's parent swaps the
validated Wave-131-ready directory for a genuine authority-created Wave-130
store that has no Wave-131 manifest/readiness receipt. The unchanged Wave-131
serve path then reopens the pathname and serves the second store.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_INIT_RECOVERY as w131
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_AUTHENTICATED_ANCHOR as protocol

TOOLS = Path(__file__).resolve().parents[1] / "tools"
W131 = TOOLS / "AXM_FLOWING_COMPUTE_PROCESS_WITNESS_INIT_RECOVERY.py"
W130 = TOOLS / "AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_AUTHORITY_BOUNDARY.py"
ENV_UID = w131.w130.FORBIDDEN_WORKER_UID_ENV


def pycmd(*args: str) -> list[str]:
    out = [sys.executable]
    if sys.flags.optimize:
        out.append("-O")
    return [*out, *args]


def env(worker_uid: int) -> dict[str, str]:
    e = os.environ.copy()
    e["PYTHONPATH"] = str(TOOLS)
    e["HOME"] = "/tmp"
    e[ENV_UID] = str(worker_uid)
    return e


def demote(uid: int):
    def _drop() -> None:
        os.setgroups([])
        os.setgid(uid)
        os.setuid(uid)
    return _drop


def run_as(uid: int, worker_uid: int, args: list[str], *, check: bool = True,
           timeout: float = 40.0) -> subprocess.CompletedProcess:
    cp = subprocess.run(
        args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        env=env(worker_uid), preexec_fn=demote(uid), timeout=timeout,
        check=False,
    )
    if check and cp.returncode != 0:
        raise RuntimeError(f"child-failed:{uid}:{cp.returncode}:{args}:{cp.stdout}:{cp.stderr}")
    return cp


def popen_as(uid: int, worker_uid: int, args: list[str]) -> subprocess.Popen:
    return subprocess.Popen(
        args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        env=env(worker_uid), preexec_fn=demote(uid),
    )


def parse(cp: subprocess.CompletedProcess) -> dict:
    lines = cp.stdout.strip().splitlines()
    if not lines:
        raise RuntimeError(f"missing-json:{cp.returncode}:{cp.stderr}")
    return json.loads(lines[-1])


def wait_json(path: Path, proc: subprocess.Popen | None = None,
              timeout: float = 15.0) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        if path.exists() and path.stat().st_size:
            try:
                return json.loads(path.read_text())
            except Exception:
                pass
        if proc is not None and proc.poll() is not None:
            out, err = proc.communicate()
            raise RuntimeError(f"process-exited-before-file:{proc.returncode}:{out}:{err}")
        time.sleep(0.02)
    raise TimeoutError(str(path))


def child_serve(anchor: Path, socket_path: Path, ready: Path, error: Path,
                validated: Path, go: Path) -> int:
    original = w131.validate_initialized_anchor

    def gated(path: str | Path) -> dict:
        result = original(path)
        validated.write_text(json.dumps({
            "pid": os.getpid(),
            "validated_anchor_fp": result["root"]["anchor_credential_fingerprint"],
            "validated_response_fp": result["response_public_fingerprint"],
        }, sort_keys=True) + "\n")
        end = time.time() + 20
        while time.time() < end and not go.exists():
            time.sleep(0.01)
        if not go.exists():
            raise TimeoutError("verifier-gate-release-timeout")
        return result

    # Harness-only race widening: builder files are unchanged. The original
    # serve_anchor still performs its real validation and lower delegation.
    w131.validate_initialized_anchor = gated
    return w131.serve_anchor(anchor, socket_path, ready, error)


def child_ping(socket_path: Path, anchor_fp: str, public_path: Path) -> int:
    try:
        out = protocol.anchor_request(
            socket_path, {"op": "ping"}, anchor_fp, public_path, timeout=5.0
        )
        print(json.dumps({"ok": True, "body": out}, sort_keys=True))
        return 0
    except BaseException as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 3


def worker_swap(active: Path, unready: Path, preserved_ready: Path) -> None:
    os.rename(active, preserved_ready)
    os.rename(unready, active)


def run_suite(worker_uid: int, anchor_uid: int, report: Path | None) -> int:
    if os.geteuid() != 0:
        raise PermissionError("verifier-requires-root-orchestrator")
    if worker_uid == anchor_uid:
        raise ValueError("worker-and-anchor-uid-must-differ")

    base = Path(tempfile.mkdtemp(prefix="axm-w131-ready-swap-"))
    os.chmod(base, 0o777)
    server: subprocess.Popen | None = None
    try:
        active = base / "active-anchor"
        unready = base / "unready-wave130-anchor"
        preserved_ready = base / "validated-ready-anchor"
        witness_ready = base / "witness-ready"
        witness_unready = base / "witness-unready"
        socket_path = base / "anchor.sock"
        ready_file = base / "serve.ready"
        error_file = base / "serve.error"
        validated_file = base / "validated.marker"
        go_file = base / "go.marker"

        # Two genuine witness identities, both created by the authority uid.
        run_as(anchor_uid, worker_uid, pycmd(str(W131), "init-witness", str(witness_ready), "--witness-id", "wave131-ready-witness"))
        run_as(anchor_uid, worker_uid, pycmd(str(W130), "init-witness", str(witness_unready), "--witness-id", "wave130-unready-witness"))

        ready_init = parse(run_as(
            anchor_uid, worker_uid,
            pycmd(str(W131), "init-anchor", str(active), str(witness_ready), "--anchor-id", "wave131-ready-anchor"),
        ))
        unready_init = parse(run_as(
            anchor_uid, worker_uid,
            pycmd(str(W130), "init-anchor", str(unready), str(witness_unready), "--anchor-id", "wave130-only-anchor"),
        ))

        ready_fp = ready_init["anchor_credential_fingerprint"]
        unready_fp = unready_init["anchor_credential_fingerprint"]
        preconditions = {
            "active_has_wave131_manifest": (active / w131.MANIFEST).exists(),
            "active_has_wave131_ready": (active / w131.READY).exists(),
            "unready_has_wave131_manifest": (unready / w131.MANIFEST).exists(),
            "unready_has_wave131_ready": (unready / w131.READY).exists(),
            "active_mode": oct(stat.S_IMODE(active.stat().st_mode)),
            "unready_mode": oct(stat.S_IMODE(unready.stat().st_mode)),
            "active_owner_uid": active.stat().st_uid,
            "unready_owner_uid": unready.stat().st_uid,
            "parent_mode": oct(stat.S_IMODE(base.stat().st_mode)),
        }

        server = popen_as(
            anchor_uid, worker_uid,
            pycmd(str(Path(__file__).resolve()), "--child-serve", str(active), str(socket_path),
                  str(ready_file), str(error_file), str(validated_file), str(go_file)),
        )
        validated = wait_json(validated_file, server)

        # Perform the pathname replacement as the ordinary worker uid. This does
        # not read, write, or enter either authority-owned 0700 anchor directory;
        # rename authority comes from the writable parent directory.
        swap_code = (
            "import os,sys; "
            "os.rename(sys.argv[1],sys.argv[3]); "
            "os.rename(sys.argv[2],sys.argv[1]); "
            "print(os.geteuid())"
        )
        swap_cp = run_as(
            worker_uid, worker_uid,
            pycmd("-c", swap_code, str(active), str(unready), str(preserved_ready)),
        )
        go_file.write_text("go\n")
        os.chmod(go_file, 0o644)

        served = wait_json(ready_file, server)
        ping = parse(run_as(
            worker_uid, worker_uid,
            pycmd(str(Path(__file__).resolve()), "--child-ping", str(socket_path),
                  unready_fp, str(witness_unready / protocol.WITNESS_PUBLIC_KEY)),
        ))

        served_from_unready = (
            served.get("anchor_credential_fingerprint") == unready_fp and
            served.get("anchor_credential_fingerprint") != ready_fp
        )
        exact_attack = (
            preconditions["active_has_wave131_ready"] is True and
            preconditions["active_has_wave131_manifest"] is True and
            preconditions["unready_has_wave131_ready"] is False and
            preconditions["unready_has_wave131_manifest"] is False and
            validated.get("validated_anchor_fp") == ready_fp and
            served_from_unready and
            ping.get("ok") is True and
            ping.get("body", {}).get("anchor_credential_fingerprint") == unready_fp and
            not (active / w131.READY).exists() and
            not (active / w131.MANIFEST).exists()
        )

        result = {
            "schema": "axm.flowing-compute.verifier.wave131-ready-gate-path-swap.v1",
            "mode": "optimized" if sys.flags.optimize else "normal",
            "verdict": (
                "FAIL_WAVE131_VALIDATED_READY_PATH_CAN_BE_SWAPPED_TO_UNREADY_WAVE130_STORE_BEFORE_DELEGATION"
                if exact_attack else "ATTACK_NOT_REPRODUCED"
            ),
            "failure_reproduced": exact_attack,
            "worker_uid": worker_uid,
            "anchor_uid": anchor_uid,
            "preconditions": preconditions,
            "validated": validated,
            "ready_wave131_anchor_fp": ready_fp,
            "unready_wave130_anchor_fp": unready_fp,
            "worker_swap_returncode": swap_cp.returncode,
            "worker_swap_reported_euid": swap_cp.stdout.strip(),
            "served_ready_file": served,
            "authenticated_ping_to_unready_store": ping,
            "post_swap_active_has_wave131_ready": (active / w131.READY).exists(),
            "post_swap_active_has_wave131_manifest": (active / w131.MANIFEST).exists(),
            "preserved_original_ready_exists": (preserved_ready / w131.READY).exists(),
            "truth_boundary": (
                "same-host pathname TOCTOU where the anchor path parent is worker-writable; no authority key read, "
                "signature forgery, ledger rewrite, root/kernel compromise, cross-host claim, or performance/energy/retained-compute claim"
            ),
        }
        if report:
            report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(json.dumps(result, sort_keys=True))
        return 0 if exact_attack else 1
    finally:
        if server is not None and server.poll() is None:
            try:
                os.kill(server.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                server.wait(timeout=3)
            except Exception:
                pass
        shutil.rmtree(base, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker-uid", type=int)
    ap.add_argument("--anchor-uid", type=int)
    ap.add_argument("--report")
    ap.add_argument("--child-serve", nargs=6, metavar=("ANCHOR", "SOCKET", "READY", "ERROR", "VALIDATED", "GO"))
    ap.add_argument("--child-ping", nargs=3, metavar=("SOCKET", "ANCHOR_FP", "PUBLIC"))
    ns = ap.parse_args()
    if ns.child_serve:
        return child_serve(*(Path(x) for x in ns.child_serve))
    if ns.child_ping:
        return child_ping(Path(ns.child_ping[0]), ns.child_ping[1], Path(ns.child_ping[2]))
    if ns.worker_uid is None or ns.anchor_uid is None:
        ap.error("--worker-uid and --anchor-uid required")
    return run_suite(ns.worker_uid, ns.anchor_uid, Path(ns.report) if ns.report else None)


if __name__ == "__main__":
    raise SystemExit(main())
