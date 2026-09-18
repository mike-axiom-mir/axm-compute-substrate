#!/usr/bin/env python3
"""Wave 128 focused adversarial checks for response private-key custody.

This is intentionally narrower than the full Wave-127 protocol suite. It tests
the exact verifier-PR-52 repair boundary: no globally discoverable private-key
helper, ordinary same-UID /proc fd inspection blocked by non-dumpable anchor
custody, concurrent signing, hard-kill cleanup, and exact-store restart.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS as w
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_CUSTODY as c

TOOL = Path(c.__file__).resolve()
PRIVATE_PATTERNS = (
    "axm-w127-private-*",
    "axm-w128-private-*",
    "axm-w127-keygen-*",
    "axm-wave128-response-private*",
)


def wait_file(path: Path, proc: subprocess.Popen | None = None,
              timeout: float = 8.0) -> None:
    end = time.time() + timeout
    while time.time() < end:
        if path.exists():
            return
        if proc is not None and proc.poll() is not None:
            out, err = proc.communicate()
            raise RuntimeError(
                f"process-exited-before-ready:{proc.returncode}:{out}:{err}"
            )
        time.sleep(0.02)
    raise TimeoutError(f"marker-timeout:{path}")


def launch_anchor(anchor_dir: Path, sock: Path, ready: Path,
                  error: Path) -> tuple[subprocess.Popen, dict]:
    for p in (ready, error):
        try:
            p.unlink()
        except FileNotFoundError:
            pass
    try:
        sock.unlink()
    except FileNotFoundError:
        pass
    proc = subprocess.Popen(
        [
            sys.executable, str(TOOL), "serve-anchor", str(anchor_dir), str(sock),
            "--ready-file", str(ready), "--error-file", str(error),
        ],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    wait_file(ready, proc)
    return proc, json.loads(ready.read_text())


def hard_kill(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        os.kill(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    proc.wait(timeout=3)


def stop_anchor(proc: subprocess.Popen | None, sock: Path,
                anchor_fp: str, public_key: Path) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        c.anchor_request(sock, {"op": "stop"}, anchor_fp, public_key)
    except Exception:
        pass
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        hard_kill(proc)


class TempPrivateObserver:
    def __init__(self) -> None:
        self.root = Path(tempfile.gettempdir())
        self.initial = self._matching()
        self.seen: list[dict] = []
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _matching(self) -> set[str]:
        out: set[str] = set()
        for pattern in PRIVATE_PATTERNS:
            try:
                out.update(str(p) for p in self.root.glob(pattern))
            except Exception:
                pass
        return out

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        self.stop.set()
        self.thread.join(timeout=2)

    def _run(self) -> None:
        while not self.stop.is_set():
            for raw in self._matching() - self.initial:
                p = Path(raw)
                item = {"path": p.name, "private_pem": False, "bytes": None}
                try:
                    data = p.read_bytes()
                    item["bytes"] = len(data)
                    item["private_pem"] = b"PRIVATE KEY" in data
                except (FileNotFoundError, PermissionError, OSError):
                    pass
                self.seen.append(item)
            time.sleep(0.0005)


def check_proc_fd_denied(pid: int) -> dict:
    proc_fd = Path(f"/proc/{pid}/fd")
    try:
        names = os.listdir(proc_fd)
    except PermissionError as exc:
        # Some Linux procfs/LSM configurations deny the fd directory itself
        # once the target is non-dumpable. That is a stronger successful
        # custody result than allowing the listing but denying readlink().
        return {
            "fd_directory_listing_denied": True,
            "fd_entries_seen": 0,
            "readlink_permission_denied": 0,
            "resolved_targets": [],
            "error": f"{type(exc).__name__}:{exc}",
            "ok": True,
        }
    resolved: list[str] = []
    denied = 0
    for name in names:
        try:
            resolved.append(os.readlink(proc_fd / name))
        except PermissionError:
            denied += 1
        except FileNotFoundError:
            pass
    return {
        "fd_directory_listing_denied": False,
        "fd_entries_seen": len(names),
        "readlink_permission_denied": denied,
        "resolved_targets": resolved,
        "ok": len(resolved) == 0 and denied > 0,
    }


def run() -> dict:
    checks: list[dict] = []
    observer = TempPrivateObserver()
    observer.start()
    p_anchor = p_restart = None
    try:
        with tempfile.TemporaryDirectory(prefix="axm-wave128-custody-") as td:
            b = Path(td)
            wd = b / "witness"
            ad = b / "anchor"
            sock = b / "anchor.sock"
            ready = b / "anchor.ready"
            error = b / "anchor.error"

            witness_root = w.initialize_witness_dir(wd, "wave128-custody-witness")
            anchor_root = c.initialize_anchor_dir(ad, wd, "wave128-custody-anchor")
            anchor_fp = anchor_root["anchor_credential_fingerprint"]
            binding, public_key = c.load_response_binding(wd, anchor_fp)
            response_fp = binding["response_public_fingerprint"]

            checks.append({
                "name": "key_generation_uses_no_global_private_helper",
                "ok": not any(x.get("private_pem") for x in observer.seen),
                "detail": list(observer.seen),
            })

            p_anchor, info = launch_anchor(ad, sock, ready, error)
            checks.append({
                "name": "anchor_starts_with_exact_response_identity",
                "ok": (
                    info.get("anchor_credential_fingerprint") == anchor_fp
                    and info.get("response_public_fingerprint") == response_fp
                ),
                "detail": info,
            })

            proc_check = check_proc_fd_denied(p_anchor.pid)
            checks.append({
                "name": "ordinary_same_uid_proc_fd_targets_are_blocked",
                "ok": proc_check.pop("ok"),
                "detail": proc_check,
            })

            failures: list[str] = []
            results: list[dict] = []
            lock = threading.Lock()

            def ping_worker(i: int) -> None:
                try:
                    body = c.anchor_request(
                        sock, {"op": "ping", "worker": i}, anchor_fp, public_key
                    )
                    with lock:
                        results.append(body)
                except BaseException as exc:
                    with lock:
                        failures.append(f"{type(exc).__name__}:{exc}")

            threads = [threading.Thread(target=ping_worker, args=(i,)) for i in range(24)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=8)

            concurrent_ok = (
                len(results) == 24
                and not failures
                and all(r.get("ok") is True for r in results)
                and all(r.get("response_public_fingerprint") == response_fp for r in results)
            )
            checks.append({
                "name": "concurrent_signed_responses_verify_without_key_export",
                "ok": concurrent_ok,
                "detail": {"responses": len(results), "failures": failures},
            })

            time.sleep(0.05)
            checks.append({
                "name": "pr52_style_temp_observer_captures_no_private_key",
                "ok": not any(x.get("private_pem") for x in observer.seen),
                "detail": list(observer.seen),
            })

            hard_kill(p_anchor)
            p_anchor = None
            time.sleep(0.05)
            checks.append({
                "name": "hard_kill_leaves_no_private_key_helper_path",
                "ok": not any(x.get("private_pem") for x in observer.seen),
                "detail": list(observer.seen),
            })

            p_restart, restart_info = launch_anchor(
                ad, sock, b / "anchor.restart.ready", b / "anchor.restart.error"
            )
            body = c.anchor_request(sock, {"op": "ping"}, anchor_fp, public_key)
            checks.append({
                "name": "exact_store_restart_preserves_response_identity_and_signing",
                "ok": (
                    restart_info.get("response_public_fingerprint") == response_fp
                    and body.get("ok") is True
                    and body.get("response_public_fingerprint") == response_fp
                ),
                "detail": {
                    "restart_response_public_fingerprint": restart_info.get(
                        "response_public_fingerprint"
                    ),
                    "ping_response_public_fingerprint": body.get(
                        "response_public_fingerprint"
                    ),
                },
            })

            stop_anchor(p_restart, sock, anchor_fp, public_key)
            p_restart = None

    finally:
        hard_kill(p_anchor)
        hard_kill(p_restart)
        observer.close()

    passed = sum(1 for item in checks if item["ok"])
    return {
        "wave": 128,
        "name": "response private-key custody",
        "source": c.SOURCE,
        "checks": checks,
        "passed": passed,
        "total": len(checks),
        "ok": passed == len(checks),
        "truth_boundary": [
            "tested Linux same-host/same-uid observer without anchor-store read access or CAP_SYS_PTRACE",
            "PR_SET_DUMPABLE=0 is part of the tested custody contract, not a hostile-kernel boundary",
            "memfd and procfs behavior are Linux-specific",
            "copied genuine private keys in another namespace/host remain outside this wave",
            "no performance, energy, retained/incremental/dormant-compute or physical-finality claim",
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report")
    ns = ap.parse_args()
    report = run()
    if ns.report:
        Path(ns.report).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    for item in report["checks"]:
        print(("PASS" if item["ok"] else "FAIL") + " " + item["name"])
    print(f"SUMMARY {report['passed']}/{report['total']} passed")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
