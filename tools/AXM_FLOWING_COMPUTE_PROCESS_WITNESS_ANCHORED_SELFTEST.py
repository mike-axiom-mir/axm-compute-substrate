#!/usr/bin/env python3
"""Wave 126 adversarial self-test: separate monotonic anchor process/store."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS as w
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_HOSTBOUND as w125
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ANCHORED as w126

TOOL = Path(w126.__file__).resolve()


def h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def proposal(authority: str, transition: str, decision: str,
             stable: bool, reason: str) -> dict:
    return {
        "op": "decide",
        "authority_sha": authority,
        "transition_sha": transition,
        "proposal_sha": w.proposal_sha(authority, transition, decision, stable, reason),
        "decision": decision,
        "stable": stable,
        "reason": reason,
    }


def check(report: dict, name: str, ok: bool, detail=None) -> None:
    report["controls"].append({"name": name, "ok": bool(ok), "detail": detail})
    if not ok:
        report["failed"] += 1


def wait_file(path: Path, proc: subprocess.Popen | None = None,
              timeout: float = 8.0) -> None:
    end = time.time() + timeout
    while time.time() < end:
        if path.exists():
            return
        if proc is not None and proc.poll() is not None:
            raise RuntimeError(f"process-exited-before-marker:{proc.returncode}")
        time.sleep(0.02)
    raise TimeoutError(f"marker-timeout:{path}")


def launch_anchor(anchor_dir: Path, sock: Path, ready: Path, error: Path,
                  allow_fault: bool = False) -> tuple[subprocess.Popen, dict]:
    for p in (ready, error):
        if p.exists():
            p.unlink()
    cmd = [
        sys.executable, str(TOOL), "serve-anchor", str(anchor_dir), str(sock),
        "--ready-file", str(ready), "--error-file", str(error),
    ]
    if allow_fault:
        cmd.append("--allow-fault-injection")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    wait_file(ready, proc)
    return proc, json.loads(ready.read_text())


def launch_witness(witness_dir: Path, sock: Path, anchor_sock: Path,
                   anchor_fp: str, ready: Path, error: Path,
                   allow_fault: bool = False) -> tuple[subprocess.Popen, dict]:
    for p in (ready, error):
        if p.exists():
            p.unlink()
    cmd = [
        sys.executable, str(TOOL), "serve-witness", str(witness_dir), str(sock),
        str(anchor_sock), anchor_fp,
        "--ready-file", str(ready), "--error-file", str(error),
    ]
    if allow_fault:
        cmd.append("--allow-fault-injection")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    wait_file(ready, proc)
    return proc, json.loads(ready.read_text())


def _launch_expect_fail(cmd: list[str], ready: Path, error: Path,
                        timeout: float = 5.0) -> dict:
    for p in (ready, error):
        if p.exists():
            p.unlink()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
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


def launch_witness_expect_fail(witness_dir: Path, sock: Path, anchor_sock: Path,
                               anchor_fp: str, ready: Path, error: Path) -> dict:
    return _launch_expect_fail([
        sys.executable, str(TOOL), "serve-witness", str(witness_dir), str(sock),
        str(anchor_sock), anchor_fp, "--ready-file", str(ready),
        "--error-file", str(error),
    ], ready, error)


def launch_anchor_expect_fail(anchor_dir: Path, sock: Path,
                              ready: Path, error: Path) -> dict:
    return _launch_expect_fail([
        sys.executable, str(TOOL), "serve-anchor", str(anchor_dir), str(sock),
        "--ready-file", str(ready), "--error-file", str(error),
    ], ready, error)


def stop_witness(proc: subprocess.Popen | None, sock: Path) -> None:
    if proc is None:
        return
    if proc.poll() is None:
        try:
            w.request(sock, {"op": "stop"}, timeout=1.0)
        except Exception:
            pass
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)


def stop_anchor(proc: subprocess.Popen | None, sock: Path) -> None:
    if proc is None:
        return
    if proc.poll() is None:
        try:
            w126.anchor_request(sock, {"op": "stop"}, timeout=1.0)
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


def run() -> dict:
    report = {
        "wave": 126,
        "title": "separate monotonic anchor process/store",
        "source": w126.SOURCE,
        "controls": [],
        "failed": 0,
        "truth_boundary": [
            "same Linux host/filesystem with separate witness and anchor OS processes and durable stores",
            "witness startup requires an externally pinned exact anchor credential fingerprint; it does not bootstrap a replacement anchor",
            "anchor independently verifies the exact witness HMAC chain and mirrors it append-only before witness results are considered reconciled",
            "same-network-namespace anchor clones are serialized by a kernel abstract-socket credential lease",
            "whole witness plus anchor rollback/replacement remains an explicit counterexample",
            "another Linux network namespace/host, external-anchor-pin rollback, device/controller/kernel failure, credential compromise, and mixed older writers remain unproved",
            "no performance, energy, retained/incremental/dormant-compute, provider independence, merge, or CANON claim",
        ],
    }

    with tempfile.TemporaryDirectory(prefix="axm-wave126-") as td:
        b = Path(td)
        wd = b / "witness"
        anchor = b / "anchor"
        witness_sock = b / "witness.sock"
        anchor_sock = b / "anchor.sock"
        local = b / "local.jsonl"

        witness_root = w.initialize_witness_dir(wd, "wave126-main")
        fp = witness_root["credential_fingerprint"]
        anchor_root = w126.initialize_anchor_dir(anchor, wd, "wave126-anchor-main")
        anchor_fp = anchor_root["anchor_credential_fingerprint"]

        p_anchor = p_witness = None
        namespace_backup = None
        namespace_path = w125.host_namespace_path()
        try:
            p_anchor, ainfo = launch_anchor(
                anchor, anchor_sock, b / "anchor-ready", b / "anchor-error"
            )
            p_witness, winfo = launch_witness(
                wd, witness_sock, anchor_sock, anchor_fp,
                b / "witness-ready", b / "witness-error", allow_fault=True,
            )
            ping = w.request(witness_sock, {"op": "ping"}, fp)
            check(
                report,
                "separate_anchor_process_and_exact_identity_pin_active",
                p_anchor.pid != p_witness.pid
                and ainfo.get("anchor_credential_fingerprint") == anchor_fp
                and winfo.get("anchor_credential_fingerprint") == anchor_fp
                and ping.get("anchor_credential_fingerprint") == anchor_fp
                and ainfo.get("anchor_seq") == winfo.get("anchor_seq") == 0,
                {"anchor_ready": ainfo, "witness_ready": winfo, "ping": ping},
            )

            # Create one genuine common HOLD prefix, then preserve exact rollback snapshots.
            pa, pt = h("wave126-prefix-a"), h("wave126-prefix-t")
            w.request(witness_sock, proposal(pa, pt, "HOLD", False, "common-prefix"), fp)
            stale_witness = b / "stale-witness"
            stale_anchor = b / "stale-anchor"
            shutil.copytree(wd, stale_witness, copy_function=shutil.copy2)
            shutil.copytree(anchor, stale_anchor, copy_function=shutil.copy2)
            anchor_after_prefix = w126.anchor_request(
                anchor_sock, {"op": "summary"}, anchor_fp
            )
            check(
                report,
                "hold_prefix_is_mirrored_exactly_into_anchor",
                anchor_after_prefix.get("anchor_seq") == 1
                and anchor_after_prefix.get("witness_record_sha")
                == w.load_ledger(wd, w.load_identity(wd)[1])[-1]["record_sha"],
                anchor_after_prefix,
            )

            # Advance the current world with a genuine terminal COMMIT and local receipt.
            authority, transition = h("wave126-current-a"), h("wave126-current-t")
            result = w.decide_and_publish(
                witness_sock, fp, local, authority, transition,
                "COMMIT", True, "",
            )
            status = w.status(witness_sock, fp, local, authority)
            anchor_current = w126.anchor_request(anchor_sock, {"op": "summary"}, anchor_fp)
            check(
                report,
                "current_commit_reaches_witness_anchor_and_local_receipt",
                result["record"]["seq"] == 2
                and anchor_current.get("anchor_seq") == 2
                and status.get("status") == "AUTHORITATIVE_PROCESS_WITNESS_COMMIT",
                {"result": result, "anchor": anchor_current, "status": status},
            )

            # PR #50 boundary repair: replace only Wave 125's public host-pin namespace.
            # Wave 126 does not consult that mutable namespace, and the stale witness is
            # still rejected by the independent anchor's newer sequence.
            stop_witness(p_witness, witness_sock)
            p_witness = None
            if namespace_path.exists():
                namespace_backup = namespace_path.with_name(
                    namespace_path.name + f"-wave126-backup-{os.getpid()}"
                )
                if namespace_backup.exists():
                    shutil.rmtree(namespace_backup)
                os.rename(namespace_path, namespace_backup)
            os.mkdir(namespace_path, 0o700)
            stale_fail = launch_witness_expect_fail(
                stale_witness, b / "stale-witness.sock", anchor_sock, anchor_fp,
                b / "stale-witness-ready", b / "stale-witness-error",
            )
            check(
                report,
                "wave125_host_pin_namespace_replacement_does_not_reopen_stale_witness",
                stale_fail["returncode"] == 2
                and not stale_fail["ready"]
                and "anchor-ahead-of-witness-store" in stale_fail["error"],
                stale_fail,
            )
            shutil.rmtree(namespace_path)
            if namespace_backup is not None:
                os.rename(namespace_backup, namespace_path)
                namespace_backup = None

            p_witness, _ = launch_witness(
                wd, witness_sock, anchor_sock, anchor_fp,
                b / "witness-ready-restart", b / "witness-error-restart",
                allow_fault=True,
            )
            check(
                report,
                "current_world_restarts_against_same_anchor_after_namespace_attack",
                w.status(witness_sock, fp, local, authority).get("status")
                == "AUTHORITATIVE_PROCESS_WITNESS_COMMIT",
                w126.anchor_request(anchor_sock, {"op": "summary"}, anchor_fp),
            )

            wrong_fp = "f" * 64 if anchor_fp != "f" * 64 else "e" * 64
            stop_witness(p_witness, witness_sock)
            p_witness = None
            wrong_pin = launch_witness_expect_fail(
                wd, b / "wrong-pin.sock", anchor_sock, wrong_fp,
                b / "wrong-pin-ready", b / "wrong-pin-error",
            )
            check(
                report,
                "wrong_external_anchor_fingerprint_fails_closed",
                wrong_pin["returncode"] == 2
                and "anchor-credential-fingerprint-mismatch" in wrong_pin["error"],
                wrong_pin,
            )

            stop_anchor(p_anchor, anchor_sock)
            p_anchor = None
            anchor_down = launch_witness_expect_fail(
                wd, b / "anchor-down.sock", anchor_sock, anchor_fp,
                b / "anchor-down-ready", b / "anchor-down-error",
            )
            check(
                report,
                "missing_anchor_cannot_silently_bootstrap_or_serve",
                anchor_down["returncode"] == 2
                and not anchor_down["ready"],
                anchor_down,
            )

            p_anchor, _ = launch_anchor(
                anchor, anchor_sock, b / "anchor-ready-2", b / "anchor-error-2"
            )
            p_witness, _ = launch_witness(
                wd, witness_sock, anchor_sock, anchor_fp,
                b / "witness-ready-2", b / "witness-error-2", allow_fault=True,
            )

            # Hard-kill after witness fsync but before anchor publication. Restart must
            # reconcile the exact already-authenticated witness suffix into the anchor.
            crash_a, crash_t = h("wave126-crash-a"), h("wave126-crash-t")
            marker = b / "after-witness-before-anchor.marker"
            client = subprocess.Popen([
                sys.executable, str(TOOL), "transact", str(witness_sock), fp,
                str(local), crash_a, crash_t, "COMMIT", "true", "",
                "--fault", w126.FAULT_AFTER_WITNESS_BEFORE_ANCHOR,
                "--fault-marker", str(marker),
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            wait_file(marker, p_witness)
            hard_kill(p_witness)
            p_witness = None
            try:
                client.wait(timeout=3)
            except subprocess.TimeoutExpired:
                client.kill(); client.wait(timeout=2)
            anchor_before_recovery = w126.anchor_request(
                anchor_sock, {"op": "summary"}, anchor_fp
            )
            p_witness, _ = launch_witness(
                wd, witness_sock, anchor_sock, anchor_fp,
                b / "witness-ready-3", b / "witness-error-3", allow_fault=True,
            )
            pre_recover = w.status(witness_sock, fp, local, crash_a)
            psha = w.proposal_sha(crash_a, crash_t, "COMMIT", True, "")
            recovered = w.recover_exact(
                witness_sock, fp, local, crash_a, crash_t, psha
            )
            post_recover = w.status(witness_sock, fp, local, crash_a)
            anchor_after_recovery = w126.anchor_request(
                anchor_sock, {"op": "summary"}, anchor_fp
            )
            check(
                report,
                "sigkill_after_witness_before_anchor_recovers_exact_suffix",
                anchor_before_recovery.get("anchor_seq") == 2
                and pre_recover.get("status") == "HOLD_WITNESS_AHEAD"
                and recovered.get("recovered") is True
                and post_recover.get("status") == "AUTHORITATIVE_PROCESS_WITNESS_COMMIT"
                and anchor_after_recovery.get("anchor_seq") == 3,
                {
                    "anchor_before": anchor_before_recovery,
                    "pre_recover": pre_recover,
                    "recovered": recovered,
                    "post_recover": post_recover,
                    "anchor_after": anchor_after_recovery,
                },
            )

            # A byte-identical live anchor clone cannot serve concurrently in the same
            # Linux network namespace because the anchor credential owns a kernel lease.
            live_anchor_clone = b / "live-anchor-clone"
            shutil.copytree(anchor, live_anchor_clone, copy_function=shutil.copy2)
            clone_fail = launch_anchor_expect_fail(
                live_anchor_clone, b / "live-anchor-clone.sock",
                b / "live-anchor-clone-ready", b / "live-anchor-clone-error",
            )
            check(
                report,
                "same_namespace_live_anchor_clone_is_rejected",
                clone_fail["returncode"] == 2
                and "anchor-credential-already-live-on-host" in clone_fail["error"],
                clone_fail,
            )

            # Corrupted anchor history is not repaired from the witness by guesswork.
            stop_witness(p_witness, witness_sock)
            p_witness = None
            stop_anchor(p_anchor, anchor_sock)
            p_anchor = None
            corrupt_anchor = b / "corrupt-anchor"
            shutil.copytree(anchor, corrupt_anchor, copy_function=shutil.copy2)
            ledger = corrupt_anchor / "ledger.jsonl"
            raw = ledger.read_bytes()
            ledger.write_bytes(raw[:-1] if raw else b"x")
            corrupt_fail = launch_anchor_expect_fail(
                corrupt_anchor, b / "corrupt-anchor.sock",
                b / "corrupt-anchor-ready", b / "corrupt-anchor-error",
            )
            check(
                report,
                "corrupt_anchor_ledger_fails_closed",
                corrupt_fail["returncode"] == 2
                and "anchor-ledger-truncated-tail" in corrupt_fail["error"],
                corrupt_fail,
            )

            # Explicit counterexample: if both domains are rolled back together to the
            # older genuine prefix, the older world can serve again. Keep this visible.
            stale_anchor_sock = b / "stale-anchor.sock"
            p_stale_anchor, stale_ainfo = launch_anchor(
                stale_anchor, stale_anchor_sock,
                b / "stale-anchor-ready", b / "stale-anchor-error",
            )
            p_stale_witness = None
            try:
                p_stale_witness, stale_winfo = launch_witness(
                    stale_witness, b / "stale-world.sock", stale_anchor_sock, anchor_fp,
                    b / "stale-world-ready", b / "stale-world-error",
                )
                stale_ping = w.request(
                    b / "stale-world.sock", {"op": "ping"}, fp
                )
                check(
                    report,
                    "counterexample_whole_witness_plus_anchor_rollback_still_serves_old_prefix",
                    stale_ainfo.get("anchor_seq") == 1
                    and stale_winfo.get("anchor_seq") == 1
                    and stale_ping.get("anchor_seq") == 1,
                    {
                        "anchor_ready": stale_ainfo,
                        "witness_ready": stale_winfo,
                        "ping": stale_ping,
                        "expected_counterexample": True,
                    },
                )
            finally:
                stop_witness(p_stale_witness, b / "stale-world.sock")
                stop_anchor(p_stale_anchor, stale_anchor_sock)

            # Restore the actual current domains and prove the newer current state still exists.
            p_anchor, _ = launch_anchor(
                anchor, anchor_sock, b / "anchor-ready-final", b / "anchor-error-final"
            )
            p_witness, _ = launch_witness(
                wd, witness_sock, anchor_sock, anchor_fp,
                b / "witness-ready-final", b / "witness-error-final",
            )
            final_anchor = w126.anchor_request(anchor_sock, {"op": "summary"}, anchor_fp)
            final_status = w.status(witness_sock, fp, local, crash_a)
            check(
                report,
                "restoring_current_anchor_restores_newer_authority",
                final_anchor.get("anchor_seq") == 3
                and final_status.get("status") == "AUTHORITATIVE_PROCESS_WITNESS_COMMIT",
                {"anchor": final_anchor, "status": final_status},
            )
        finally:
            stop_witness(p_witness, witness_sock)
            stop_anchor(p_anchor, anchor_sock)
            if namespace_path.exists() and namespace_backup is not None:
                shutil.rmtree(namespace_path)
            if namespace_backup is not None and namespace_backup.exists():
                os.rename(namespace_backup, namespace_path)

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
