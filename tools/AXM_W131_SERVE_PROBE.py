#!/usr/bin/env python3
"""Temporary Wave 131 serve-start diagnostic; remove after diagnosis."""
import json, os, signal, tempfile, time
from pathlib import Path
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_INIT_RECOVERY_SELFTEST as t

worker_uid = int(os.environ["AXM_PROBE_WORKER_UID"])
anchor_uid = int(os.environ.get("AXM_PROBE_ANCHOR_UID", "23001"))
base = Path(tempfile.mkdtemp(prefix="axm-w131-serve-probe-"))
os.chmod(base, 0o777)
server = None
try:
    witness, anchor, benv = t.setup_case(base, "probe", anchor_uid, worker_uid)
    marker = base / "probe.marker"
    t.kill_at(anchor_uid, worker_uid, anchor, witness, "witness_binding", marker, "probe-anchor")
    recovered = t.parse(t.recover(anchor_uid, worker_uid, anchor, witness, "probe-anchor"))["result"]
    t.chown_tree(witness, worker_uid)
    os.chmod(witness, 0o700)
    run_dir = base / "run"
    run_dir.mkdir(mode=0o777)
    sock = run_dir / "anchor.sock"
    ready = run_dir / "anchor.ready"
    error = run_dir / "anchor.error"
    server = t.popen_as(anchor_uid, t.pycmd(
        str(t.W131), "serve-anchor", str(anchor), str(sock),
        "--ready-file", str(ready), "--error-file", str(error),
    ), extra_env={t.ENV_UID: str(worker_uid)})
    deadline = time.time() + 5
    while time.time() < deadline and not ready.exists() and server.poll() is None:
        time.sleep(0.05)
    print(json.dumps({
        "server_rc": server.poll(),
        "ready_exists": ready.exists(),
        "socket_exists": sock.exists(),
        "error_exists": error.exists(),
        "error": error.read_text() if error.exists() else None,
        "stdout": "" if server.poll() is None else server.stdout.read(),
        "stderr": "" if server.poll() is None else server.stderr.read(),
        "anchor_files": sorted(p.name for p in anchor.iterdir()),
        "anchor_fp": recovered.get("anchor_credential_fingerprint"),
        "response_fp": recovered.get("response_public_fingerprint"),
    }, sort_keys=True))
finally:
    if server is not None and server.poll() is None:
        os.kill(server.pid, signal.SIGKILL)
        server.wait(timeout=3)
