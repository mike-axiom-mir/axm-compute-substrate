#!/usr/bin/env python3
"""Independent adversarial verifier for AXM Flowing Compute Wave 123.

Counterexample target: overlapping/restarted witness processes can both own the
same witness directory because Wave 123 has no exclusive store lease/lock and
serve() unlinks/rebinds the Unix socket unconditionally. The test keeps a live
connection to the old process, starts a replacement on the exact same socket
path/store, then races contradictory terminal decisions for one
(authority_sha, transition_sha).

The long authenticated HOLD prefix only widens the legitimate load/verify
window. It is generated with the exact Wave 123 sealing code and is not part of
the attack. The attack does not forge a credential, hash, or prior record.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import os
import socket
import tempfile
import threading
import time
from pathlib import Path

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS as w


def h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def wait_file(path: Path, proc: mp.Process, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            return
        if not proc.is_alive():
            raise RuntimeError(f"witness-exited-before-ready:pid={proc.pid}:exit={proc.exitcode}")
        time.sleep(0.01)
    raise TimeoutError(f"ready-timeout:{path}")


def stop_process(proc: mp.Process | None) -> None:
    if proc is None:
        return
    if proc.is_alive():
        proc.terminate()
        proc.join(3)
    if proc.is_alive():
        proc.kill()
        proc.join(3)


def seed_authenticated_prefix(witness_dir: Path, count: int) -> dict:
    """Create a valid long prefix using the exact Wave 123 record machinery."""
    root, secret = w.load_identity(witness_dir)
    prev = "0" * 64
    chunks: list[bytes] = []
    for i in range(count):
        authority = h(f"seed-authority-{i}")
        transition = h(f"seed-transition-{i}")
        reason = "seed-retriable-hold"
        proposal = w.proposal_sha(authority, transition, "HOLD", False, reason)
        req = {
            "authority_sha": authority,
            "transition_sha": transition,
            "proposal_sha": proposal,
            "decision": "HOLD",
            "stable": False,
            "reason": reason,
        }
        record = w._seal(w._unsigned(i + 1, prev, req), secret)
        chunks.append(w.canonical(record) + b"\n")
        prev = record["record_sha"]
    payload = b"".join(chunks)
    ledger = witness_dir / "ledger.jsonl"
    with ledger.open("wb", buffering=0) as f:
        f.write(payload)
        os.fsync(f.fileno())
    w._fsync_dir(witness_dir)
    verified = w.load_ledger(witness_dir, secret)
    if len(verified) != count:
        raise AssertionError(f"seed verification mismatch:{len(verified)}!={count}")
    return {
        "seed_records": count,
        "seed_bytes": len(payload),
        "seed_last_record_sha": prev,
        "credential_fingerprint": root["credential_fingerprint"],
    }


def start_server(wd: Path, sock: Path, ready: Path, error: Path) -> mp.Process:
    for p in (ready, error):
        if p.exists():
            p.unlink()
    proc = mp.Process(target=w.serve, args=(wd, sock, ready, error, False))
    proc.start()
    wait_file(ready, proc)
    return proc


def recv_line(conn: socket.socket) -> dict:
    data = b""
    while not data.endswith(b"\n"):
        chunk = conn.recv(65536)
        if not chunk:
            break
        data += chunk
    if not data:
        raise ConnectionError("old-witness-disconnected-without-response")
    return json.loads(data)


def race_once(base: Path, wd: Path, fp: str, attempt: int) -> dict:
    sock = base / "w.sock"
    ready_old = base / f"ready-old-{attempt}.json"
    ready_new = base / f"ready-new-{attempt}.json"
    error_old = base / f"error-old-{attempt}.txt"
    error_new = base / f"error-new-{attempt}.txt"
    old_proc = new_proc = None
    old_conn = None
    try:
        if sock.exists():
            sock.unlink()
        old_proc = start_server(wd, sock, ready_old, error_old)
        old_info = json.loads(ready_old.read_text())

        # Hold a live connection to the old instance. Its listening pathname can
        # now be unlinked/rebound by a replacement while this connection remains
        # valid and routed to the old process.
        old_conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        old_conn.settimeout(60)
        old_conn.connect(str(sock))
        time.sleep(0.05)

        # Exact same witness directory + exact same configured socket path.
        # Wave 123 serve() unlinks the existing pathname and successfully binds.
        new_proc = start_server(wd, sock, ready_new, error_new)
        new_info = json.loads(ready_new.read_text())

        authority = h(f"overlap-authority-{attempt}")
        transition = h(f"overlap-transition-{attempt}")
        commit_proposal = w.proposal_sha(authority, transition, "COMMIT", True, "")
        reject_reason = "stable-adversarial-reject"
        reject_proposal = w.proposal_sha(authority, transition, "REJECT", True, reject_reason)
        old_req = {
            "op": "decide",
            "authority_sha": authority,
            "transition_sha": transition,
            "proposal_sha": commit_proposal,
            "decision": "COMMIT",
            "stable": True,
            "reason": "",
        }
        new_req = {
            "op": "decide",
            "authority_sha": authority,
            "transition_sha": transition,
            "proposal_sha": reject_proposal,
            "decision": "REJECT",
            "stable": True,
            "reason": reject_reason,
        }

        barrier = threading.Barrier(3)
        results: dict[str, object] = {}

        def call_old() -> None:
            try:
                barrier.wait()
                old_conn.sendall(w.canonical(old_req) + b"\n")
                results["old"] = recv_line(old_conn)
            except BaseException as exc:
                results["old_error"] = f"{type(exc).__name__}:{exc}"

        def call_new() -> None:
            try:
                barrier.wait()
                results["new"] = w.request(sock, new_req, fp, timeout=60)
            except BaseException as exc:
                results["new_error"] = f"{type(exc).__name__}:{exc}"

        t_old = threading.Thread(target=call_old, daemon=True)
        t_new = threading.Thread(target=call_new, daemon=True)
        t_old.start(); t_new.start(); barrier.wait()
        t_old.join(70); t_new.join(70)
        if t_old.is_alive() or t_new.is_alive():
            raise TimeoutError("racing clients did not finish")

        old_out = results.get("old")
        new_out = results.get("new")
        both_ok = bool(
            isinstance(old_out, dict) and old_out.get("ok") is True
            and isinstance(new_out, dict) and new_out.get("ok") is True
        )
        detail = {
            "attempt": attempt,
            "old_pid": old_info.get("pid"),
            "new_pid": new_info.get("pid"),
            "same_credential_fingerprint": old_info.get("credential_fingerprint") == new_info.get("credential_fingerprint") == fp,
            "old_result": old_out,
            "new_result": new_out,
            "old_error": results.get("old_error"),
            "new_error": results.get("new_error"),
            "both_terminal_requests_accepted": both_ok,
        }
        if both_ok:
            old_record = old_out["record"]
            new_record = new_out["record"]
            detail.update({
                "decisions": sorted([old_record["decision"], new_record["decision"]]),
                "same_seq": old_record["seq"] == new_record["seq"],
                "same_prev_record_sha": old_record["prev_record_sha"] == new_record["prev_record_sha"],
                "record_shas_differ": old_record["record_sha"] != new_record["record_sha"],
            })
            # The exact normal publication primitive can retain each signed
            # acknowledgement independently before a later status refresh.
            local_old = base / f"local-old-{attempt}.jsonl"
            local_new = base / f"local-new-{attempt}.jsonl"
            w.append_local_receipt(local_old, old_record, fp)
            w.append_local_receipt(local_new, new_record, fp)
            detail["local_old_receipt_valid"] = len(w.read_local_journal(local_old)) == 1
            detail["local_new_receipt_valid"] = len(w.read_local_journal(local_new)) == 1

            try:
                _, secret = w.load_identity(wd)
                w.load_ledger(wd, secret)
                detail["post_race_ledger_validation"] = "UNEXPECTEDLY_VALID"
            except Exception as exc:
                detail["post_race_ledger_validation"] = f"{type(exc).__name__}:{exc}"
        return detail
    finally:
        if old_conn is not None:
            try: old_conn.close()
            except Exception: pass
        stop_process(new_proc)
        stop_process(old_proc)
        if sock.exists():
            try: sock.unlink()
            except Exception: pass


def run(seed_records: int, attempts: int) -> dict:
    report = {
        "verifier": "independent-wave123-overlapping-witness-instance",
        "builder_head": "fe431e64b3aee7840cff848395aef2e9af2847db",
        "builder_tested_source": "b594d1bac276c11f98ce6a6f558fb929ed0c30eb",
        "tool_blob": "2e87f9416d8ec0d9d04b46e842ac2d7a1a9e0f08",
        "attack": "overlapping restart instances share one witness store/socket identity",
        "counterexample_reproduced": False,
        "attempts": [],
        "truth_boundary": [
            "same Linux host and same witness directory",
            "no credential/hash/signature forgery and no prior-record rewrite",
            "long valid HOLD prefix widens concurrent load/verify only",
            "post-race chain failure is fail-closed on a later validation/status, not a stale-authority takeover",
            "no power-loss, device, network-provider, speed, energy, retained/incremental/dormant-compute claim",
        ],
    }
    with tempfile.TemporaryDirectory(prefix="axm-wave123-overlap-") as td:
        base = Path(td)
        wd = base / "witness"
        root = w.initialize_witness_dir(wd, "wave123-overlap-verifier")
        report["seed"] = seed_authenticated_prefix(wd, seed_records)
        fp = root["credential_fingerprint"]
        for attempt in range(1, attempts + 1):
            result = race_once(base, wd, fp, attempt)
            report["attempts"].append(result)
            if result.get("both_terminal_requests_accepted"):
                report["counterexample_reproduced"] = True
                report["winning_attempt"] = result
                break
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed-records", type=int, default=20000)
    ap.add_argument("--attempts", type=int, default=6)
    ap.add_argument("--report")
    ns = ap.parse_args()
    report = run(ns.seed_records, ns.attempts)
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if ns.report:
        Path(ns.report).write_text(text + "\n")
    return 0 if report["counterexample_reproduced"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
