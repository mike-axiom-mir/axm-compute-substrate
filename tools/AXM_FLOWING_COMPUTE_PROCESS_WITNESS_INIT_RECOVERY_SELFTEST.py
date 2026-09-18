#!/usr/bin/env python3
"""Wave 131 adversarial self-test: exact-provenance init crash recovery."""
from __future__ import annotations

import argparse
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

# Import Wave 131 first so the active protocol receives Wave128/129/130/131 hooks.
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_INIT_RECOVERY as w131
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_AUTHENTICATED_ANCHOR as protocol

SCRIPT = Path(__file__).resolve()
TOOLS = SCRIPT.parent
W131 = TOOLS / "AXM_FLOWING_COMPUTE_PROCESS_WITNESS_INIT_RECOVERY.py"
ENV_UID = w131.w130.FORBIDDEN_WORKER_UID_ENV
STAGES = [
    "manifest",
    "anchor_credential",
    "root",
    "response_private",
    "response_public",
    "witness_public",
    "witness_binding",
    "ready",
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
           check: bool = True, timeout: float = 40.0) -> subprocess.CompletedProcess:
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


def wait_file(path: Path, proc: subprocess.Popen | None = None, timeout: float = 15.0) -> None:
    end = time.time() + timeout
    while time.time() < end:
        if path.exists() and path.stat().st_size:
            try:
                json.loads(path.read_text())
            except Exception:
                pass
            else:
                return
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


def snap_file(path: Path) -> dict:
    st = path.stat()
    return {
        "bytes": path.read_bytes().hex(),
        "uid": st.st_uid,
        "gid": st.st_gid,
        "mode": stat.S_IMODE(st.st_mode),
    }


def snapshot(anchor: Path, witness: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if anchor.exists():
        for p in sorted(anchor.iterdir()):
            if p.is_file():
                out[f"anchor/{p.name}"] = snap_file(p)
    for name in (protocol.WITNESS_PUBLIC_KEY, protocol.WITNESS_BINDING):
        p = witness / name
        if p.exists():
            out[f"witness/{name}"] = snap_file(p)
    return out


def existing_preserved(before: dict[str, dict], after: dict[str, dict]) -> tuple[bool, list[str]]:
    changed = [k for k, v in before.items() if after.get(k) != v]
    return not changed, changed


def setup_case(base: Path, name: str, anchor_uid: int, worker_uid: int) -> tuple[Path, Path, dict[str, str]]:
    case = base / name
    case.mkdir(mode=0o777)
    witness = case / "witness"
    anchor = case / "anchor"
    benv = {ENV_UID: str(worker_uid)}
    run_as(anchor_uid, pycmd(str(W131), "init-witness", str(witness), "--witness-id", f"{name}-witness"), extra_env=benv)
    return witness, anchor, benv


def start_fault_init(anchor_uid: int, worker_uid: int, anchor: Path, witness: Path,
                     stage: str, marker: Path, anchor_id: str) -> subprocess.Popen:
    return popen_as(anchor_uid, pycmd(
        str(SCRIPT), "--child-init", str(anchor), str(witness),
        "--anchor-id", anchor_id, "--fault-after", stage,
        "--fault-marker", str(marker),
    ), extra_env={ENV_UID: str(worker_uid)})


def recover(anchor_uid: int, worker_uid: int, anchor: Path, witness: Path,
            anchor_id: str, check: bool = True) -> subprocess.CompletedProcess:
    return run_as(anchor_uid, pycmd(
        str(SCRIPT), "--child-init", str(anchor), str(witness),
        "--anchor-id", anchor_id,
    ), extra_env={ENV_UID: str(worker_uid)}, check=check)


def kill_at(anchor_uid: int, worker_uid: int, anchor: Path, witness: Path,
            stage: str, marker: Path, anchor_id: str) -> None:
    proc = start_fault_init(anchor_uid, worker_uid, anchor, witness, stage, marker, anchor_id)
    try:
        wait_file(marker, proc)
        os.kill(proc.pid, signal.SIGKILL)
        proc.wait(timeout=4)
    finally:
        if proc.poll() is None:
            os.kill(proc.pid, signal.SIGKILL)
            proc.wait(timeout=4)


def child_init(anchor: Path, witness: Path, anchor_id: str,
               fault_after: str | None, fault_marker: Path | None) -> int:
    try:
        out = w131.initialize_anchor_dir(
            anchor, witness, anchor_id,
            fault_after=fault_after, fault_marker=fault_marker,
        )
    except BaseException as exc:
        print(json.dumps({
            "ok": False,
            "error": f"{type(exc).__name__}:{exc}",
            "pid": os.getpid(),
        }, sort_keys=True))
        return 3
    print(json.dumps({"ok": True, "result": out, "pid": os.getpid()}, sort_keys=True))
    return 0


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


def run_suite(worker_uid: int, anchor_uid: int, report_path: Path | None) -> int:
    if os.geteuid() != 0:
        raise PermissionError("wave131-selftest-requires-root-orchestrator")
    if worker_uid == anchor_uid:
        raise ValueError("worker-and-anchor-uid-must-differ")

    results: list[dict] = []
    base = Path(tempfile.mkdtemp(prefix="axm-w131-init-recovery-"))
    os.chmod(base, 0o777)
    server: subprocess.Popen | None = None
    try:
        recovered_for_serve: tuple[Path, Path, dict, str] | None = None

        # Positive matrix: hard-kill after every named durable publication point,
        # then exact recovery and a second idempotent recovery. Existing artifacts
        # must remain byte/owner/mode identical.
        for stage in STAGES:
            witness, anchor, benv = setup_case(base, f"cut-{stage}", anchor_uid, worker_uid)
            anchor_id = f"wave131-{stage}"
            marker = base / f"{stage}.marker"
            kill_at(anchor_uid, worker_uid, anchor, witness, stage, marker, anchor_id)
            before = snapshot(anchor, witness)
            cp = recover(anchor_uid, worker_uid, anchor, witness, anchor_id)
            first = parse(cp)
            after = snapshot(anchor, witness)
            preserved, changed = existing_preserved(before, after)
            cp2 = recover(anchor_uid, worker_uid, anchor, witness, anchor_id)
            second = parse(cp2)
            after2 = snapshot(anchor, witness)
            idempotent_unchanged = after2 == after
            r1 = first.get("result", {})
            r2 = second.get("result", {})
            same_identity = (
                first.get("ok") is True and second.get("ok") is True and
                r1.get("anchor_credential_fingerprint") == r2.get("anchor_credential_fingerprint") and
                r1.get("response_public_fingerprint") == r2.get("response_public_fingerprint") and
                r2.get("wave131_init_recovery", {}).get("idempotent") is True
            )
            ok = preserved and idempotent_unchanged and same_identity and (anchor / w131.READY).exists()
            results.append({
                "name": f"sigkill_after_{stage}_recovers_exactly",
                "ok": ok,
                "detail": {
                    "preexisting_artifact_count": len(before),
                    "changed_preexisting": changed,
                    "idempotent_unchanged": idempotent_unchanged,
                    "anchor_fp": r2.get("anchor_credential_fingerprint"),
                    "response_fp": r2.get("response_public_fingerprint"),
                    "second_idempotent": r2.get("wave131_init_recovery", {}).get("idempotent"),
                },
            })
            if stage == "witness_binding":
                recovered_for_serve = (witness, anchor, r2, anchor_id)

        # A recovered store must still provide the genuine authenticated endpoint
        # after handoff of the witness side to the worker uid.
        if recovered_for_serve is None:
            raise RuntimeError("missing-recovered-serve-case")
        witness, anchor, recovered, _ = recovered_for_serve
        chown_tree(witness, worker_uid)
        os.chmod(witness, 0o700)
        run_dir = base / "serve-run"
        run_dir.mkdir(mode=0o777)
        socket_path = run_dir / "anchor.sock"
        ready = run_dir / "anchor.ready"
        error = run_dir / "anchor.error"
        server = popen_as(anchor_uid, pycmd(
            str(W131), "serve-anchor", str(anchor), str(socket_path),
            "--ready-file", str(ready), "--error-file", str(error),
        ), extra_env={ENV_UID: str(worker_uid)})
        wait_file(ready, server)
        os.chmod(socket_path, 0o777)
        ping = parse(run_as(worker_uid, pycmd(
            str(SCRIPT), "--child-ping", str(socket_path),
            recovered["anchor_credential_fingerprint"],
            str(witness / protocol.WITNESS_PUBLIC_KEY),
        )))
        serve_ok = (
            ping.get("ok") is True and
            ping.get("body", {}).get("anchor_credential_fingerprint") == recovered["anchor_credential_fingerprint"] and
            ping.get("body", {}).get("response_public_fingerprint") == recovered["response_public_fingerprint"]
        )
        results.append({"name": "recovered_store_serves_exact_authenticated_identity",
                        "ok": serve_ok, "detail": ping})
        os.kill(server.pid, signal.SIGKILL)
        server.wait(timeout=4)
        server = None

        # Negative: a manifest is bound to the exact witness identity. Replacing
        # the witness with a fresh genuine identity must not be interpreted as a retry.
        witness, anchor, _ = setup_case(base, "neg-witness", anchor_uid, worker_uid)
        marker = base / "neg-witness.marker"
        kill_at(anchor_uid, worker_uid, anchor, witness, "manifest", marker, "neg-witness-anchor")
        shutil.rmtree(witness)
        run_as(anchor_uid, pycmd(str(W131), "init-witness", str(witness), "--witness-id", "replacement-witness"),
               extra_env={ENV_UID: str(worker_uid)})
        before_anchor = snapshot(anchor, witness)
        cp = recover(anchor_uid, worker_uid, anchor, witness, "neg-witness-anchor", check=False)
        after_anchor = snapshot(anchor, witness)
        results.append({
            "name": "mismatched_witness_identity_fails_closed",
            "ok": cp.returncode != 0 and before_anchor == after_anchor,
            "detail": {"returncode": cp.returncode, "stderr_tail": cp.stderr[-500:]},
        })

        # Negative: an existing root with different content is not silently rebuilt.
        witness, anchor, _ = setup_case(base, "neg-root", anchor_uid, worker_uid)
        marker = base / "neg-root.marker"
        kill_at(anchor_uid, worker_uid, anchor, witness, "root", marker, "neg-root-anchor")
        root_path = anchor / "root.json"
        root_obj = json.loads(root_path.read_text())
        root_obj["anchor_id"] = "tampered-anchor-id"
        root_path.write_bytes(w131.w.canonical(root_obj) + b"\n")
        os.chown(root_path, anchor_uid, anchor_uid)
        os.chmod(root_path, 0o600)
        before = snapshot(anchor, witness)
        cp = recover(anchor_uid, worker_uid, anchor, witness, "neg-root-anchor", check=False)
        after = snapshot(anchor, witness)
        results.append({
            "name": "mismatched_root_is_not_silently_rewritten",
            "ok": cp.returncode != 0 and before == after,
            "detail": {"returncode": cp.returncode, "stderr_tail": cp.stderr[-500:]},
        })

        # Negative: public material without its durable private predecessor is
        # ambiguous and must not trigger generation of a new private identity.
        witness, anchor, _ = setup_case(base, "neg-public", anchor_uid, worker_uid)
        marker = base / "neg-public.marker"
        kill_at(anchor_uid, worker_uid, anchor, witness, "response_public", marker, "neg-public-anchor")
        (anchor / protocol.PRIVATE_KEY).unlink()
        before = snapshot(anchor, witness)
        cp = recover(anchor_uid, worker_uid, anchor, witness, "neg-public-anchor", check=False)
        after = snapshot(anchor, witness)
        results.append({
            "name": "public_without_private_predecessor_remains_ambiguous",
            "ok": cp.returncode != 0 and before == after and not (anchor / protocol.PRIVATE_KEY).exists(),
            "detail": {"returncode": cp.returncode, "stderr_tail": cp.stderr[-500:]},
        })

        # Negative: exact binding mismatch is evidence, not a candidate to overwrite.
        witness, anchor, _ = setup_case(base, "neg-binding", anchor_uid, worker_uid)
        marker = base / "neg-binding.marker"
        kill_at(anchor_uid, worker_uid, anchor, witness, "witness_binding", marker, "neg-binding-anchor")
        bp = witness / protocol.WITNESS_BINDING
        binding = json.loads(bp.read_text())
        binding["response_public_fingerprint"] = "0" * 64
        bp.write_bytes(w131.w.canonical(binding) + b"\n")
        os.chown(bp, anchor_uid, anchor_uid)
        os.chmod(bp, 0o600)
        before = snapshot(anchor, witness)
        cp = recover(anchor_uid, worker_uid, anchor, witness, "neg-binding-anchor", check=False)
        after = snapshot(anchor, witness)
        results.append({
            "name": "mismatched_witness_binding_is_not_overwritten",
            "ok": cp.returncode != 0 and before == after,
            "detail": {"returncode": cp.returncode, "stderr_tail": cp.stderr[-500:]},
        })

        # Negative: unknown leftovers, including the kind an interruption inside
        # _atomic_write could leave, stay fail-closed instead of being garbage-collected.
        witness, anchor, _ = setup_case(base, "neg-unexpected", anchor_uid, worker_uid)
        marker = base / "neg-unexpected.marker"
        kill_at(anchor_uid, worker_uid, anchor, witness, "manifest", marker, "neg-unexpected-anchor")
        junk = anchor / "root.json.tmp-interrupted-example"
        junk.write_bytes(b"partial")
        os.chown(junk, anchor_uid, anchor_uid)
        os.chmod(junk, 0o600)
        before = snapshot(anchor, witness)
        cp = recover(anchor_uid, worker_uid, anchor, witness, "neg-unexpected-anchor", check=False)
        after = snapshot(anchor, witness)
        results.append({
            "name": "unknown_partial_write_ballast_fails_closed",
            "ok": cp.returncode != 0 and before == after,
            "detail": {"returncode": cp.returncode, "stderr_tail": cp.stderr[-500:]},
        })

        # Negative: readiness is an exact final receipt. Tampering it blocks service
        # and must not expose a socket as if the initialization were complete.
        witness, anchor, benv = setup_case(base, "neg-ready", anchor_uid, worker_uid)
        complete = parse(recover(anchor_uid, worker_uid, anchor, witness, "neg-ready-anchor"))["result"]
        rp = anchor / w131.READY
        ready_obj = json.loads(rp.read_text())
        ready_obj["response_public_fingerprint"] = "f" * 64
        rp.write_bytes(w131.w.canonical(ready_obj) + b"\n")
        os.chown(rp, anchor_uid, anchor_uid)
        os.chmod(rp, 0o600)
        run_dir = base / "neg-ready-run"
        run_dir.mkdir(mode=0o777)
        socket_path = run_dir / "anchor.sock"
        error_path = run_dir / "anchor.error"
        cp = run_as(anchor_uid, pycmd(
            str(W131), "serve-anchor", str(anchor), str(socket_path),
            "--error-file", str(error_path),
        ), extra_env=benv, check=False)
        results.append({
            "name": "tampered_readiness_receipt_blocks_service",
            "ok": cp.returncode != 0 and not socket_path.exists() and error_path.exists(),
            "detail": {
                "returncode": cp.returncode,
                "anchor_fp": complete.get("anchor_credential_fingerprint"),
                "error_tail": error_path.read_text()[-500:] if error_path.exists() else "",
            },
        })

        passed = sum(1 for r in results if r["ok"])
        report = {
            "schema": "axm.flowing-compute.wave131-init-recovery-selftest.v1",
            "mode": "optimized" if sys.flags.optimize else "normal",
            "worker_uid": worker_uid,
            "anchor_uid": anchor_uid,
            "passed": passed,
            "total": len(results),
            "results": results,
            "fresh_verifier_boundary": {
                "pr": 55,
                "result": "environment-blocked-userns-alias-attack; not falsified and not proven safe",
                "tested_head": "1e942411959d919cc627a12ebaa9c15468d758a2",
                "ci_run": 35314687612,
            },
            "truth_boundary": (
                "named post-publication SIGKILL recovery only; a kill inside _atomic_write may leave an unknown temp artifact and "
                "deliberately fails closed. Trusted UID namespace only; userns/container UID aliasing remains unproved after PR55 "
                "was environment-blocked. Root/kernel, authority-uid compromise, cross-host genuine-key clones, whole-domain rollback, "
                "hardware custody, performance/energy/retained/incremental/dormant-compute, provider and physical finality remain unproved"
            ),
        }
        if report_path:
            report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps(report, sort_keys=True))
        return 0 if passed == len(results) else 1
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
    ap.add_argument("--child-init", nargs=2, metavar=("ANCHOR", "WITNESS"))
    ap.add_argument("--anchor-id", default="wave131-anchor")
    ap.add_argument("--fault-after")
    ap.add_argument("--fault-marker")
    ap.add_argument("--child-ping", nargs=3, metavar=("SOCKET", "ANCHOR_FP", "PUBLIC"))
    ns = ap.parse_args()

    if ns.child_init:
        return child_init(
            Path(ns.child_init[0]), Path(ns.child_init[1]), ns.anchor_id,
            ns.fault_after, Path(ns.fault_marker) if ns.fault_marker else None,
        )
    if ns.child_ping:
        return child_ping(Path(ns.child_ping[0]), ns.child_ping[1], Path(ns.child_ping[2]))
    if ns.worker_uid is None or ns.anchor_uid is None:
        ap.error("--worker-uid and --anchor-uid required")
    return run_suite(ns.worker_uid, ns.anchor_uid, Path(ns.report) if ns.report else None)


if __name__ == "__main__":
    raise SystemExit(main())
