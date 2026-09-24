#!/usr/bin/env python3
"""Wave 125 adversarial self-test: host-bound witness identity and stale-clone pin."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS as w123
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_EXCLUSIVE as w124
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_HOSTBOUND as w125

TOOL124 = Path(w124.__file__).resolve()
TOOL125 = Path(w125.__file__).resolve()


def h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def proposal(authority: str, transition: str, decision: str, stable: bool, reason: str) -> dict:
    return {
        "op": "decide",
        "authority_sha": authority,
        "transition_sha": transition,
        "proposal_sha": w123.proposal_sha(authority, transition, decision, stable, reason),
        "decision": decision,
        "stable": stable,
        "reason": reason,
    }


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


def launch(tool: Path, wd: Path, sock: Path, ready: Path, error: Path,
           allow_fault: bool = False) -> tuple[subprocess.Popen, dict]:
    for p in (ready, error):
        if p.exists():
            p.unlink()
    cmd = [
        sys.executable, str(tool), "serve", str(wd), str(sock),
        "--ready-file", str(ready), "--error-file", str(error),
    ]
    if allow_fault:
        cmd.append("--allow-fault-injection")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    wait_file(ready, proc)
    return proc, json.loads(ready.read_text())


def launch_expect_fail(tool: Path, wd: Path, sock: Path, ready: Path, error: Path,
                       timeout: float = 5.0) -> dict:
    for p in (ready, error):
        if p.exists():
            p.unlink()
    proc = subprocess.Popen(
        [sys.executable, str(tool), "serve", str(wd), str(sock),
         "--ready-file", str(ready), "--error-file", str(error)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    end = time.time() + timeout
    while time.time() < end and proc.poll() is None and not error.exists() and not ready.exists():
        time.sleep(0.02)
    if proc.poll() is None:
        proc.kill()
        proc.wait(timeout=2)
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
            proc.kill()
            proc.wait(timeout=2)


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


def cleanup_pin(fp: str) -> None:
    try:
        w125.host_pin_path(fp).unlink()
    except FileNotFoundError:
        pass


def run() -> dict:
    report = {
        "wave": 125,
        "title": "host-bound process witness identity and stale-clone high-water pin",
        "source": w125.SOURCE,
        "controls": [],
        "failed": 0,
        "truth_boundary": [
            "same Linux network namespace plus one OS user's trusted host-pin namespace",
            "first host-pin creation is a bootstrap boundary; pre-existing Wave 124 same-credential forks are not resolved",
            "cooperating Wave 125 servers only; mixed older servers and direct out-of-protocol writers are not covered",
            "opened-directory binding detects live witness-path rename/replacement but does not make filesystem/storage physically immutable",
            "valid ledger extension may advance a lagging pin after hard kill; another host/network namespace with the copied credential is outside this claim",
            "whole witness plus host-pin rollback remains an explicit counterexample",
            "no performance, energy, retained/incremental/dormant-compute, provider/network independence, merge, or CANON claim",
        ],
    }

    with tempfile.TemporaryDirectory(prefix="axm-wave125-") as td:
        b = Path(td)

        # Prerequisite: reproduce verifier PR #49 directly against untouched Wave 124.
        old, old_clone = b / "w124-original", b / "w124-clone"
        old_sock, old_clone_sock = b / "w124-original.sock", b / "w124-clone.sock"
        old_root = w123.initialize_witness_dir(old, "wave124-clone-prereq")
        old_fp = old_root["credential_fingerprint"]
        p_old = p_old_clone = None
        try:
            p_old, _ = launch(TOOL124, old, old_sock, b / "old-ready", b / "old-err")
            pa, pt = h("w124-prefix-a"), h("w124-prefix-t")
            w123.request(old_sock, proposal(pa, pt, "HOLD", False, "common-prefix"), old_fp)
            prefix = (old / "ledger.jsonl").read_bytes()
            shutil.copytree(old, old_clone, copy_function=shutil.copy2)
            p_old_clone, _ = launch(TOOL124, old_clone, old_clone_sock, b / "old-clone-ready", b / "old-clone-err")
            a, t = h("w124-fork-a"), h("w124-fork-t")
            commit = w123.request(old_sock, proposal(a, t, "COMMIT", True, ""), old_fp)["record"]
            reject = w123.request(old_clone_sock, proposal(a, t, "REJECT", True, "stable-fork"), old_fp)["record"]
            _, sec_a = w123.load_identity(old)
            _, sec_b = w123.load_identity(old_clone)
            la = w123.load_ledger(old, sec_a)
            lb = w123.load_ledger(old_clone, sec_b)
            check(
                report,
                "wave124_pr49_cloned_store_fork_reproduced",
                prefix == (old_clone / "ledger.jsonl").read_bytes().splitlines(keepends=True)[0]
                and commit["seq"] == reject["seq"] == 2
                and commit["prev_record_sha"] == reject["prev_record_sha"]
                and commit["record_sha"] != reject["record_sha"]
                and len(la) == len(lb) == 2,
                {"commit": commit, "reject": reject, "records_original": len(la), "records_clone": len(lb)},
            )
        finally:
            stop(p_old_clone, old_clone_sock)
            stop(p_old, old_sock)

        # Wave 125 primary: one credential identity cannot be live twice even if
        # the whole witness directory is cloned to another inode/path.
        wd, stale_clone = b / "w125-original", b / "w125-stale-clone"
        sock, clone_sock = b / "w125.sock", b / "w125-clone.sock"
        root = w123.initialize_witness_dir(wd, "wave125-main")
        fp = root["credential_fingerprint"]
        primary = None
        local = b / "local.jsonl"
        try:
            primary, info = launch(TOOL125, wd, sock, b / "ready-primary", b / "err-primary")
            ping0 = w123.request(sock, {"op": "ping"}, fp)
            check(
                report,
                "kernel_credential_lease_and_external_pin_active",
                info.get("credential_host_lease") is True
                and ping0.get("credential_host_lease") is True
                and ping0.get("host_pin_seq") == 0
                and w125.host_pin_path(fp).exists(),
                {"ready": info, "ping": ping0, "pin": str(w125.host_pin_path(fp))},
            )

            pa, pt = h("w125-prefix-a"), h("w125-prefix-t")
            w123.request(sock, proposal(pa, pt, "HOLD", False, "common-prefix"), fp)
            prefix_bytes = (wd / "ledger.jsonl").read_bytes()
            shutil.copytree(wd, stale_clone, copy_function=shutil.copy2)

            clone_fail = launch_expect_fail(
                TOOL125, stale_clone, clone_sock, b / "ready-clone-live", b / "err-clone-live"
            )
            alive = w123.request(sock, {"op": "ping"}, fp)
            check(
                report,
                "live_cloned_store_is_rejected_by_credential_identity_not_path_inode",
                clone_fail["returncode"] == 2
                and not clone_fail["ready"]
                and "witness-credential-already-live-on-host" in clone_fail["error"]
                and alive["pid"] == primary.pid
                and (stale_clone / "ledger.jsonl").read_bytes() == prefix_bytes,
                {"clone_start": clone_fail, "original_ping": alive},
            )

            a, t = h("w125-current-a"), h("w125-current-t")
            w123.decide_and_publish(sock, fp, local, a, t, "COMMIT", True, "")
            current = w123.status(sock, fp, local, a)
            pin_after_commit = json.loads(w125.host_pin_path(fp).read_text())
            check(
                report,
                "terminal_commit_advances_external_high_water_pin",
                current["status"] == "AUTHORITATIVE_PROCESS_WITNESS_COMMIT"
                and pin_after_commit["last_seq"] == 2
                and pin_after_commit["last_record_sha"] == current["witness_record"]["record_sha"],
                {"status": current, "pin": pin_after_commit},
            )

            established = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            established.settimeout(3)
            established.connect(str(sock))
            current_saved = b / "w125-current-saved"
            os.rename(wd, current_saved)
            shutil.copytree(stale_clone, wd, copy_function=shutil.copy2)
            established.sendall(w123.canonical({"op": "ping"}) + b"\n")
            replaced_reply = recv_line(established)
            established.close()
            replacement_live_fail = launch_expect_fail(
                TOOL125, wd, b / "w125-swapped.sock", b / "ready-swapped-live", b / "err-swapped-live"
            )
            check(
                report,
                "live_directory_replacement_fails_closed_and_clone_still_cannot_serve",
                replaced_reply.get("ok") is False
                and "witness-store-path-identity-mismatch" in replaced_reply.get("error", "")
                and "witness-credential-already-live-on-host" in replacement_live_fail["error"],
                {"established_reply": replaced_reply, "clone_start": replacement_live_fail},
            )

            stop(primary, sock)
            primary = None
            stale_after_exit = launch_expect_fail(
                TOOL125, wd, b / "w125-stale-after-exit.sock",
                b / "ready-stale-after-exit", b / "err-stale-after-exit"
            )
            check(
                report,
                "stale_clone_rejected_after_original_exit_by_host_pin",
                "host-pin-ahead-of-witness-store" in stale_after_exit["error"],
                stale_after_exit,
            )

            shutil.rmtree(wd)
            os.rename(current_saved, wd)
            primary, restored_info = launch(
                TOOL125, wd, sock, b / "ready-restored-current", b / "err-restored-current"
            )
            restored = w123.status(sock, fp, local, a)
            check(
                report,
                "exact_current_store_restarts_and_preserves_authority",
                restored_info["host_pin_seq"] == 2
                and restored["status"] == "AUTHORITATIVE_PROCESS_WITNESS_COMMIT",
                {"ready": restored_info, "status": restored},
            )

            current_clone = b / "w125-current-clone"
            shutil.copytree(wd, current_clone, copy_function=shutil.copy2)
            live_current_clone = launch_expect_fail(
                TOOL125, current_clone, b / "w125-current-clone-live.sock",
                b / "ready-current-clone-live", b / "err-current-clone-live"
            )
            stop(primary, sock)
            primary = None
            clone_proc, clone_info = launch(
                TOOL125, current_clone, b / "w125-current-clone-after.sock",
                b / "ready-current-clone-after", b / "err-current-clone-after"
            )
            try:
                clone_status = w123.status(b / "w125-current-clone-after.sock", fp, local, a)
                check(
                    report,
                    "up_to_date_clone_can_take_over_only_after_lease_release",
                    "witness-credential-already-live-on-host" in live_current_clone["error"]
                    and clone_info["host_pin_seq"] == 2
                    and clone_status["status"] == "AUTHORITATIVE_PROCESS_WITNESS_COMMIT",
                    {"live_attempt": live_current_clone, "takeover": clone_info, "status": clone_status},
                )
            finally:
                stop(clone_proc, b / "w125-current-clone-after.sock")
        finally:
            stop(primary, sock)
            cleanup_pin(fp)

        # Real SIGKILL after ledger fsync but before host-pin publication.
        crash_wd, crash_sock = b / "crash-witness", b / "crash.sock"
        crash_root = w123.initialize_witness_dir(crash_wd, "wave125-crash-recovery")
        crash_fp = crash_root["credential_fingerprint"]
        crash_proc = None
        try:
            crash_proc, _ = launch(
                TOOL125, crash_wd, crash_sock, b / "ready-crash", b / "err-crash", allow_fault=True
            )
            crash_local = b / "crash-local.jsonl"
            ca, ct = h("crash-a"), h("crash-t")
            marker = b / "after-ledger.marker"
            client = subprocess.Popen(
                [
                    sys.executable, str(TOOL125), "transact",
                    str(crash_sock), crash_fp, str(crash_local), ca, ct,
                    "COMMIT", "true", "",
                    "--fault", w125.FAULT_AFTER_LEDGER_BEFORE_PIN,
                    "--fault-marker", str(marker),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            wait_file(marker, crash_proc)
            stale_pin = json.loads(w125.host_pin_path(crash_fp).read_text())
            _, crash_secret = w123.load_identity(crash_wd)
            ledger_after_fsync = w123.load_ledger(crash_wd, crash_secret)
            hard_kill(crash_proc)
            crash_proc = None
            try:
                client.wait(timeout=3)
            except subprocess.TimeoutExpired:
                client.kill()
                client.wait(timeout=2)

            crash_proc, recovered_ready = launch(
                TOOL125, crash_wd, crash_sock, b / "ready-crash-recover", b / "err-crash-recover"
            )
            expected = w123.proposal_sha(ca, ct, "COMMIT", True, "")
            before_recover = w123.status(crash_sock, crash_fp, crash_local, ca)
            w123.recover_exact(crash_sock, crash_fp, crash_local, ca, ct, expected)
            after_recover = w123.status(crash_sock, crash_fp, crash_local, ca)
            advanced_pin = json.loads(w125.host_pin_path(crash_fp).read_text())
            check(
                report,
                "sigkill_after_ledger_fsync_recovers_exact_valid_extension_without_fork",
                stale_pin["last_seq"] == 0
                and len(ledger_after_fsync) == 1
                and recovered_ready["host_pin_seq"] == 1
                and advanced_pin["last_seq"] == 1
                and before_recover["status"] == "HOLD_WITNESS_AHEAD"
                and after_recover["status"] == "AUTHORITATIVE_PROCESS_WITNESS_COMMIT",
                {
                    "pin_before_kill": stale_pin,
                    "ready_after_restart": recovered_ready,
                    "pin_after_restart": advanced_pin,
                    "status_before_local_recovery": before_recover,
                    "status_after_local_recovery": after_recover,
                },
            )

            stop(crash_proc, crash_sock)
            crash_proc = None
            pin_path = w125.host_pin_path(crash_fp)
            good_pin = pin_path.read_bytes()
            pin_path.write_bytes(b"{broken")
            corrupt = launch_expect_fail(
                TOOL125, crash_wd, crash_sock, b / "ready-corrupt-pin", b / "err-corrupt-pin"
            )
            pin_path.write_bytes(good_pin)
            crash_proc, _ = launch(
                TOOL125, crash_wd, crash_sock, b / "ready-pin-restored", b / "err-pin-restored"
            )
            repaired_status = w123.status(crash_sock, crash_fp, crash_local, ca)
            check(
                report,
                "host_pin_corruption_fails_closed_without_silent_rewrite",
                "host-pin-json-corrupt" in corrupt["error"]
                and repaired_status["status"] == "AUTHORITATIVE_PROCESS_WITNESS_COMMIT",
                {"corrupt_start": corrupt, "restored_status": repaired_status},
            )
        finally:
            stop(crash_proc, crash_sock)
            cleanup_pin(crash_fp)

        # Explicit surviving counterexample: roll back both witness and external pin.
        roll_wd, roll_sock = b / "rollback-witness", b / "rollback.sock"
        roll_root = w123.initialize_witness_dir(roll_wd, "wave125-whole-state-rollback")
        roll_fp = roll_root["credential_fingerprint"]
        roll_proc = None
        try:
            roll_proc, _ = launch(TOOL125, roll_wd, roll_sock, b / "ready-roll", b / "err-roll")
            rollback_store = b / "rollback-snapshot"
            shutil.copytree(roll_wd, rollback_store, copy_function=shutil.copy2)
            rollback_pin = w125.host_pin_path(roll_fp).read_bytes()

            ra, rt = h("rollback-a"), h("rollback-t")
            roll_local = b / "rollback-local.jsonl"
            w123.decide_and_publish(roll_sock, roll_fp, roll_local, ra, rt, "COMMIT", True, "")
            accepted_newer = w123.status(roll_sock, roll_fp, roll_local, ra)
            stop(roll_proc, roll_sock)
            roll_proc = None

            shutil.rmtree(roll_wd)
            shutil.copytree(rollback_store, roll_wd, copy_function=shutil.copy2)
            w125.host_pin_path(roll_fp).write_bytes(rollback_pin)

            roll_proc, rolled_info = launch(
                TOOL125, roll_wd, roll_sock, b / "ready-rolled", b / "err-rolled"
            )
            rolled_summary = w123.request(roll_sock, {"op": "summary"}, roll_fp)
            check(
                report,
                "whole_witness_plus_host_pin_rollback_remains_counterexample",
                accepted_newer["status"] == "AUTHORITATIVE_PROCESS_WITNESS_COMMIT"
                and rolled_info["host_pin_seq"] == 0
                and rolled_summary["last_seq"] == 0
                and rolled_summary["terminal_records"] == [],
                {
                    "newer_before_rollback": accepted_newer,
                    "rolled_ready": rolled_info,
                    "rolled_summary": rolled_summary,
                },
            )
        finally:
            stop(roll_proc, roll_sock)
            cleanup_pin(roll_fp)

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
