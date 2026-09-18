#!/usr/bin/env python3
"""Wave 127 exact repair for OpenSSL access through retained store file descriptors.

The first Wave 127 candidate kept witness/anchor stores pinned through an opened
directory file descriptor, but passed `/proc/self/fd/<n>/...` key paths into a
new OpenSSL child. Python closes unrelated file descriptors in that child, so
the cryptographic helper could not open the pinned path. This wrapper preserves
the Wave 127 protocol and changes only key handoff to OpenSSL: the parent first
reads the already-pinned key bytes, writes a mode-0600 ephemeral helper file,
runs the one signing/verification operation, then deletes that helper file.

Experimental lane only / NON-CANON. This is not a new authority model and makes
no broader durability, performance, energy, or finality claim.
"""
from __future__ import annotations

import base64
import os
import subprocess
import tempfile
from pathlib import Path

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_AUTHENTICATED_ANCHOR as _base
from AXM_FLOWING_COMPUTE_PROCESS_WITNESS_AUTHENTICATED_ANCHOR import *  # noqa: F401,F403


def _secure_temp_bytes(prefix: str, data: bytes) -> Path:
    fd, name = tempfile.mkstemp(prefix=prefix)
    path = Path(name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb", closefd=True) as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise
    return path


def _sign_pinned(private_key_path: str | Path, payload: bytes) -> str:
    private_pem = Path(private_key_path).read_bytes()
    temp_key = _secure_temp_bytes("axm-w127-private-", private_pem)
    try:
        sig = _base._run_openssl(
            ["dgst", "-sha256", "-sign", str(temp_key)], payload
        )
        return base64.b64encode(sig).decode("ascii")
    finally:
        try:
            temp_key.unlink()
        except FileNotFoundError:
            pass


def _verify_pinned(public_key_path: str | Path, payload: bytes,
                   signature_b64: str) -> bool:
    try:
        signature = base64.b64decode(signature_b64, validate=True)
    except Exception:
        return False
    public_pem = Path(public_key_path).read_bytes()
    temp_key = _secure_temp_bytes("axm-w127-public-", public_pem)
    temp_sig = _secure_temp_bytes("axm-w127-signature-", signature)
    try:
        try:
            cp = subprocess.run(
                [
                    "openssl", "dgst", "-sha256",
                    "-verify", str(temp_key),
                    "-signature", str(temp_sig),
                ],
                input=payload,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        except FileNotFoundError:
            return False
        return cp.returncode == 0
    finally:
        for path in (temp_sig, temp_key):
            try:
                path.unlink()
            except FileNotFoundError:
                pass


# Keep the protocol implementation in one place; replace only the OpenSSL key
# transport helpers used by its runtime functions.
_base._sign = _sign_pinned
_base._verify = _verify_pinned


def __getattr__(name: str):
    return getattr(_base, name)


def main() -> int:
    return _base.main()


if __name__ == "__main__":
    raise SystemExit(main())
