#!/usr/bin/env python3
"""Wave 129 adversarial self-test: response-key custody across initialization.

The test first preserves verifier PR #53 as a counterexample against unchanged
Wave 128, then runs the same direct-parent /proc memory probe against Wave 129.
It also checks exact key persistence, authenticated restart, and fail-closed
behavior after a hard kill immediately before the private-key atomic write.

The memory probe is intentionally bounded to writable child mappings and only
accepts a candidate that OpenSSL validates as a real private key. The adversary
is same-UID, direct parent, and has no CAP_SYS_PTRACE on the tested CI host.
"""
from __future__ import annotations

import argparse
import ctypes
import errno
import importlib
import json
import os
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS as w

PR_GET_DUMPABLE = 3
CAP_SYS_PTRACE = 19
PRIVATE_KEY = "response_private.pem"
PUBLIC_KEY = "response_public.pem"
WITNESS_PUBLIC_KEY = "anchor_response_public.pem"
FIXED_TOOL = Path(__file__).with_name(
    "AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_LIFECYCLE.py"
).resolve()


def wait_file(path: Path, proc: subprocess.Popen | None = None,
              timeout: float = 12.0) -> None:
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


def cap_eff() -> int:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("CapEff:"):
            return int(line.split()[1], 16)
    return -1


def get_dumpable() -> int:
    libc = ctypes.CDLL(None, use_errno=True)
    rc = libc.prctl(PR_GET_DUMPABLE, 0, 0, 0, 0)
    if rc < 0:
        err = ctypes.get_errno()
        raise OSError(err, "prctl(PR_GET_DUMPABLE) failed")
    return int(rc)


def hard_kill(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        os.kill(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    proc.wait(timeout=3)


def private_key_valid(pem: bytes) -> bool:
    try:
        cp = subprocess.run(
            ["openssl", "pkey", "-noout", "-check"],
            input=pem,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=4,
        )
    except Exception:
        return False
    return cp.returncode == 0


def public_from_private(pem: bytes) -> bytes:
    cp = subprocess.run(
        ["openssl", "pkey", "-pubout"],
        input=pem,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=4,
    )
    if cp.returncode != 0:
        raise RuntimeError(cp.stderr.decode("utf-8", "replace"))
    return cp.stdout


def candidate_pems(blob: bytes) -> list[bytes]:
    begin = b"-----BEGIN " + b"PRIVATE KEY-----"
    end = b"-----END " + b"PRIVATE KEY-----"
    out: list[bytes] = []
    pos = 0
    while True:
        start = blob.find(begin, pos)
        if start < 0:
            break
        stop = blob.find(end, start + len(begin))
        if stop >= 0:
            stop += len(end)
            if stop < len(blob) and blob[stop:stop + 1] == b"\n":
                stop += 1
            item = blob[start:stop]
            if 500 <= len(item) <= 8192:
                out.append(item)
        pos = start + 1
    return out


def scan_child_memory(pid: int) -> tuple[bytes | None, dict]:
    detail = {
        "access_denied": False,
        "bytes_scanned": 0,
        "writable_regions_considered": 0,
        "errors": [],
    }
    try:
        maps = Path(f"/proc/{pid}/maps").read_text().splitlines()
    except PermissionError as exc:
        detail["access_denied"] = True
        detail["errors"].append(f"maps:{type(exc).__name__}:{exc}")
        return None, detail
    try:
        fd = os.open(f"/proc/{pid}/mem", os.O_RDONLY)
    except OSError as exc:
        if exc.errno in (errno.EPERM, errno.EACCES):
            detail["access_denied"] = True
        detail["errors"].append(f"mem-open:{type(exc).__name__}:{exc}")
        return None, detail
    try:
        for line in maps:
            parts = line.split(None, 5)
            if len(parts) < 2:
                continue
            addr, perms = parts[0], parts[1]
            if not perms.startswith("r") or "w" not in perms:
                continue
            start_s, end_s = addr.split("-", 1)
            start, end = int(start_s, 16), int(end_s, 16)
            if end <= start:
                continue
            detail["writable_regions_considered"] += 1
            pos = start
            limit = min(end, start + 128 * 1024 * 1024)
            overlap = b""
            while pos < limit and detail["bytes_scanned"] < 512 * 1024 * 1024:
                want = min(1024 * 1024, limit - pos)
                try:
                    chunk = os.pread(fd, want, pos)
                except OSError as exc:
                    if exc.errno in (errno.EPERM, errno.EACCES):
                        detail["access_denied"] = True
                    elif exc.errno not in (errno.EIO, errno.EFAULT):
                        detail["errors"].append(
                            f"pread:{type(exc).__name__}:{exc}"
                        )
                    break
                if not chunk:
                    break
                detail["bytes_scanned"] += len(chunk)
                probe = overlap + chunk
                for pem in candidate_pems(probe):
                    if private_key_valid(pem):
                        return pem, detail
                overlap = probe[-8192:]
                pos += len(chunk)
        return None, detail
    finally:
        os.close(fd)


def child_initialize(base: Path, mode: str) -> int:
    module_name = (
        "AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_CUSTODY"
        if mode == "wave128"
        else "AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_LIFECYCLE"
    )
    c = importlib.import_module(module_name)
    wd = base / "witness"
    ad = base / "anchor"
    pause = base / "initializer.pause.json"
    release = base / "initializer.release"
    done = base / "initializer.done.json"
    error = base / "initializer.error.txt"
    try:
        w.initialize_witness_dir(wd, f"{mode}-init-memory-witness")
        original_atomic = w._atomic_write
        paused = False

        def hooked_atomic(path, data, file_mode=0o600):
            nonlocal paused
            p = Path(path)
            if not paused and p.name == PRIVATE_KEY and p.parent == ad:
                paused = True
                pause.write_text(json.dumps({
                    "pid": os.getpid(),
                    "uid": os.getuid(),
                    "euid": os.geteuid(),
                    "dumpable": get_dumpable(),
                    "private_path_exists_before_write": p.exists(),
                    "private_bytes_argument_length": len(data),
                    "mode": mode,
                }, sort_keys=True) + "\n")
                while not release.exists():
                    time.sleep(0.01)
            return original_atomic(path, data, file_mode)

        w._atomic_write = hooked_atomic
        try:
            root = c.initialize_anchor_dir(ad, wd, f"{mode}-init-memory-anchor")
        finally:
            w._atomic_write = original_atomic
        done.write_text(json.dumps(root, sort_keys=True) + "\n")
        return 0
    except BaseException as exc:
        error.write_text(f"{type(exc).__name__}:{exc}\n")
        raise


def run_init_probe(root: Path, mode: str, release_after_scan: bool = True) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    pause = root / "initializer.pause.json"
    release = root / "initializer.release"
    done = root / "initializer.done.json"
    proc = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--child-init", mode, str(root)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        wait_file(pause, proc)
        pause_info = json.loads(pause.read_text())
        captured = None
        scan_detail = {}
        scan_error = ""
        try:
            captured, scan_detail = scan_child_memory(proc.pid)
        except Exception as exc:
            scan_error = f"{type(exc).__name__}:{exc}"
        if release_after_scan:
            release.write_text("release\n")
            wait_file(done, proc)
            rc = proc.wait(timeout=8)
            if rc != 0:
                out, err = proc.communicate()
                raise RuntimeError(f"initializer-exit:{rc}:{out}:{err}")
        return {
            "proc": proc,
            "pause": pause_info,
            "captured": captured,
            "scan": scan_detail,
            "scan_error": scan_error,
            "done": json.loads(done.read_text()) if done.exists() else None,
        }
    except BaseException:
        hard_kill(proc)
        raise


def launch_anchor(anchor_dir: Path, sock: Path, ready: Path, error: Path):
    for p in (ready, error, sock):
        try:
            p.unlink()
        except FileNotFoundError:
            pass
    proc = subprocess.Popen(
        [
            sys.executable, str(FIXED_TOOL), "serve-anchor", str(anchor_dir), str(sock),
            "--ready-file", str(ready), "--error-file", str(error),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    wait_file(ready, proc)
    return proc, json.loads(ready.read_text())


def run() -> dict:
    checks: list[dict] = []
    caps = cap_eff()
    no_ptrace_cap = caps >= 0 and not bool(caps & (1 << CAP_SYS_PTRACE))
    checks.append({
        "name": "adversary_has_no_cap_sys_ptrace",
        "ok": no_ptrace_cap,
        "detail": {"cap_eff_hex": hex(caps) if caps >= 0 else None},
    })

    with tempfile.TemporaryDirectory(prefix="axm-wave129-lifecycle-") as td:
        b = Path(td)

        old = run_init_probe(b / "wave128", "wave128")
        old_private = old["captured"]
        old_public = (b / "wave128" / "witness" / WITNESS_PUBLIC_KEY).read_bytes()
        old_matches = bool(
            old_private
            and private_key_valid(old_private)
            and public_from_private(old_private) == old_public
        )
        checks.append({
            "name": "wave128_initializer_memory_counterexample_is_preserved",
            "ok": (
                old["pause"].get("dumpable") == 1
                and old["pause"].get("uid") == os.getuid()
                and old["pause"].get("euid") == os.geteuid()
                and not old["pause"].get("private_path_exists_before_write", True)
                and old_matches
            ),
            "detail": {
                "pause": old["pause"],
                "scan": old["scan"],
                "scan_error": old["scan_error"],
                "captured_private_bytes": len(old_private or b""),
                "captured_key_matches_persisted_public": old_matches,
            },
        })

        fixed = run_init_probe(b / "wave129", "wave129")
        fixed_private_path = b / "wave129" / "anchor" / PRIVATE_KEY
        fixed_public = (b / "wave129" / "witness" / WITNESS_PUBLIC_KEY).read_bytes()
        persisted_private = fixed_private_path.read_bytes()
        fixed_mode = stat.S_IMODE(fixed_private_path.stat().st_mode)
        checks.append({
            "name": "wave129_initializer_is_non_dumpable_before_private_persistence",
            "ok": (
                fixed["pause"].get("dumpable") == 0
                and fixed["pause"].get("uid") == os.getuid()
                and fixed["pause"].get("euid") == os.geteuid()
                and not fixed["pause"].get("private_path_exists_before_write", True)
            ),
            "detail": fixed["pause"],
        })
        checks.append({
            "name": "same_uid_direct_parent_cannot_recover_wave129_private_key_from_proc",
            "ok": fixed["captured"] is None and fixed["scan"].get("access_denied") is True,
            "detail": {
                "scan": fixed["scan"],
                "scan_error": fixed["scan_error"],
                "captured_private_bytes": len(fixed["captured"] or b""),
            },
        })
        checks.append({
            "name": "wave129_persists_exact_keypair_with_private_mode_0600",
            "ok": (
                fixed_mode == 0o600
                and private_key_valid(persisted_private)
                and public_from_private(persisted_private) == fixed_public
            ),
            "detail": {
                "private_mode_octal": oct(fixed_mode),
                "private_bytes": len(persisted_private),
                "public_bytes": len(fixed_public),
            },
        })

        c = importlib.import_module(
            "AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_LIFECYCLE"
        )
        ad = b / "wave129" / "anchor"
        wd = b / "wave129" / "witness"
        sock = b / "wave129" / "anchor.sock"
        p1 = p2 = None
        try:
            binding, public_path = c.load_response_binding(
                wd, fixed["done"]["anchor_credential_fingerprint"]
            )
            anchor_fp = fixed["done"]["anchor_credential_fingerprint"]
            p1, info1 = launch_anchor(
                ad, sock, b / "wave129" / "anchor.ready",
                b / "wave129" / "anchor.error",
            )
            ping1 = c.anchor_request(sock, {"op": "ping"}, anchor_fp, public_path)
            try:
                c.anchor_request(sock, {"op": "stop"}, anchor_fp, public_path)
            except Exception:
                pass
            p1.wait(timeout=4)
            p1 = None
            p2, info2 = launch_anchor(
                ad, sock, b / "wave129" / "anchor.restart.ready",
                b / "wave129" / "anchor.restart.error",
            )
            ping2 = c.anchor_request(sock, {"op": "ping"}, anchor_fp, public_path)
            checks.append({
                "name": "completed_wave129_store_restarts_with_exact_authenticated_identity",
                "ok": (
                    ping1.get("ok") is True
                    and ping2.get("ok") is True
                    and info1.get("response_public_fingerprint")
                        == binding["response_public_fingerprint"]
                    and info2.get("response_public_fingerprint")
                        == binding["response_public_fingerprint"]
                    and ping2.get("response_public_fingerprint")
                        == binding["response_public_fingerprint"]
                ),
                "detail": {
                    "first": info1,
                    "restart": info2,
                    "response_public_fingerprint": binding[
                        "response_public_fingerprint"
                    ],
                },
            })
        finally:
            if p1 is not None:
                hard_kill(p1)
            if p2 is not None:
                try:
                    c.anchor_request(sock, {"op": "stop"}, anchor_fp, public_path)
                    p2.wait(timeout=3)
                except Exception:
                    hard_kill(p2)

        crash_root = b / "hard-kill-before-private-write"
        crash = run_init_probe(crash_root, "wave129", release_after_scan=False)
        crash_proc = crash["proc"]
        hard_kill(crash_proc)
        private_absent = not (crash_root / "anchor" / PRIVATE_KEY).exists()
        checks.append({
            "name": "hard_kill_before_private_write_leaves_no_response_private_key_file",
            "ok": (
                crash["pause"].get("dumpable") == 0
                and crash["captured"] is None
                and crash["scan"].get("access_denied") is True
                and private_absent
            ),
            "detail": {
                "pause": crash["pause"],
                "scan": crash["scan"],
                "private_path_exists_after_sigkill": not private_absent,
            },
        })

        crash_sock = crash_root / "anchor.sock"
        crash_ready = crash_root / "serve.ready"
        crash_error = crash_root / "serve.error"
        proc = subprocess.Popen(
            [
                sys.executable, str(FIXED_TOOL), "serve-anchor",
                str(crash_root / "anchor"), str(crash_sock),
                "--ready-file", str(crash_ready), "--error-file", str(crash_error),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        end = time.time() + 5
        while time.time() < end and proc.poll() is None and not crash_error.exists():
            time.sleep(0.02)
        if proc.poll() is None:
            hard_kill(proc)
        else:
            proc.wait(timeout=2)
        checks.append({
            "name": "partial_hard_killed_initializer_fails_closed_instead_of_serving",
            "ok": not crash_ready.exists() and (crash_error.exists() or proc.returncode not in (0, None)),
            "detail": {
                "returncode": proc.returncode,
                "ready_exists": crash_ready.exists(),
                "error": crash_error.read_text().strip() if crash_error.exists() else None,
                "counterexample_retained": "partial initialized anchor state is not yet automatically resumable",
            },
        })

    passed = sum(1 for item in checks if item["ok"])
    return {
        "wave": 129,
        "name": "response private-key full initialization lifecycle custody",
        "checks": checks,
        "passed": passed,
        "total": len(checks),
        "ok": passed == len(checks),
        "truth_boundary": [
            "same Linux host; same Unix uid direct-parent adversary; no CAP_SYS_PTRACE",
            "Wave 128 counterexample must remain reproducible rather than being rewritten away",
            "Wave 129 protects process memory/proc exposure, not an adversary allowed to read the anchor store itself",
            "hard kill before response-key persistence is fail-closed but leaves partial lower anchor initialization; automatic resume is not claimed",
            "sibling-process behavior can be affected by host ptrace policy and is not generalized from the direct-parent result",
            "copied genuine key on another namespace/host, whole-domain rollback, kernel/root compromise, hardware custody, power/device/provider and physical finality remain open",
            "no performance, energy, retained/incremental/dormant-compute, throughput or scaling claim",
        ],
        "next_gate": (
            "make interrupted anchor initialization explicitly recoverable without guessing identity, "
            "then resume the copied-genuine-key cross-network-namespace/second-host fork test"
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report")
    ap.add_argument("--child-init", nargs=2, metavar=("MODE", "BASE"))
    ns = ap.parse_args()
    if ns.child_init:
        mode, base = ns.child_init
        return child_initialize(Path(base), mode)
    report = run()
    if ns.report:
        Path(ns.report).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    for item in report["checks"]:
        print(("PASS" if item["ok"] else "FAIL") + " " + item["name"])
    print(f"SUMMARY {report['passed']}/{report['total']} passed")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
