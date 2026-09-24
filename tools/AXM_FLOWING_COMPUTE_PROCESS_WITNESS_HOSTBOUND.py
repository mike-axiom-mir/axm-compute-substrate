#!/usr/bin/env python3
"""AXM Flowing Compute Wave 125: host-bound process witness identity.

Experimental lane only. Repairs the Wave 124 cloned-store fork reproduced by
independent verifier PR #49.

The witness now combines:
1. the Wave 124 per-store file lease;
2. a Linux abstract-UNIX-socket lease keyed by the exact witness credential
   fingerprint, so byte-for-byte directory clones cannot be live concurrently
   in the same Linux network namespace; and
3. an external host-local high-water pin keyed by that credential, so a stale
   clone cannot become current after the live process exits merely because its
   copied HMAC credential still verifies.

The server keeps an open directory handle to the accepted witness store and
refuses requests if the caller-visible path is renamed/replaced while it is
live. Ledger operations use the opened directory handle rather than silently
following a replacement pathname.

Truth boundary: this is one Linux network namespace + one OS user's trusted
host-pin namespace, for cooperating Wave 125 servers. The first host-pin
bootstrap is an initialization boundary. Mixed older servers, direct
out-of-protocol writers, another network namespace/host, replacement or rollback
of the host-pin namespace itself, power/device/controller/kernel failure, and
whole witness + host-pin rollback remain outside the claim. No performance,
energy, retained/incremental/dormant-compute, merge, or CANON claim is made.
"""
from __future__ import annotations

import argparse
import errno
import json
import os
import socket
import stat
import time
from pathlib import Path

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS as w
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_EXCLUSIVE as w124

SCHEMA_HOST_PIN = "axm.flowing-compute.process-witness-host-pin.v1"
HOST_NAMESPACE_NAME = "axm-flowing-compute-wave125-host-v1"
ABSTRACT_PREFIX = "\0axm-flowing-compute-wave125-credential-"
FAULT_AFTER_LEDGER_BEFORE_PIN = "pause_after_ledger_before_host_pin"
FAULT_AFTER_PIN_BEFORE_REPLY = "pause_after_host_pin_before_reply"

SOURCE = {
    "wave124_evidence_head": "27ccee01297feaa9dac169a00d6af456979f606b",
    "wave124_tested_source_commit": "959e4c46e7c2ecf8e2043ebaa177b696d7d35f31",
    "wave124_tool_blob": "d8ececaab8aedd3ca9543b36c5e90d9130d19905",
    "wave124_selftest_blob": "c2a916feebb3026a434cd0f25eb777efb0729bd4",
    "wave124_ci_run": 35288384036,
    "wave124_artifact_sha256": "e4b5fb8be91366487d2b3334a27f5dea4dc50e8ecea1f964170a178703a12c4d",
    "verifier_pr": 49,
    "verifier_evidence_head": "45f082097f415151879a9aadb33553118f4a80d3",
    "verifier_tested_head": "8a64415d9d2e93dc405e254fb2bc04be5841093e",
    "verifier_artifact_sha256": "00c75622e0902114fba5acb81c87b0eb24e826a78bd03035fe5a3e407f7a8ad3",
}


def host_namespace_path() -> Path:
    return Path("/tmp") / f"{HOST_NAMESPACE_NAME}-{os.getuid()}"


def _ensure_host_namespace() -> int:
    p = host_namespace_path()
    try:
        os.mkdir(p, 0o700)
    except FileExistsError:
        pass
    st = os.lstat(p)
    if not stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode):
        raise RuntimeError("host-pin-namespace-not-real-directory")
    if st.st_uid != os.getuid():
        raise PermissionError("host-pin-namespace-owner-mismatch")
    if stat.S_IMODE(st.st_mode) & 0o077:
        raise PermissionError("host-pin-namespace-permissions-too-broad")
    return os.open(str(p), os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)


def _stable_dir_path(fd: int) -> Path:
    return Path(f"/proc/self/fd/{fd}")


def host_pin_path(credential_fingerprint: str) -> Path:
    return host_namespace_path() / f"{credential_fingerprint}.pin.json"


def _host_pin_path_from_fd(host_dir_fd: int, credential_fingerprint: str) -> Path:
    return _stable_dir_path(host_dir_fd) / f"{credential_fingerprint}.pin.json"


def _root_sha(root: dict) -> str:
    return w.sha256_hex(w.canonical(root))


def _pin_body(root: dict, records: list[dict]) -> dict:
    last_seq = len(records)
    last_sha = records[-1]["record_sha"] if records else "0" * 64
    return {
        "schema": SCHEMA_HOST_PIN,
        "credential_fingerprint": root["credential_fingerprint"],
        "root_sha": _root_sha(root),
        "last_seq": last_seq,
        "last_record_sha": last_sha,
    }


def _seal_pin(root: dict, records: list[dict]) -> dict:
    body = _pin_body(root, records)
    return {**body, "pin_sha": w.sha256_hex(w.canonical(body))}


def _verify_pin(pin: dict, root: dict) -> None:
    keys = {
        "schema", "credential_fingerprint", "root_sha",
        "last_seq", "last_record_sha", "pin_sha",
    }
    if set(pin) != keys:
        raise ValueError("host-pin-fields-mismatch")
    if pin.get("schema") != SCHEMA_HOST_PIN:
        raise ValueError("host-pin-schema-mismatch")
    if pin.get("credential_fingerprint") != root.get("credential_fingerprint"):
        raise ValueError("host-pin-credential-mismatch")
    if pin.get("root_sha") != _root_sha(root):
        raise ValueError("host-pin-root-identity-mismatch")
    seq = pin.get("last_seq")
    sha = pin.get("last_record_sha")
    if not isinstance(seq, int) or seq < 0:
        raise ValueError("host-pin-sequence-invalid")
    if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("host-pin-record-sha-invalid")
    body = {k: pin[k] for k in (
        "schema", "credential_fingerprint", "root_sha",
        "last_seq", "last_record_sha",
    )}
    if pin.get("pin_sha") != w.sha256_hex(w.canonical(body)):
        raise ValueError("host-pin-self-hash-mismatch")


def _read_pin(path: Path, root: dict) -> dict | None:
    if not path.exists():
        return None
    raw = path.read_bytes()
    try:
        pin = json.loads(raw)
    except Exception as exc:
        raise ValueError("host-pin-json-corrupt") from exc
    _verify_pin(pin, root)
    return pin


def _write_pin(path: Path, root: dict, records: list[dict]) -> dict:
    pin = _seal_pin(root, records)
    w._atomic_write(path, w.canonical(pin) + b"\n", 0o600)
    return pin


def reconcile_host_pin(host_dir_fd: int, root: dict, records: list[dict]) -> dict:
    """Verify/advance the external high-water pin against one valid ledger."""
    path = _host_pin_path_from_fd(host_dir_fd, root["credential_fingerprint"])
    pin = _read_pin(path, root)
    if pin is None:
        pin = _write_pin(path, root, records)
        return {**pin, "created": True, "advanced": False}

    pseq = pin["last_seq"]
    if pseq > len(records):
        raise ValueError("host-pin-ahead-of-witness-store")
    if pseq == 0:
        if pin["last_record_sha"] != "0" * 64:
            raise ValueError("host-pin-zero-head-mismatch")
    elif records[pseq - 1]["record_sha"] != pin["last_record_sha"]:
        raise ValueError("host-pin-ledger-fork")

    if len(records) > pseq:
        new_pin = _write_pin(path, root, records)
        return {**new_pin, "created": False, "advanced": True}
    return {**pin, "created": False, "advanced": False}


def _acquire_credential_lease(credential_fingerprint: str) -> socket.socket:
    """Acquire a kernel-scoped lease that cannot be copied with store files."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    name = ABSTRACT_PREFIX + credential_fingerprint
    try:
        s.bind(name)
    except OSError as exc:
        s.close()
        if exc.errno == errno.EADDRINUSE:
            raise RuntimeError("witness-credential-already-live-on-host") from exc
        raise
    return s


def _open_witness_dir(path: str | Path) -> tuple[int, tuple[int, int]]:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(str(path), flags)
    st = os.fstat(fd)
    return fd, (st.st_dev, st.st_ino)


def _assert_path_identity(path: str | Path, expected: tuple[int, int]) -> None:
    try:
        st = os.lstat(path)
    except FileNotFoundError as exc:
        raise RuntimeError("witness-store-path-missing") from exc
    if not stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode):
        raise RuntimeError("witness-store-path-replaced")
    if (st.st_dev, st.st_ino) != expected:
        raise RuntimeError("witness-store-path-identity-mismatch")


def _pause(marker: str | Path | None) -> None:
    if not marker:
        raise ValueError("fault-marker-required")
    Path(marker).write_text(str(os.getpid()))
    while True:
        time.sleep(1)


def _validated_records(stable_store: Path, host_dir_fd: int, root: dict, secret: bytes) -> tuple[list[dict], dict]:
    records = w.load_ledger(stable_store, secret)
    pin = reconcile_host_pin(host_dir_fd, root, records)
    return records, pin


def decide(stable_store: Path, host_dir_fd: int, root: dict, secret: bytes, req: dict, allow_fault: bool = False) -> dict:
    _validated_records(stable_store, host_dir_fd, root, secret)
    fault = req.get("fault")
    if fault in {FAULT_AFTER_LEDGER_BEFORE_PIN, FAULT_AFTER_PIN_BEFORE_REPLY} and not allow_fault:
        raise ValueError("fault-injection-disabled")

    out = w.decide(stable_store, root, secret, req, allow_fault)
    if fault == FAULT_AFTER_LEDGER_BEFORE_PIN:
        _pause(req.get("fault_marker"))

    records = w.load_ledger(stable_store, secret)
    pin = reconcile_host_pin(host_dir_fd, root, records)
    out["host_pin_seq"] = pin["last_seq"]
    out["host_pin_record_sha"] = pin["last_record_sha"]

    if fault == FAULT_AFTER_PIN_BEFORE_REPLY:
        _pause(req.get("fault_marker"))
    return out


def summary(stable_store: Path, host_dir_fd: int, root: dict, secret: bytes, authority_sha: str | None = None) -> dict:
    _, pin = _validated_records(stable_store, host_dir_fd, root, secret)
    out = w.summary(stable_store, root, secret, authority_sha)
    out["host_pin_seq"] = pin["last_seq"]
    out["host_pin_record_sha"] = pin["last_record_sha"]
    return out


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
    store_fd: int | None = None
    host_dir_fd: int | None = None
    store_lease_fd: int | None = None
    credential_lease: socket.socket | None = None
    listener: socket.socket | None = None
    socket_bound = False
    sp = Path(socket_path)

    try:
        store_fd, store_identity = _open_witness_dir(witness_dir)
        stable_store = _stable_dir_path(store_fd)
        root, secret = w.load_identity(stable_store)

        credential_lease = _acquire_credential_lease(root["credential_fingerprint"])
        store_lease_fd = w124.acquire_store_lease(stable_store)
        host_dir_fd = _ensure_host_namespace()
        _, pin = _validated_records(stable_store, host_dir_fd, root, secret)
        _assert_path_identity(witness_dir, store_identity)

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
                    "exclusive_store_lease": True,
                    "credential_host_lease": True,
                    "host_pin_seq": pin["last_seq"],
                    "host_pin_record_sha": pin["last_record_sha"],
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
                        }
                        running = False
                    else:
                        _assert_path_identity(witness_dir, store_identity)
                        if op == "ping":
                            _, current_pin = _validated_records(stable_store, host_dir_fd, root, secret)
                            out = {
                                "ok": True,
                                "pid": os.getpid(),
                                "credential_fingerprint": root["credential_fingerprint"],
                                "exclusive_store_lease": True,
                                "credential_host_lease": True,
                                "host_pin_seq": current_pin["last_seq"],
                                "host_pin_record_sha": current_pin["last_record_sha"],
                                "store_dev": store_identity[0],
                                "store_ino": store_identity[1],
                            }
                        elif op == "decide":
                            out = decide(stable_store, host_dir_fd, root, secret, req, allow_fault)
                        elif op == "summary":
                            out = summary(stable_store, host_dir_fd, root, secret, req.get("authority_sha"))
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
        if host_dir_fd is not None:
            try:
                os.close(host_dir_fd)
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

    p = sub.add_parser("init")
    p.add_argument("witness_dir")
    p.add_argument("--witness-id", default="wave125-witness")

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
