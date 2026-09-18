#!/usr/bin/env python3
"""AXM Flowing Compute Wave 128: private-key custody without global temp files.

Experimental lane only / NON-CANON / no automatic merge.

Wave 127 authenticated anchor replies, but verifier PR #52 showed that the exact
fixed runtime copied the response private key into a mode-0600 file in the
process-global temporary directory for each OpenSSL signature. A same-UID
pathname observer could copy that helper key and then re-open the already known
Unix-socket substitution attack with valid fresh signatures.

Wave 128 keeps the Wave-127 response protocol and Wave-126 durability model, but
changes cryptographic key transport:

* response private-key bytes are never materialized in a filesystem tempfile;
* signing uses an anonymous Linux memfd passed explicitly to the OpenSSL child;
* verification uses anonymous memfds for the public key and signature too;
* the anchor process and each crypto child set PR_SET_DUMPABLE=0 before secret
  key access, so ordinary same-UID /proc fd/memory inspection is denied by the
  kernel ptrace access check on the tested Linux boundary;
* RSA key generation streams the private key through pipes rather than a
  globally discoverable temporary path.

This is deliberately not a claim against a hostile kernel, CAP_SYS_PTRACE,
anchor-store read access, private-key compromise before this boundary, a copied
genuine key on another host/namespace, power/device failure, or physical
finality. It makes no speed, energy, retained/incremental/dormant-compute claim.
"""
from __future__ import annotations

import argparse
import base64
import ctypes
import hmac
import os
import subprocess
import sys
from pathlib import Path

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS as w
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_AUTHENTICATED_ANCHOR as _base
from AXM_FLOWING_COMPUTE_PROCESS_WITNESS_AUTHENTICATED_ANCHOR import *  # noqa: F401,F403

SIGNATURE_ALGORITHM = "rsa-pkcs1v15-sha256-openssl-memfd"
PR_SET_DUMPABLE = 4
SUID_DUMP_DISABLE = 0

SOURCE = {
    "wave127_evidence_head": "10140773f21d17fca9f38f04ff1d762a2d0d90e8",
    "wave127_tested_source_commit": "e45a5610879ac2b5fcb46a72222a212a91e6cf68",
    "wave127_fixed_tool_blob": "1d2fbe3f32b175dbbbcbae3431d9698769b5d0a2",
    "verifier_pr": 52,
    "verifier_tested_head": "b6fa4d78d21410a8691a9554d6a199d6858bc5bb",
    "verifier_ci_run": 35302389245,
    "verifier_artifact_sha256": "779dbaf1a9bc2a13074f9b734c1952a0843643f52dff1bae2f8929b39ca3b1dc",
}


def _require_linux() -> None:
    if not sys.platform.startswith("linux"):
        raise RuntimeError("wave128-key-custody-requires-linux")
    if not hasattr(os, "memfd_create"):
        raise RuntimeError("wave128-key-custody-requires-memfd-create")


def _set_dumpable_disabled() -> None:
    """Fail closed unless this process can disable ordinary ptrace/proc reads."""
    _require_linux()
    libc = ctypes.CDLL(None, use_errno=True)
    rc = libc.prctl(PR_SET_DUMPABLE, SUID_DUMP_DISABLE, 0, 0, 0)
    if rc != 0:
        err = ctypes.get_errno()
        raise OSError(err, "prctl(PR_SET_DUMPABLE,0) failed")


def _child_disable_dumpable() -> None:
    """subprocess pre-exec hook; use os._exit because exceptions are unsafe here."""
    try:
        _set_dumpable_disabled()
    except BaseException:
        os._exit(126)


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError("short-write-to-memfd")
        view = view[written:]
    os.lseek(fd, 0, os.SEEK_SET)


def _memfd_bytes(label: str, data: bytes) -> int:
    _require_linux()
    fd = os.memfd_create(label, os.MFD_CLOEXEC)
    try:
        _write_all(fd, data)
        return fd
    except BaseException:
        os.close(fd)
        raise


def _run_openssl_private(args: list[str], data: bytes | None = None,
                         pass_fds: tuple[int, ...] = ()) -> bytes:
    """Run OpenSSL with the crypto child non-dumpable and exact inherited fds."""
    try:
        cp = subprocess.run(
            ["openssl", *args],
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            pass_fds=pass_fds,
            preexec_fn=_child_disable_dumpable,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("openssl-required-for-wave128-key-custody") from exc
    if cp.returncode != 0:
        raise ValueError(
            "openssl-command-failed:" + cp.stderr.decode("utf-8", "replace").strip()
        )
    return cp.stdout


def _generate_response_keypair_memfd() -> tuple[bytes, bytes]:
    """Generate RSA key material without a private-key filesystem helper path."""
    private_pem = _run_openssl_private([
        "genpkey", "-algorithm", "RSA",
        "-pkeyopt", "rsa_keygen_bits:2048",
    ])
    public_pem = _run_openssl_private(["pkey", "-pubout"], private_pem)
    if b"BEGIN PRIVATE KEY" not in private_pem:
        raise ValueError("wave128-private-key-generation-invalid")
    if b"BEGIN PUBLIC KEY" not in public_pem:
        raise ValueError("wave128-public-key-generation-invalid")
    return private_pem, public_pem


def _sign_memfd(private_key_path: str | Path, payload: bytes) -> str:
    """Sign through an anonymous inherited fd; never copy the key to /tmp."""
    private_pem = Path(private_key_path).read_bytes()
    key_fd = _memfd_bytes("axm-wave128-response-private", private_pem)
    try:
        signature = _run_openssl_private(
            ["dgst", "-sha256", "-sign", f"/proc/self/fd/{key_fd}"],
            payload,
            (key_fd,),
        )
        return base64.b64encode(signature).decode("ascii")
    finally:
        os.close(key_fd)


def _verify_memfd(public_key_path: str | Path, payload: bytes,
                  signature_b64: str) -> bool:
    try:
        signature = base64.b64decode(signature_b64, validate=True)
    except Exception:
        return False
    public_pem = Path(public_key_path).read_bytes()
    pub_fd = _memfd_bytes("axm-wave128-response-public", public_pem)
    sig_fd = _memfd_bytes("axm-wave128-response-signature", signature)
    try:
        try:
            cp = subprocess.run(
                [
                    "openssl", "dgst", "-sha256",
                    "-verify", f"/proc/self/fd/{pub_fd}",
                    "-signature", f"/proc/self/fd/{sig_fd}",
                ],
                input=payload,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                pass_fds=(pub_fd, sig_fd),
                preexec_fn=_child_disable_dumpable,
            )
        except FileNotFoundError:
            return False
        return cp.returncode == 0
    finally:
        os.close(sig_fd)
        os.close(pub_fd)


def _signed_response_memfd(anchor_fp: str, request: dict, body: dict,
                           private_key_path: str | Path) -> dict:
    unsigned = {
        "schema": _base.RESPONSE_SCHEMA,
        "request_nonce": request["nonce"],
        "request_sha": _base._request_sha(request),
        "anchor_credential_fingerprint": anchor_fp,
        "body": body,
    }
    signature = _sign_memfd(private_key_path, w.canonical(unsigned))
    return {
        **unsigned,
        "signature_algorithm": SIGNATURE_ALGORITHM,
        "anchor_response_signature": signature,
    }


def _verify_response_memfd(envelope: dict, request: dict, expected_anchor_fp: str,
                           public_key_path: str | Path) -> dict:
    expected_keys = {
        "schema", "request_nonce", "request_sha",
        "anchor_credential_fingerprint", "body",
        "signature_algorithm", "anchor_response_signature",
    }
    if set(envelope) != expected_keys:
        raise PermissionError("anchor-response-fields-mismatch")
    if envelope.get("schema") != _base.RESPONSE_SCHEMA:
        raise PermissionError("anchor-response-schema-mismatch")
    if envelope.get("signature_algorithm") != SIGNATURE_ALGORITHM:
        raise PermissionError("anchor-response-signature-algorithm-mismatch")
    if not hmac.compare_digest(
        str(envelope.get("request_nonce", "")), request["nonce"]
    ):
        raise PermissionError("anchor-response-nonce-mismatch")
    if not hmac.compare_digest(
        str(envelope.get("request_sha", "")), _base._request_sha(request)
    ):
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
    if not _verify_memfd(
        public_key_path,
        w.canonical(unsigned),
        str(envelope.get("anchor_response_signature", "")),
    ):
        raise PermissionError("anchor-response-signature-invalid")
    body = envelope.get("body")
    if not isinstance(body, dict):
        raise PermissionError("anchor-response-body-invalid")
    return body


_original_serve_anchor = _base.serve_anchor


def serve_anchor(anchor_dir: str | Path, socket_path: str | Path,
                 ready_file: str | Path | None = None,
                 error_file: str | Path | None = None,
                 allow_fault: bool = False) -> int:
    # The long-lived process becomes non-dumpable before opening the stable
    # store handle or reading the response private key.
    _set_dumpable_disabled()
    return _original_serve_anchor(
        anchor_dir, socket_path, ready_file, error_file, allow_fault
    )


# Keep the Wave-127 protocol implementation in one place, but replace exact
# key generation, key transport, envelope algorithm identity, verification,
# and anchor process custody before invoking its CLI/runtime.
_base._generate_response_keypair = _generate_response_keypair_memfd
_base._sign = _sign_memfd
_base._verify = _verify_memfd
_base._signed_response = _signed_response_memfd
_base._verify_response = _verify_response_memfd
_base.serve_anchor = serve_anchor


def __getattr__(name: str):
    return getattr(_base, name)


def main() -> int:
    return _base.main()


if __name__ == "__main__":
    raise SystemExit(main())
