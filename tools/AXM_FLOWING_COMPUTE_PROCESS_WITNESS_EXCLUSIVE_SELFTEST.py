#!/usr/bin/env python3
"""Wave 124 adversarial self-test: exclusive witness-store lifetime lease."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS as w123
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_EXCLUSIVE as w124

TOOL123 = Path(w123.__file__).resolve()
TOOL124 = Path(w124.__file__).resolve()


def h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def check(report: dict, name: str, ok: bool, detail=None) -> None:
    report["controls"].append({"name": name, "ok": bool(ok), "detail": detail})
    if not ok:
        report["failed"] += 1


def wait_file(path: Path, proc: subprocess.Popen | None = None, timeout: float = 8.0) -> None:
    end = time.time() + timeout
    while time.time() < end:
        if path.exists():
            return
        if proc is not None and proc.poll() is not None:
            raise RuntimeError(f"process-exited-before-marker:{proc.returncode}")
        time.sleep(0.02)
    raise TimeoutError(f"marker-timeout:{path}")


def launch(tool: Path, wd: Path, sock: Path, ready: Path, error: Path) -> tuple[subprocess.Popen, dict]:
    for p in (ready, error):
        if p.exists():
            p.unlink()
    proc = subprocess.Popen(
        [sys.executable, str(tool), "serve", str(wd), str(sock), "--ready-file", str(ready), "--error-file", str(error)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    wait_file(ready, proc)
    return proc, json.loads(ready.read_text())


def launch_expect_fail(tool: Path, wd: Path, sock: Path, ready: Path, error: Path, timeout: float = 5.0) -> dict:
    for p in (ready, error):
        if p.exists():
            p.unlink()
    proc = subprocess.Popen(
        [sys.executable, str(tool), "serve", str(wd), str(sock), "--ready-file", str(ready), "--error-file", str(error)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    end = time.time() + timeout
    while time.time() < end and proc.poll() is None and not error.exists() and not ready.exists():
        time.sleep(0.02)
    if proc.poll() is None and (error.exists() or ready.exists()):
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            proc.kill(); proc.wait(timeout=2)
    elif proc.poll() is None:
        proc.kill(); proc.wait(timeout=2)
    out, err = proc.communicate() if proc.stdout is not None else ("", "")
    return {
        "returncode": proc.returncode,
        "ready": ready.exists(),
        "error": error.read_text().strip() if error.exists() else "",
        "stdout": out,
        "stderr": err,
    }


def stop(proc: subprocess.Popen | None, sock: Path) -> None:
    if proc is None:
        return
    if proc.poll() is None:
        try:
            w123.request(sock, {"op": "stop"}, timeout=1.0)
        except Exception:
            pass
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill(); proc.wait(timeout=2)


def hard_kill(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        os.kill(proc.pid, signal.SIGKILL)
    proc.wait(timeout=3)


def recv_line(conn: socket.socket) -> dict:
    data = b""
    while not data.endswith(b"\n"):
        part = conn.recv(65536)
        if not part:
            break
        data += part
    if not data:
        raise ConnectionError("disconnected-without-response")
    return json.loads(data)


def run() -> dict:
    report = {
        "wave": 124,
        "title": "exclusive process-witness store lifetime lease",
        "source": w124.SOURCE,
        "controls": [],
        "failed": 0,
        "truth_boundary": [
            "same Linux host and advisory-lock-capable filesystem only",
            "lease serializes cooperating Wave 124 servers; direct out-of-protocol ledger writers are not covered",
            "directory/inode substitution while a server is live is not proved safe",
            "SIGKILL releases the kernel lease but does not prove power-loss or device finality",
            "whole witness plus surviving client-pin rollback remains a predecessor counterexample",
            "no performance, energy, retained/incremental/dormant-compute, network/provider, merge, or CANON claim",
        ],
    }

    with tempfile.TemporaryDirectory(prefix="axm-wave124-") as td:
        b = Path(td)

        # Deterministic prerequisite reproduction: unchanged Wave 123 permits two
        # live servers on one store/socket while the old accepted connection survives.
        wd0, sock0 = b / "w123", b / "w123.sock"
        r0 = w123.initialize_witness_dir(wd0, "wave123-overlap-prereq")
        p0a = p0b = None
        old_conn = None
        try:
            p0a, i0a = launch(TOOL123, wd0, sock0, b / "w123-ready-a", b / "w123-err-a")
            old_conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            old_conn.settimeout(3)
            old_conn.connect(str(sock0))
            p0b, i0b = launch(TOOL123, wd0, sock0, b / "w123-ready-b", b / "w123-err-b")
            old_conn.sendall(w123.canonical({"op": "ping"}) + b"\n")
            old_ping = recv_line(old_conn)
            new_ping = w123.request(sock0, {"op": "ping"}, r0["credential_fingerprint"])
            check(
                report,
                "wave123_prerequisite_allows_overlapping_store_instances",
                p0a.poll() is None and p0b.poll() is None
                and old_ping.get("pid") == p0a.pid and new_ping.get("pid") == p0b.pid
                and old_ping.get("credential_fingerprint") == new_ping.get("credential_fingerprint") == r0["credential_fingerprint"],
                {"old_pid": p0a.pid, "new_pid": p0b.pid, "old_ping": old_ping, "new_ping": new_ping},
            )
        finally:
            if old_conn is not None:
                try: old_conn.close()
                except Exception: pass
            if p0b is not None and p0b.poll() is None:
                hard_kill(p0b)
            if p0a is not None and p0a.poll() is None:
                hard_kill(p0a)

        # Wave 124 primary store.
        wd, sock = b / "w124", b / "w124.sock"
        root = w123.initialize_witness_dir(wd, "wave124-main")
        fp = root["credential_fingerprint"]
        primary = None
        established = None
        try:
            primary, info = launch(TOOL124, wd, sock, b / "ready-primary", b / "err-primary")
            ping = w123.request(sock, {"op": "ping"}, fp)
            check(report, "exclusive_server_is_separate_process", ping["pid"] == primary.pid and ping.get("exclusive_store_lease") is True, ping)
            check(report, "credential_identity_preserved_from_wave123", info["credential_fingerprint"] == fp == ping["credential_fingerprint"], info)

            # Hold an already-established connection open, exactly as verifier PR #48 did.
            established = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            established.settimeout(3)
            established.connect(str(sock))
            socket_inode_before = sock.stat().st_ino
            ledger_before = (wd / "ledger.jsonl").read_bytes()
            rejected = launch_expect_fail(TOOL124, wd, sock, b / "ready-replacement", b / "err-replacement")
            socket_inode_after = sock.stat().st_ino
            established.sendall(w123.canonical({"op": "ping"}) + b"\n")
            old_reply = recv_line(established)
            established.close(); established = None
            path_reply = w123.request(sock, {"op": "ping"}, fp)
            check(
                report,
                "overlapping_same_store_replacement_is_rejected_before_socket_touch",
                rejected["returncode"] == 2 and not rejected["ready"]
                and "witness-store-already-served" in rejected["error"]
                and socket_inode_before == socket_inode_after
                and old_reply.get("pid") == primary.pid == path_reply.get("pid"),
                {"replacement": rejected, "socket_inode_before": socket_inode_before, "socket_inode_after": socket_inode_after,
                 "established_reply": old_reply, "path_reply": path_reply},
            )
            check(report, "rejected_replacement_does_not_mutate_witness_ledger", (wd / "ledger.jsonl").read_bytes() == ledger_before)

            # Lease is store-scoped, not merely socket-scoped.
            alt = launch_expect_fail(TOOL124, wd, b / "different.sock", b / "ready-alt", b / "err-alt")
            check(report, "same_store_different_socket_is_also_rejected", alt["returncode"] == 2 and "witness-store-already-served" in alt["error"], alt)

            # Normal terminal semantics still work through the leased server.
            a, t = h("wave124-clean-a"), h("wave124-clean-t")
            local = b / "local.jsonl"
            w123.decide_and_publish(sock, fp, local, a, t, "COMMIT", True, "")
            state = w123.status(sock, fp, local, a)
            led_once, loc_once = (wd / "ledger.jsonl").read_bytes(), local.read_bytes()
            w123.decide_and_publish(sock, fp, local, a, t, "COMMIT", True, "")
            check(report, "clean_commit_remains_authoritative", state["status"] == "AUTHORITATIVE_PROCESS_WITNESS_COMMIT", state)
            check(report, "exact_retry_remains_idempotent", (wd / "ledger.jsonl").read_bytes() == led_once and local.read_bytes() == loc_once)

            conflict = None
            try:
                w123.decide_and_publish(sock, fp, local, a, t, "REJECT", True, "contradictory-terminal")
            except Exception as exc:
                conflict = str(exc)
            check(report, "conflicting_terminal_outcome_still_fails_closed", conflict is not None and (wd / "ledger.jsonl").read_bytes() == led_once, conflict)

            # Separate stores may legitimately run at the same time.
            wd2, sock2 = b / "w124-second", b / "w124-second.sock"
            root2 = w123.initialize_witness_dir(wd2, "wave124-independent-store")
            second, info2 = launch(TOOL124, wd2, sock2, b / "ready-second-store", b / "err-second-store")
            try:
                p2 = w123.request(sock2, {"op": "ping"}, root2["credential_fingerprint"])
                check(report, "independent_witness_stores_can_serve_concurrently", primary.poll() is None and second.poll() is None and p2["pid"] == second.pid and second.pid != primary.pid, {"primary": primary.pid, "second": second.pid})
            finally:
                stop(second, sock2)

            # Hard kill must release only the operational lease. Durable witness/local
            # evidence remains unchanged and a successor may take over the same store.
            before_kill_ledger = (wd / "ledger.jsonl").read_bytes()
            before_kill_local = local.read_bytes()
            killed_pid = primary.pid
            hard_kill(primary); primary = None
            stale_socket_existed = sock.exists()
            successor, sinfo = launch(TOOL124, wd, sock, b / "ready-successor", b / "err-successor")
            primary = successor
            post = w123.status(sock, fp, local, a)
            check(
                report,
                "sigkill_releases_lease_and_exact_successor_recovers_same_store",
                stale_socket_existed and successor.pid != killed_pid and sinfo["credential_fingerprint"] == fp
                and (wd / "ledger.jsonl").read_bytes() == before_kill_ledger
                and local.read_bytes() == before_kill_local
                and post["status"] == "AUTHORITATIVE_PROCESS_WITNESS_COMMIT",
                {"killed_pid": killed_pid, "successor_pid": successor.pid, "status": post},
            )

            # Startup validation still fails closed, and a failed startup releases
            # its lease so exact repair/restart is possible.
            stop(primary, sock); primary = None
            good = (wd / "ledger.jsonl").read_bytes()
            (wd / "ledger.jsonl").write_bytes(good[:-1])
            bad_start = launch_expect_fail(TOOL124, wd, sock, b / "ready-corrupt", b / "err-corrupt")
            (wd / "ledger.jsonl").write_bytes(good)
            primary, _ = launch(TOOL124, wd, sock, b / "ready-restored", b / "err-restored")
            restored = w123.status(sock, fp, local, a)
            check(report, "corrupt_startup_fails_closed_and_releases_lease", "ledger-truncated-tail" in bad_start["error"] and restored["status"] == "AUTHORITATIVE_PROCESS_WITNESS_COMMIT", {"failed_start": bad_start, "restored": restored})

            check(report, "lease_file_is_operational_not_authority_evidence", (wd / w124.LEASE_NAME).exists() and (wd / w124.LEASE_NAME).read_bytes() == b"")
        finally:
            if established is not None:
                try: established.close()
                except Exception: pass
            stop(primary, sock)

    report["passed"] = len(report["controls"]) - report["failed"]
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report")
    ns = ap.parse_args()
    report = run()
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if ns.report:
        Path(ns.report).write_text(text + "\n")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
