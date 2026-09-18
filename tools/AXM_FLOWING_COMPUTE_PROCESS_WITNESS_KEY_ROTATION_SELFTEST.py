#!/usr/bin/env python3
"""Wave 132 adversarial self-test: predecessor-authorized response-key rotation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_INIT_RECOVERY as w131
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_ROTATION as w132
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_AUTHENTICATED_ANCHOR as protocol

SCRIPT = Path(__file__).resolve()
TOOLS = SCRIPT.parent
W131 = TOOLS / "AXM_FLOWING_COMPUTE_PROCESS_WITNESS_INIT_RECOVERY.py"
ENV_UID = w131.w130.FORBIDDEN_WORKER_UID_ENV
STAGES = [
    "pending", "authority_lineage", "witness_lineage", "successor_public",
    "authority_key", "witness_public", "witness_binding", "state",
]


def pycmd(*args: str) -> list[str]:
    out = [sys.executable]
    if sys.flags.optimize:
        out.append("-O")
    return [*out, *args]


def demote(uid: int):
    def _drop() -> None:
        os.setgroups([])
        os.setgid(uid)
        os.setuid(uid)
    return _drop


def env(extra: dict[str, str] | None = None) -> dict[str, str]:
    e = os.environ.copy()
    e["PYTHONPATH"] = str(TOOLS)
    e["HOME"] = "/tmp"
    if extra:
        e.update(extra)
    return e


def run_as(uid: int, args: list[str], *, extra_env: dict[str, str] | None = None,
           check: bool = True, timeout: float = 45.0) -> subprocess.CompletedProcess:
    cp = subprocess.run(
        args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        check=False, timeout=timeout, env=env(extra_env), preexec_fn=demote(uid),
    )
    if check and cp.returncode != 0:
        raise RuntimeError(f"child-failed:{uid}:{cp.returncode}:{args}:{cp.stdout}:{cp.stderr}")
    return cp


def popen_as(uid: int, args: list[str], *, extra_env: dict[str, str] | None = None) -> subprocess.Popen:
    return subprocess.Popen(
        args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        env=env(extra_env), preexec_fn=demote(uid),
    )


def parse(cp: subprocess.CompletedProcess) -> dict:
    lines = cp.stdout.strip().splitlines()
    if not lines:
        raise RuntimeError(f"missing-json:{cp.returncode}:{cp.stderr}")
    return json.loads(lines[-1])


def wait_json(path: Path, proc: subprocess.Popen | None = None, timeout: float = 15.0) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        if path.exists() and path.stat().st_size:
            try:
                return json.loads(path.read_text())
            except Exception:
                pass
        if proc is not None and proc.poll() is not None:
            out, err = proc.communicate()
            raise RuntimeError(f"process-exited-before-marker:{proc.returncode}:{out}:{err}")
        time.sleep(0.02)
    raise TimeoutError(f"marker-timeout:{path}")


def chown_tree(path: Path, uid: int) -> None:
    for root, dirs, files in os.walk(path):
        os.chown(root, uid, uid)
        for name in dirs:
            os.chown(Path(root) / name, uid, uid)
        for name in files:
            os.chown(Path(root) / name, uid, uid)


def setup_case(base: Path, name: str, anchor_uid: int, worker_uid: int) -> tuple[Path, Path, dict[str, str], dict]:
    case = base / name
    case.mkdir(mode=0o777)
    witness = case / "witness"
    anchor = case / "anchor"
    benv = {ENV_UID: str(worker_uid)}
    run_as(anchor_uid, pycmd(str(W131), "init-witness", str(witness), "--witness-id", f"{name}-witness"), extra_env=benv)
    init = parse(run_as(anchor_uid, pycmd(
        str(W131), "init-anchor", str(anchor), str(witness), "--anchor-id", f"{name}-anchor"
    ), extra_env=benv))
    return witness, anchor, benv, init


def rid(name: str) -> str:
    return hashlib.sha256(("AXM-W132-" + name).encode()).hexdigest()


def child_rotate(anchor: Path, witness: Path, rotation_id: str,
                 fault_after: str | None, marker: Path | None) -> int:
    try:
        out = w132.rotate_response_key(
            anchor, witness, rotation_id,
            fault_after=fault_after, fault_marker=marker,
        )
    except BaseException as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 3
    print(json.dumps({"ok": True, "result": out}, sort_keys=True))
    return 0


def child_validate(anchor: Path, witness: Path) -> int:
    try:
        out = w132.validate_rotation_state(anchor, witness)
    except BaseException as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 3
    print(json.dumps({"ok": True, "result": out}, sort_keys=True))
    return 0


def child_serve(anchor: Path, witness: Path, socket_path: Path,
                ready: Path, error: Path) -> int:
    return w132.serve_anchor(anchor, witness, socket_path, ready, error)


def child_ping(socket_path: Path, anchor_fp: str, public_path: Path) -> int:
    try:
        body = protocol.anchor_request(
            socket_path, {"op": "ping"}, anchor_fp, public_path, timeout=5.0
        )
    except BaseException as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 3
    print(json.dumps({"ok": True, "body": body}, sort_keys=True))
    return 0


def start_fault(anchor_uid: int, worker_uid: int, anchor: Path, witness: Path,
                rotation_id: str, stage: str, marker: Path) -> subprocess.Popen:
    return popen_as(anchor_uid, pycmd(
        str(SCRIPT), "--child-rotate", str(anchor), str(witness), rotation_id,
        "--fault-after", stage, "--fault-marker", str(marker),
    ), extra_env={ENV_UID: str(worker_uid)})


def recover(anchor_uid: int, worker_uid: int, anchor: Path, witness: Path,
            rotation_id: str, check: bool = True) -> subprocess.CompletedProcess:
    return run_as(anchor_uid, pycmd(
        str(SCRIPT), "--child-rotate", str(anchor), str(witness), rotation_id,
    ), extra_env={ENV_UID: str(worker_uid)}, check=check)


def kill_at(anchor_uid: int, worker_uid: int, anchor: Path, witness: Path,
            rotation_id: str, stage: str, marker: Path) -> None:
    proc = start_fault(anchor_uid, worker_uid, anchor, witness, rotation_id, stage, marker)
    try:
        wait_json(marker, proc)
        os.kill(proc.pid, signal.SIGKILL)
        proc.wait(timeout=4)
    finally:
        if proc.poll() is None:
            os.kill(proc.pid, signal.SIGKILL)
            proc.wait(timeout=4)


def run_suite(worker_uid: int, anchor_uid: int, report_path: Path | None) -> int:
    if os.geteuid() != 0:
        raise PermissionError("wave132-selftest-requires-root-orchestrator")
    if worker_uid == anchor_uid:
        raise ValueError("worker-and-anchor-uid-must-differ")
    results: list[dict] = []
    base = Path(tempfile.mkdtemp(prefix="axm-w132-key-rotation-"))
    os.chmod(base, 0o777)
    server: subprocess.Popen | None = None
    try:
        for stage in STAGES:
            witness, anchor, benv, initial = setup_case(base, f"cut-{stage}", anchor_uid, worker_uid)
            rotation_id = rid(f"cut-{stage}")
            marker = base / f"{stage}.marker"
            old_fp = initial["response_public_fingerprint"]
            kill_at(anchor_uid, worker_uid, anchor, witness, rotation_id, stage, marker)
            first = parse(recover(anchor_uid, worker_uid, anchor, witness, rotation_id))
            second = parse(recover(anchor_uid, worker_uid, anchor, witness, rotation_id))
            v = parse(run_as(anchor_uid, pycmd(
                str(SCRIPT), "--child-validate", str(anchor), str(witness)
            ), extra_env=benv))
            rd = anchor / w132.ROT_DIR
            pending_left = [name for name in (
                w132.PENDING, w132.PENDING_CERT, w132.PENDING_PUBLIC, w132.PENDING_PRIVATE
            ) if (rd / name).exists()]
            r1, r2 = first.get("result", {}), second.get("result", {})
            ok = (
                first.get("ok") is True and second.get("ok") is True and v.get("ok") is True and
                r1.get("seq") == 1 and r2.get("seq") == 1 and
                r1.get("current_response_public_fingerprint") != old_fp and
                r2.get("current_response_public_fingerprint") == r1.get("current_response_public_fingerprint") and
                r2.get("idempotent") is True and not pending_left and
                len((rd / w132.LINEAGE).read_text().splitlines()) == 1 and
                (rd / w132.LINEAGE).read_bytes() == (witness / w132.WITNESS_LINEAGE).read_bytes()
            )
            results.append({
                "name": f"sigkill_after_{stage}_resumes_same_authorized_rotation",
                "ok": ok,
                "detail": {
                    "old_response_fp": old_fp,
                    "new_response_fp": r1.get("current_response_public_fingerprint"),
                    "retry_idempotent": r2.get("idempotent"),
                    "pending_left": pending_left,
                },
            })

        witness, anchor, benv, _ = setup_case(base, "two-rotations", anchor_uid, worker_uid)
        one = parse(recover(anchor_uid, worker_uid, anchor, witness, rid("two-one")))
        two = parse(recover(anchor_uid, worker_uid, anchor, witness, rid("two-two")))
        final = parse(run_as(anchor_uid, pycmd(
            str(SCRIPT), "--child-validate", str(anchor), str(witness)
        ), extra_env=benv))
        rows = [json.loads(line) for line in (anchor / w132.ROT_DIR / w132.LINEAGE).read_text().splitlines()]
        chain_ok = (
            one.get("result", {}).get("seq") == 1 and two.get("result", {}).get("seq") == 2 and
            final.get("result", {}).get("seq") == 2 and len(rows) == 2 and
            rows[1]["prev_rotation_sha"] == w132._cert_sha(rows[0]) and
            rows[0]["new_response_public_fingerprint"] == rows[1]["old_response_public_fingerprint"]
        )
        results.append({"name": "two_rotations_chain_through_exact_predecessor", "ok": chain_ok,
                        "detail": {"seq": final.get("result", {}).get("seq")}})

        witness, anchor, benv, _ = setup_case(base, "neg-id", anchor_uid, worker_uid)
        marker = base / "neg-id.marker"
        kill_at(anchor_uid, worker_uid, anchor, witness, rid("neg-id-a"), "pending", marker)
        before = (anchor / w132.ROT_DIR / w132.PENDING).read_bytes()
        cp = recover(anchor_uid, worker_uid, anchor, witness, rid("neg-id-b"), check=False)
        after = (anchor / w132.ROT_DIR / w132.PENDING).read_bytes()
        results.append({
            "name": "different_rotation_id_cannot_reinterpret_pending_transaction",
            "ok": cp.returncode != 0 and before == after,
            "detail": {"returncode": cp.returncode},
        })

        witness, anchor, benv, _ = setup_case(base, "neg-cert", anchor_uid, worker_uid)
        marker = base / "neg-cert.marker"
        rotation_id = rid("neg-cert")
        kill_at(anchor_uid, worker_uid, anchor, witness, rotation_id, "pending", marker)
        cert_path = anchor / w132.ROT_DIR / w132.PENDING_CERT
        cert = json.loads(cert_path.read_text())
        cert["new_response_public_fingerprint"] = "0" * 64
        cert_path.write_bytes(w132.w.canonical(cert) + b"\n")
        os.chown(cert_path, anchor_uid, anchor_uid)
        os.chmod(cert_path, 0o600)
        cp = recover(anchor_uid, worker_uid, anchor, witness, rotation_id, check=False)
        results.append({
            "name": "tampered_predecessor_certificate_fails_closed",
            "ok": cp.returncode != 0 and (anchor / w132.ROT_DIR / w132.PENDING).exists(),
            "detail": {"returncode": cp.returncode},
        })

        witness, anchor, benv, _ = setup_case(base, "neg-pin-rollback", anchor_uid, worker_uid)
        clean = parse(recover(anchor_uid, worker_uid, anchor, witness, rid("neg-pin-rollback")))
        genesis = (anchor / w132.ROT_DIR / w132.GENESIS_PUBLIC).read_bytes()
        public_path = witness / protocol.WITNESS_PUBLIC_KEY
        public_path.write_bytes(genesis)
        os.chown(public_path, anchor_uid, anchor_uid)
        os.chmod(public_path, 0o600)
        cp = run_as(anchor_uid, pycmd(
            str(SCRIPT), "--child-validate", str(anchor), str(witness)
        ), extra_env=benv, check=False)
        results.append({
            "name": "witness_verifier_rollback_against_newer_lineage_fails_closed",
            "ok": cp.returncode != 0 and clean.get("result", {}).get("seq") == 1,
            "detail": {"returncode": cp.returncode},
        })

        witness, anchor, benv, _ = setup_case(base, "neg-lineage", anchor_uid, worker_uid)
        recover(anchor_uid, worker_uid, anchor, witness, rid("neg-lineage"))
        wp = witness / w132.WITNESS_LINEAGE
        row = json.loads(wp.read_text().splitlines()[0])
        row["rotation_id"] = rid("forged-lineage-id")
        wp.write_bytes(w132.w.canonical(row) + b"\n")
        os.chown(wp, anchor_uid, anchor_uid)
        os.chmod(wp, 0o600)
        cp = run_as(anchor_uid, pycmd(
            str(SCRIPT), "--child-validate", str(anchor), str(witness)
        ), extra_env=benv, check=False)
        results.append({
            "name": "witness_lineage_tamper_fails_closed",
            "ok": cp.returncode != 0,
            "detail": {"returncode": cp.returncode},
        })

        witness, anchor, benv, initial = setup_case(base, "serve", anchor_uid, worker_uid)
        clean = parse(recover(anchor_uid, worker_uid, anchor, witness, rid("serve")))
        root = w132.w126.load_anchor_identity(anchor)[0]
        chown_tree(witness, worker_uid)
        os.chmod(witness, 0o700)
        run_dir = base / "serve-run"
        run_dir.mkdir(mode=0o777)
        socket_path = run_dir / "anchor.sock"
        ready = run_dir / "anchor.ready"
        error = run_dir / "anchor.error"
        server = popen_as(anchor_uid, pycmd(
            str(SCRIPT), "--child-serve", str(anchor), str(witness), str(socket_path),
            str(ready), str(error),
        ), extra_env={ENV_UID: str(worker_uid)})
        wait_json(ready, server)
        os.chmod(socket_path, 0o777)
        ping = parse(run_as(worker_uid, pycmd(
            str(SCRIPT), "--child-ping", str(socket_path),
            root["anchor_credential_fingerprint"], str(witness / protocol.WITNESS_PUBLIC_KEY),
        )))
        rotated_fp = clean.get("result", {}).get("current_response_public_fingerprint")
        serve_ok = (
            ping.get("ok") is True and rotated_fp != initial["response_public_fingerprint"] and
            ping.get("body", {}).get("response_public_fingerprint") == rotated_fp
        )
        results.append({"name": "rotated_authority_serves_exact_authenticated_identity",
                        "ok": serve_ok, "detail": ping})
        os.kill(server.pid, signal.SIGKILL)
        server.wait(timeout=4)
        server = None

    finally:
        if server is not None and server.poll() is None:
            os.kill(server.pid, signal.SIGKILL)
            server.wait(timeout=4)

    passed = sum(bool(r["ok"]) for r in results)
    report = {
        "schema": "axm.flowing-compute.wave132-key-rotation-selftest.v1",
        "mode": "optimized" if sys.flags.optimize else "normal",
        "worker_uid": worker_uid,
        "anchor_uid": anchor_uid,
        "passed": passed,
        "total": len(results),
        "results": results,
        "truth_boundary": (
            "same-host dedicated-UID response-key rotation with predecessor-signed lineage and named "
            "post-publication SIGKILL recovery only. Initial verifier/bootstrap rollback, a crash during "
            "rotation-metadata bootstrap, root/kernel or authority-uid compromise, cross-host genuine-key "
            "clones, whole-domain rollback, hardware custody, performance/energy/retained/incremental/"
            "dormant-compute, provider and physical finality remain unproved"
        ),
    }
    if report_path:
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if passed == len(results) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker-uid", type=int)
    ap.add_argument("--anchor-uid", type=int)
    ap.add_argument("--report")
    ap.add_argument("--child-rotate", nargs=3, metavar=("ANCHOR", "WITNESS", "RID"))
    ap.add_argument("--child-validate", nargs=2, metavar=("ANCHOR", "WITNESS"))
    ap.add_argument("--child-serve", nargs=5, metavar=("ANCHOR", "WITNESS", "SOCKET", "READY", "ERROR"))
    ap.add_argument("--child-ping", nargs=3, metavar=("SOCKET", "ANCHOR_FP", "PUBLIC"))
    ap.add_argument("--fault-after", choices=STAGES)
    ap.add_argument("--fault-marker")
    ns = ap.parse_args()
    if ns.child_rotate:
        a, wi, ri = ns.child_rotate
        return child_rotate(Path(a), Path(wi), ri, ns.fault_after,
                            Path(ns.fault_marker) if ns.fault_marker else None)
    if ns.child_validate:
        a, wi = ns.child_validate
        return child_validate(Path(a), Path(wi))
    if ns.child_serve:
        a, wi, sock, ready, error = ns.child_serve
        return child_serve(Path(a), Path(wi), Path(sock), Path(ready), Path(error))
    if ns.child_ping:
        sock, fp, public = ns.child_ping
        return child_ping(Path(sock), fp, Path(public))
    if ns.worker_uid is None or ns.anchor_uid is None:
        ap.error("--worker-uid and --anchor-uid required")
    return run_suite(ns.worker_uid, ns.anchor_uid, Path(ns.report) if ns.report else None)


if __name__ == "__main__":
    raise SystemExit(main())
