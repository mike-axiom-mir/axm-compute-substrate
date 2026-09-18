#!/usr/bin/env python3
"""Independent adversarial verifier for AXM Flowing Compute Wave 124.

Target: the Wave 124 lifetime flock is scoped to one witness-directory inode.
An exact byte-for-byte clone of a live witness store receives a different lock
inode while preserving the same witness credential and ledger prefix. Both
cooperating Wave 124 servers can therefore run at the same time and issue
contradictory terminal outcomes that are individually authenticated and whose
separate ledgers both remain valid.

This deliberately tests the cloned-store/directory-identity boundary that Wave
124 lists as its next gate. It does not claim the bounded same-directory repair
failed, and it does not forge credentials, hashes, signatures, or prior rows.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS as w123
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_EXCLUSIVE as w124

TOOL124 = Path(w124.__file__).resolve()


def h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def wait_file(path: Path, proc: subprocess.Popen, timeout: float = 8.0) -> None:
    end = time.time() + timeout
    while time.time() < end:
        if path.exists():
            return
        if proc.poll() is not None:
            raise RuntimeError(f"process-exited-before-marker:{proc.returncode}")
        time.sleep(0.02)
    raise TimeoutError(f"marker-timeout:{path}")


def launch(wd: Path, sock: Path, ready: Path, error: Path) -> tuple[subprocess.Popen, dict]:
    for p in (ready, error):
        if p.exists():
            p.unlink()
    proc = subprocess.Popen(
        [sys.executable, str(TOOL124), "serve", str(wd), str(sock),
         "--ready-file", str(ready), "--error-file", str(error)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    wait_file(ready, proc)
    return proc, json.loads(ready.read_text())


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


def req(authority: str, transition: str, decision: str, stable: bool, reason: str) -> dict:
    return {
        "op": "decide",
        "authority_sha": authority,
        "transition_sha": transition,
        "proposal_sha": w123.proposal_sha(authority, transition, decision, stable, reason),
        "decision": decision,
        "stable": stable,
        "reason": reason,
    }


def run() -> dict:
    report = {
        "verifier": "independent-wave124-cloned-store-fork",
        "builder_evidence_head": "27ccee01297feaa9dac169a00d6af456979f606b",
        "builder_tested_source": "959e4c46e7c2ecf8e2043ebaa177b696d7d35f31",
        "wave124_tool_blob": "d8ececaab8aedd3ca9543b36c5e90d9130d19905",
        "wave124_selftest_blob": "c2a916feebb3026a434cd0f25eb777efb0729bd4",
        "attack": "clone live witness store to a new directory inode and fork one pinned credential into two valid terminal histories",
        "counterexample_reproduced": False,
        "truth_boundary": [
            "same Linux host and cooperating Wave 124 servers",
            "exact witness credential and valid ledger prefix copied without modification",
            "no credential/hash/signature forgery and no prior-record rewrite",
            "tests the directory/inode-substitution and cloned-store boundary explicitly left open by Wave 124",
            "does not falsify Wave 124 same-directory flock exclusion",
            "no performance, energy, retained/incremental/dormant-compute, power/device, network/provider, merge, or CANON claim",
        ],
    }

    with tempfile.TemporaryDirectory(prefix="axm-wave124-clone-") as td:
        base = Path(td)
        original = base / "witness-original"
        clone = base / "witness-clone"
        sock_a = base / "witness-a.sock"
        sock_b = base / "witness-b.sock"
        root = w123.initialize_witness_dir(original, "wave124-clone-verifier")
        fp = root["credential_fingerprint"]
        proc_a = proc_b = None
        try:
            proc_a, info_a = launch(original, sock_a, base / "ready-a.json", base / "err-a.txt")

            # Give the live store a genuine authenticated prefix before cloning.
            pa, pt = h("wave124-clone-prefix-authority"), h("wave124-clone-prefix-transition")
            prefix_reason = "retriable-common-prefix"
            prefix = w123.request(sock_a, req(pa, pt, "HOLD", False, prefix_reason), fp)
            prefix_bytes = (original / "ledger.jsonl").read_bytes()
            if prefix["record"]["seq"] != 1:
                raise AssertionError("unexpected prefix sequence")

            # Copy the live store exactly. serve.lock bytes copy, but its kernel
            # lock does not: the clone has a new inode and can acquire its own flock.
            shutil.copytree(original, clone, copy_function=shutil.copy2)
            cloned_prefix_bytes = (clone / "ledger.jsonl").read_bytes()
            proc_b, info_b = launch(clone, sock_b, base / "ready-b.json", base / "err-b.txt")

            ping_a = w123.request(sock_a, {"op": "ping"}, fp)
            ping_b = w123.request(sock_b, {"op": "ping"}, fp)

            authority = h("wave124-cloned-fork-authority")
            transition = h("wave124-cloned-fork-transition")
            reject_reason = "stable-cloned-fork-reject"

            commit = w123.request(sock_a, req(authority, transition, "COMMIT", True, ""), fp)
            reject = w123.request(sock_b, req(authority, transition, "REJECT", True, reject_reason), fp)
            cr, rr = commit["record"], reject["record"]

            # Each history is internally valid when checked against the exact same
            # cloned credential. Unlike the Wave 123 shared-file race, neither
            # ledger needs to corrupt itself for the contradiction to persist.
            _, secret_a = w123.load_identity(original)
            _, secret_b = w123.load_identity(clone)
            valid_a = w123.load_ledger(original, secret_a)
            valid_b = w123.load_ledger(clone, secret_b)

            local_a = base / "local-a.jsonl"
            local_b = base / "local-b.jsonl"
            w123.append_local_receipt(local_a, cr, fp)
            w123.append_local_receipt(local_b, rr, fp)
            local_a_valid = len(w123.read_local_journal(local_a)) == 1
            local_b_valid = len(w123.read_local_journal(local_b)) == 1

            summary_a = w123.request(sock_a, {"op": "summary", "authority_sha": authority}, fp)
            summary_b = w123.request(sock_b, {"op": "summary", "authority_sha": authority}, fp)

            same_prefix = prefix_bytes == cloned_prefix_bytes
            same_fp = (
                info_a.get("credential_fingerprint") == info_b.get("credential_fingerprint") == fp
                and ping_a.get("credential_fingerprint") == ping_b.get("credential_fingerprint") == fp
            )
            both_live = proc_a.poll() is None and proc_b.poll() is None and proc_a.pid != proc_b.pid
            contradictory = {cr["decision"], rr["decision"]} == {"COMMIT", "REJECT"}
            same_chain_position = cr["seq"] == rr["seq"] and cr["prev_record_sha"] == rr["prev_record_sha"]
            both_valid = len(valid_a) == 2 and len(valid_b) == 2
            individually_pinned = local_a_valid and local_b_valid

            report["detail"] = {
                "original_pid": proc_a.pid,
                "clone_pid": proc_b.pid,
                "same_credential_fingerprint": same_fp,
                "common_prefix_byte_identical": same_prefix,
                "common_prefix_record_sha": prefix["record"]["record_sha"],
                "original_lease_inode": (original / w124.LEASE_NAME).stat().st_ino,
                "clone_lease_inode": (clone / w124.LEASE_NAME).stat().st_ino,
                "both_servers_live": both_live,
                "original_terminal": cr,
                "clone_terminal": rr,
                "same_terminal_sequence": cr["seq"] == rr["seq"],
                "same_terminal_predecessor": cr["prev_record_sha"] == rr["prev_record_sha"],
                "terminal_record_shas_differ": cr["record_sha"] != rr["record_sha"],
                "original_ledger_valid_records": len(valid_a),
                "clone_ledger_valid_records": len(valid_b),
                "local_commit_receipt_valid": local_a_valid,
                "local_reject_receipt_valid": local_b_valid,
                "original_summary": summary_a,
                "clone_summary": summary_b,
            }
            report["counterexample_reproduced"] = bool(
                same_prefix and same_fp and both_live and contradictory and same_chain_position
                and cr["record_sha"] != rr["record_sha"] and both_valid and individually_pinned
            )
        finally:
            stop(proc_b, sock_b)
            stop(proc_a, sock_a)

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
    return 0 if report["counterexample_reproduced"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
