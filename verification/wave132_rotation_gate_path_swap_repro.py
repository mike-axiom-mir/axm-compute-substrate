#!/usr/bin/env python3
"""Independent Wave 132 verifier: rotation-gate pathname swap.

DRAFT / NON-CANON verifier lane. Builder implementation is unchanged.

Wave 132 serve_anchor validates authority rotation state by pathname and then
hands the same pathname to the lower server. This harness widens only that
natural handoff. In the exact builder-style 0777 parent directory, the ordinary
worker uid renames the validated rotated store aside and moves a genuine
Wave-131-ready (but Wave-132-unbootstrapped) authority store into the same
pathname. The lower server then reopens and serves the replacement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_INIT_RECOVERY as w131
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_ROTATION as w132
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_AUTHENTICATED_ANCHOR as protocol

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
W131 = TOOLS / "AXM_FLOWING_COMPUTE_PROCESS_WITNESS_INIT_RECOVERY.py"
ENV_UID = w131.w130.FORBIDDEN_WORKER_UID_ENV


def pycmd(*args: str) -> list[str]:
    out = [sys.executable]
    if sys.flags.optimize:
        out.append("-O")
    return [*out, *args]


def env(worker_uid: int) -> dict[str, str]:
    e = os.environ.copy()
    e["PYTHONPATH"] = str(TOOLS)
    e["HOME"] = "/tmp"
    e[ENV_UID] = str(worker_uid)
    return e


def demote(uid: int):
    def _drop() -> None:
        os.setgroups([])
        os.setgid(uid)
        os.setuid(uid)
    return _drop


def run_as(uid: int, worker_uid: int, args: list[str], *, check: bool = True,
           timeout: float = 45.0) -> subprocess.CompletedProcess:
    cp = subprocess.run(
        args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        check=False, timeout=timeout, env=env(worker_uid), preexec_fn=demote(uid),
    )
    if check and cp.returncode != 0:
        raise RuntimeError(f"child-failed:{uid}:{cp.returncode}:{args}:{cp.stdout}:{cp.stderr}")
    return cp


def popen_as(uid: int, worker_uid: int, args: list[str]) -> subprocess.Popen:
    return subprocess.Popen(
        args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        env=env(worker_uid), preexec_fn=demote(uid),
    )


def parse(cp: subprocess.CompletedProcess) -> dict:
    lines = cp.stdout.strip().splitlines()
    if not lines:
        raise RuntimeError(f"missing-json:{cp.returncode}:{cp.stderr}")
    return json.loads(lines[-1])


def wait_json(path: Path, proc: subprocess.Popen | None = None,
              timeout: float = 15.0) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        if path.exists() and path.stat().st_size:
            try:
                return json.loads(path.read_text())
            except Exception:
                pass
        if proc is not None and proc.poll() is not None:
            out, err = proc.communicate()
            raise RuntimeError(f"process-exited-before-file:{proc.returncode}:{out}:{err}")
        time.sleep(0.02)
    raise TimeoutError(str(path))


def chown_tree(path: Path, uid: int) -> None:
    for root, dirs, files in os.walk(path):
        os.chown(root, uid, uid)
        for name in dirs:
            os.chown(Path(root) / name, uid, uid)
        for name in files:
            os.chown(Path(root) / name, uid, uid)


def child_rotate(anchor: Path, witness: Path, rid: str) -> int:
    try:
        out = w132.rotate_response_key(anchor, witness, rid)
        print(json.dumps({"ok": True, "result": out}, sort_keys=True))
        return 0
    except BaseException as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 3


def child_serve(anchor: Path, witness: Path, socket_path: Path, ready: Path,
                error: Path, validated: Path, release: Path) -> int:
    original = w132.validate_authority_rotation_state

    def gated(path: str | Path) -> dict:
        out = original(path)
        validated.write_text(json.dumps({
            "pid": os.getpid(),
            "validated_seq": out["seq"],
            "validated_anchor_fp": out["root"]["anchor_credential_fingerprint"],
            "validated_response_fp": out["current_response_public_fingerprint"],
        }, sort_keys=True) + "\n")
        end = time.time() + 20
        while time.time() < end and not release.exists():
            time.sleep(0.01)
        if not release.exists():
            raise TimeoutError("verifier-release-timeout")
        return out

    w132.validate_authority_rotation_state = gated
    return w132.serve_anchor(anchor, witness, socket_path, ready, error)


def child_ping(socket_path: Path, anchor_fp: str, public_path: Path) -> int:
    try:
        body = protocol.anchor_request(
            socket_path, {"op": "ping"}, anchor_fp, public_path, timeout=5.0
        )
        print(json.dumps({"ok": True, "body": body}, sort_keys=True))
        return 0
    except BaseException as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 3


def run(worker_uid: int, anchor_uid: int, report: Path | None) -> int:
    if os.geteuid() != 0:
        raise PermissionError("root-orchestrator-required")
    if worker_uid == anchor_uid:
        raise ValueError("uids-must-differ")

    base = Path(tempfile.mkdtemp(prefix="axm-w132-gate-swap-"))
    os.chmod(base, 0o777)
    server: subprocess.Popen | None = None
    try:
        active = base / "active-wave132-anchor"
        replacement = base / "replacement-wave131-anchor"
        preserved = base / "preserved-wave132-anchor"
        witness_a = base / "witness-wave132"
        witness_b = base / "witness-wave131"
        socket_path = base / "anchor.sock"
        ready = base / "serve.ready"
        error = base / "serve.error"
        validated_file = base / "validated.marker"
        release = base / "release.marker"

        # Store A: genuine Wave-131 initialization plus one genuine Wave-132 rotation.
        init_a = parse(run_as(anchor_uid, worker_uid, pycmd(
            str(W131), "init-witness", str(witness_a), "--witness-id", "w132-gate-a-witness"
        )))
        init_a = parse(run_as(anchor_uid, worker_uid, pycmd(
            str(W131), "init-anchor", str(active), str(witness_a), "--anchor-id", "w132-gate-a-anchor"
        )))
        rid = hashlib.sha256(b"AXM-W132-VERIFIER-PATH-SWAP").hexdigest()
        rot = parse(run_as(anchor_uid, worker_uid, pycmd(
            str(Path(__file__).resolve()), "--child-rotate", str(active), str(witness_a), rid
        )))
        if not rot.get("ok") or rot.get("result", {}).get("seq") != 1:
            raise RuntimeError(f"rotation-setup-failed:{rot}")

        # Store B: a fully genuine Wave-131-ready authority, deliberately never
        # bootstrapped into Wave 132 and therefore missing response_rotation/.
        parse(run_as(anchor_uid, worker_uid, pycmd(
            str(W131), "init-witness", str(witness_b), "--witness-id", "w131-replacement-witness"
        )))
        init_b = parse(run_as(anchor_uid, worker_uid, pycmd(
            str(W131), "init-anchor", str(replacement), str(witness_b), "--anchor-id", "w131-replacement-anchor"
        )))

        a_fp = init_a["anchor_credential_fingerprint"]
        b_fp = init_b["anchor_credential_fingerprint"]
        pre = {
            "parent_mode": oct(stat.S_IMODE(base.stat().st_mode)),
            "active_owner_uid": active.stat().st_uid,
            "active_mode": oct(stat.S_IMODE(active.stat().st_mode)),
            "active_has_wave132_rotation_dir": (active / w132.ROT_DIR).is_dir(),
            "replacement_owner_uid": replacement.stat().st_uid,
            "replacement_mode": oct(stat.S_IMODE(replacement.stat().st_mode)),
            "replacement_has_wave131_ready": (replacement / w131.READY).exists(),
            "replacement_has_wave132_rotation_dir": (replacement / w132.ROT_DIR).exists(),
            "rotation_seq": rot.get("result", {}).get("seq"),
        }

        # Hand only B's public verifier/binding to the ordinary worker for the
        # post-swap authenticated client check. The authority store stays 0700.
        chown_tree(witness_b, worker_uid)
        os.chmod(witness_b, 0o700)

        server = popen_as(anchor_uid, worker_uid, pycmd(
            str(Path(__file__).resolve()), "--child-serve", str(active), str(witness_a),
            str(socket_path), str(ready), str(error), str(validated_file), str(release)
        ))
        validated = wait_json(validated_file, server)

        # Actual attack step runs as worker UID. It never reads/enters either
        # authority-owned 0700 directory; rename rights come from the 0777 parent.
        swap_code = (
            "import os,sys;"
            "os.rename(sys.argv[1],sys.argv[3]);"
            "os.rename(sys.argv[2],sys.argv[1]);"
            "print(os.geteuid())"
        )
        swap = run_as(worker_uid, worker_uid, pycmd(
            "-c", swap_code, str(active), str(replacement), str(preserved)
        ))
        release.write_text("go\n")
        os.chmod(release, 0o644)

        served = wait_json(ready, server)
        os.chmod(socket_path, 0o777)
        ping_cp = run_as(worker_uid, worker_uid, pycmd(
            str(Path(__file__).resolve()), "--child-ping", str(socket_path), b_fp,
            str(witness_b / protocol.WITNESS_PUBLIC_KEY)
        ), check=False)
        ping = parse(ping_cp)

        reproduced = (
            pre["active_has_wave132_rotation_dir"] is True and
            pre["replacement_has_wave131_ready"] is True and
            pre["replacement_has_wave132_rotation_dir"] is False and
            validated.get("validated_seq") == 1 and
            validated.get("validated_anchor_fp") == a_fp and
            swap.returncode == 0 and swap.stdout.strip() == str(worker_uid) and
            served.get("anchor_credential_fingerprint") == b_fp and
            served.get("anchor_credential_fingerprint") != a_fp and
            ping_cp.returncode == 0 and ping.get("ok") is True and
            ping.get("body", {}).get("anchor_credential_fingerprint") == b_fp and
            not (active / w132.ROT_DIR).exists() and
            (preserved / w132.ROT_DIR).exists()
        )

        out = {
            "schema": "axm.flowing-compute.verifier.wave132-rotation-gate-path-swap.v1",
            "mode": "optimized" if sys.flags.optimize else "normal",
            "verdict": (
                "FAIL_WAVE132_ROTATION_GATE_REOPENS_REPLACEABLE_PATH_BEFORE_LOWER_SERVICE"
                if reproduced else "ATTACK_NOT_REPRODUCED"
            ),
            "failure_reproduced": reproduced,
            "worker_uid": worker_uid,
            "anchor_uid": anchor_uid,
            "preconditions": pre,
            "validated_wave132_store": validated,
            "wave132_anchor_fp": a_fp,
            "replacement_wave131_anchor_fp": b_fp,
            "worker_swap_reported_euid": swap.stdout.strip(),
            "served_ready_file": served,
            "authenticated_worker_ping_to_replacement": ping,
            "post_swap_active_has_wave132_rotation_dir": (active / w132.ROT_DIR).exists(),
            "preserved_original_has_wave132_rotation_dir": (preserved / w132.ROT_DIR).exists(),
            "truth_boundary": (
                "same-host worker-writable parent pathname TOCTOU only; no authority-store/private-key read, "
                "signature forgery, ledger/rotation-lineage rewrite, root/kernel compromise in the attack step, "
                "cross-host result, or performance/energy/retained/incremental/dormant-compute claim"
            ),
        }
        if report:
            report.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
        print(json.dumps(out, sort_keys=True))
        return 0 if reproduced else 1
    finally:
        if server is not None and server.poll() is None:
            try:
                os.kill(server.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                server.wait(timeout=3)
            except Exception:
                pass
        shutil.rmtree(base, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker-uid", type=int)
    ap.add_argument("--anchor-uid", type=int)
    ap.add_argument("--report")
    ap.add_argument("--child-rotate", nargs=3)
    ap.add_argument("--child-serve", nargs=7)
    ap.add_argument("--child-ping", nargs=3)
    ns = ap.parse_args()
    if ns.child_rotate:
        return child_rotate(Path(ns.child_rotate[0]), Path(ns.child_rotate[1]), ns.child_rotate[2])
    if ns.child_serve:
        return child_serve(*(Path(x) for x in ns.child_serve))
    if ns.child_ping:
        return child_ping(Path(ns.child_ping[0]), ns.child_ping[1], Path(ns.child_ping[2]))
    if ns.worker_uid is None or ns.anchor_uid is None:
        ap.error("--worker-uid and --anchor-uid required")
    return run(ns.worker_uid, ns.anchor_uid, Path(ns.report) if ns.report else None)


if __name__ == "__main__":
    raise SystemExit(main())
