#!/usr/bin/env python3
"""AXM Flowing Compute Wave 127: authenticated anchor response channel.

Experimental lane only. Repairs the Wave 126 Unix-socket substitution failure
reproduced by independent verifier PR #51.

Wave 127 keeps the Wave 126 witness/anchor durability model but adds a distinct
RSA response-signing key owned by the anchor. Only the public verifier is
provisioned into the witness store. Every anchor RPC is wrapped in a fresh
nonce-bearing request envelope. The anchor signs the exact request digest,
nonce, pinned anchor identity, and exact response body. The witness rejects
unsigned responses, replayed responses, request/response splicing, and body
tampering before using reconciliation results.

Truth boundary: this is application-layer endpoint authentication on the tested
Linux/OpenSSL path. The witness-side public verifier file remains a provisioning
and rollback boundary. Replacing/rolling back the witness store together with
that verifier, replacing both authority domains, OpenSSL/private-key compromise,
device/controller/kernel failure, and provider-independent finality remain
unproved. No speed, energy, retained/incremental/dormant-compute, merge, or
CANON claim is made.
"""
from __future__ import annotations

import argparse
import base64
import hmac
import json
import os
import secrets
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS as w
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_EXCLUSIVE as w124
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_HOSTBOUND as w125
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ANCHORED as w126

REQUEST_SCHEMA = "axm.flowing-compute.anchor-request.v1"
RESPONSE_SCHEMA = "axm.flowing-compute.anchor-response.v1"
RESPONSE_BINDING_SCHEMA = "axm.flowing-compute.anchor-response-binding.v1"
PRIVATE_KEY = "response_private.pem"
PUBLIC_KEY = "response_public.pem"
WITNESS_PUBLIC_KEY = "anchor_response_public.pem"
WITNESS_BINDING = "anchor_response_binding.json"

SOURCE = {
    "wave126_evidence_head": "cd1e234cad6da6488296d6f00408f59a57aa9687",
    "wave126_tested_source_commit": "b3713154cc1ca587b365ae3647578f791a750e48",
    "wave126_tool_blob": "cf267f87aca1dd53e182f306697eb0e15c529769",
    "wave126_selftest_blob": "afbb5938b288a531998ef27fa192361bba5c430d",
    "verifier_pr": 51,
    "verifier_tested_head": "04d803a6e1ecc45fc3dc18b6d3aa845c717d3d2b",
    "verifier_ci_run": 35298843623,
    "verifier_artifact_sha256": "5d80f023e5f88ca89d096fb8ed6029fccca8a3b218b154dfe12bc48cf5f3e774",
}


def _run_openssl(args: list[str], data: bytes | None = None) -> bytes:
    try:
        cp = subprocess.run(
            ["openssl", *args],
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("openssl-required-for-wave127-response-auth") from exc
    if cp.returncode != 0:
        raise ValueError(
            "openssl-command-failed:" + cp.stderr.decode("utf-8", "replace").strip()
        )
    return cp.stdout


def _public_fingerprint(public_pem: bytes) -> str:
    return w.sha256_hex(b"AXM-W127-ANCHOR-RESPONSE-PUBLIC\0" + public_pem)


def _generate_response_keypair() -> tuple[bytes, bytes]:
    with tempfile.TemporaryDirectory(prefix="axm-w127-keygen-") as td:
        private = Path(td) / "private.pem"
        public = Path(td) / "public.pem"
        _run_openssl([
            "genpkey", "-algorithm", "RSA",
            "-pkeyopt", "rsa_keygen_bits:2048",
            "-out", str(private),
        ])
        _run_openssl(["pkey", "-in", str(private), "-pubout", "-out", str(public)])
        return private.read_bytes(), public.read_bytes()


def _sign(private_key_path: str | Path, payload: bytes) -> str:
    sig = _run_openssl([
        "dgst", "-sha256", "-sign", str(private_key_path)
    ], payload)
    return base64.b64encode(sig).decode("ascii")


def _verify(public_key_path: str | Path, payload: bytes, signature_b64: str) -> bool:
    try:
        signature = base64.b64decode(signature_b64, validate=True)
    except Exception:
        return False
    with tempfile.NamedTemporaryFile(prefix="axm-w127-sig-", delete=False) as fh:
        sig_path = Path(fh.name)
        fh.write(signature)
    try:
        cp = subprocess.run(
            [
                "openssl", "dgst", "-sha256",
                "-verify", str(public_key_path),
                "-signature", str(sig_path),
            ],
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        return cp.returncode == 0
    except FileNotFoundError:
        return False
    finally:
        try:
            sig_path.unlink()
        except FileNotFoundError:
            pass


def initialize_anchor_dir(anchor_dir: str | Path, witness_dir: str | Path,
                          anchor_id: str = "wave127-anchor") -> dict:
    """Initialize Wave 126 anchor state plus an asymmetric response identity."""
    root = w126.initialize_anchor_dir(anchor_dir, witness_dir, anchor_id)
    ad = Path(anchor_dir)
    wd = Path(witness_dir)
    private_pem, public_pem = _generate_response_keypair()
    response_fp = _public_fingerprint(public_pem)
    binding = {
        "schema": RESPONSE_BINDING_SCHEMA,
        "anchor_credential_fingerprint": root["anchor_credential_fingerprint"],
        "response_public_fingerprint": response_fp,
    }
    w._atomic_write(ad / PRIVATE_KEY, private_pem, 0o600)
    w._atomic_write(ad / PUBLIC_KEY, public_pem, 0o600)
    w._atomic_write(wd / WITNESS_PUBLIC_KEY, public_pem, 0o600)
    w._atomic_write(wd / WITNESS_BINDING, w.canonical(binding) + b"\n", 0o600)
    return {**root, "response_public_fingerprint": response_fp}


def load_response_binding(witness_dir: str | Path, expected_anchor_fp: str) -> tuple[dict, Path]:
    wd = Path(witness_dir)
    binding = json.loads((wd / WITNESS_BINDING).read_text())
    if set(binding) != {
        "schema", "anchor_credential_fingerprint", "response_public_fingerprint"
    }:
        raise ValueError("anchor-response-binding-fields-mismatch")
    if binding.get("schema") != RESPONSE_BINDING_SCHEMA:
        raise ValueError("anchor-response-binding-schema-mismatch")
    if not hmac.compare_digest(
        str(binding.get("anchor_credential_fingerprint", "")), expected_anchor_fp
    ):
        raise PermissionError("anchor-response-binding-anchor-mismatch")
    public_path = wd / WITNESS_PUBLIC_KEY
    public_pem = public_path.read_bytes()
    if not hmac.compare_digest(
        str(binding.get("response_public_fingerprint", "")),
        _public_fingerprint(public_pem),
    ):
        raise PermissionError("anchor-response-public-key-mismatch")
    return binding, public_path


def _request_envelope(payload: dict, nonce: str | None = None) -> dict:
    return {
        "schema": REQUEST_SCHEMA,
        "nonce": nonce or secrets.token_hex(32),
        "payload": payload,
    }


def _request_sha(envelope: dict) -> str:
    return w.sha256_hex(w.canonical(envelope))


def _signed_response(anchor_fp: str, request: dict, body: dict,
                     private_key_path: str | Path) -> dict:
    unsigned = {
        "schema": RESPONSE_SCHEMA,
        "request_nonce": request["nonce"],
        "request_sha": _request_sha(request),
        "anchor_credential_fingerprint": anchor_fp,
        "body": body,
    }
    signature = _sign(private_key_path, w.canonical(unsigned))
    return {
        **unsigned,
        "signature_algorithm": "rsa-pkcs1v15-sha256-openssl",
        "anchor_response_signature": signature,
    }


def _validate_request_envelope(req: dict) -> dict:
    if set(req) != {"schema", "nonce", "payload"}:
        raise ValueError("anchor-request-envelope-fields-mismatch")
    if req.get("schema") != REQUEST_SCHEMA:
        raise ValueError("anchor-request-envelope-schema-mismatch")
    nonce = req.get("nonce")
    if not isinstance(nonce, str) or len(nonce) != 64:
        raise ValueError("anchor-request-nonce-invalid")
    try:
        bytes.fromhex(nonce)
    except Exception as exc:
        raise ValueError("anchor-request-nonce-invalid") from exc
    payload = req.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("anchor-request-payload-invalid")
    return payload


def _verify_response(envelope: dict, request: dict, expected_anchor_fp: str,
                     public_key_path: str | Path) -> dict:
    expected_keys = {
        "schema", "request_nonce", "request_sha",
        "anchor_credential_fingerprint", "body",
        "signature_algorithm", "anchor_response_signature",
    }
    if set(envelope) != expected_keys:
        raise PermissionError("anchor-response-fields-mismatch")
    if envelope.get("schema") != RESPONSE_SCHEMA:
        raise PermissionError("anchor-response-schema-mismatch")
    if envelope.get("signature_algorithm") != "rsa-pkcs1v15-sha256-openssl":
        raise PermissionError("anchor-response-signature-algorithm-mismatch")
    if not hmac.compare_digest(str(envelope.get("request_nonce", "")), request["nonce"]):
        raise PermissionError("anchor-response-nonce-mismatch")
    if not hmac.compare_digest(str(envelope.get("request_sha", "")), _request_sha(request)):
        raise PermissionError("anchor-response-request-digest-mismatch")
    if not hmac.compare_digest(
        str(envelope.get("anchor_credential_fingerprint", "")), expected_anchor_fp
    ):
        raise PermissionError("anchor-response-anchor-identity-mismatch")
    unsigned = {
        "schema": envelope["schema"],
        "request_nonce": envelope["request_nonce"],
        "request_sha": envelope["request_sha"],
        "anchor_credential_fingerprint": envelope["anchor_credential_fingerprint"],
        "body": envelope["body"],
    }
    if not _verify(
        public_key_path, w.canonical(unsigned),
        str(envelope.get("anchor_response_signature", "")),
    ):
        raise PermissionError("anchor-response-signature-invalid")
    body = envelope.get("body")
    if not isinstance(body, dict):
        raise PermissionError("anchor-response-body-invalid")
    return body


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
        root, anchor_secret, witness_secret = w126.load_anchor_identity(stable_store)
        private_path = Path(stable_store) / PRIVATE_KEY
        public_path = Path(stable_store) / PUBLIC_KEY
        if not private_path.exists() or not public_path.exists():
            raise ValueError("anchor-response-keypair-missing")
        public_fp = _public_fingerprint(public_path.read_bytes())
        credential_lease = w126._acquire_anchor_lease(root["anchor_credential_fingerprint"])
        store_lease_fd = w124.acquire_store_lease(stable_store)
        rows = w126.load_anchor_ledger(stable_store, root, anchor_secret, witness_secret)
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
                    "response_public_fingerprint": public_fp,
                    "anchor_seq": len(rows),
                    "exclusive_store_lease": True,
                    "anchor_host_lease": True,
                    "authenticated_response_channel": True,
                    "store_dev": store_identity[0],
                    "store_ino": store_identity[1],
                }) + b"\n",
            )

        running = True
        while running:
            conn, _ = listener.accept()
            with conn:
                request = None
                try:
                    data = b""
                    while not data.endswith(b"\n"):
                        chunk = conn.recv(65536)
                        if not chunk:
                            break
                        data += chunk
                    request = json.loads(data)
                    payload = _validate_request_envelope(request)
                    op = payload.get("op")
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
                            rows = w126.load_anchor_ledger(
                                stable_store, root, anchor_secret, witness_secret
                            )
                            out = {
                                "ok": True,
                                "pid": os.getpid(),
                                "anchor_credential_fingerprint": root["anchor_credential_fingerprint"],
                                "witness_credential_fingerprint": root["witness_credential_fingerprint"],
                                "response_public_fingerprint": public_fp,
                                "anchor_seq": len(rows),
                                "witness_record_sha": rows[-1]["witness_record_sha"] if rows else "0" * 64,
                            }
                        elif op == "summary":
                            rows = w126.load_anchor_ledger(
                                stable_store, root, anchor_secret, witness_secret
                            )
                            out = {
                                "ok": True,
                                "anchor_credential_fingerprint": root["anchor_credential_fingerprint"],
                                "witness_credential_fingerprint": root["witness_credential_fingerprint"],
                                "response_public_fingerprint": public_fp,
                                "anchor_seq": len(rows),
                                "anchor_record_sha": rows[-1]["anchor_record_sha"] if rows else "0" * 64,
                                "witness_record_sha": rows[-1]["witness_record_sha"] if rows else "0" * 64,
                            }
                        elif op == "reconcile":
                            fault = payload.get("fault")
                            if fault == w126.FAULT_ANCHOR_AFTER_APPEND_BEFORE_REPLY and not allow_fault:
                                raise ValueError("fault-injection-disabled")
                            out = w126.reconcile_anchor(
                                stable_store, root, anchor_secret, witness_secret,
                                str(payload.get("witness_root_sha", "")),
                                str(payload.get("witness_credential_fingerprint", "")),
                                payload.get("records"),
                            )
                            out["response_public_fingerprint"] = public_fp
                            if fault == w126.FAULT_ANCHOR_AFTER_APPEND_BEFORE_REPLY:
                                w126._pause(payload.get("fault_marker"))
                        else:
                            raise ValueError("unknown-anchor-operation")
                except Exception as exc:
                    out = {
                        "ok": False,
                        "error": f"{type(exc).__name__}:{exc}",
                        "anchor_credential_fingerprint": root["anchor_credential_fingerprint"],
                        "response_public_fingerprint": public_fp,
                    }
                    if request is None or not isinstance(request, dict):
                        continue
                try:
                    response = _signed_response(
                        root["anchor_credential_fingerprint"], request, out, private_path
                    )
                    conn.sendall(w.canonical(response) + b"\n")
                except OSError:
                    pass
        return 0
    except BaseException as exc:
        w126._write_error(error_file, exc)
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
                   expected_anchor_fp: str, verifier_public_key: str | Path,
                   timeout: float = 5.0,
                   nonce: str | None = None) -> dict:
    request = _request_envelope(payload, nonce)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(str(socket_path))
        s.sendall(w.canonical(request) + b"\n")
        data = b""
        while not data.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            data += chunk
    if not data:
        raise ConnectionError("anchor-disconnected-without-response")
    envelope = json.loads(data)
    out = _verify_response(envelope, request, expected_anchor_fp, verifier_public_key)
    if not out.get("ok"):
        raise ValueError(out.get("error", "anchor-request-failed"))
    return out


def reconcile_with_anchor(stable_witness: str | Path, witness_root: dict,
                          witness_secret: bytes, anchor_socket: str | Path,
                          expected_anchor_fp: str,
                          fault: str | None = None,
                          fault_marker: str | Path | None = None) -> dict:
    _, public_path = load_response_binding(stable_witness, expected_anchor_fp)
    records = w.load_ledger(stable_witness, witness_secret)
    payload: dict[str, Any] = {
        "op": "reconcile",
        "witness_root_sha": w126._root_sha(witness_root),
        "witness_credential_fingerprint": witness_root["credential_fingerprint"],
        "records": records,
    }
    if fault:
        payload["fault"] = fault
        payload["fault_marker"] = str(fault_marker) if fault_marker else None
    out = anchor_request(
        anchor_socket, payload, expected_anchor_fp, public_path
    )
    expected_sha = records[-1]["record_sha"] if records else "0" * 64
    if out.get("anchor_seq") != len(records) or out.get("witness_record_sha") != expected_sha:
        raise ValueError("anchor-reconcile-head-mismatch")
    if out.get("witness_credential_fingerprint") != witness_root["credential_fingerprint"]:
        raise ValueError("anchor-reconcile-witness-identity-mismatch")
    return out


def decide(stable_store: Path, witness_root: dict, witness_secret: bytes,
           anchor_socket: str | Path, expected_anchor_fp: str,
           req: dict, allow_fault: bool = False) -> dict:
    reconcile_with_anchor(
        stable_store, witness_root, witness_secret, anchor_socket, expected_anchor_fp
    )
    fault = req.get("fault")
    if fault in {w126.FAULT_AFTER_WITNESS_BEFORE_ANCHOR,
                 w126.FAULT_AFTER_ANCHOR_BEFORE_REPLY} and not allow_fault:
        raise ValueError("fault-injection-disabled")
    out = w.decide(stable_store, witness_root, witness_secret, req, allow_fault)
    if fault == w126.FAULT_AFTER_WITNESS_BEFORE_ANCHOR:
        w126._pause(req.get("fault_marker"))
    anchor = reconcile_with_anchor(
        stable_store, witness_root, witness_secret, anchor_socket, expected_anchor_fp
    )
    out["anchor_credential_fingerprint"] = expected_anchor_fp
    out["anchor_seq"] = anchor["anchor_seq"]
    out["anchor_record_sha"] = anchor["anchor_record_sha"]
    if fault == w126.FAULT_AFTER_ANCHOR_BEFORE_REPLY:
        w126._pause(req.get("fault_marker"))
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
        binding, _ = load_response_binding(stable_store, expected_anchor_fp)
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
                    "response_public_fingerprint": binding["response_public_fingerprint"],
                    "anchor_seq": anchor["anchor_seq"],
                    "exclusive_store_lease": True,
                    "credential_host_lease": True,
                    "authenticated_anchor_response": True,
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
        w126._write_error(error_file, exc)
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
    p.add_argument("--witness-id", default="wave127-witness")

    p = sub.add_parser("init-anchor")
    p.add_argument("anchor_dir")
    p.add_argument("witness_dir")
    p.add_argument("--anchor-id", default="wave127-anchor")

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
