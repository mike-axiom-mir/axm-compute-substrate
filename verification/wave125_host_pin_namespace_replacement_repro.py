#!/usr/bin/env python3
"""Independent adversarial verifier for Wave 125.

This lane does two things without modifying builder code:
1. exercises the untested hard-kill boundary after host-pin publication but before reply;
2. reproduces the explicitly untrusted host-pin namespace replacement boundary more narrowly
   than the builder's whole-witness+pin rollback counterexample.

Expected verdict for (2): FAIL_HOST_PIN_NAMESPACE_REPLACEMENT_REOPENS_STALE_CLONE.
This is a boundary failure, not a falsification of Wave 125's stated trusted-host-pin-namespace claim.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS as w123
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_HOSTBOUND as w125
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_HOSTBOUND_SELFTEST as t125

TOOL125 = Path(w125.__file__).resolve()


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
    if proc.poll() is None and (error.exists() or ready.exists()):
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
    elif proc.poll() is None:
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


def clean_pin(fp: str) -> None:
    try:
        w125.host_pin_path(fp).unlink()
    except FileNotFoundError:
        pass


def check(report: dict, name: str, ok: bool, detail: dict) -> None:
    report["controls"].append({"name": name, "ok": bool(ok), "detail": detail})
    if not ok:
        report["failed"] += 1


def hard_kill(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        os.kill(proc.pid, signal.SIGKILL)
    proc.wait(timeout=3)


def test_kill_after_pin_before_reply(base: Path, report: dict) -> None:
    wd = base / "pin-before-reply-witness"
    sock = base / "pin-before-reply.sock"
    root = w123.initialize_witness_dir(wd, "wave125-verifier-pin-before-reply")
    fp = root["credential_fingerprint"]
    local = base / "pin-before-reply-local.jsonl"
    proc = None
    client = None
    try:
        proc, _ = t125.launch(
            TOOL125, wd, sock,
            base / "pin-before-reply-ready",
            base / "pin-before-reply-error",
            allow_fault=True,
        )
        authority = t125.h("pin-before-reply-authority")
        transition = t125.h("pin-before-reply-transition")
        marker = base / "pin-before-reply.marker"
        client = subprocess.Popen(
            [
                sys.executable, str(TOOL125), "transact",
                str(sock), fp, str(local), authority, transition,
                "COMMIT", "true", "",
                "--fault", w125.FAULT_AFTER_PIN_BEFORE_REPLY,
                "--fault-marker", str(marker),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        t125.wait_file(marker, proc)
        pin_before_kill = json.loads(w125.host_pin_path(fp).read_text())
        _, secret = w123.load_identity(wd)
        ledger_before_kill = w123.load_ledger(wd, secret)
        hard_kill(proc)
        proc = None
        try:
            client.wait(timeout=3)
        except subprocess.TimeoutExpired:
            client.kill()
            client.wait(timeout=2)

        proc, ready = t125.launch(
            TOOL125, wd, sock,
            base / "pin-before-reply-restart-ready",
            base / "pin-before-reply-restart-error",
        )
        before = w123.status(sock, fp, local, authority)
        proposal_sha = w123.proposal_sha(authority, transition, "COMMIT", True, "")
        recovered = w123.recover_exact(sock, fp, local, authority, transition, proposal_sha)
        after = w123.status(sock, fp, local, authority)
        check(
            report,
            "sigkill_after_host_pin_before_reply_recovers_exact_receipt",
            pin_before_kill["last_seq"] == 1
            and len(ledger_before_kill) == 1
            and ready["host_pin_seq"] == 1
            and before["status"] == "HOLD_WITNESS_AHEAD"
            and recovered.get("recovered") is True
            and after["status"] == "AUTHORITATIVE_PROCESS_WITNESS_COMMIT",
            {
                "pin_before_kill": pin_before_kill,
                "ledger_records_before_kill": len(ledger_before_kill),
                "ready_after_restart": ready,
                "status_before_recovery": before,
                "recover_exact": recovered,
                "status_after_recovery": after,
            },
        )
    finally:
        if client is not None and client.poll() is None:
            client.kill()
            client.wait(timeout=2)
        t125.stop(proc, sock)
        clean_pin(fp)


def test_host_namespace_replacement(base: Path, report: dict) -> None:
    wd = base / "namespace-original"
    stale = base / "namespace-stale-clone"
    sock = base / "namespace-original.sock"
    stale_sock = base / "namespace-stale.sock"
    root = w123.initialize_witness_dir(wd, "wave125-verifier-host-namespace")
    fp = root["credential_fingerprint"]
    local = base / "namespace-local.jsonl"
    primary = stale_proc = restored_proc = None
    host_ns = w125.host_namespace_path()
    backup_ns = host_ns.with_name(host_ns.name + f".verifier-backup-{os.getpid()}")
    namespace_swapped = False
    try:
        primary, initial_ready = t125.launch(
            TOOL125, wd, sock, base / "namespace-ready", base / "namespace-error"
        )
        # Snapshot a genuine old prefix while the credential and host pin are valid.
        prefix_authority = t125.h("namespace-prefix-authority")
        prefix_transition = t125.h("namespace-prefix-transition")
        w123.request(
            sock,
            t125.proposal(prefix_authority, prefix_transition, "HOLD", False, "common-prefix"),
            fp,
        )
        shutil.copytree(wd, stale, copy_function=shutil.copy2)
        stale_prefix_summary = w123.request(sock, {"op": "summary"}, fp)

        authority = t125.h("namespace-newer-authority")
        transition = t125.h("namespace-newer-transition")
        w123.decide_and_publish(sock, fp, local, authority, transition, "COMMIT", True, "")
        accepted = w123.status(sock, fp, local, authority)
        pin_current = json.loads(w125.host_pin_path(fp).read_text())

        # Replace only the *pathname* of the trusted host-pin namespace with a new empty
        # same-owner/mode directory. The live server continues through its already-open fd.
        if backup_ns.exists():
            raise RuntimeError(f"backup namespace path unexpectedly exists:{backup_ns}")
        os.rename(host_ns, backup_ns)
        os.mkdir(host_ns, 0o700)
        namespace_swapped = True
        live_after_swap = w123.request(sock, {"op": "ping"}, fp)

        # Release the kernel credential lease. The current witness store remains intact;
        # only the host-pin namespace pathname has been replaced.
        t125.stop(primary, sock)
        primary = None

        # The stale cloned witness can now bootstrap a fresh pin in the replacement namespace.
        stale_proc, stale_ready = t125.launch(
            TOOL125, stale, stale_sock,
            base / "namespace-stale-ready", base / "namespace-stale-error"
        )
        stale_summary = w123.request(stale_sock, {"op": "summary"}, fp)
        fresh_pin = json.loads(w125.host_pin_path(fp).read_text())

        failure_reproduced = (
            initial_ready["host_pin_seq"] == 0
            and stale_prefix_summary["last_seq"] == 1
            and accepted["status"] == "AUTHORITATIVE_PROCESS_WITNESS_COMMIT"
            and pin_current["last_seq"] == 2
            and live_after_swap["host_pin_seq"] == 2
            and stale_ready["host_pin_seq"] == 1
            and stale_summary["last_seq"] == 1
            and stale_summary["terminal_records"] == []
            and fresh_pin["last_seq"] == 1
        )
        check(
            report,
            "FAIL_HOST_PIN_NAMESPACE_REPLACEMENT_REOPENS_STALE_CLONE",
            failure_reproduced,
            {
                "accepted_newer_status": accepted,
                "old_host_pin_before_namespace_swap": pin_current,
                "live_server_after_namespace_path_swap": live_after_swap,
                "stale_clone_ready_after_primary_exit": stale_ready,
                "stale_clone_summary": stale_summary,
                "new_replacement_namespace_pin": fresh_pin,
                "current_original_store_still_exists": wd.exists(),
                "old_host_namespace_backup_still_exists": backup_ns.exists(),
            },
        )

        # Stop stale world, restore the exact original host namespace, and prove the current
        # witness is still recoverable/authoritative. This bounds the counterexample to trust-root
        # namespace substitution, not corruption of the current witness ledger itself.
        t125.stop(stale_proc, stale_sock)
        stale_proc = None
        try:
            w125.host_pin_path(fp).unlink()
        except FileNotFoundError:
            pass
        os.rmdir(host_ns)
        os.rename(backup_ns, host_ns)
        namespace_swapped = False
        restored_proc, restored_ready = t125.launch(
            TOOL125, wd, sock,
            base / "namespace-restored-ready", base / "namespace-restored-error"
        )
        restored_status = w123.status(sock, fp, local, authority)
        check(
            report,
            "restoring_original_host_namespace_restores_newer_authority",
            restored_ready["host_pin_seq"] == 2
            and restored_status["status"] == "AUTHORITATIVE_PROCESS_WITNESS_COMMIT",
            {"ready": restored_ready, "status": restored_status},
        )
    finally:
        t125.stop(stale_proc, stale_sock)
        t125.stop(restored_proc, sock)
        t125.stop(primary, sock)
        if namespace_swapped:
            try:
                clean_pin(fp)
                os.rmdir(host_ns)
            except FileNotFoundError:
                pass
            if backup_ns.exists() and not host_ns.exists():
                os.rename(backup_ns, host_ns)
        clean_pin(fp)


def main() -> int:
    report = {
        "wave": 125,
        "verifier": "independent-adversarial",
        "builder_evidence_head": "f7c5d920a01acae729745aaf0e0b51f8cb928163",
        "builder_exact_ci_source": "d9b9621bd26f6bf981bfd0f8b51881aaf3f0c886",
        "controls": [],
        "failed": 0,
        "truth_boundary": [
            "does not rewrite builder evidence or claim CANON",
            "pin-before-reply test is same-host same-network-namespace only",
            "namespace replacement result attacks the trust boundary Wave 125 explicitly excludes",
            "no credential/HMAC/hash forgery and no modification of the accepted newer witness ledger",
            "no speed, energy, retained/incremental/dormant-compute, provider, or physical-finality claim",
        ],
    }
    with tempfile.TemporaryDirectory(prefix="axm-wave125-verifier-") as td:
        base = Path(td)
        test_kill_after_pin_before_reply(base, report)
        test_host_namespace_replacement(base, report)
    report["passed"] = len(report["controls"]) - report["failed"]
    print(json.dumps(report, indent=2, sort_keys=True))
    # Expected success means the resilience control survived AND the boundary failure reproduced.
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
