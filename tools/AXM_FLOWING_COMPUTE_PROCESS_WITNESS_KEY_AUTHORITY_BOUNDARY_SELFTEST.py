#!/usr/bin/env python3
"""Wave 130 adversarial self-test for the durable response-key uid boundary.

Runs under root only so the harness can create two numeric Unix identities, then
executes the adversary as the ordinary worker uid and the real anchor as a
separate service uid. Root is test orchestration, not part of the claimed
attacker boundary.
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

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS as w
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_AUTHENTICATED_ANCHOR as protocol

SCRIPT = Path(__file__).resolve()
TOOLS = SCRIPT.parent
W129 = TOOLS / "AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_LIFECYCLE.py"
W130 = TOOLS / "AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_AUTHORITY_BOUNDARY.py"
PRIVATE_KEY = "response_private.pem"
WITNESS_PUBLIC_KEY = "anchor_response_public.pem"
ENV_UID = "AXM_W130_FORBIDDEN_WORKER_UID"


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


def base_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(TOOLS)
    env["HOME"] = "/tmp"
    if extra:
        env.update(extra)
    return env


def run_as(uid: int, args: list[str], *, env: dict[str, str] | None = None,
           check: bool = True, timeout: float = 30.0) -> subprocess.CompletedProcess:
    cp = subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=timeout,
        env=env or base_env(),
        preexec_fn=demote(uid),
    )
    if check and cp.returncode != 0:
        raise RuntimeError(
            f"child-failed:{uid}:{cp.returncode}:{args}:{cp.stdout}:{cp.stderr}"
        )
    return cp


def popen_as(uid: int, args: list[str], *, env: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        preexec_fn=demote(uid),
    )


def wait_file(path: Path, proc: subprocess.Popen | None = None,
              timeout: float = 12.0) -> None:
    end = time.time() + timeout
    while time.time() < end:
        if path.exists() and path.stat().st_size:
            return
        if proc is not None and proc.poll() is not None:
            out, err = proc.communicate()
            raise RuntimeError(
                f"process-exited-before-ready:{proc.returncode}:{out}:{err}"
            )
        time.sleep(0.02)
    raise TimeoutError(f"marker-timeout:{path}")


def chown_tree(path: Path, uid: int, gid: int) -> None:
    for root, dirs, files in os.walk(path):
        os.chown(root, uid, gid)
        for name in dirs:
            os.chown(Path(root) / name, uid, gid)
        for name in files:
            os.chown(Path(root) / name, uid, gid)


def child_read_key(private_path: Path, public_path: Path) -> int:
    try:
        private = private_path.read_bytes()
    except BaseException as exc:
        print(json.dumps({
            "readable": False,
            "error": f"{type(exc).__name__}:{exc}",
            "uid": os.getuid(), "euid": os.geteuid(),
        }, sort_keys=True))
        return 0
    cp = subprocess.run(
        ["openssl", "pkey", "-pubout"], input=private,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    derived = cp.stdout if cp.returncode == 0 else b""
    public = public_path.read_bytes()
    print(json.dumps({
        "readable": True,
        "private_bytes": len(private),
        "derived_public_matches": derived == public,
        "uid": os.getuid(), "euid": os.geteuid(),
    }, sort_keys=True))
    return 0


def child_proc_probe(pid: int) -> int:
    out = {
        "uid": os.getuid(), "euid": os.geteuid(),
        "mem_open": False, "readable_fd_count": 0, "errors": [],
    }
    try:
        fd = os.open(f"/proc/{pid}/mem", os.O_RDONLY)
    except BaseException as exc:
        out["errors"].append(f"mem:{type(exc).__name__}:{exc}")
    else:
        out["mem_open"] = True
        os.close(fd)
    try:
        names = os.listdir(f"/proc/{pid}/fd")
    except BaseException as exc:
        out["errors"].append(f"fd-list:{type(exc).__name__}:{exc}")
    else:
        for name in names:
            try:
                fd = os.open(f"/proc/{pid}/fd/{name}", os.O_RDONLY)
            except BaseException:
                continue
            else:
                out["readable_fd_count"] += 1
                os.close(fd)
    print(json.dumps(out, sort_keys=True))
    return 0


def child_ping(socket_path: Path, anchor_fp: str, public_path: Path) -> int:
    try:
        body = protocol.anchor_request(
            socket_path, {"op": "ping"}, anchor_fp, public_path, timeout=4.0
        )
        print(json.dumps({"ok": True, "body": body}, sort_keys=True))
        return 0
    except BaseException as exc:
        print(json.dumps({
            "ok": False, "error": f"{type(exc).__name__}:{exc}"
        }, sort_keys=True))
        return 3


def child_unlink(path: Path) -> int:
    try:
        path.unlink()
        print(json.dumps({"ok": True}, sort_keys=True))
        return 0
    except BaseException as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}))
        return 2


def child_fake_server(socket_path: Path, ready_path: Path) -> int:
    import socket
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.bind(str(socket_path))
        os.chmod(socket_path, 0o777)
        ready_path.write_text("ready\n")
        s.listen(1)
        conn, _ = s.accept()
        with conn:
            data = b""
            while not data.endswith(b"\n"):
                chunk = conn.recv(65536)
                if not chunk:
                    break
                data += chunk
            conn.sendall(w.canonical({
                "schema": protocol.RESPONSE_SCHEMA,
                "body": {"ok": True, "fake": True},
            }) + b"\n")
        return 0
    finally:
        s.close()
        try:
            socket_path.unlink()
        except FileNotFoundError:
            pass


def parse_json_line(cp: subprocess.CompletedProcess) -> dict:
    text = cp.stdout.strip().splitlines()
    if not text:
        raise RuntimeError(f"missing-json-output:{cp.stderr}")
    return json.loads(text[-1])


def start_anchor(uid: int, anchor_dir: Path, socket_path: Path, ready: Path,
                 error: Path, worker_uid: int) -> subprocess.Popen:
    for p in (socket_path, ready, error):
        try:
            p.unlink()
        except FileNotFoundError:
            pass
    env = base_env({ENV_UID: str(worker_uid)})
    proc = popen_as(uid, pycmd(
        str(W130), "serve-anchor", str(anchor_dir), str(socket_path),
        "--ready-file", str(ready), "--error-file", str(error),
    ), env=env)
    wait_file(ready, proc)
    os.chmod(socket_path, 0o777)
    return proc


def run_suite(worker_uid: int, anchor_uid: int, report_path: Path | None) -> int:
    if os.geteuid() != 0:
        raise PermissionError("wave130-selftest-requires-root-or-sudo-orchestrator")
    if worker_uid == anchor_uid:
        raise ValueError("worker-and-anchor-uid-must-differ")

    results: list[dict] = []
    base = Path(tempfile.mkdtemp(prefix="axm-w130-boundary-"))
    os.chmod(base, 0o777)
    anchor_proc: subprocess.Popen | None = None
    fake_proc: subprocess.Popen | None = None
    try:
        pred = base / "predecessor"
        pred.mkdir(mode=0o777)
        run_as(worker_uid, pycmd(str(W129), "init-witness", str(pred / "witness")))
        run_as(worker_uid, pycmd(
            str(W129), "init-anchor", str(pred / "anchor"), str(pred / "witness")
        ))
        pred_read = parse_json_line(run_as(worker_uid, pycmd(
            str(SCRIPT), "--child-read-key",
            str(pred / "anchor" / PRIVATE_KEY),
            str(pred / "witness" / WITNESS_PUBLIC_KEY),
        )))
        ok = bool(pred_read.get("readable") and pred_read.get("derived_public_matches"))
        results.append({"name": "predecessor_wave129_same_uid_read_reproduced", "ok": ok,
                        "detail": pred_read})

        fixed = base / "fixed"
        fixed.mkdir(mode=0o777)
        env_anchor = base_env({ENV_UID: str(worker_uid)})
        run_as(anchor_uid, pycmd(str(W130), "init-witness", str(fixed / "witness")),
               env=env_anchor)
        init = parse_json_line(run_as(anchor_uid, pycmd(
            str(W130), "init-anchor", str(fixed / "anchor"), str(fixed / "witness"),
            "--anchor-id", "wave130-dedicated-uid-anchor",
        ), env=env_anchor))
        chown_tree(fixed / "witness", worker_uid, worker_uid)
        os.chmod(fixed / "witness", 0o700)

        ad_st = (fixed / "anchor").stat()
        pk_st = (fixed / "anchor" / PRIVATE_KEY).stat()
        boundary_ok = (
            ad_st.st_uid == anchor_uid and stat.S_IMODE(ad_st.st_mode) == 0o700
            and pk_st.st_uid == anchor_uid and stat.S_IMODE(pk_st.st_mode) == 0o600
            and init["wave130_durable_key_boundary"]["forbidden_worker_uid"] == worker_uid
        )
        results.append({"name": "dedicated_uid_private_store_boundary", "ok": boundary_ok,
                        "detail": init["wave130_durable_key_boundary"]})

        fixed_read = parse_json_line(run_as(worker_uid, pycmd(
            str(SCRIPT), "--child-read-key",
            str(fixed / "anchor" / PRIVATE_KEY),
            str(fixed / "witness" / WITNESS_PUBLIC_KEY),
        )))
        results.append({"name": "worker_direct_private_key_read_denied",
                        "ok": not fixed_read.get("readable", True), "detail": fixed_read})

        run_dir = fixed / "run"
        run_dir.mkdir(mode=0o777)
        os.chmod(run_dir, 0o777)
        socket_path = run_dir / "anchor.sock"
        ready = run_dir / "anchor.ready"
        error = run_dir / "anchor.error"
        anchor_proc = start_anchor(
            anchor_uid, fixed / "anchor", socket_path, ready, error, worker_uid
        )

        proc_probe = parse_json_line(run_as(worker_uid, pycmd(
            str(SCRIPT), "--child-proc-probe", str(anchor_proc.pid)
        )))
        proc_ok = not proc_probe.get("mem_open") and proc_probe.get("readable_fd_count") == 0
        results.append({"name": "worker_proc_secret_paths_denied", "ok": proc_ok,
                        "detail": proc_probe})

        anchor_fp = init["anchor_credential_fingerprint"]
        public_path = fixed / "witness" / WITNESS_PUBLIC_KEY
        ping = parse_json_line(run_as(worker_uid, pycmd(
            str(SCRIPT), "--child-ping", str(socket_path), anchor_fp, str(public_path)
        )))
        results.append({"name": "worker_can_use_authenticated_anchor_without_key", "ok": ping.get("ok") is True,
                        "detail": ping})

        run_as(worker_uid, pycmd(str(SCRIPT), "--child-unlink", str(socket_path)))
        fake_ready = run_dir / "fake.ready"
        fake_proc = popen_as(worker_uid, pycmd(
            str(SCRIPT), "--child-fake-server", str(socket_path), str(fake_ready)
        ), env=base_env())
        wait_file(fake_ready, fake_proc)
        fake_ping_cp = run_as(worker_uid, pycmd(
            str(SCRIPT), "--child-ping", str(socket_path), anchor_fp, str(public_path)
        ), check=False)
        fake_ping = parse_json_line(fake_ping_cp)
        if fake_proc.poll() is None:
            fake_proc.wait(timeout=3)
        fake_proc = None
        results.append({"name": "worker_socket_substitution_still_rejected",
                        "ok": fake_ping_cp.returncode != 0 and fake_ping.get("ok") is False,
                        "detail": fake_ping})

        os.kill(anchor_proc.pid, signal.SIGKILL)
        anchor_proc.wait(timeout=3)
        anchor_proc = None
        restart_ready = run_dir / "anchor.restart.ready"
        restart_error = run_dir / "anchor.restart.error"
        anchor_proc = start_anchor(
            anchor_uid, fixed / "anchor", socket_path, restart_ready,
            restart_error, worker_uid
        )
        restart_ping = parse_json_line(run_as(worker_uid, pycmd(
            str(SCRIPT), "--child-ping", str(socket_path), anchor_fp, str(public_path)
        )))
        same_identity = (
            restart_ping.get("ok") is True
            and restart_ping.get("body", {}).get("anchor_credential_fingerprint") == anchor_fp
            and restart_ping.get("body", {}).get("response_public_fingerprint")
                == init.get("response_public_fingerprint")
        )
        results.append({"name": "sigkill_restart_preserves_exact_anchor_identity",
                        "ok": same_identity, "detail": restart_ping})

        bad = base / "same-uid-refusal"
        bad.mkdir(mode=0o777)
        run_as(worker_uid, pycmd(str(W130), "init-witness", str(bad / "witness")),
               env=base_env({ENV_UID: str(worker_uid)}))
        bad_cp = run_as(worker_uid, pycmd(
            str(W130), "init-anchor", str(bad / "anchor"), str(bad / "witness")
        ), env=base_env({ENV_UID: str(worker_uid)}), check=False)
        no_private = not (bad / "anchor" / PRIVATE_KEY).exists()
        results.append({"name": "same_uid_authority_configuration_fails_before_key_generation",
                        "ok": bad_cp.returncode != 0 and no_private,
                        "detail": {"returncode": bad_cp.returncode,
                                   "stderr_tail": bad_cp.stderr[-500:],
                                   "private_exists": not no_private}})

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
                "tested Unix uid/process isolation only; root/kernel, anchor-uid compromise, "
                "cross-host copied keys, interrupted-init recovery, rotation, hardware custody, "
                "performance and physical/provider finality remain unproved"
            ),
        }
        if report_path:
            report_path.parent.mkdir(parents=True, exist_ok=True)
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
    worker_uid = ns.worker_uid
    if worker_uid is None:
        raise ValueError("--worker-uid-required")
    return run_suite(worker_uid, ns.anchor_uid, ns.report)


if __name__ == "__main__":
    raise SystemExit(main())
