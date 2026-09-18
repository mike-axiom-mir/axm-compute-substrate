#!/usr/bin/env python3
"""Wave 131 verifier v2: readiness validation -> lower-server pathname swap.

Verifier-only harness. Builder files are unchanged. The pause is inserted only
after the genuine Wave-131 validation returns and before the unchanged lower
server reopens the anchor pathname.
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

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
W131 = TOOLS / "AXM_FLOWING_COMPUTE_PROCESS_WITNESS_INIT_RECOVERY.py"
W130 = TOOLS / "AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_AUTHORITY_BOUNDARY.py"
ENV_UID = w131.w130.FORBIDDEN_WORKER_UID_ENV


def pycmd(*args: str) -> list[str]:
    cmd = [sys.executable]
    if sys.flags.optimize:
        cmd.append("-O")
    return [*cmd, *args]


def child_env(worker_uid: int) -> dict[str, str]:
    e = os.environ.copy()
    e["PYTHONPATH"] = str(TOOLS)
    e["HOME"] = "/tmp"
    e[ENV_UID] = str(worker_uid)
    return e


def drop_to(uid: int):
    def inner() -> None:
        os.setgroups([])
        os.setgid(uid)
        os.setuid(uid)
    return inner


def run_as(uid: int, worker_uid: int, args: list[str], *, check: bool = True,
           timeout: float = 40.0) -> subprocess.CompletedProcess:
    cp = subprocess.run(
        args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        check=False, timeout=timeout, env=child_env(worker_uid), preexec_fn=drop_to(uid),
    )
    if check and cp.returncode != 0:
        raise RuntimeError(f"child-failed:{uid}:{cp.returncode}:{args}:{cp.stdout}:{cp.stderr}")
    return cp


def popen_as(uid: int, worker_uid: int, args: list[str]) -> subprocess.Popen:
    return subprocess.Popen(
        args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        env=child_env(worker_uid), preexec_fn=drop_to(uid),
    )


def last_json(cp: subprocess.CompletedProcess) -> dict:
    lines = cp.stdout.strip().splitlines()
    if not lines:
        raise RuntimeError(f"missing-json:{cp.returncode}:{cp.stderr}")
    return json.loads(lines[-1])


def wait_json(path: Path, proc: subprocess.Popen | None = None, timeout: float = 15.0) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        if path.exists() and path.stat().st_size:
            try:
                return json.loads(path.read_text())
            except Exception:
                pass
        if proc is not None and proc.poll() is not None:
            out, err = proc.communicate()
            raise RuntimeError(f"child-exited:{proc.returncode}:{out}:{err}")
        time.sleep(0.02)
    raise TimeoutError(str(path))


def chown_tree(path: Path, uid: int) -> None:
    for root, dirs, files in os.walk(path):
        os.chown(root, uid, uid)
        for name in dirs:
            os.chown(Path(root) / name, uid, uid)
        for name in files:
            os.chown(Path(root) / name, uid, uid)


def child_serve(anchor: Path, socket_path: Path, ready: Path, error: Path,
                validated: Path, release: Path) -> int:
    original = w131.validate_initialized_anchor

    def gated(path: str | Path) -> dict:
        out = original(path)
        validated.write_text(json.dumps({
            "pid": os.getpid(),
            "validated_anchor_fp": out["root"]["anchor_credential_fingerprint"],
            "validated_response_fp": out["response_public_fingerprint"],
        }, sort_keys=True) + "\n")
        end = time.time() + 20
        while time.time() < end and not release.exists():
            time.sleep(0.01)
        if not release.exists():
            raise TimeoutError("verifier-release-timeout")
        return out

    w131.validate_initialized_anchor = gated
    return w131.serve_anchor(anchor, socket_path, ready, error)


def child_ping(socket_path: Path, anchor_fp: str, public_path: Path) -> int:
    try:
        body = protocol.anchor_request(
            socket_path, {"op": "ping"}, anchor_fp, public_path, timeout=5.0
        )
        print(json.dumps({"ok": True, "body": body}, sort_keys=True))
        return 0
    except BaseException as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 3


def run(worker_uid: int, anchor_uid: int, report: Path | None) -> int:
    if os.geteuid() != 0:
        raise PermissionError("root-orchestrator-required")
    if worker_uid == anchor_uid:
        raise ValueError("uids-must-differ")

    base = Path(tempfile.mkdtemp(prefix="axm-w131-gate-swap-v2-"))
    os.chmod(base, 0o777)
    server: subprocess.Popen | None = None
    try:
        active = base / "active-anchor"
        unready = base / "unready-wave130-anchor"
        saved = base / "validated-ready-anchor"
        witness_a = base / "witness-a"
        witness_b = base / "witness-b"
        socket_path = base / "anchor.sock"
        ready_file = base / "serve.ready"
        error_file = base / "serve.error"
        validated_file = base / "validated.marker"
        release_file = base / "release.marker"

        run_as(anchor_uid, worker_uid, pycmd(str(W131), "init-witness", str(witness_a), "--witness-id", "ready-witness"))
        run_as(anchor_uid, worker_uid, pycmd(str(W130), "init-witness", str(witness_b), "--witness-id", "unready-witness"))
        ready_init = last_json(run_as(
            anchor_uid, worker_uid,
            pycmd(str(W131), "init-anchor", str(active), str(witness_a), "--anchor-id", "ready-wave131"),
        ))
        unready_init = last_json(run_as(
            anchor_uid, worker_uid,
            pycmd(str(W130), "init-anchor", str(unready), str(witness_b), "--anchor-id", "unready-wave130"),
        ))

        ready_fp = ready_init["anchor_credential_fingerprint"]
        unready_fp = unready_init["anchor_credential_fingerprint"]
        pre = {
            "ready_has_manifest": (active / w131.MANIFEST).exists(),
            "ready_has_receipt": (active / w131.READY).exists(),
            "unready_has_manifest": (unready / w131.MANIFEST).exists(),
            "unready_has_receipt": (unready / w131.READY).exists(),
            "ready_owner_uid": active.stat().st_uid,
            "unready_owner_uid": unready.stat().st_uid,
            "ready_mode": oct(stat.S_IMODE(active.stat().st_mode)),
            "unready_mode": oct(stat.S_IMODE(unready.stat().st_mode)),
            "parent_mode": oct(stat.S_IMODE(base.stat().st_mode)),
        }

        # Real deployment handoff: the witness-side public verifier/binding is
        # worker-readable while the anchor store remains authority-owned 0700.
        chown_tree(witness_b, worker_uid)
        os.chmod(witness_b, 0o700)

        server = popen_as(
            anchor_uid, worker_uid,
            pycmd(str(Path(__file__).resolve()), "--child-serve", str(active), str(socket_path),
                  str(ready_file), str(error_file), str(validated_file), str(release_file)),
        )
        validated = wait_json(validated_file, server)

        # The swap itself runs as the ordinary worker uid, not root/authority.
        swap_code = (
            "import os,sys;"
            "os.rename(sys.argv[1],sys.argv[3]);"
            "os.rename(sys.argv[2],sys.argv[1]);"
            "print(os.geteuid())"
        )
        swap = run_as(
            worker_uid, worker_uid,
            pycmd("-c", swap_code, str(active), str(unready), str(saved)),
        )
        release_file.write_text("go\n")
        os.chmod(release_file, 0o644)

        served = wait_json(ready_file, server)
        ping_cp = run_as(
            worker_uid, worker_uid,
            pycmd(str(Path(__file__).resolve()), "--child-ping", str(socket_path),
                  unready_fp, str(witness_b / protocol.WITNESS_PUBLIC_KEY)),
            check=False,
        )
        ping = last_json(ping_cp)

        reproduced = (
            pre["ready_has_manifest"] and pre["ready_has_receipt"] and
            not pre["unready_has_manifest"] and not pre["unready_has_receipt"] and
            validated.get("validated_anchor_fp") == ready_fp and
            swap.returncode == 0 and swap.stdout.strip() == str(worker_uid) and
            served.get("anchor_credential_fingerprint") == unready_fp and
            served.get("anchor_credential_fingerprint") != ready_fp and
            ping_cp.returncode == 0 and ping.get("ok") is True and
            ping.get("body", {}).get("anchor_credential_fingerprint") == unready_fp and
            not (active / w131.MANIFEST).exists() and not (active / w131.READY).exists() and
            (saved / w131.MANIFEST).exists() and (saved / w131.READY).exists()
        )
        out = {
            "schema": "axm.flowing-compute.verifier.wave131-ready-gate-path-swap.v2",
            "mode": "optimized" if sys.flags.optimize else "normal",
            "verdict": (
                "FAIL_WAVE131_READY_GATE_REOPENS_REPLACEABLE_PATH_BEFORE_LOWER_SERVICE"
                if reproduced else "ATTACK_NOT_REPRODUCED"
            ),
            "failure_reproduced": reproduced,
            "worker_uid": worker_uid,
            "anchor_uid": anchor_uid,
            "preconditions": pre,
            "validated": validated,
            "validated_ready_anchor_fp": ready_fp,
            "served_unready_anchor_fp": unready_fp,
            "worker_swap_euid": swap.stdout.strip(),
            "served_ready_file": served,
            "worker_authenticated_ping": ping,
            "active_after_swap_has_manifest": (active / w131.MANIFEST).exists(),
            "active_after_swap_has_ready": (active / w131.READY).exists(),
            "original_ready_store_preserved": (saved / w131.READY).exists(),
            "truth_boundary": (
                "same-host worker-writable parent pathname TOCTOU only; the worker does not read the authority-owned 0700 stores or private key, "
                "forge a signature, rewrite a ledger, use root/kernel compromise, or establish any performance/energy/retained-compute result"
            ),
        }
        if report:
            report.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
        print(json.dumps(out, sort_keys=True))
        return 0 if reproduced else 1
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
    ap.add_argument("--child-serve", nargs=6)
    ap.add_argument("--child-ping", nargs=3)
    ns = ap.parse_args()
    if ns.child_serve:
        return child_serve(*(Path(x) for x in ns.child_serve))
    if ns.child_ping:
        return child_ping(Path(ns.child_ping[0]), ns.child_ping[1], Path(ns.child_ping[2]))
    if ns.worker_uid is None or ns.anchor_uid is None:
        ap.error("--worker-uid and --anchor-uid required")
    return run(ns.worker_uid, ns.anchor_uid, Path(ns.report) if ns.report else None)


if __name__ == "__main__":
    raise SystemExit(main())
