#!/usr/bin/env python3
"""AXM Flowing Compute Wave 124: exclusive lifetime lease for process witness.

Experimental lane only. Repairs the Wave 123 overlapping-instance race found by
independent verifier PR #48. A witness process must acquire a non-blocking
kernel advisory lock on the exact witness store before it may inspect/unlink the
Unix socket, load the credential/ledger, or answer requests. The lock is held
for the full server lifetime and is released by the kernel on process exit,
including SIGKILL.

Truth boundary: this is a same-Linux-host/process-store linearizability repair.
It does not prove power-loss/device finality, network/provider independence,
protection against directory/inode substitution, or safety if some other writer
bypasses this server and edits the ledger directly. No performance, energy,
retained/incremental/dormant-compute, merge, or CANON claim is made.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import socket
from pathlib import Path

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS as w

LEASE_NAME = "serve.lock"
SOURCE = {
    "wave123_evidence_head": "fe431e64b3aee7840cff848395aef2e9af2847db",
    "wave123_tested_source_commit": "b594d1bac276c11f98ce6a6f558fb929ed0c30eb",
    "wave123_tool_blob": "2e87f9416d8ec0d9d04b46e842ac2d7a1a9e0f08",
    "wave123_selftest_blob": "cb7828109185284a9d543a697a85129a3273d7a9",
    "wave123_ci_run": 35283872389,
    "wave123_artifact_sha256": "315c44825ff48f49c05f95e26b14d210cf70e05ba045c7cfa07854f6a11fbc90",
    "verifier_pr": 48,
    "verifier_head": "b58c6ab768bb6eaf2400a542db8e960041fc2b25",
    "verifier_artifact_sha256": "3f1f64de3a8836588285e40f411f106abf18cd4616083732d051072e096afdaf",
}


def acquire_store_lease(witness_dir: str | Path) -> int:
    """Acquire the one-live-server lease for a witness directory.

    The file's bytes are not evidence and are never interpreted as authority.
    Exclusivity comes from the kernel lock attached to the open file
    description. A stale zero-byte lease file after a crash is harmless.
    """
    d = Path(witness_dir)
    d.mkdir(parents=True, exist_ok=True)
    p = d / LEASE_NAME
    fd = os.open(str(p), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        os.chmod(p, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("witness-store-already-served") from exc
        return fd
    except BaseException:
        os.close(fd)
        raise


def release_store_lease(fd: int) -> None:
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _write_error(error_file: str | Path | None, exc: BaseException) -> None:
    if not error_file:
        return
    try:
        Path(error_file).write_text(f"{type(exc).__name__}:{exc}\n")
    except Exception:
        pass


def serve(witness_dir: str | Path, socket_path: str | Path,
          ready_file: str | Path | None = None,
          error_file: str | Path | None = None,
          allow_fault: bool = False) -> int:
    """Serve Wave 123 protocol while holding an exclusive store lifetime lease."""
    lease_fd: int | None = None
    listener: socket.socket | None = None
    sp = Path(socket_path)
    try:
        # Critical ordering: acquire the store lease before touching the socket.
        # A rejected replacement therefore cannot unlink a live server's socket.
        lease_fd = acquire_store_lease(witness_dir)
        root, secret = w.load_identity(witness_dir)
        w.load_ledger(witness_dir, secret)

        if sp.exists():
            sp.unlink()
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(sp))
        listener.listen(16)
        if ready_file:
            w._atomic_write(
                Path(ready_file),
                w.canonical({
                    "pid": os.getpid(),
                    "credential_fingerprint": root["credential_fingerprint"],
                    "exclusive_store_lease": True,
                }) + b"\n",
            )

        running = True
        while running:
            conn, _ = listener.accept()
            with conn:
                try:
                    data = b""
                    while not data.endswith(b"\n"):
                        chunk = conn.recv(65536)
                        if not chunk:
                            break
                        data += chunk
                    req = json.loads(data)
                    op = req.get("op")
                    if op == "ping":
                        out = {
                            "ok": True,
                            "pid": os.getpid(),
                            "credential_fingerprint": root["credential_fingerprint"],
                            "exclusive_store_lease": True,
                        }
                    elif op == "decide":
                        out = w.decide(witness_dir, root, secret, req, allow_fault)
                    elif op == "summary":
                        out = w.summary(witness_dir, root, secret, req.get("authority_sha"))
                    elif op == "stop":
                        out = {
                            "ok": True,
                            "stopping": True,
                            "credential_fingerprint": root["credential_fingerprint"],
                        }
                        running = False
                    else:
                        raise ValueError("unknown-operation")
                    conn.sendall(w.canonical(out) + b"\n")
                except Exception as exc:
                    try:
                        conn.sendall(w.canonical({
                            "ok": False,
                            "error": f"{type(exc).__name__}:{exc}",
                            "credential_fingerprint": root["credential_fingerprint"],
                        }) + b"\n")
                    except OSError:
                        pass
        return 0
    except BaseException as exc:
        _write_error(error_file, exc)
        return 2
    finally:
        if listener is not None:
            try:
                listener.close()
            except Exception:
                pass
        # Only a process that acquired the lease is allowed to remove the socket.
        if lease_fd is not None:
            try:
                if sp.exists():
                    sp.unlink()
            except Exception:
                pass
            try:
                release_store_lease(lease_fd)
            except Exception:
                pass


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    p.add_argument("witness_dir")
    p.add_argument("--witness-id", default="wave124-witness")
    p = sub.add_parser("serve")
    p.add_argument("witness_dir")
    p.add_argument("socket_path")
    p.add_argument("--ready-file")
    p.add_argument("--error-file")
    p.add_argument("--allow-fault-injection", action="store_true")
    p = sub.add_parser("transact")
    p.add_argument("socket_path")
    p.add_argument("expected_fp")
    p.add_argument("local_journal")
    p.add_argument("authority_sha")
    p.add_argument("transition_sha")
    p.add_argument("decision", choices=sorted(w.DECISIONS))
    p.add_argument("stable", choices=["true", "false"])
    p.add_argument("reason")
    p.add_argument("--fault")
    p.add_argument("--fault-marker")
    p.add_argument("--pause-after-witness")
    p.add_argument("--pause-after-local")
    ns = ap.parse_args()

    if ns.cmd == "init":
        print(json.dumps(w.initialize_witness_dir(ns.witness_dir, ns.witness_id), sort_keys=True))
        return 0
    if ns.cmd == "serve":
        return serve(ns.witness_dir, ns.socket_path, ns.ready_file, ns.error_file, ns.allow_fault_injection)
    out = w.decide_and_publish(
        ns.socket_path, ns.expected_fp, ns.local_journal,
        ns.authority_sha, ns.transition_sha, ns.decision,
        ns.stable == "true", ns.reason, ns.fault, ns.fault_marker,
        ns.pause_after_witness, ns.pause_after_local,
    )
    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
