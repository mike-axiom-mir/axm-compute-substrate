#!/usr/bin/env python3
"""Wave 130 verifier v2: UID-only user-namespace alias, preserving v1 failure.

NON-CANON verifier lane. V1 attempted a GID map that the runner denied at
/proc/self/setgroups. Wave 130's authority decision is UID-only, so this version
does not ask for a GID mapping; it tests only the UID semantic the builder uses.
"""
from __future__ import annotations

import argparse, ctypes, errno, json, os, shutil, stat, subprocess, sys, tempfile
from pathlib import Path

CLONE_NEWUSER = 0x10000000
CAP_VERSION = 0x20080522
ENV_UID = "AXM_W130_FORBIDDEN_WORKER_UID"
PRIVATE_KEY = "response_private.pem"
WITNESS_PUBLIC_KEY = "anchor_response_public.pem"

class CapHeader(ctypes.Structure):
    _fields_ = [("version", ctypes.c_uint32), ("pid", ctypes.c_int)]

class CapData(ctypes.Structure):
    _fields_ = [("effective", ctypes.c_uint32),
                ("permitted", ctypes.c_uint32),
                ("inheritable", ctypes.c_uint32)]

def pycmd(*args: str) -> list[str]:
    out = [sys.executable]
    if sys.flags.optimize:
        out.append("-O")
    return [*out, *args]

def status(name: str) -> str:
    prefix = name + ":"
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip()
    return ""

def parse_json(text: str) -> dict:
    for line in reversed(text.strip().splitlines()):
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            return obj
    raise ValueError("missing-json")

def zero_caps() -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    header = CapHeader(CAP_VERSION, 0)
    data = (CapData * 2)()
    if libc.capset(ctypes.byref(header), ctypes.byref(data)) != 0:
        err = ctypes.get_errno()
        raise OSError(err, "capset-zero-failed")

def child(ns_uid: int, worker_uid: int, tool: Path, anchor: Path,
          witness: Path, preflight: Path) -> int:
    if os.geteuid() != worker_uid:
        print(json.dumps({"ok": False, "stage": "pre", "euid": os.geteuid()}))
        return 71
    host_uid, host_gid = os.geteuid(), os.getegid()
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.unshare(CLONE_NEWUSER) != 0:
        err = ctypes.get_errno()
        print(json.dumps({"ok": False, "stage": "unshare", "errno": err,
                          "error": f"{errno.errorcode.get(err, 'ERRNO')}:{os.strerror(err)}"}))
        return 77
    try:
        # Deliberately map only the UID. Wave 130 uses euid/st_uid only.
        Path("/proc/self/uid_map").write_text(f"{ns_uid} {host_uid} 1\n")
        mapped_uid = os.geteuid()
        mapped_gid = os.getegid()  # expected overflow/unmapped; not part of Wave 130 policy.
        zero_caps()
        pf = {
            "ok": True,
            "stage": "uid-mapped-before-exec",
            "parent_host_uid": host_uid,
            "parent_host_gid": host_gid,
            "namespace_euid": mapped_uid,
            "namespace_egid": mapped_gid,
            "uid_map": Path("/proc/self/uid_map").read_text().strip(),
            "gid_map": Path("/proc/self/gid_map").read_text().strip(),
            "cap_eff": status("CapEff"),
            "cap_prm": status("CapPrm"),
            "no_new_privs": status("NoNewPrivs"),
        }
        preflight.write_text(json.dumps(pf, indent=2, sort_keys=True) + "\n")
    except BaseException as exc:
        print(json.dumps({"ok": False, "stage": "uid-map-or-cap-drop",
                          "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 78

    env = os.environ.copy()
    env.update({"PYTHONPATH": str(tool.parent), "HOME": "/tmp", ENV_UID: str(worker_uid)})
    argv = pycmd(str(tool), "init-anchor", str(anchor), str(witness),
                 "--anchor-id", "wave130-userns-uid-only-verifier")
    os.execve(sys.executable, argv, env)
    return 79

def derive_public(private: bytes) -> bytes:
    cp = subprocess.run(["openssl", "pkey", "-pubout"], input=private,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if cp.returncode:
        raise RuntimeError(cp.stderr.decode("utf-8", "replace"))
    return cp.stdout

def run(worker_uid: int, ns_uid: int, tool: Path, report: Path | None) -> int:
    if os.geteuid() != worker_uid:
        raise PermissionError(f"must-run-as-worker:{os.geteuid()}!={worker_uid}")
    base = Path(tempfile.mkdtemp(prefix="axm-w130-userns-v2-"))
    try:
        witness, anchor = base / "witness", base / "anchor"
        preflight = base / "preflight.json"
        env = os.environ.copy()
        env.update({"PYTHONPATH": str(tool.parent), "HOME": "/tmp", ENV_UID: str(worker_uid)})

        wi = subprocess.run(pycmd(str(tool), "init-witness", str(witness)),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, env=env, check=False)
        ch = subprocess.run(pycmd(str(Path(__file__).resolve()), "--child",
                                  "--worker-uid", str(worker_uid),
                                  "--namespace-uid", str(ns_uid),
                                  "--tool", str(tool),
                                  "--anchor", str(anchor),
                                  "--witness", str(witness),
                                  "--preflight", str(preflight)),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, env=env, check=False)

        pf = json.loads(preflight.read_text()) if preflight.exists() else {}
        ai = parse_json(ch.stdout) if ch.returncode == 0 else {}
        boundary = ai.get("wave130_durable_key_boundary", {})

        pkey = anchor / PRIVATE_KEY
        pub = witness / WITNESS_PUBLIC_KEY
        obs = {"private_key_exists": pkey.exists()}
        if pkey.exists():
            st = pkey.stat()
            obs.update({"private_key_owner_uid": st.st_uid,
                        "private_key_mode": oct(stat.S_IMODE(st.st_mode))})
            try:
                raw = pkey.read_bytes()
                obs.update({"worker_readable": True,
                            "private_bytes": len(raw),
                            "derived_public_matches": pub.exists() and derive_public(raw) == pub.read_bytes()})
            except BaseException as exc:
                obs.update({"worker_readable": False,
                            "read_error": f"{type(exc).__name__}:{exc}"})
        else:
            obs.update({"private_key_owner_uid": None, "private_key_mode": None,
                        "worker_readable": False, "private_bytes": 0,
                        "derived_public_matches": False})

        ce = str(pf.get("cap_eff", ""))
        cap_zero = bool(ce) and int(ce, 16) == 0
        reproduced = all([
            wi.returncode == 0, ch.returncode == 0,
            pf.get("ok") is True,
            pf.get("parent_host_uid") == worker_uid,
            pf.get("namespace_euid") == ns_uid,
            cap_zero,
            boundary.get("separate_uid") is True,
            boundary.get("authority_uid") == ns_uid,
            boundary.get("forbidden_worker_uid") == worker_uid,
            boundary.get("private_key_owner_uid") == ns_uid,
            obs.get("private_key_owner_uid") == worker_uid,
            obs.get("private_key_mode") == "0o600",
            obs.get("worker_readable") is True,
            obs.get("derived_public_matches") is True,
        ])

        out = {
            "schema": "axm.flowing-compute.verifier.wave130-userns-uid-alias.v2",
            "mode": "optimized" if sys.flags.optimize else "normal",
            "attack": "FAIL_USER_NAMESPACE_UID_ALIAS_COLLAPSES_WAVE130_AUTHORITY_BOUNDARY",
            "reproduced": reproduced,
            "worker_parent": {"uid": os.geteuid(), "gid": os.getegid(),
                              "cap_eff": status("CapEff"),
                              "uid_map": Path("/proc/self/uid_map").read_text().strip()},
            "namespace_preflight": pf,
            "wave130_init": ai,
            "outside_namespace_observation": obs,
            "process_results": {
                "init_witness_returncode": wi.returncode,
                "namespace_init_returncode": ch.returncode,
                "namespace_init_stdout_tail": ch.stdout[-1600:],
                "namespace_init_stderr_tail": ch.stderr[-1600:],
            },
            "v1_correction": (
                "V1 failed at /proc/self/setgroups while trying to map GID. "
                "Wave 130 makes no GID decision, so v2 removes that irrelevant setup "
                "and attacks only the UID comparison/st_uid contract."
            ),
            "truth_boundary": (
                "This is an ordinary-worker, same-host, unprivileged user-namespace test. "
                "It does not claim root/kernel compromise; kernels/policies that disable "
                "unprivileged user namespaces are a different boundary."
            ),
        }
        if report:
            report.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
        print(json.dumps(out, sort_keys=True))
        return 0 if reproduced else 1
    finally:
        shutil.rmtree(base, ignore_errors=True)

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker-uid", type=int, default=os.geteuid())
    ap.add_argument("--namespace-uid", type=int, default=23001)
    ap.add_argument("--tool", type=Path, default=Path("/tmp/axm-w130-code/AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_AUTHORITY_BOUNDARY.py"))
    ap.add_argument("--report", type=Path)
    ap.add_argument("--child", action="store_true")
    ap.add_argument("--anchor", type=Path)
    ap.add_argument("--witness", type=Path)
    ap.add_argument("--preflight", type=Path)
    a = ap.parse_args()
    if a.child:
        if not a.anchor or not a.witness or not a.preflight:
            ap.error("child requires --anchor --witness --preflight")
        return child(a.namespace_uid, a.worker_uid, a.tool, a.anchor, a.witness, a.preflight)
    return run(a.worker_uid, a.namespace_uid, a.tool, a.report)

if __name__ == "__main__":
    raise SystemExit(main())
