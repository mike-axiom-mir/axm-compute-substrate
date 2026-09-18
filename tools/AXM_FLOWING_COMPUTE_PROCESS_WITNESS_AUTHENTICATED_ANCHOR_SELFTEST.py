#!/usr/bin/env python3
"""Wave 127 adversarial self-test: authenticated anchor response channel."""
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
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_AUTHENTICATED_ANCHOR as w127

TOOL = Path(w127.__file__).resolve()


def h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def check(report: dict, name: str, ok: bool, detail=None) -> None:
    report["controls"].append({"name": name, "ok": bool(ok), "detail": detail})
    if not ok:
        report["failed"] += 1


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


def launch_anchor(anchor_dir: Path, sock: Path, ready: Path, error: Path) -> tuple[subprocess.Popen, dict]:
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
                   anchor_fp: str, ready: Path, error: Path) -> tuple[subprocess.Popen, dict]:
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


def raw_anchor_rpc(sock: Path, request: dict) -> dict:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(3.0)
        s.connect(str(sock))
        s.sendall(w.canonical(request) + b"\n")
        data = b""
        while not data.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            data += chunk
    if not data:
        raise ConnectionError("no-anchor-response")
    return json.loads(data)


class SubstituteAnchor:
    """Pathname substitute that owns no Wave 127 private response key."""

    def __init__(self, sock: Path, mode: str, anchor_fp: str,
                 witness_fp: str, replay: dict | None = None):
        self.sock = sock
        self.mode = mode
        self.anchor_fp = anchor_fp
        self.witness_fp = witness_fp
        self.replay = replay
        self.seen: list[dict] = []
        self.ready = threading.Event()
        self.stop = threading.Event()
        self.error: str | None = None
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self.thread.start()
        if not self.ready.wait(5):
            raise TimeoutError("substitute-anchor-not-ready")
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
                    self.seen.append(request)
                    if self.mode == "replay" and self.replay is not None:
                        out = self.replay
                    else:
                        payload = request.get("payload") if isinstance(request, dict) else {}
                        records = payload.get("records") if isinstance(payload, dict) else []
                        records = records or []
                        head = records[-1]["record_sha"] if records else "0" * 64
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
        "wave": 127,
        "title": "authenticated anchor response channel",
        "source": w127.SOURCE,
        "controls": [],
        "failed": 0,
        "truth_boundary": [
            "same Linux/OpenSSL host path as Wave 126 with separate witness and anchor processes/stores",
            "anchor response signing key is private to anchor store; witness receives only public verifier material",
            "fresh request nonce + request digest + exact response body + exact anchor identity are signed together",
            "Unix-socket pathname substitution without the response private key must fail before witness append",
            "old signed response replay and signed-body splicing must fail closed",
            "witness-side public verifier provisioning/rollback, whole-domain rollback, private-key compromise, device/kernel/provider failure remain unproved",
            "no performance, energy, retained/incremental/dormant-compute, merge, or CANON claim",
        ],
    }

    with tempfile.TemporaryDirectory(prefix="axm-wave127-") as td:
        b = Path(td)
        wd = b / "witness"
        ad = b / "anchor"
        wsock = b / "witness.sock"
        asock = b / "anchor.sock"
        local = b / "local.jsonl"

        witness_root = w.initialize_witness_dir(wd, "wave127-main")
        witness_fp = witness_root["credential_fingerprint"]
        anchor_root = w127.initialize_anchor_dir(ad, wd, "wave127-anchor")
        anchor_fp = anchor_root["anchor_credential_fingerprint"]
        binding, public_key = w127.load_response_binding(wd, anchor_fp)

        p_anchor = p_witness = None
        fake = None
        try:
            p_anchor, ainfo = launch_anchor(
                ad, asock, b / "anchor.ready", b / "anchor.error"
            )
            p_witness, winfo = launch_witness(
                wd, wsock, asock, anchor_fp, b / "witness.ready", b / "witness.error"
            )
            check(
                report,
                "separate_processes_and_asymmetric_response_identity_active",
                p_anchor.pid != p_witness.pid
                and ainfo.get("authenticated_response_channel") is True
                and winfo.get("authenticated_anchor_response") is True
                and ainfo.get("response_public_fingerprint")
                == binding["response_public_fingerprint"]
                == winfo.get("response_public_fingerprint"),
                {"anchor_ready": ainfo, "witness_ready": winfo},
            )

            a1, t1 = h("wave127-control-a1"), h("wave127-control-t1")
            first = w.decide_and_publish(
                wsock, witness_fp, local, a1, t1, "COMMIT", True, ""
            )
            first_status = w.status(wsock, witness_fp, local, a1)
            aroot, asecret, copied_witness_secret = w126.load_anchor_identity(ad)
            anchor_rows = w126.load_anchor_ledger(
                ad, aroot, asecret, copied_witness_secret
            )
            check(
                report,
                "genuine_commit_reaches_authenticated_anchor",
                first["record"]["seq"] == 1
                and len(anchor_rows) == 1
                and first_status.get("status") == "AUTHORITATIVE_PROCESS_WITNESS_COMMIT",
                {"status": first_status, "anchor_seq": len(anchor_rows)},
            )

            fixed_request = w127._request_envelope(
                {"op": "summary"}, "11" * 32
            )
            signed_summary = raw_anchor_rpc(asock, fixed_request)
            verified_summary = w127._verify_response(
                signed_summary, fixed_request, anchor_fp, public_key
            )
            check(
                report,
                "genuine_signed_response_verifies",
                verified_summary.get("ok") is True
                and verified_summary.get("anchor_seq") == 1,
                verified_summary,
            )

            asock.unlink()
            fake = SubstituteAnchor(asock, "unsigned", anchor_fp, witness_fp)
            fake.start()
            before_witness_rows = len(w.load_ledger(wd, w.load_identity(wd)[1]))
            a2, t2 = h("wave127-attack-a2"), h("wave127-attack-t2")
            blocked_detail = ""
            try:
                w.decide_and_publish(
                    wsock, witness_fp, local, a2, t2, "COMMIT", True, ""
                )
                unsigned_blocked = False
            except Exception as exc:
                blocked_detail = f"{type(exc).__name__}:{exc}"
                unsigned_blocked = "anchor-response-" in blocked_detail
            after_witness_rows = len(w.load_ledger(wd, w.load_identity(wd)[1]))
            anchor_rows_after = w126.load_anchor_ledger(
                ad, aroot, asecret, copied_witness_secret
            )
            check(
                report,
                "unsigned_socket_substitution_fails_before_witness_append",
                unsigned_blocked
                and after_witness_rows == before_witness_rows == 1
                and len(anchor_rows_after) == 1
                and p_anchor.poll() is None,
                {
                    "error": blocked_detail,
                    "fake_requests": len(fake.seen),
                    "witness_rows": after_witness_rows,
                    "genuine_anchor_rows": len(anchor_rows_after),
                    "genuine_anchor_alive": p_anchor.poll() is None,
                },
            )
            fake.close()
            fake = None

            hard_kill(p_anchor)
            p_anchor, restart_info = launch_anchor(
                ad, asock, b / "anchor.restart.ready", b / "anchor.restart.error"
            )
            check(
                report,
                "legitimate_anchor_restart_preserves_response_identity_and_seq",
                restart_info.get("response_public_fingerprint")
                == binding["response_public_fingerprint"]
                and restart_info.get("anchor_seq") == 1,
                restart_info,
            )

            hard_kill(p_anchor)
            if asock.exists():
                asock.unlink()
            fake = SubstituteAnchor(
                asock, "replay", anchor_fp, witness_fp, replay=signed_summary
            )
            fake.start()
            replay_detail = ""
            try:
                w.request(wsock, {"op": "ping"}, witness_fp)
                replay_blocked = False
            except Exception as exc:
                replay_detail = f"{type(exc).__name__}:{exc}"
                replay_blocked = (
                    "anchor-response-nonce-mismatch" in replay_detail
                    or "anchor-response-request-digest-mismatch" in replay_detail
                )
            check(
                report,
                "old_signed_response_replay_is_rejected",
                replay_blocked,
                {"error": replay_detail, "fake_requests": len(fake.seen)},
            )
            fake.close()
            fake = None

            tampered = json.loads(json.dumps(signed_summary))
            tampered["body"]["anchor_seq"] = 999
            tampered["body"]["witness_record_sha"] = "f" * 64
            splice_detail = ""
            try:
                w127._verify_response(tampered, fixed_request, anchor_fp, public_key)
                splice_blocked = False
            except Exception as exc:
                splice_detail = f"{type(exc).__name__}:{exc}"
                splice_blocked = "anchor-response-signature-invalid" in splice_detail
            check(
                report,
                "signed_head_sequence_splicing_is_rejected",
                splice_blocked,
                splice_detail,
            )

            p_anchor, _ = launch_anchor(
                ad, asock, b / "anchor.final.ready", b / "anchor.final.error"
            )
            second = w.decide_and_publish(
                wsock, witness_fp, local, a2, t2, "COMMIT", True, ""
            )
            second_status = w.status(wsock, witness_fp, local, a2)
            anchor_final = w127.anchor_request(
                asock, {"op": "summary"}, anchor_fp, public_key
            )
            check(
                report,
                "exact_legitimate_retry_after_attacks_commits_cleanly",
                second["record"]["seq"] == 2
                and anchor_final.get("anchor_seq") == 2
                and second_status.get("status") == "AUTHORITATIVE_PROCESS_WITNESS_COMMIT",
                {"status": second_status, "anchor": anchor_final},
            )

            original_public = public_key.read_bytes()
            _, unrelated_public = w127._generate_response_keypair()
            w._atomic_write(public_key, unrelated_public, 0o600)
            verifier_detail = ""
            try:
                w127.load_response_binding(wd, anchor_fp)
                verifier_blocked = False
            except Exception as exc:
                verifier_detail = f"{type(exc).__name__}:{exc}"
                verifier_blocked = "anchor-response-public-key-mismatch" in verifier_detail
            w._atomic_write(public_key, original_public, 0o600)
            check(
                report,
                "witness_public_verifier_substitution_is_detected",
                verifier_blocked,
                verifier_detail,
            )

        finally:
            if fake is not None:
                fake.close()
            stop_witness(p_witness, wsock)
            hard_kill(p_anchor)

    report["passed"] = len(report["controls"]) - report["failed"]
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report")
    ns = ap.parse_args()
    report = run()
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if ns.report:
        Path(ns.report).write_text(text + "\n")
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
