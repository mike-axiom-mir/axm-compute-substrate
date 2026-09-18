#!/usr/bin/env python3
"""Independent Wave 126 adversarial verifier: anchor socket substitution.

This verifier does not modify builder code. It keeps the genuine Wave 126 anchor
process and its durable ledger alive, unlinks only the pathname of its Unix
socket, binds a protocol-compatible fake anchor at the same pathname without the
anchor secret, and asks the unchanged Wave 126 witness to append a new terminal
COMMIT. The expected failure is that the witness/client accept the fake anchor's
self-asserted public fingerprint while the genuine anchor remains one sequence
behind.

The counterexample is same-host/same-filesystem and does not use credential
forgery, witness-ledger rewriting, anchor-ledger rewriting, hash collision,
older writer code, namespace rollback, or performance/energy claims.
"""
from __future__ import annotations

import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS as w
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ANCHORED as w126

TOOL = Path(w126.__file__).resolve()
VERDICT = "FAIL_UNAUTHENTICATED_ANCHOR_SOCKET_SUBSTITUTION_ADVANCES_WITNESS_WITHOUT_GENUINE_ANCHOR"


def h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def wait_file(path: Path, proc: subprocess.Popen | None = None, timeout: float = 8.0) -> None:
    end = time.time() + timeout
    while time.time() < end:
        if path.exists():
            return
        if proc is not None and proc.poll() is not None:
            out, err = proc.communicate()
            raise RuntimeError(f"process-exited-before-ready:{proc.returncode}:{out}:{err}")
        time.sleep(0.02)
    raise TimeoutError(f"marker-timeout:{path}")


def launch_anchor(anchor_dir: Path, sock: Path, ready: Path, error: Path) -> subprocess.Popen:
    proc = subprocess.Popen([
        sys.executable, str(TOOL), "serve-anchor", str(anchor_dir), str(sock),
        "--ready-file", str(ready), "--error-file", str(error),
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    wait_file(ready, proc)
    return proc


def launch_witness(witness_dir: Path, sock: Path, anchor_sock: Path,
                   anchor_fp: str, ready: Path, error: Path) -> subprocess.Popen:
    proc = subprocess.Popen([
        sys.executable, str(TOOL), "serve-witness", str(witness_dir), str(sock),
        str(anchor_sock), anchor_fp,
        "--ready-file", str(ready), "--error-file", str(error),
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    wait_file(ready, proc)
    return proc


def kill_proc(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        os.kill(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2)


class FakeAnchor:
    """Protocol-compatible pathname substitute; intentionally owns no anchor secret."""

    def __init__(self, sock: Path, anchor_fp: str, witness_fp: str):
        self.sock = sock
        self.anchor_fp = anchor_fp
        self.witness_fp = witness_fp
        self.seen: list[dict] = []
        self.error: str | None = None
        self.ready = threading.Event()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self.thread.start()
        if not self.ready.wait(5.0):
            raise TimeoutError("fake-anchor-not-ready")
        if self.error:
            raise RuntimeError(self.error)

    def close(self) -> None:
        self.stop.set()
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(0.2)
                s.connect(str(self.sock))
                s.sendall(b'{"op":"stop"}\n')
        except Exception:
            pass
        self.thread.join(timeout=2.0)

    def _run(self) -> None:
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            listener.bind(str(self.sock))
            listener.listen(16)
            listener.settimeout(0.2)
            self.ready.set()
            while not self.stop.is_set():
                try:
                    conn, _ = listener.accept()
                except socket.timeout:
                    continue
                with conn:
                    data = b""
                    while not data.endswith(b"\n"):
                        chunk = conn.recv(65536)
                        if not chunk:
                            break
                        data += chunk
                    if not data:
                        continue
                    req = json.loads(data)
                    if req.get("op") == "stop":
                        break
                    if req.get("op") != "reconcile":
                        out = {
                            "ok": False,
                            "error": "ValueError:fake-anchor-only-reconcile",
                            "anchor_credential_fingerprint": self.anchor_fp,
                        }
                    else:
                        records = req.get("records") or []
                        head = records[-1]["record_sha"] if records else "0" * 64
                        self.seen.append({
                            "record_count": len(records),
                            "head": head,
                            "witness_root_sha": req.get("witness_root_sha"),
                            "witness_credential_fingerprint": req.get("witness_credential_fingerprint"),
                        })
                        out = {
                            "ok": True,
                            "anchor_credential_fingerprint": self.anchor_fp,
                            "witness_credential_fingerprint": self.witness_fp,
                            "anchor_seq": len(records),
                            "anchor_record_sha": "a" * 64,
                            "witness_record_sha": head,
                            "appended": 0,
                            "idempotent": True,
                        }
                    conn.sendall(w.canonical(out) + b"\n")
        except BaseException as exc:
            self.error = f"{type(exc).__name__}:{exc}"
            self.ready.set()
        finally:
            try:
                listener.close()
            except Exception:
                pass


def run() -> dict:
    report = {
        "wave": 126,
        "builder_head": "cd1e234cad6da6488296d6f00408f59a57aa9687",
        "builder_tested_source": "b3713154cc1ca587b365ae3647578f791a750e48",
        "builder_tool_blob": "cf267f87aca1dd53e182f306697eb0e15c529769",
        "verdict": VERDICT,
        "reproduced": False,
        "truth_boundary": [
            "same Linux host/filesystem as Wave 126 claim",
            "genuine anchor process/store remain alive and unmodified during attack",
            "only the mutable Unix-socket pathname is unlinked/rebound",
            "fake anchor does not read or possess anchor credential.bin",
            "no witness credential forgery, witness ledger rewrite, anchor ledger rewrite, hash collision, mixed older writer, network namespace replacement, power/device/provider, performance, energy, or retained-compute claim",
        ],
    }

    with tempfile.TemporaryDirectory(prefix="axm-wave126-verifier-") as td:
        b = Path(td)
        wd = b / "witness"
        ad = b / "anchor"
        wsock = b / "witness.sock"
        asock = b / "anchor.sock"
        local = b / "local.jsonl"
        a_ready, a_error = b / "anchor.ready", b / "anchor.error"
        w_ready, w_error = b / "witness.ready", b / "witness.error"

        witness_root = w.initialize_witness_dir(wd, "wave126-verifier-witness")
        witness_fp = witness_root["credential_fingerprint"]
        anchor_root = w126.initialize_anchor_dir(ad, wd, "wave126-verifier-anchor")
        anchor_fp = anchor_root["anchor_credential_fingerprint"]

        p_anchor = p_witness = None
        fake: FakeAnchor | None = None
        try:
            p_anchor = launch_anchor(ad, asock, a_ready, a_error)
            p_witness = launch_witness(wd, wsock, asock, anchor_fp, w_ready, w_error)

            current_a, current_t = h("wave126-verifier-current-a"), h("wave126-verifier-current-t")
            current = w.decide_and_publish(
                wsock, witness_fp, local, current_a, current_t, "COMMIT", True, ""
            )
            current_status = w.status(wsock, witness_fp, local, current_a)
            genuine_before = w126.anchor_request(asock, {"op": "summary"}, anchor_fp)

            if current_status.get("status") != "AUTHORITATIVE_PROCESS_WITNESS_COMMIT":
                raise RuntimeError(f"control-current-not-authoritative:{current_status}")
            if genuine_before.get("anchor_seq") != 1 or current["record"]["seq"] != 1:
                raise RuntimeError(f"control-unexpected-sequence:{genuine_before}:{current}")

            # Core adversarial step: the pinned fingerprint is public metadata, and
            # anchor_request authenticates only by comparing that self-asserted field.
            # The genuine anchor keeps running on its already-open (now unlinked)
            # Unix-socket inode, while a fake process binds the same pathname.
            asock.unlink()
            fake = FakeAnchor(asock, anchor_fp, witness_fp)
            fake.start()

            attack_a, attack_t = h("wave126-verifier-attack-a"), h("wave126-verifier-attack-t")
            attacked = w.decide_and_publish(
                wsock, witness_fp, local, attack_a, attack_t, "COMMIT", True, ""
            )
            attacked_status = w.status(wsock, witness_fp, local, attack_a)

            # Diagnostic read occurs only after the attack. It verifies that the real
            # anchor ledger never advanced even though the witness/client reported an
            # anchored sequence-2 result.
            aroot, asecret, copied_witness_secret = w126.load_anchor_identity(ad)
            genuine_rows = w126.load_anchor_ledger(ad, aroot, asecret, copied_witness_secret)
            _, witness_secret = w.load_identity(wd)
            witness_rows = w.load_ledger(wd, witness_secret)

            report.update({
                "current_control": {
                    "witness_seq": current["record"]["seq"],
                    "anchor_seq": genuine_before.get("anchor_seq"),
                    "status": current_status.get("status"),
                },
                "attack": {
                    "real_anchor_pid_alive": p_anchor.poll() is None,
                    "fake_used_anchor_secret": False,
                    "fake_reconcile_calls": fake.seen,
                    "witness_reply_record_seq": attacked["record"]["seq"],
                    "witness_reply_anchor_seq": attacked.get("anchor_seq"),
                    "witness_reply_anchor_fp": attacked.get("anchor_credential_fingerprint"),
                    "client_status": attacked_status.get("status"),
                    "genuine_anchor_ledger_seq_after": len(genuine_rows),
                    "witness_ledger_seq_after": len(witness_rows),
                    "genuine_anchor_head_after": genuine_rows[-1]["witness_record_sha"] if genuine_rows else "0" * 64,
                    "witness_head_after": witness_rows[-1]["record_sha"] if witness_rows else "0" * 64,
                },
            })

            reproduced = (
                p_anchor.poll() is None
                and attacked["record"]["seq"] == 2
                and attacked.get("anchor_seq") == 2
                and attacked.get("anchor_credential_fingerprint") == anchor_fp
                and attacked_status.get("status") == "AUTHORITATIVE_PROCESS_WITNESS_COMMIT"
                and len(witness_rows) == 2
                and len(genuine_rows) == 1
                and len(fake.seen) >= 3  # pre-decision, post-decision, status/summary
                and any(x["record_count"] == 2 for x in fake.seen)
            )
            report["reproduced"] = reproduced
            if not reproduced:
                raise AssertionError(json.dumps(report, sort_keys=True))
            return report
        finally:
            if fake is not None:
                fake.close()
            kill_proc(p_witness)
            kill_proc(p_anchor)


if __name__ == "__main__":
    out = run()
    print(json.dumps(out, indent=2, sort_keys=True))
