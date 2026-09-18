#!/usr/bin/env python3
"""Wave 130 adversarial self-test: durable response key behind a distinct Unix uid.

Root is used only as test orchestration so the harness can create two numeric
identities. The claimed attacker is the ordinary worker uid, not root.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Import Wave 130 first. Its Wave129->Wave128 chain installs the current memfd
# signing/verification hooks into the shared Wave127 protocol module. Importing
# the protocol directly first would leave this test client on Wave127's older
# signature-algorithm expectation and would not test the current source.
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_AUTHORITY_BOUNDARY as w130
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_AUTHENTICATED_ANCHOR as protocol

SCRIPT = Path(__file__).resolve()
TOOLS = SCRIPT.parent
W129 = TOOLS / "AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_LIFECYCLE.py"
W130 = TOOLS / "AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_AUTHORITY_BOUNDARY.py"
PRIVATE_KEY = "response_private.pem"
WITNESS_PUBLIC_KEY = "anchor_response_public.pem"
ENV_UID = w130.FORBIDDEN_WORKER_UID_ENV


def pycmd(*args: str) -> list[str]:
    out = [sys.executable]
    if sys.flags.optimize:
        out.append("-O")
    return [*out, *args]


def demote(uid: int):
    def _drop() -> None:
        os.setgroups([])
        os.setgid(uid)
        os.setuid(uid)
    return _drop


def env(extra: dict[str, str] | None = None) -> dict[str, str]:
    e = os.environ.copy()
    e["PYTHONPATH"] = str(TOOLS)
    e["HOME"] = "/tmp"
    if extra:
        e.update(extra)
    return e


def run_as(uid: int, args: list[str], *, extra_env: dict[str, str] | None = None,
           check: bool = True, timeout: float = 30.0) -> subprocess.CompletedProcess:
    cp = subprocess.run(
        args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        check=False, timeout=timeout, env=env(extra_env), preexec_fn=demote(uid),
    )
    if check and cp.returncode != 0:
        raise RuntimeError(f"child-failed:{uid}:{cp.returncode}:{args}:{cp.stdout}:{cp.stderr}")
    return cp


def popen_as(uid: int, args: list[str], *, extra_env: dict[str, str] | None = None) -> subprocess.Popen:
    return subprocess.Popen(
        args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        env=env(extra_env), preexec_fn=demote(uid),
    )


def parse(cp: subprocess.CompletedProcess) -> dict:
    lines = cp.stdout.strip().splitlines()
    if not lines:
        raise RuntimeError(f"missing-json:{cp.returncode}:{cp.stderr}")
    return json.loads(lines[-1])


def wait_file(path: Path, proc: subprocess.Popen | None = None, timeout: float = 12.0) -> None:
    end = time.time() + timeout
    while time.time() < end:
        if path.exists() and path.stat().st_size:
            return
        if proc is not None and proc.poll() is not None:
            out, err = proc.communicate()
            raise RuntimeError(f"process-exited-before-ready:{proc.returncode}:{out}:{err}")
        time.sleep(0.02)
    raise TimeoutError(f"marker-timeout:{path}")


def chown_tree(path: Path, uid: int) -> None:
    for root, dirs, files in os.walk(path):
        os.chown(root, uid, uid)
        for name in dirs:
            os.chown(Path(root) / name, uid, uid)
        for name in files:
            os.chown(Path(root) / name, uid, uid)


def child_read_key(private_path: Path, public_path: Path) -> int:
    try:
        private = private_path.read_bytes()
    except BaseException as exc:
        print(json.dumps({"readable": False, "error": f"{type(exc).__name__}:{exc}", "uid": os.getuid()}))
        return 0
    cp = subprocess.run(
        ["openssl", "pkey", "-pubout"], input=private,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    print(json.dumps({
        "readable": True,
        "private_bytes": len(private),
        "derived_public_matches": cp.returncode == 0 and cp.stdout == public_path.read_bytes(),
        "uid": os.getuid(),
    }, sort_keys=True))
    return 0


def child_proc_probe(pid: int) -> int:
    out = {"mem_open": False, "fd_dir_listable": False, "uid": os.getuid(), "errors": []}
    try:
        fd = os.open(f"/proc/{pid}/mem", os.O_RDONLY)
    except BaseException as exc:
        out["errors"].append(f"mem:{type(exc).__name__}:{exc}")
    else:
        out["mem_open"] = True
        os.close(fd)
    try:
        os.listdir(f"/proc/{pid}/fd")
    except BaseException as exc:
        out["errors"].append(f"fd:{type(exc).__name__}:{exc}")
    else:
        out["fd_dir_listable"] = True
    print(json.dumps(out, sort_keys=True))
    return 0


def child_ping(socket_path: Path, anchor_fp: str, public_path: Path) -> int:
    try:
        body = protocol.anchor_request(socket_path, {"op": "ping"}, anchor_fp, public_path, timeout=4.0)
    except BaseException as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 3
    print(json.dumps({"ok": True, "body": body}, sort_keys=True))
    return 0


def child_unlink(path: Path) -> int:
    try:
        path.unlink()
    except BaseException as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 2
    print(json.dumps({"ok": True}, sort_keys=True))
    return 0


def child_fake_server(socket_path: Path, ready: Path) -> int:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.bind(str(socket_path))
        os.chmod(socket_path, 0o777)
        ready.write_text("ready\n")
        s.listen(1)
        conn, _ = s.accept()
        with conn:
            data = b""
            while not data.endswith(b"\n"):
                chunk = conn.recv(65536)
                if not chunk:
                    break
                data += chunk
            # Deliberately unsigned. A pathname replacement must not gain authority.
            conn.sendall(json.dumps({"schema": protocol.RESPONSE_SCHEMA, "body": {"ok": True, "fake": True}}).encode() + b"\n")
        return 0
    finally:
        s.close()
        try:
            socket_path.unlink()
        except FileNotFoundError:
            pass


def start_anchor(anchor_uid: int, worker_uid: int, anchor_dir: Path,
                 socket_path: Path, ready: Path, error: Path) -> subprocess.Popen:
    for p in (socket_path, ready, error):
        try:
            p.unlink()
        except FileNotFoundError:
            pass
    proc = popen_as(anchor_uid, pycmd(
        str(W130), "serve-anchor", str(anchor_dir), str(socket_path),
        "--ready-file", str(ready), "--error-file", str(error),
    ), extra_env={ENV_UID: str(worker_uid)})
    wait_file(ready, proc)
    os.chmod(socket_path, 0o777)
    return proc


def run_suite(worker_uid: int, anchor_uid: int, report_path: Path | None) -> int:
    if os.geteuid() != 0:
        raise PermissionError("wave130-selftest-requires-root-orchestrator")
    if worker_uid == anchor_uid:
        raise ValueError("worker-and-anchor-uid-must-differ")

    results: list[dict] = []
    base = Path(tempfile.mkdtemp(prefix="axm-w130-boundary-"))
    os.chmod(base, 0o777)
    anchor_proc: subprocess.Popen | None = None
    fake_proc: subprocess.Popen | None = None
    try:
        # Permanent predecessor counterexample: Wave129's durable 0600 key is
        # readable by another process with the same uid.
        pred = base / "predecessor"
        pred.mkdir(mode=0o777)
        run_as(worker_uid, pycmd(str(W129), "init-witness", str(pred / "witness")))
        pred_init = parse(run_as(worker_uid, pycmd(
            str(W129), "init-anchor", str(pred / "anchor"), str(pred / "witness")
        )))
        pred_read = parse(run_as(worker_uid, pycmd(
            str(SCRIPT), "--child-read-key", str(pred / "anchor" / PRIVATE_KEY),
            str(pred / "witness" / WITNESS_PUBLIC_KEY)
        )))
        results.append({"name": "predecessor_wave129_same_uid_read_reproduced",
                        "ok": bool(pred_read.get("readable") and pred_read.get("derived_public_matches")),
                        "detail": pred_read})

        fixed = base / "fixed"
        fixed.mkdir(mode=0o777)
        boundary_env = {ENV_UID: str(worker_uid)}
        run_as(anchor_uid, pycmd(str(W130), "init-witness", str(fixed / "witness")), extra_env=boundary_env)
        init = parse(run_as(anchor_uid, pycmd(
            str(W130), "init-anchor", str(fixed / "anchor"), str(fixed / "witness"),
            "--anchor-id", "wave130-dedicated-uid-anchor"
        ), extra_env=boundary_env))
        chown_tree(fixed / "witness", worker_uid)
        os.chmod(fixed / "witness", 0o700)

        ad = (fixed / "anchor").stat()
        pk = (fixed / "anchor" / PRIVATE_KEY).stat()
        boundary_ok = (
            ad.st_uid == anchor_uid and stat.S_IMODE(ad.st_mode) == 0o700 and
            pk.st_uid == anchor_uid and stat.S_IMODE(pk.st_mode) == 0o600 and
            init["wave130_durable_key_boundary"]["forbidden_worker_uid"] == worker_uid
        )
        results.append({"name": "dedicated_uid_private_store_boundary", "ok": boundary_ok,
                        "detail": init["wave130_durable_key_boundary"]})

        fixed_read = parse(run_as(worker_uid, pycmd(
            str(SCRIPT), "--child-read-key", str(fixed / "anchor" / PRIVATE_KEY),
            str(fixed / "witness" / WITNESS_PUBLIC_KEY)
        )))
        results.append({"name": "worker_direct_private_key_read_denied",
                        "ok": not fixed_read.get("readable", True), "detail": fixed_read})

        run_dir = fixed / "run"
        run_dir.mkdir(mode=0o777)
        socket_path = run_dir / "anchor.sock"
        anchor_proc = start_anchor(anchor_uid, worker_uid, fixed / "anchor", socket_path,
                                   run_dir / "anchor.ready", run_dir / "anchor.error")

        probe = parse(run_as(worker_uid, pycmd(str(SCRIPT), "--child-proc-probe", str(anchor_proc.pid))))
        results.append({"name": "worker_proc_secret_paths_denied",
                        "ok": not probe["mem_open"] and not probe["fd_dir_listable"], "detail": probe})

        anchor_fp = init["anchor_credential_fingerprint"]
        public_path = fixed / "witness" / WITNESS_PUBLIC_KEY
        ping = parse(run_as(worker_uid, pycmd(
            str(SCRIPT), "--child-ping", str(socket_path), anchor_fp, str(public_path)
        )))
        results.append({"name": "worker_uses_authenticated_anchor_without_private_key",
                        "ok": ping.get("ok") is True, "detail": ping})

        run_as(worker_uid, pycmd(str(SCRIPT), "--child-unlink", str(socket_path)))
        fake_ready = run_dir / "fake.ready"
        fake_proc = popen_as(worker_uid, pycmd(
            str(SCRIPT), "--child-fake-server", str(socket_path), str(fake_ready)
        ))
        wait_file(fake_ready, fake_proc)
        fake_ping_cp = run_as(worker_uid, pycmd(
            str(SCRIPT), "--child-ping", str(socket_path), anchor_fp, str(public_path)
        ), check=False)
        fake_ping = parse(fake_ping_cp)
        fake_proc.wait(timeout=3)
        fake_proc = None
        results.append({"name": "worker_socket_substitution_still_rejected",
                        "ok": fake_ping_cp.returncode != 0 and fake_ping.get("ok") is False,
                        "detail": fake_ping})

        os.kill(anchor_proc.pid, signal.SIGKILL)
        anchor_proc.wait(timeout=3)
        anchor_proc = start_anchor(anchor_uid, worker_uid, fixed / "anchor", socket_path,
                                   run_dir / "anchor.restart.ready", run_dir / "anchor.restart.error")
        restart = parse(run_as(worker_uid, pycmd(
            str(SCRIPT), "--child-ping", str(socket_path), anchor_fp, str(public_path)
        )))
        same_identity = (
            restart.get("ok") is True and
            restart["body"].get("anchor_credential_fingerprint") == anchor_fp and
            restart["body"].get("response_public_fingerprint") == init.get("response_public_fingerprint")
        )
        results.append({"name": "sigkill_restart_preserves_exact_anchor_identity",
                        "ok": same_identity, "detail": restart})

        bad = base / "same-uid-refusal"
        bad.mkdir(mode=0o777)
        run_as(worker_uid, pycmd(str(W130), "init-witness", str(bad / "witness")), extra_env=boundary_env)
        bad_cp = run_as(worker_uid, pycmd(
            str(W130), "init-anchor", str(bad / "anchor"), str(bad / "witness")
        ), extra_env=boundary_env, check=False)
        private_exists = (bad / "anchor" / PRIVATE_KEY).exists()
        results.append({"name": "same_uid_configuration_fails_before_key_generation",
                        "ok": bad_cp.returncode != 0 and not private_exists,
                        "detail": {"returncode": bad_cp.returncode, "private_exists": private_exists,
                                   "stderr_tail": bad_cp.stderr[-400:]}})

        passed = sum(1 for r in results if r["ok"])
        report = {
            "schema": "axm.flowing-compute.wave130-dedicated-uid-boundary-selftest.v1",
            "mode": "optimized" if sys.flags.optimize else "normal",
            "worker_uid": worker_uid,
            "anchor_uid": anchor_uid,
            "passed": passed,
            "total": len(results),
            "results": results,
            "truth_boundary": (
                "tested Unix uid/process isolation only; root/kernel, anchor-uid compromise, ACL/LSM-equivalent access, "
                "cross-host copied genuine keys, interrupted-init recovery, rotation, hardware custody, performance, "
                "and physical/provider finality remain unproved"
            ),
        }
        if report_path:
            report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps(report, sort_keys=True))
        return 0 if passed == len(results) else 1
    finally:
        for proc in (fake_proc, anchor_proc):
            if proc is not None and proc.poll() is None:
                try:
                    os.kill(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    proc.wait(timeout=3)
                except Exception:
                    pass
        shutil.rmtree(base, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker-uid", type=int)
    ap.add_argument("--anchor-uid", type=int, default=23001)
    ap.add_argument("--report", type=Path)
    ap.add_argument("--child-read-key", nargs=2)
    ap.add_argument("--child-proc-probe", type=int)
    ap.add_argument("--child-ping", nargs=3)
    ap.add_argument("--child-unlink")
    ap.add_argument("--child-fake-server", nargs=2)
    ns = ap.parse_args()
    if ns.child_read_key:
        return child_read_key(Path(ns.child_read_key[0]), Path(ns.child_read_key[1]))
    if ns.child_proc_probe is not None:
        return child_proc_probe(ns.child_proc_probe)
    if ns.child_ping:
        return child_ping(Path(ns.child_ping[0]), ns.child_ping[1], Path(ns.child_ping[2]))
    if ns.child_unlink:
        return child_unlink(Path(ns.child_unlink))
    if ns.child_fake_server:
        return child_fake_server(Path(ns.child_fake_server[0]), Path(ns.child_fake_server[1]))
    if ns.worker_uid is None:
        raise ValueError("--worker-uid-required")
    return run_suite(ns.worker_uid, ns.anchor_uid, ns.report)


if __name__ == "__main__":
    raise SystemExit(main())
