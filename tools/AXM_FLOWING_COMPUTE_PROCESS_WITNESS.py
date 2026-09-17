#!/usr/bin/env python3
"""AXM Flowing Compute Wave 123: separate-process durable outcome witness.

Experimental lane only. Moves bounded COMMIT / stable-REJECT / retriable-HOLD
witnessing into a separate OS process with its own credential and append-only,
fsync'd JSONL ledger.

Truth boundary: one host/filesystem only; fsync is not proof against power,
device/controller/kernel failure. The client must preserve the pinned witness
credential fingerprint. Whole-domain replacement including that pin remains a
counterexample. No network/provider independence, Byzantine consensus,
performance, energy, retained/incremental/dormant-compute or physical-finality
claim. No automatic merge or CANON promotion.
"""
from __future__ import annotations

import argparse, hashlib, hmac, json, os, secrets, socket, stat, time
from pathlib import Path
from typing import Any

SCHEMA_ROOT = "axm.flowing-compute.process-witness-root.v1"
SCHEMA_RECORD = "axm.flowing-compute.process-witness-record.v1"
SCHEMA_LOCAL = "axm.flowing-compute.process-witness-local.v1"
DECISIONS = {"COMMIT", "REJECT", "HOLD"}
TERMINAL = {"COMMIT", "REJECT"}
SOURCE = {
    "wave122_evidence_head": "41f1719b48aace2c5db5ae68cadb9ccbce14970d",
    "wave122_tested_source_commit": "5ebe63488494c6767637b82407be8675d1fcca52",
    "wave122_tool_blob": "78df9135f97e568e64ef37b83d743d6475a8adee",
    "wave122_selftest_blob": "1818037e4e017f69c98f1e269b08fc3d2de66071",
    "wave122_ci_run": 35278477192,
    "wave122_artifact_sha256": "1bc3634aaff202d7da051a3fcbf3841ec6a2b8a50121fd7c3e679142ef98e8d9",
}


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fsync_dir(path: Path) -> None:
    fd = os.open(str(path), os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


def _atomic_write(path: Path, data: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}-{secrets.token_hex(4)}")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        os.write(fd, data); os.fsync(fd)
    finally: os.close(fd)
    os.replace(tmp, path); os.chmod(path, mode); _fsync_dir(path.parent)


def _append_fsync(path: Path, line: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, line); os.fsync(fd)
    finally: os.close(fd)
    _fsync_dir(path.parent)


def credential_fingerprint(secret: bytes) -> str:
    return sha256_hex(b"AXM-W123-WITNESS-CREDENTIAL\0" + secret)


def initialize_witness_dir(witness_dir: str | Path, witness_id: str = "wave123-witness") -> dict:
    d = Path(witness_dir); d.mkdir(parents=True, exist_ok=True)
    if any((d / n).exists() for n in ("root.json", "credential.bin", "ledger.jsonl")):
        raise FileExistsError("witness directory is not empty")
    secret = secrets.token_bytes(32); fp = credential_fingerprint(secret)
    root = {"schema": SCHEMA_ROOT, "witness_id": witness_id, "credential_fingerprint": fp}
    _atomic_write(d / "credential.bin", secret, 0o600)
    _atomic_write(d / "root.json", canonical(root) + b"\n")
    _atomic_write(d / "ledger.jsonl", b"", 0o600)
    return root


def load_identity(witness_dir: str | Path) -> tuple[dict, bytes]:
    d = Path(witness_dir)
    root = json.loads((d / "root.json").read_text())
    secret = (d / "credential.bin").read_bytes()
    if root.get("schema") != SCHEMA_ROOT: raise ValueError("witness-root-schema-mismatch")
    if not hmac.compare_digest(str(root.get("credential_fingerprint", "")), credential_fingerprint(secret)):
        raise ValueError("witness-credential-root-mismatch")
    if stat.S_IMODE((d / "credential.bin").stat().st_mode) & 0o077:
        raise ValueError("witness-credential-permissions-too-broad")
    return root, secret


def _unsigned(seq: int, prev: str, req: dict) -> dict:
    decision, stable, reason = req.get("decision"), bool(req.get("stable")), str(req.get("reason", ""))
    if decision not in DECISIONS: raise ValueError("unknown-witness-decision")
    if decision in TERMINAL and not stable: raise ValueError("terminal-outcome-must-be-stable")
    if decision == "HOLD" and stable: raise ValueError("hold-must-remain-retriable")
    if decision in {"REJECT", "HOLD"} and not reason: raise ValueError("non-commit-outcome-requires-reason")
    vals = {k: str(req.get(k, "")) for k in ("authority_sha", "transition_sha", "proposal_sha")}
    for k, v in vals.items():
        if len(v) != 64 or any(c not in "0123456789abcdef" for c in v): raise ValueError(f"invalid-{k}")
    return {"schema": SCHEMA_RECORD, "seq": seq, "prev_record_sha": prev, **vals,
            "decision": decision, "stable": stable, "reason": reason}


def _seal(unsigned: dict, secret: bytes) -> dict:
    sig = hmac.new(secret, canonical(unsigned), hashlib.sha256).hexdigest()
    body = {**unsigned, "signature": sig}
    return {**body, "record_sha": sha256_hex(canonical(body))}


def _verify(record: dict, secret: bytes, seq: int, prev: str) -> None:
    if record.get("schema") != SCHEMA_RECORD or record.get("seq") != seq or record.get("prev_record_sha") != prev:
        raise ValueError("ledger-chain-position-mismatch")
    keys = ("schema", "seq", "prev_record_sha", "authority_sha", "transition_sha", "proposal_sha", "decision", "stable", "reason")
    body = {k: record[k] for k in keys}
    sig = hmac.new(secret, canonical(body), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(str(record.get("signature", "")), sig): raise ValueError("ledger-record-signature-mismatch")
    signed = {**body, "signature": record["signature"]}
    if not hmac.compare_digest(str(record.get("record_sha", "")), sha256_hex(canonical(signed))): raise ValueError("ledger-record-sha-mismatch")
    if record["decision"] not in DECISIONS: raise ValueError("ledger-unknown-decision")
    if record["decision"] in TERMINAL and record["stable"] is not True: raise ValueError("ledger-terminal-not-stable")
    if record["decision"] == "HOLD" and record["stable"] is not False: raise ValueError("ledger-hold-became-stable")


def load_ledger(witness_dir: str | Path, secret: bytes) -> list[dict]:
    p = Path(witness_dir) / "ledger.jsonl"; raw = p.read_bytes() if p.exists() else b""
    if raw and not raw.endswith(b"\n"): raise ValueError("ledger-truncated-tail")
    out, prev, terminal = [], "0" * 64, set()
    for seq, line in enumerate(raw.splitlines(), 1):
        try: r = json.loads(line)
        except Exception as exc: raise ValueError("ledger-json-corrupt") from exc
        _verify(r, secret, seq, prev)
        key = (r["authority_sha"], r["transition_sha"])
        if r["decision"] in TERMINAL:
            if key in terminal: raise ValueError("ledger-terminal-outcome-not-unique")
            terminal.add(key)
        out.append(r); prev = r["record_sha"]
    return out


def decide(witness_dir: str | Path, root: dict, secret: bytes, req: dict, allow_fault: bool = False) -> dict:
    records = load_ledger(witness_dir, secret)
    for r in records:
        if all(r.get(k) == req.get(k) for k in ("authority_sha", "transition_sha", "proposal_sha", "decision", "stable", "reason")):
            return {"ok": True, "idempotent": True, "credential_fingerprint": root["credential_fingerprint"], "record": r}
    key = (req.get("authority_sha"), req.get("transition_sha"))
    if any((r["authority_sha"], r["transition_sha"]) == key and r["decision"] in TERMINAL for r in records):
        raise ValueError("terminal-outcome-conflict")
    r = _seal(_unsigned(len(records) + 1, records[-1]["record_sha"] if records else "0" * 64, req), secret)
    fault, marker = req.get("fault"), req.get("fault_marker")
    if fault and not allow_fault: raise ValueError("fault-injection-disabled")
    if fault == "pause_before_append":
        Path(marker).write_text(str(os.getpid()))
        while True: time.sleep(1)
    _append_fsync(Path(witness_dir) / "ledger.jsonl", canonical(r) + b"\n")
    if fault == "pause_after_fsync":
        Path(marker).write_text(str(os.getpid()))
        while True: time.sleep(1)
    return {"ok": True, "idempotent": False, "credential_fingerprint": root["credential_fingerprint"], "record": r}


def summary(witness_dir: str | Path, root: dict, secret: bytes, authority_sha: str | None = None) -> dict:
    rs = load_ledger(witness_dir, secret)
    if authority_sha is not None: rs = [r for r in rs if r["authority_sha"] == authority_sha]
    return {"ok": True, "credential_fingerprint": root["credential_fingerprint"], "records": rs,
            "last_seq": rs[-1]["seq"] if rs else 0, "terminal_records": [r for r in rs if r["decision"] in TERMINAL]}


def serve(witness_dir: str | Path, socket_path: str | Path, ready_file: str | Path | None = None,
          error_file: str | Path | None = None, allow_fault: bool = False) -> int:
    sp = Path(socket_path)
    try:
        root, secret = load_identity(witness_dir); load_ledger(witness_dir, secret)
        if sp.exists(): sp.unlink()
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.bind(str(sp)); s.listen(16)
        if ready_file: _atomic_write(Path(ready_file), canonical({"pid": os.getpid(), "credential_fingerprint": root["credential_fingerprint"]}) + b"\n")
        running = True
        while running:
            conn, _ = s.accept()
            with conn:
                try:
                    data = b""
                    while not data.endswith(b"\n"):
                        chunk = conn.recv(65536)
                        if not chunk: break
                        data += chunk
                    req = json.loads(data)
                    op = req.get("op")
                    if op == "ping": out = {"ok": True, "pid": os.getpid(), "credential_fingerprint": root["credential_fingerprint"]}
                    elif op == "decide": out = decide(witness_dir, root, secret, req, allow_fault)
                    elif op == "summary": out = summary(witness_dir, root, secret, req.get("authority_sha"))
                    elif op == "stop": out, running = {"ok": True, "stopping": True, "credential_fingerprint": root["credential_fingerprint"]}, False
                    else: raise ValueError("unknown-operation")
                    conn.sendall(canonical(out) + b"\n")
                except Exception as exc:
                    try: conn.sendall(canonical({"ok": False, "error": f"{type(exc).__name__}:{exc}", "credential_fingerprint": root["credential_fingerprint"]}) + b"\n")
                    except OSError: pass
        s.close()
        if sp.exists(): sp.unlink()
        return 0
    except BaseException as exc:
        if error_file:
            try: Path(error_file).write_text(f"{type(exc).__name__}:{exc}\n")
            except Exception: pass
        return 2


def request(socket_path: str | Path, payload: dict, expected_fp: str | None = None, timeout: float = 5.0) -> dict:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout); s.connect(str(socket_path)); s.sendall(canonical(payload) + b"\n"); data = b""
        while not data.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk: break
            data += chunk
    if not data: raise ConnectionError("witness-disconnected-without-response")
    out = json.loads(data)
    if expected_fp is not None and not hmac.compare_digest(str(out.get("credential_fingerprint")), expected_fp):
        raise PermissionError("witness-credential-fingerprint-mismatch")
    if not out.get("ok"): raise ValueError(out.get("error", "witness-request-failed"))
    return out


def proposal_sha(authority_sha: str, transition_sha: str, decision: str, stable: bool, reason: str) -> str:
    return sha256_hex(canonical({"authority_sha": authority_sha, "transition_sha": transition_sha,
                                 "decision": decision, "stable": bool(stable), "reason": reason}))


def read_local_journal(path: str | Path) -> list[dict]:
    p = Path(path)
    if not p.exists(): return []
    raw = p.read_bytes()
    if raw and not raw.endswith(b"\n"): raise ValueError("local-journal-truncated-tail")
    out, prev = [], "0" * 64
    for seq, line in enumerate(raw.splitlines(), 1):
        r = json.loads(line)
        if r.get("schema") != SCHEMA_LOCAL or r.get("seq") != seq or r.get("prev_local_sha") != prev:
            raise ValueError("local-journal-chain-position-mismatch")
        keys = ("schema", "seq", "prev_local_sha", "witness_credential_fingerprint", "witness_record_sha", "witness_seq", "authority_sha", "transition_sha", "proposal_sha", "decision")
        body = {k: r[k] for k in keys}
        if sha256_hex(canonical(body)) != r.get("local_sha"): raise ValueError("local-journal-sha-mismatch")
        out.append(r); prev = r["local_sha"]
    return out


def append_local_receipt(path: str | Path, wr: dict, fp: str) -> dict:
    rows = read_local_journal(path)
    body = {"schema": SCHEMA_LOCAL, "seq": len(rows) + 1, "prev_local_sha": rows[-1]["local_sha"] if rows else "0" * 64,
            "witness_credential_fingerprint": fp, "witness_record_sha": wr["record_sha"], "witness_seq": wr["seq"],
            "authority_sha": wr["authority_sha"], "transition_sha": wr["transition_sha"], "proposal_sha": wr["proposal_sha"], "decision": wr["decision"]}
    row = {**body, "local_sha": sha256_hex(canonical(body))}; _append_fsync(Path(path), canonical(row) + b"\n"); return row


def decide_and_publish(socket_path, fp, local_journal, authority_sha, transition_sha, decision, stable, reason,
                       fault=None, fault_marker=None, pause_after_witness=None, pause_after_local=None):
    psha = proposal_sha(authority_sha, transition_sha, decision, stable, reason)
    req = {"op": "decide", "authority_sha": authority_sha, "transition_sha": transition_sha, "proposal_sha": psha,
           "decision": decision, "stable": bool(stable), "reason": reason}
    if fault: req.update(fault=fault, fault_marker=fault_marker)
    out = request(socket_path, req, fp)
    if pause_after_witness:
        Path(pause_after_witness).write_text(str(os.getpid()))
        while True: time.sleep(1)
    if decision in TERMINAL:
        rows = read_local_journal(local_journal)
        if not any(r["witness_record_sha"] == out["record"]["record_sha"] for r in rows): append_local_receipt(local_journal, out["record"], fp)
    if pause_after_local:
        Path(pause_after_local).write_text(str(os.getpid()))
        while True: time.sleep(1)
    return out


def status(socket_path, fp, local_journal, authority_sha) -> dict:
    try: rows = read_local_journal(local_journal)
    except Exception as exc: return {"status": "HOLD_LOCAL_CORRUPT", "detail": f"{type(exc).__name__}:{exc}"}
    try: remote = request(socket_path, {"op": "summary", "authority_sha": authority_sha}, fp)
    except PermissionError as exc: return {"status": "HOLD_WITNESS_CREDENTIAL_MISMATCH", "detail": str(exc)}
    except Exception as exc: return {"status": "HOLD_WITNESS_UNAVAILABLE", "detail": f"{type(exc).__name__}:{exc}"}
    terms = remote["terminal_records"]
    if not terms: return {"status": "HOLD_NO_TERMINAL_OUTCOME", "witness_last_seq": remote["last_seq"]}
    latest = terms[-1]; local = [r for r in rows if r["authority_sha"] == authority_sha]
    if not local: return {"status": "HOLD_WITNESS_AHEAD", "witness_record": latest}
    local = local[-1]
    if local["witness_credential_fingerprint"] != fp: return {"status": "HOLD_LOCAL_WITNESS_IDENTITY_MISMATCH"}
    if local["witness_seq"] < latest["seq"]: return {"status": "HOLD_WITNESS_AHEAD", "witness_record": latest, "local_record": local}
    if local["witness_record_sha"] != latest["record_sha"] or local["proposal_sha"] != latest["proposal_sha"]:
        return {"status": "HOLD_LOCAL_DIVERGED", "witness_record": latest, "local_record": local}
    return {"status": "AUTHORITATIVE_PROCESS_WITNESS_COMMIT" if latest["decision"] == "COMMIT" else "REJECTED_PROCESS_WITNESS",
            "witness_record": latest, "local_record": local}


def recover_exact(socket_path, fp, local_journal, authority_sha, transition_sha, expected_proposal_sha) -> dict:
    remote = request(socket_path, {"op": "summary", "authority_sha": authority_sha}, fp)
    matches = [r for r in remote["terminal_records"] if r["transition_sha"] == transition_sha]
    if len(matches) != 1: raise ValueError("recovery-terminal-outcome-not-unique")
    r = matches[0]
    if r["proposal_sha"] != expected_proposal_sha: raise ValueError("recovery-proposal-identity-mismatch")
    rows = read_local_journal(local_journal)
    if any(x["witness_record_sha"] == r["record_sha"] for x in rows): return {"recovered": False, "idempotent": True, "record": r}
    append_local_receipt(local_journal, r, fp); return {"recovered": True, "idempotent": False, "record": r}


def main() -> int:
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("witness_dir"); p.add_argument("--witness-id", default="wave123-witness")
    p = sub.add_parser("serve"); p.add_argument("witness_dir"); p.add_argument("socket_path"); p.add_argument("--ready-file"); p.add_argument("--error-file"); p.add_argument("--allow-fault-injection", action="store_true")
    p = sub.add_parser("transact"); p.add_argument("socket_path"); p.add_argument("expected_fp"); p.add_argument("local_journal"); p.add_argument("authority_sha"); p.add_argument("transition_sha"); p.add_argument("decision", choices=sorted(DECISIONS)); p.add_argument("stable", choices=["true", "false"]); p.add_argument("reason"); p.add_argument("--fault"); p.add_argument("--fault-marker"); p.add_argument("--pause-after-witness"); p.add_argument("--pause-after-local")
    ns = ap.parse_args()
    if ns.cmd == "init": print(json.dumps(initialize_witness_dir(ns.witness_dir, ns.witness_id), sort_keys=True)); return 0
    if ns.cmd == "serve": return serve(ns.witness_dir, ns.socket_path, ns.ready_file, ns.error_file, ns.allow_fault_injection)
    out = decide_and_publish(ns.socket_path, ns.expected_fp, ns.local_journal, ns.authority_sha, ns.transition_sha, ns.decision,
                             ns.stable == "true", ns.reason, ns.fault, ns.fault_marker, ns.pause_after_witness, ns.pause_after_local)
    print(json.dumps(out, sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
