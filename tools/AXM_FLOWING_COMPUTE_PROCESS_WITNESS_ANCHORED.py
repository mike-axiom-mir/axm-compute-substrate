#!/usr/bin/env python3
"""AXM Flowing Compute Wave 126: independently anchored process witness.

Experimental lane only. Repairs the Wave 125 host-pin namespace replacement
boundary reproduced by independent verifier PR #50.

Wave 126 removes witness monotonicity from Wave 125's replaceable /tmp host-pin
pathname. A separate anchor process owns a different durable store and credential.
The anchor keeps an append-only, HMAC-authenticated mirror of every accepted
witness record. The witness must be started with the exact expected anchor
credential fingerprint and cannot silently bootstrap a fresh anchor when that
identity is missing.

The anchor independently validates each mirrored witness record with a copy of
the witness credential provisioned at anchor initialization. It accepts only an
exact chain extension, rejects stale witnesses when the anchor is ahead, rejects
forks at an already anchored sequence, and is idempotent for exact retries.

Truth boundary: tested same Linux host/filesystem with two real OS processes and
separate durable stores. The anchor's expected fingerprint is an external
configuration/pinning boundary. Copying or rolling back both witness and anchor,
replacing that external anchor pin, compromise of either shared credential,
filesystem/device/controller/kernel failure, mixed older writers, and a truly
separate host remain outside the claim. The anchor uses an abstract-socket lease
only to prevent concurrent same-credential anchor clones in one Linux network
namespace; another network namespace/host is the next gate. No performance,
energy, retained/incremental/dormant-compute, merge, or CANON claim is made.
"""
from __future__ import annotations

import argparse
import errno
import hashlib
import hmac
import json
import os
import secrets
import socket
import stat
import time
from pathlib import Path
from typing import Any

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS as w
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_EXCLUSIVE as w124
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_HOSTBOUND as w125

SCHEMA_ANCHOR_ROOT = "axm.flowing-compute.process-witness-anchor-root.v1"
SCHEMA_ANCHOR_RECORD = "axm.flowing-compute.process-witness-anchor-record.v1"
ANCHOR_ABSTRACT_PREFIX = "\0axm-flowing-compute-wave126-anchor-"
FAULT_AFTER_WITNESS_BEFORE_ANCHOR = "pause_after_witness_ledger_before_anchor"
FAULT_AFTER_ANCHOR_BEFORE_REPLY = "pause_after_anchor_before_reply"
FAULT_ANCHOR_AFTER_APPEND_BEFORE_REPLY = "pause_anchor_after_append_before_reply"

SOURCE = {
    "wave125_evidence_head": "f7c5d920a01acae729745aaf0e0b51f8cb928163",
    "wave125_tested_source_commit": "d9b9621bd26f6bf981bfd0f8b51881aaf3f0c886",
    "wave125_tool_blob": "9a07d4b61bf071d144cee10ac297d35de968f3f3",
    "wave125_selftest_fixed_blob": "a30503ecfeb27962b4bdf7549fd08d4c770fc498",
    "wave125_ci_run": 35293032557,
    "wave125_artifact_sha256": "4388d40ce0d4354ce93d030421973f68fbf54c63548a800b126f5ba513ccb547",
    "verifier_pr": 50,
    "verifier_evidence_head": "8b9ed8685e23e2688b66faea907ec01c63ae2d5d",
    "verifier_tested_head": "b9a3253c0dd2d1d510db75aa5b10ba5b45e3518e",
    "verifier_ci_run": 35294548142,
    "verifier_artifact_sha256": "ddebc0894e994ad5a2cffc66ac66a6537d5e7f55810abcd28f0f6bc965b5abf8",
}


def _root_sha(root: dict) -> str:
    return w.sha256_hex(w.canonical(root))


def anchor_credential_fingerprint(secret: bytes) -> str:
    return w.sha256_hex(b"AXM-W126-ANCHOR-CREDENTIAL\0" + secret)


def initialize_anchor_dir(anchor_dir: str | Path, witness_dir: str | Path,
                          anchor_id: str = "wave126-anchor") -> dict:
    """Create a separate anchor identity bound to one exact witness identity."""
    d = Path(anchor_dir)
    d.mkdir(parents=True, exist_ok=True)
    names = ("root.json", "credential.bin", "witness_credential.bin", "ledger.jsonl")
    if any((d / name).exists() for name in names):
        raise FileExistsError("anchor directory is not empty")

    witness_root, witness_secret = w.load_identity(witness_dir)
    anchor_secret = secrets.token_bytes(32)
    anchor_fp = anchor_credential_fingerprint(anchor_secret)
    root = {
        "schema": SCHEMA_ANCHOR_ROOT,
        "anchor_id": anchor_id,
        "anchor_credential_fingerprint": anchor_fp,
        "witness_credential_fingerprint": witness_root["credential_fingerprint"],
        "witness_root_sha": _root_sha(witness_root),
    }
    w._atomic_write(d / "credential.bin", anchor_secret, 0o600)
    w._atomic_write(d / "witness_credential.bin", witness_secret, 0o600)
    w._atomic_write(d / "root.json", w.canonical(root) + b"\n", 0o600)
    w._atomic_write(d / "ledger.jsonl", b"", 0o600)
    return root


def load_anchor_identity(anchor_dir: str | Path) -> tuple[dict, bytes, bytes]:
    d = Path(anchor_dir)
    root = json.loads((d / "root.json").read_text())
    anchor_secret = (d / "credential.bin").read_bytes()
    witness_secret = (d / "witness_credential.bin").read_bytes()
    if root.get("schema") != SCHEMA_ANCHOR_ROOT:
        raise ValueError("anchor-root-schema-mismatch")
    if not hmac.compare_digest(
        str(root.get("anchor_credential_fingerprint", "")),
        anchor_credential_fingerprint(anchor_secret),
    ):
        raise ValueError("anchor-credential-root-mismatch")
    if not hmac.compare_digest(
        str(root.get("witness_credential_fingerprint", "")),
        w.credential_fingerprint(witness_secret),
    ):
        raise ValueError("anchor-witness-credential-mismatch")
    for name in ("credential.bin", "witness_credential.bin", "root.json"):
        if stat.S_IMODE((d / name).stat().st_mode) & 0o077:
            raise ValueError(f"anchor-{name}-permissions-too-broad")
    return root, anchor_secret, witness_secret


def _validate_witness_records(records: list[dict], witness_secret: bytes) -> None:
    prev = "0" * 64
    terminal: set[tuple[str, str]] = set()
    for seq, record in enumerate(records, 1):
        w._verify(record, witness_secret, seq, prev)
        key = (record["authority_sha"], record["transition_sha"])
        if record["decision"] in w.TERMINAL:
            if key in terminal:
                raise ValueError("anchor-witness-terminal-outcome-not-unique")
            terminal.add(key)
        prev = record["record_sha"]


def _anchor_unsigned(seq: int, prev_anchor_sha: str, root: dict, witness_record: dict) -> dict:
    return {
        "schema": SCHEMA_ANCHOR_RECORD,
        "seq": seq,
        "prev_anchor_sha": prev_anchor_sha,
        "anchor_credential_fingerprint": root["anchor_credential_fingerprint"],
        "witness_credential_fingerprint": root["witness_credential_fingerprint"],
        "witness_root_sha": root["witness_root_sha"],
        "witness_record": witness_record,
        "witness_record_sha": witness_record["record_sha"],
    }


def _seal_anchor(unsigned: dict, anchor_secret: bytes) -> dict:
    sig = hmac.new(anchor_secret, w.canonical(unsigned), hashlib.sha256).hexdigest()
    body = {**unsigned, "anchor_signature": sig}
    return {**body, "anchor_record_sha": w.sha256_hex(w.canonical(body))}


def _verify_anchor_record(record: dict, root: dict, anchor_secret: bytes,
                          witness_secret: bytes, seq: int,
                          prev_anchor_sha: str, prev_witness_sha: str) -> None:
    expected_keys = {
        "schema", "seq", "prev_anchor_sha", "anchor_credential_fingerprint",
        "witness_credential_fingerprint", "witness_root_sha", "witness_record",
        "witness_record_sha", "anchor_signature", "anchor_record_sha",
    }
    if set(record) != expected_keys:
        raise ValueError("anchor-record-fields-mismatch")
    if record.get("schema") != SCHEMA_ANCHOR_RECORD:
        raise ValueError("anchor-record-schema-mismatch")
    if record.get("seq") != seq or record.get("prev_anchor_sha") != prev_anchor_sha:
        raise ValueError("anchor-record-chain-position-mismatch")
    if record.get("anchor_credential_fingerprint") != root["anchor_credential_fingerprint"]:
        raise ValueError("anchor-record-anchor-identity-mismatch")
    if record.get("witness_credential_fingerprint") != root["witness_credential_fingerprint"]:
        raise ValueError("anchor-record-witness-identity-mismatch")
    if record.get("witness_root_sha") != root["witness_root_sha"]:
        raise ValueError("anchor-record-witness-root-mismatch")

    wr = record["witness_record"]
    w._verify(wr, witness_secret, seq, prev_witness_sha)
    if record.get("witness_record_sha") != wr.get("record_sha"):
        raise ValueError("anchor-record-embedded-witness-sha-mismatch")

    unsigned = {k: record[k] for k in (
        "schema", "seq", "prev_anchor_sha", "anchor_credential_fingerprint",
        "witness_credential_fingerprint", "witness_root_sha", "witness_record",
        "witness_record_sha",
    )}
    expected_sig = hmac.new(anchor_secret, w.canonical(unsigned), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(str(record.get("anchor_signature", "")), expected_sig):
        raise ValueError("anchor-record-signature-mismatch")
    body = {**unsigned, "anchor_signature": record["anchor_signature"]}
    if not hmac.compare_digest(
        str(record.get("anchor_record_sha", "")), w.sha256_hex(w.canonical(body))
    ):
        raise ValueError("anchor-record-sha-mismatch")


def load_anchor_ledger(anchor_dir: str | Path, root: dict,
                       anchor_secret: bytes, witness_secret: bytes) -> list[dict]:
    p = Path(anchor_dir) / "ledger.jsonl"
    raw = p.read_bytes() if p.exists() else b""
    if raw and not raw.endswith(b"\n"):
        raise ValueError("anchor-ledger-truncated-tail")
    rows: list[dict] = []
    prev_anchor = "0" * 64
    prev_witness = "0" * 64
    terminal: set[tuple[str, str]] = set()
    for seq, line in enumerate(raw.splitlines(), 1):
        try:
            row = json.loads(line)
        except Exception as exc:
            raise ValueError("anchor-ledger-json-corrupt") from exc
        _verify_anchor_record(
            row, root, anchor_secret, witness_secret, seq, prev_anchor, prev_witness
        )
        wr = row["witness_record"]
        key = (wr["authority_sha"], wr["transition_sha"])
        if wr["decision"] in w.TERMINAL:
            if key in terminal:
                raise ValueError("anchor-ledger-terminal-outcome-not-unique")
            terminal.add(key)
        rows.append(row)
        prev_anchor = row["anchor_record_sha"]
        prev_witness = wr["record_sha"]
    return rows


def reconcile_anchor(anchor_dir: str | Path, root: dict, anchor_secret: bytes,
                     witness_secret: bytes, witness_root_sha: str,
                     witness_fp: str, records: list[dict]) -> dict:
    """Advance one anchor only through an exact, independently verified suffix."""
    if witness_root_sha != root["witness_root_sha"]:
        raise ValueError("anchor-request-witness-root-mismatch")
    if witness_fp != root["witness_credential_fingerprint"]:
        raise ValueError("anchor-request-witness-credential-mismatch")
    if not isinstance(records, list):
        raise ValueError("anchor-request-records-not-list")
    _validate_witness_records(records, witness_secret)
    current = load_anchor_ledger(anchor_dir, root, anchor_secret, witness_secret)
    if len(current) > len(records):
        raise ValueError("anchor-ahead-of-witness-store")
    for i, row in enumerate(current):
        if row["witness_record_sha"] != records[i]["record_sha"]:
            raise ValueError("anchor-witness-fork")

    appended = 0
    prev_anchor = current[-1]["anchor_record_sha"] if current else "0" * 64
    for wr in records[len(current):]:
        row = _seal_anchor(
            _anchor_unsigned(len(current) + appended + 1, prev_anchor, root, wr),
            anchor_secret,
        )
        w._append_fsync(Path(anchor_dir) / "ledger.jsonl", w.canonical(row) + b"\n")
        prev_anchor = row["anchor_record_sha"]
        appended += 1

    final = load_anchor_ledger(anchor_dir, root, anchor_secret, witness_secret)
    head_witness = final[-1]["witness_record_sha"] if final else "0" * 64
    head_anchor = final[-1]["anchor_record_sha"] if final else "0" * 64
    return {
        "ok": True,
        "anchor_credential_fingerprint": root["anchor_credential_fingerprint"],
        "witness_credential_fingerprint": root["witness_credential_fingerprint"],
        "anchor_seq": len(final),
        "anchor_record_sha": head_anchor,
        "witness_record_sha": head_witness,
        "appended": appended,
        "idempotent": appended == 0,
    }


def _acquire_anchor_lease(anchor_fp: str) -> socket.socket:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        s.bind(ANCHOR_ABSTRACT_PREFIX + anchor_fp)
    except OSError as exc:
        s.close()
        if exc.errno == errno.EADDRINUSE:
            raise RuntimeError("anchor-credential-already-live-on-host") from exc
        raise
    return s


def _pause(marker: str | Path | None) -> None:
    if not marker:
        raise ValueError("fault-marker-required")
    Path(marker).write_text(str(os.getpid()))
    while True:
        time.sleep(1)


def _write_error(error_file: str | Path | None, exc: BaseException) -> None:
    if not error_file:
        return
    try:
        Path(error_file).write_text(f"{type(exc).__name__}:{exc}\n")
    except Exception:
        pass


def serve_anchor(anchor_dir: str | Path, socket_path: str | Path,
                 ready_file: str | Path | None = None,
                 error_file: str | Path | None = None,
                 allow_fault: bool = False) -> int:
    store_fd: int | None = None
    store_lease_fd: int | None = None
    credential_lease: socket.socket | None = None
    listener: socket.socket | None = None
    socket_bound = False
    sp = Path(socket_path)
    try:
        store_fd, store_identity = w125._open_witness_dir(anchor_dir)
        stable_store = w125._stable_dir_path(store_fd)
        root, anchor_secret, witness_secret = load_anchor_identity(stable_store)
        credential_lease = _acquire_anchor_lease(root["anchor_credential_fingerprint"])
        store_lease_fd = w124.acquire_store_lease(stable_store)
        rows = load_anchor_ledger(stable_store, root, anchor_secret, witness_secret)
        w125._assert_path_identity(anchor_dir, store_identity)

        if sp.exists():
            sp.unlink()
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(sp))
        socket_bound = True
        listener.listen(16)
        if ready_file:
            w._atomic_write(
                Path(ready_file),
                w.canonical({
                    "pid": os.getpid(),
                    "anchor_credential_fingerprint": root["anchor_credential_fingerprint"],
                    "witness_credential_fingerprint": root["witness_credential_fingerprint"],
                    "anchor_seq": len(rows),
                    "exclusive_store_lease": True,
                    "anchor_host_lease": True,
                    "store_dev": store_identity[0],
                    "store_ino": store_identity[1],
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
                    if op == "stop":
                        out = {
                            "ok": True,
                            "stopping": True,
                            "anchor_credential_fingerprint": root["anchor_credential_fingerprint"],
                        }
                        running = False
                    else:
                        w125._assert_path_identity(anchor_dir, store_identity)
                        if op == "ping":
                            rows = load_anchor_ledger(stable_store, root, anchor_secret, witness_secret)
                            out = {
                                "ok": True,
                                "pid": os.getpid(),
                                "anchor_credential_fingerprint": root["anchor_credential_fingerprint"],
                                "witness_credential_fingerprint": root["witness_credential_fingerprint"],
                                "anchor_seq": len(rows),
                                "witness_record_sha": rows[-1]["witness_record_sha"] if rows else "0" * 64,
                            }
                        elif op == "summary":
                            rows = load_anchor_ledger(stable_store, root, anchor_secret, witness_secret)
                            out = {
                                "ok": True,
                                "anchor_credential_fingerprint": root["anchor_credential_fingerprint"],
                                "witness_credential_fingerprint": root["witness_credential_fingerprint"],
                                "anchor_seq": len(rows),
                                "anchor_record_sha": rows[-1]["anchor_record_sha"] if rows else "0" * 64,
                                "witness_record_sha": rows[-1]["witness_record_sha"] if rows else "0" * 64,
                            }
                        elif op == "reconcile":
                            fault = req.get("fault")
                            if fault == FAULT_ANCHOR_AFTER_APPEND_BEFORE_REPLY and not allow_fault:
                                raise ValueError("fault-injection-disabled")
                            out = reconcile_anchor(
                                stable_store, root, anchor_secret, witness_secret,
                                str(req.get("witness_root_sha", "")),
                                str(req.get("witness_credential_fingerprint", "")),
                                req.get("records"),
                            )
                            if fault == FAULT_ANCHOR_AFTER_APPEND_BEFORE_REPLY:
                                _pause(req.get("fault_marker"))
                        else:
                            raise ValueError("unknown-anchor-operation")
                        conn.sendall(w.canonical(out) + b"\n")
                except Exception as exc:
                    try:
                        conn.sendall(w.canonical({
                            "ok": False,
                            "error": f"{type(exc).__name__}:{exc}",
                            "anchor_credential_fingerprint": root["anchor_credential_fingerprint"],
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
        if socket_bound:
            try:
                if sp.exists():
                    sp.unlink()
            except Exception:
                pass
        if store_lease_fd is not None:
            try:
                w124.release_store_lease(store_lease_fd)
            except Exception:
                pass
        if credential_lease is not None:
            try:
                credential_lease.close()
            except Exception:
                pass
        if store_fd is not None:
            try:
                os.close(store_fd)
            except Exception:
                pass


def anchor_request(socket_path: str | Path, payload: dict,
                   expected_anchor_fp: str | None = None,
                   timeout: float = 5.0) -> dict:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(str(socket_path))
        s.sendall(w.canonical(payload) + b"\n")
        data = b""
        while not data.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            data += chunk
    if not data:
        raise ConnectionError("anchor-disconnected-without-response")
    out = json.loads(data)
    if expected_anchor_fp is not None and not hmac.compare_digest(
        str(out.get("anchor_credential_fingerprint", "")), expected_anchor_fp
    ):
        raise PermissionError("anchor-credential-fingerprint-mismatch")
    if not out.get("ok"):
        raise ValueError(out.get("error", "anchor-request-failed"))
    return out


def reconcile_with_anchor(stable_witness: str | Path, witness_root: dict,
                          witness_secret: bytes, anchor_socket: str | Path,
                          expected_anchor_fp: str,
                          fault: str | None = None,
                          fault_marker: str | Path | None = None) -> dict:
    records = w.load_ledger(stable_witness, witness_secret)
    payload: dict[str, Any] = {
        "op": "reconcile",
        "witness_root_sha": _root_sha(witness_root),
        "witness_credential_fingerprint": witness_root["credential_fingerprint"],
        "records": records,
    }
    if fault:
        payload["fault"] = fault
        payload["fault_marker"] = str(fault_marker) if fault_marker else None
    out = anchor_request(anchor_socket, payload, expected_anchor_fp)
    expected_sha = records[-1]["record_sha"] if records else "0" * 64
    if out.get("anchor_seq") != len(records) or out.get("witness_record_sha") != expected_sha:
        raise ValueError("anchor-reconcile-head-mismatch")
    if out.get("witness_credential_fingerprint") != witness_root["credential_fingerprint"]:
        raise ValueError("anchor-reconcile-witness-identity-mismatch")
    return out


def decide(stable_store: Path, witness_root: dict, witness_secret: bytes,
           anchor_socket: str | Path, expected_anchor_fp: str,
           req: dict, allow_fault: bool = False) -> dict:
    reconcile_with_anchor(stable_store, witness_root, witness_secret, anchor_socket, expected_anchor_fp)
    fault = req.get("fault")
    if fault in {FAULT_AFTER_WITNESS_BEFORE_ANCHOR, FAULT_AFTER_ANCHOR_BEFORE_REPLY} and not allow_fault:
        raise ValueError("fault-injection-disabled")

    out = w.decide(stable_store, witness_root, witness_secret, req, allow_fault)
    if fault == FAULT_AFTER_WITNESS_BEFORE_ANCHOR:
        _pause(req.get("fault_marker"))
    anchor = reconcile_with_anchor(
        stable_store, witness_root, witness_secret, anchor_socket, expected_anchor_fp
    )
    out["anchor_credential_fingerprint"] = expected_anchor_fp
    out["anchor_seq"] = anchor["anchor_seq"]
    out["anchor_record_sha"] = anchor["anchor_record_sha"]
    if fault == FAULT_AFTER_ANCHOR_BEFORE_REPLY:
        _pause(req.get("fault_marker"))
    return out


def summary(stable_store: Path, witness_root: dict, witness_secret: bytes,
            anchor_socket: str | Path, expected_anchor_fp: str,
            authority_sha: str | None = None) -> dict:
    anchor = reconcile_with_anchor(
        stable_store, witness_root, witness_secret, anchor_socket, expected_anchor_fp
    )
    out = w.summary(stable_store, witness_root, witness_secret, authority_sha)
    out["anchor_credential_fingerprint"] = expected_anchor_fp
    out["anchor_seq"] = anchor["anchor_seq"]
    out["anchor_record_sha"] = anchor["anchor_record_sha"]
    return out


def serve_witness(witness_dir: str | Path, socket_path: str | Path,
                  anchor_socket: str | Path, expected_anchor_fp: str,
                  ready_file: str | Path | None = None,
                  error_file: str | Path | None = None,
                  allow_fault: bool = False) -> int:
    store_fd: int | None = None
    store_lease_fd: int | None = None
    credential_lease: socket.socket | None = None
    listener: socket.socket | None = None
    socket_bound = False
    sp = Path(socket_path)
    try:
        store_fd, store_identity = w125._open_witness_dir(witness_dir)
        stable_store = w125._stable_dir_path(store_fd)
        root, secret = w.load_identity(stable_store)
        credential_lease = w125._acquire_credential_lease(root["credential_fingerprint"])
        store_lease_fd = w124.acquire_store_lease(stable_store)
        anchor = reconcile_with_anchor(
            stable_store, root, secret, anchor_socket, expected_anchor_fp
        )
        w125._assert_path_identity(witness_dir, store_identity)

        if sp.exists():
            sp.unlink()
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(sp))
        socket_bound = True
        listener.listen(16)
        if ready_file:
            w._atomic_write(
                Path(ready_file),
                w.canonical({
                    "pid": os.getpid(),
                    "credential_fingerprint": root["credential_fingerprint"],
                    "anchor_credential_fingerprint": expected_anchor_fp,
                    "anchor_seq": anchor["anchor_seq"],
                    "exclusive_store_lease": True,
                    "credential_host_lease": True,
                    "store_dev": store_identity[0],
                    "store_ino": store_identity[1],
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
                    if op == "stop":
                        out = {
                            "ok": True,
                            "stopping": True,
                            "credential_fingerprint": root["credential_fingerprint"],
                            "anchor_credential_fingerprint": expected_anchor_fp,
                        }
                        running = False
                    else:
                        w125._assert_path_identity(witness_dir, store_identity)
                        if op == "ping":
                            anchor = reconcile_with_anchor(
                                stable_store, root, secret, anchor_socket, expected_anchor_fp
                            )
                            out = {
                                "ok": True,
                                "pid": os.getpid(),
                                "credential_fingerprint": root["credential_fingerprint"],
                                "anchor_credential_fingerprint": expected_anchor_fp,
                                "anchor_seq": anchor["anchor_seq"],
                            }
                        elif op == "decide":
                            out = decide(
                                stable_store, root, secret, anchor_socket,
                                expected_anchor_fp, req, allow_fault,
                            )
                        elif op == "summary":
                            out = summary(
                                stable_store, root, secret, anchor_socket,
                                expected_anchor_fp, req.get("authority_sha"),
                            )
                        else:
                            raise ValueError("unknown-operation")
                        conn.sendall(w.canonical(out) + b"\n")
                except Exception as exc:
                    try:
                        conn.sendall(w.canonical({
                            "ok": False,
                            "error": f"{type(exc).__name__}:{exc}",
                            "credential_fingerprint": root["credential_fingerprint"],
                            "anchor_credential_fingerprint": expected_anchor_fp,
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
        if socket_bound:
            try:
                if sp.exists():
                    sp.unlink()
            except Exception:
                pass
        if store_lease_fd is not None:
            try:
                w124.release_store_lease(store_lease_fd)
            except Exception:
                pass
        if credential_lease is not None:
            try:
                credential_lease.close()
            except Exception:
                pass
        if store_fd is not None:
            try:
                os.close(store_fd)
            except Exception:
                pass


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init-witness")
    p.add_argument("witness_dir")
    p.add_argument("--witness-id", default="wave126-witness")

    p = sub.add_parser("init-anchor")
    p.add_argument("anchor_dir")
    p.add_argument("witness_dir")
    p.add_argument("--anchor-id", default="wave126-anchor")

    p = sub.add_parser("serve-anchor")
    p.add_argument("anchor_dir")
    p.add_argument("socket_path")
    p.add_argument("--ready-file")
    p.add_argument("--error-file")
    p.add_argument("--allow-fault-injection", action="store_true")

    p = sub.add_parser("serve-witness")
    p.add_argument("witness_dir")
    p.add_argument("socket_path")
    p.add_argument("anchor_socket")
    p.add_argument("expected_anchor_fp")
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
    if ns.cmd == "init-witness":
        print(json.dumps(w.initialize_witness_dir(ns.witness_dir, ns.witness_id), sort_keys=True))
        return 0
    if ns.cmd == "init-anchor":
        print(json.dumps(initialize_anchor_dir(ns.anchor_dir, ns.witness_dir, ns.anchor_id), sort_keys=True))
        return 0
    if ns.cmd == "serve-anchor":
        return serve_anchor(
            ns.anchor_dir, ns.socket_path, ns.ready_file, ns.error_file,
            ns.allow_fault_injection,
        )
    if ns.cmd == "serve-witness":
        return serve_witness(
            ns.witness_dir, ns.socket_path, ns.anchor_socket, ns.expected_anchor_fp,
            ns.ready_file, ns.error_file, ns.allow_fault_injection,
        )
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
