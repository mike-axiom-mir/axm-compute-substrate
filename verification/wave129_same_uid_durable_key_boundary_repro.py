#!/usr/bin/env python3
"""Independent adversarial verifier for Wave 129 durable response-key custody.

Wave 129 correctly moves anchor initialization behind a Linux non-dumpable
process boundary before response-key generation/persistence. This verifier does
not attack that narrower pre-persistence /proc claim. It tests whether the
phrase "same-UID custody" remains meaningful after the generated private key is
persisted with ordinary Unix owner-only mode bits.

The production Wave-129 initializer creates response_private.pem mode 0600.
A separate process running under the same uid/euid then reads that exact file
through the normal filesystem, without CAP_SYS_PTRACE, derives the public key
from the private bytes, and proves that it matches the witness-pinned response
public key. No /proc memory access, ptrace, kernel/root capability, credential
forgery, or ledger rewrite is used.

Expected verdict on the current implementation:
FAIL_SAME_UID_DURABLE_PRIVATE_KEY_IS_DIRECTLY_READABLE_AFTER_WAVE129_INIT

Verifier lane only / NON-CANON / do not auto-merge.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS as w
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_LIFECYCLE as c

VERDICT = "FAIL_SAME_UID_DURABLE_PRIVATE_KEY_IS_DIRECTLY_READABLE_AFTER_WAVE129_INIT"
PRIVATE_KEY = "response_private.pem"
WITNESS_PUBLIC_KEY = "anchor_response_public.pem"
CAP_SYS_PTRACE = 19
PR_GET_DUMPABLE = 3


def cap_eff() -> int:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("CapEff:"):
            return int(line.split()[1], 16)
    return -1


def dumpable() -> int:
    libc = ctypes.CDLL(None, use_errno=True)
    rc = libc.prctl(PR_GET_DUMPABLE, 0, 0, 0, 0)
    if rc < 0:
        err = ctypes.get_errno()
        raise OSError(err, "prctl(PR_GET_DUMPABLE) failed")
    return int(rc)


def public_from_private(private_pem: bytes) -> bytes:
    cp = subprocess.run(
        ["openssl", "pkey", "-pubout"],
        input=private_pem,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=5,
    )
    if cp.returncode != 0:
        raise RuntimeError(cp.stderr.decode("utf-8", "replace"))
    return cp.stdout


def child_read(anchor_dir: Path, witness_dir: Path, report_path: Path) -> int:
    private_path = anchor_dir / PRIVATE_KEY
    public_path = witness_dir / WITNESS_PUBLIC_KEY
    caps = cap_eff()
    report: dict = {
        "uid": os.getuid(),
        "euid": os.geteuid(),
        "cap_eff_hex": hex(caps) if caps >= 0 else None,
        "has_cap_sys_ptrace": bool(caps >= 0 and (caps & (1 << CAP_SYS_PTRACE))),
        "dumpable": dumpable(),
        "private_path": str(private_path),
        "private_exists": private_path.exists(),
        "private_mode_octal": None,
        "private_owner_uid": None,
        "read_succeeded": False,
        "private_bytes": 0,
        "derived_public_matches_witness_pin": False,
        "private_sha256_prefix": None,
        "error": None,
    }
    try:
        st = private_path.stat()
        report["private_mode_octal"] = oct(stat.S_IMODE(st.st_mode))
        report["private_owner_uid"] = st.st_uid
        private_pem = private_path.read_bytes()
        report["read_succeeded"] = True
        report["private_bytes"] = len(private_pem)
        # Keep only a short diagnostic prefix; the key itself is never emitted.
        report["private_sha256_prefix"] = hashlib.sha256(private_pem).hexdigest()[:16]
        derived_public = public_from_private(private_pem)
        witness_public = public_path.read_bytes()
        report["derived_public_matches_witness_pin"] = derived_public == witness_public
    except BaseException as exc:
        report["error"] = f"{type(exc).__name__}:{exc}"
    report_path.write_text(json.dumps(report, sort_keys=True) + "\n")
    return 0 if report["read_succeeded"] else 2


def run() -> dict:
    out: dict = {
        "wave": 129,
        "verifier": "same-UID durable response-key filesystem authority boundary",
        "verdict": None,
        "attack_reproduced": False,
        "truth_boundary": [
            "uses the unchanged production Wave-129 initializer",
            "separate reader process has the same uid/euid as the initializer output owner",
            "reader requires no CAP_SYS_PTRACE and performs no /proc memory read",
            "only normal filesystem owner permissions are used",
            "no root/kernel exploit, credential forgery, hash/signature forgery, or ledger rewrite",
            "this does not falsify Wave 129's narrower pre-persistence non-dumpable /proc-memory claim",
            "it challenges whether same-UID key-custody language is meaningful after persistence without uid/LSM/sandbox separation",
            "not a performance, energy, retained/incremental/dormant-compute, cross-host, or physical-finality result",
        ],
    }

    with tempfile.TemporaryDirectory(prefix="axm-wave129-durable-key-verifier-") as td:
        base = Path(td)
        wd = base / "witness"
        ad = base / "anchor"
        child_report = base / "same_uid_reader.json"

        w.initialize_witness_dir(wd, "wave129-same-uid-durable-key-witness")
        init = c.initialize_anchor_dir(ad, wd, "wave129-same-uid-durable-key-anchor")

        parent_caps = cap_eff()
        parent_uid = os.getuid()
        parent_euid = os.geteuid()
        parent_dumpable = dumpable()
        private_path = ad / PRIVATE_KEY
        st = private_path.stat()

        cp = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--child-read",
                str(ad),
                str(wd),
                str(child_report),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=12,
        )
        child = json.loads(child_report.read_text()) if child_report.exists() else {
            "error": f"child-no-report:rc={cp.returncode}:stderr={cp.stderr}"
        }

        same_identity = (
            child.get("uid") == parent_uid
            and child.get("euid") == parent_euid
            and child.get("private_owner_uid") == parent_uid
        )
        no_ptrace_cap = child.get("has_cap_sys_ptrace") is False
        owner_only_mode = stat.S_IMODE(st.st_mode) == 0o600
        exact_key = child.get("derived_public_matches_witness_pin") is True
        reproduced = bool(
            cp.returncode == 0
            and same_identity
            and no_ptrace_cap
            and owner_only_mode
            and child.get("read_succeeded") is True
            and int(child.get("private_bytes", 0)) > 500
            and exact_key
        )

        out["attack_reproduced"] = reproduced
        out["verdict"] = VERDICT if reproduced else "NOT_REPRODUCED"
        out["initializer"] = {
            "uid": parent_uid,
            "euid": parent_euid,
            "dumpable_after_init": parent_dumpable,
            "cap_eff_hex": hex(parent_caps) if parent_caps >= 0 else None,
            "private_mode_octal": oct(stat.S_IMODE(st.st_mode)),
            "private_owner_uid": st.st_uid,
            "response_public_fingerprint": init.get("response_public_fingerprint"),
        }
        out["same_uid_reader"] = child
        out["interpretation"] = (
            "Wave 129's pre-persistence /proc-memory repair can remain correct while a normal "
            "same-UID process is still authorized by Unix DAC to read the persisted 0600 private key. "
            "Therefore same-UID non-dumpable protection is not a complete same-UID key-confidentiality "
            "boundary unless the durable key is moved behind a different uid, LSM/sandbox, hardware/key-agent, "
            "or equivalent access boundary."
        )

    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report")
    ap.add_argument("--child-read", nargs=3, metavar=("ANCHOR_DIR", "WITNESS_DIR", "REPORT"))
    args = ap.parse_args()
    if args.child_read:
        return child_read(Path(args.child_read[0]), Path(args.child_read[1]), Path(args.child_read[2]))
    result = run()
    text = json.dumps(result, indent=2, sort_keys=True)
    print(text)
    if args.report:
        Path(args.report).write_text(text + "\n")
    # The verifier job succeeds only when the expected counterexample is reproduced.
    return 0 if result.get("attack_reproduced") else 1


if __name__ == "__main__":
    raise SystemExit(main())
