#!/usr/bin/env python3
"""AXM Flowing Compute Wave 99: registry-bound three-witness quorum + monotonic-store checks.

Additive experiment over the exact Wave 98 local checkpoint/signature primitives. This wave repairs
verifier PR #23's duplicate-witness and mutable-head counterexamples before any claim of physical
failure-domain separation. All three remote witnesses are still modeled in one Python process.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import statistics
import time
from copy import deepcopy

import AXM_FLOWING_COMPUTE_DUAL_REMOTE_WITNESS as w98

REMOTE_IDS = ("remote-a", "remote-b", "remote-c")
QUORUM = 2
SRC = {
    "wave98_head": "56bb92218f9af62aceacee1ee625755b8ef54789",
    "wave98_tool_blob": "bc4347a75f04f6d9ff97e58128d2f5f0a16c85a1",
    "wave98_report_blob": "397e1023f1ec1e233e3b0a6943d4b6e62854512b",
    "verifier_pr": 23,
    "verifier_head": "ac4929e3404a14b6fe6d902f4c923b16a31427b5",
    "verifier_evidence_blob": "5933c0c720507e4a760b2166eedfe07973942632",
}


def H(x: bytes) -> str:
    return hashlib.sha256(x).hexdigest()


def binding(app_state_sha: str, registry_sha: str) -> str:
    return w98.D({
        "schema": "authority-state-binding/w99-v1",
        "app_state_sha": app_state_sha,
        "remote_registry_sha": registry_sha,
    })


def make_registry(slots: dict, generation: int = 0, predecessor_registry_sha: str | None = None) -> dict:
    return w98.seal({
        "schema": "remote-witness-registry/w99-v1",
        "generation": generation,
        "predecessor_registry_sha": predecessor_registry_sha,
        "quorum": QUORUM,
        "slots": deepcopy(slots),
        "registry_sha": "",
    }, "registry_sha")


def validate_registry(registry: dict, store: dict, expected_sha: str | None = None) -> dict:
    w98.chk(registry, "registry_sha")
    if expected_sha is not None and registry["registry_sha"] != expected_sha:
        raise ValueError("registry key/body mismatch")
    if registry.get("schema") != "remote-witness-registry/w99-v1":
        raise ValueError("registry schema mismatch")
    if registry.get("quorum") != QUORUM:
        raise ValueError("registry quorum mismatch")
    if set(registry.get("slots", {})) != set(REMOTE_IDS):
        raise ValueError("registry slot set mismatch")
    service_ids, credentials, domains = [], [], []
    for slot in REMOTE_IDS:
        row = registry["slots"][slot]
        if set(row) != {"service_id", "credential_hash", "failure_domain_id"}:
            raise ValueError("registry row shape mismatch")
        if row["service_id"] != slot:
            raise ValueError("registry slot/service mismatch")
        service_ids.append(row["service_id"])
        credentials.append(row["credential_hash"])
        domains.append(row["failure_domain_id"])
    if len(set(service_ids)) != len(service_ids):
        raise ValueError("duplicate service identity")
    if len(set(credentials)) != len(credentials):
        raise ValueError("duplicate credential identity")
    if len(set(domains)) != len(domains):
        raise ValueError("duplicate failure-domain identity")
    if registry["generation"] == 0:
        if registry["predecessor_registry_sha"] is not None:
            raise ValueError("registry genesis predecessor mismatch")
    else:
        pred_sha = registry["predecessor_registry_sha"]
        if pred_sha not in store:
            raise ValueError("registry predecessor missing")
        pred = deepcopy(store[pred_sha])
        validate_registry(pred, store, pred_sha)
        if registry["generation"] != pred["generation"] + 1:
            raise ValueError("registry generation discontinuity")
    return registry


def get_registry(store: dict, sha: str) -> dict:
    if sha not in store:
        raise ValueError("registry body missing")
    reg = deepcopy(store[sha])
    return validate_registry(reg, store, sha)


def put_registry(store: dict, reg: dict) -> str:
    validate_registry(reg, store)
    sha = reg["registry_sha"]
    if sha in store and store[sha] != reg:
        raise ValueError("registry collision")
    store[sha] = deepcopy(reg)
    return sha


def rotate_registry_credential(store: dict, current_sha: str, slot: str, new_credential_hash: str) -> dict:
    current = get_registry(store, current_sha)
    if slot not in REMOTE_IDS:
        raise ValueError("unknown slot")
    slots = deepcopy(current["slots"])
    if slots[slot]["credential_hash"] == new_credential_hash:
        raise ValueError("credential did not rotate")
    slots[slot]["credential_hash"] = new_credential_hash
    successor = make_registry(slots, current["generation"] + 1, current_sha)
    put_registry(store, successor)
    return successor


def remote_record(service_id: str, seq: int, authority_epoch: int, authority_sha: str,
                  checkpoint_sha: str, registry_sha: str, previous_record_sha: str | None,
                  kind: str = "NORMAL", recovery_from_record_sha: str | None = None,
                  predecessor_registry_sha: str | None = None) -> dict:
    return w98.seal({
        "schema": "axm-remote-anchor/w99-v1",
        "service_id": service_id,
        "seq": seq,
        "authority_epoch": authority_epoch,
        "authority_sha": authority_sha,
        "checkpoint_sha": checkpoint_sha,
        "registry_sha": registry_sha,
        "kind": kind,
        "recovery_from_record_sha": recovery_from_record_sha,
        "predecessor_registry_sha": predecessor_registry_sha,
        "previous_record_sha": previous_record_sha,
        "record_sha": "",
    }, "record_sha")


def verify_service_identity(service: dict, slot: str, row: dict) -> None:
    if service.get("schema") != "modeled-remote-service/w99-v1":
        raise ValueError("remote service schema mismatch")
    if service.get("service_id") != slot or service.get("service_id") != row["service_id"]:
        raise ValueError("remote slot/service identity mismatch")
    if service.get("credential_hash") != row["credential_hash"]:
        raise ValueError("remote credential identity mismatch")
    if service.get("failure_domain_id") != row["failure_domain_id"]:
        raise ValueError("remote failure-domain identity mismatch")
    if not isinstance(service.get("records"), dict):
        raise ValueError("remote record store shape mismatch")


def verify_remote_full(service: dict, slot: str, row: dict) -> dict | None:
    verify_service_identity(service, slot, row)
    records = service["records"]
    if not records:
        if service.get("head") is not None:
            raise ValueError("remote empty-store head mismatch")
        return None
    by_seq = {}
    for key, body in records.items():
        rec = deepcopy(body)
        w98.chk(rec, "record_sha")
        if rec["record_sha"] != key:
            raise ValueError("remote record key/body mismatch")
        if rec.get("schema") != "axm-remote-anchor/w99-v1" or rec.get("service_id") != slot:
            raise ValueError("remote record identity mismatch")
        seq = rec.get("seq")
        if not isinstance(seq, int) or seq < 1 or seq in by_seq:
            raise ValueError("remote sequence invalid/duplicate")
        if rec.get("kind") not in ("NORMAL", "RECOVERY"):
            raise ValueError("remote record kind mismatch")
        by_seq[seq] = rec
    n = len(by_seq)
    if set(by_seq) != set(range(1, n + 1)):
        raise ValueError("remote sequence discontinuity")
    for seq in range(1, n + 1):
        rec = by_seq[seq]
        expected_prev = None if seq == 1 else by_seq[seq - 1]["record_sha"]
        if rec["previous_record_sha"] != expected_prev:
            raise ValueError("remote predecessor mismatch")
        if rec["kind"] == "NORMAL":
            if rec["recovery_from_record_sha"] is not None or rec["predecessor_registry_sha"] is not None:
                raise ValueError("normal record carries recovery fields")
        else:
            if seq == 1 or rec["recovery_from_record_sha"] != expected_prev or rec["predecessor_registry_sha"] is None:
                raise ValueError("recovery binding mismatch")
    max_head = by_seq[n]
    if service.get("head") != max_head["record_sha"]:
        raise ValueError("remote head is not maximal committed record")
    return deepcopy(max_head)


def append_raw(service: dict, slot: str, row: dict, token: bytes, authority_epoch: int,
               authority_sha: str, checkpoint_sha: str, registry_sha: str,
               kind: str = "NORMAL", predecessor_registry_sha: str | None = None) -> str:
    if not service.get("online"):
        return "UNAVAILABLE"
    try:
        prev = verify_remote_full(service, slot, row)
    except Exception:
        return "REMOTE_CORRUPT"
    if H(token) != row["credential_hash"] or H(token) != service["credential_hash"]:
        return "AUTH_FAIL"
    if prev and prev["authority_epoch"] == authority_epoch and prev["authority_sha"] == authority_sha \
            and prev["checkpoint_sha"] == checkpoint_sha and prev["registry_sha"] == registry_sha:
        return "ALREADY_CURRENT"
    prev_sha = None if prev is None else prev["record_sha"]
    rec = remote_record(
        slot, 1 if prev is None else prev["seq"] + 1, authority_epoch, authority_sha,
        checkpoint_sha, registry_sha, prev_sha, kind,
        prev_sha if kind == "RECOVERY" else None,
        predecessor_registry_sha if kind == "RECOVERY" else None,
    )
    w98.put(service["records"], rec, "record_sha")
    service["head"] = rec["record_sha"]
    return "APPENDED"


def fixture() -> tuple:
    st, priv, boot, rt, _, _ = w98.fixture()
    tokens, services, slots = {}, {}, {}
    for i, slot in enumerate(REMOTE_IDS):
        token = secrets.token_bytes(32)
        tokens[slot] = token
        domain = f"modeled-failure-domain-{i + 1}"
        slots[slot] = {
            "service_id": slot,
            "credential_hash": H(token),
            "failure_domain_id": domain,
        }
        services[slot] = {
            "schema": "modeled-remote-service/w99-v1",
            "service_id": slot,
            "credential_hash": H(token),
            "failure_domain_id": domain,
            "online": True,
            "head": None,
            "records": {},
        }
    registry_store = {}
    registry = make_registry(slots)
    put_registry(registry_store, registry)
    rt["app_state_sha"] = rt["state_sha"]
    rt["remote_registry_sha"] = registry["registry_sha"]
    rt["state_sha"] = binding(rt["app_state_sha"], rt["remote_registry_sha"])
    return st, priv, boot, rt, services, tokens, registry_store


def current_local(rt: dict, st: dict, boot: dict):
    status, link, cp = w98.local_status(rt, st, boot)
    return status, link, cp


def authority(rt: dict, st: dict, boot: dict, services: dict, registry_store: dict) -> str:
    try:
        reg = get_registry(registry_store, rt["remote_registry_sha"])
    except Exception:
        return "HOLD_REGISTRY"
    if set(services) != set(REMOTE_IDS):
        return "HOLD_REMOTE_SET"
    # Detect the exact PR #23 alias attack even before body checks.
    if len({id(services[slot]) for slot in REMOTE_IDS}) != len(REMOTE_IDS):
        return "HOLD_REMOTE_ALIAS"
    try:
        for slot in REMOTE_IDS:
            verify_service_identity(services[slot], slot, reg["slots"][slot])
    except Exception:
        return "HOLD_REMOTE_IDENTITY"

    status, link, cp = current_local(rt, st, boot)
    if status == "GENESIS":
        try:
            if any(verify_remote_full(services[s], s, reg["slots"][s]) is not None for s in REMOTE_IDS):
                return "HOLD_REMOTE_AHEAD"
        except Exception:
            return "HOLD_REMOTE_CORRUPT"
        if rt.get("state_sha") != binding(rt.get("app_state_sha"), reg["registry_sha"]):
            return "HOLD_STATE_BINDING"
        return "AUTHORITATIVE_GENESIS_MODELED"
    if status != "LOCAL_OK":
        return status
    expected_binding = binding(rt.get("app_state_sha"), reg["registry_sha"])
    if rt.get("state_sha") != expected_binding or cp.get("state_sha") != expected_binding:
        return "HOLD_STATE_BINDING"

    current = 0
    unavailable = corrupt = divergent = 0
    for slot in REMOTE_IDS:
        svc = services[slot]
        if not svc.get("online"):
            unavailable += 1
            continue
        try:
            head = verify_remote_full(svc, slot, reg["slots"][slot])
        except Exception:
            corrupt += 1
            continue
        if head is None:
            divergent += 1
            continue
        exact = (
            head["authority_epoch"] == link["epoch"]
            and head["authority_sha"] == link["authority_sha"]
            and head["checkpoint_sha"] == cp["checkpoint_sha"]
            and head["registry_sha"] == reg["registry_sha"]
        )
        if exact:
            current += 1
        else:
            divergent += 1
    if current >= reg["quorum"]:
        return f"AUTHORITATIVE_QUORUM_{current}_OF_3_MODELED"
    if corrupt:
        return "HOLD_REMOTE_CORRUPT_QUORUM"
    if unavailable:
        return "HOLD_REMOTE_UNAVAILABLE_QUORUM"
    return "HOLD_REMOTE_DIVERGED_QUORUM"


def prepare(rt: dict, st: dict, priv: dict, boot: dict, services: dict, registry_store: dict,
            target_app_state_sha: str | None = None, target_registry_sha: str | None = None) -> tuple:
    if not authority(rt, st, boot, services, registry_store).startswith("AUTHORITATIVE"):
        raise ValueError("predecessor HOLD")
    target_registry_sha = target_registry_sha or rt["remote_registry_sha"]
    get_registry(registry_store, target_registry_sha)
    target_app_state_sha = target_app_state_sha or rt["app_state_sha"]
    target_state_sha = binding(target_app_state_sha, target_registry_sha)

    pl, pc, pu = w98.pred_parts(st, rt)
    epoch = 1 if pc is None else pc["epoch"] + 1
    current = deepcopy(boot if pc is None else pc["next_signer_keys"])
    for root in w98.ROOTS:
        if current[root] not in priv or priv[current[root]].get("reserved") is not None:
            raise ValueError("signer unavailable/reserved")
    nxt = w98.successors(st, priv, current)
    pay = w98.payload(epoch, None if pc is None else pc["checkpoint_sha"], target_state_sha, current, nxt)
    sig = {
        root: w98.sign(priv[current[root]], w98.get(st["P"], current[root], "pub_sha"), {**pay, "root": root})
        for root in w98.ROOTS
    }
    cp = w98.seal({
        "schema": "checkpoint/w98-v1",
        "epoch": epoch,
        "predecessor_checkpoint_sha": None if pc is None else pc["checkpoint_sha"],
        "state_sha": target_state_sha,
        "signer_keys": current,
        "next_signer_keys": nxt,
        "signatures": sig,
        "checkpoint_sha": "",
    }, "checkpoint_sha")
    w98.put(st["C"], cp, "checkpoint_sha")
    for root in w98.ROOTS:
        priv[current[root]]["reserved"] = cp["checkpoint_sha"]
    use = w98.use(cp, None if pu is None else pu["use_sha"])
    w98.put(st["U"], use, "use_sha")
    link = w98.link(cp, use, None if pl is None else pl["authority_sha"])
    w98.put(st["L"], link, "authority_sha")
    w98.resolve(st, link["authority_sha"], boot)
    meta = {
        "target_app_state_sha": target_app_state_sha,
        "target_registry_sha": target_registry_sha,
        "target_state_sha": target_state_sha,
    }
    return cp, use, link, meta


def commit(rt: dict, st: dict, boot: dict, link_sha: str, meta: dict, n: int | None = None) -> str:
    try:
        link, cp, _ = w98.resolve(st, link_sha, boot)
    except Exception:
        return "VALIDATION_HOLD"
    try:
        expected = binding(meta["target_app_state_sha"], meta["target_registry_sha"])
    except Exception:
        return "TARGET_BINDING_HOLD"
    if expected != meta.get("target_state_sha") or expected != cp.get("state_sha"):
        return "TARGET_BINDING_HOLD"
    result = w98.commit_sha(rt, st, boot, link["authority_sha"], n)
    if result == "COMMITTED":
        rt["app_state_sha"] = meta["target_app_state_sha"]
        rt["remote_registry_sha"] = meta["target_registry_sha"]
        rt["state_sha"] = meta["target_state_sha"]
    return result


def publish(rt: dict, st: dict, boot: dict, services: dict, tokens: dict,
            registry_store: dict, slot: str) -> str:
    try:
        reg = get_registry(registry_store, rt["remote_registry_sha"])
    except Exception:
        return "REGISTRY_HOLD"
    if slot not in REMOTE_IDS or slot not in services or slot not in tokens:
        return "REMOTE_IDENTITY_HOLD"
    svc, row = services[slot], reg["slots"][slot]
    try:
        verify_service_identity(svc, slot, row)
        prev = verify_remote_full(svc, slot, row)
    except Exception:
        return "REMOTE_CORRUPT"
    status, link, cp = current_local(rt, st, boot)
    if status != "LOCAL_OK" or cp["state_sha"] != binding(rt["app_state_sha"], reg["registry_sha"]):
        return "LOCAL_HOLD"
    if prev is not None:
        if (prev["authority_sha"], prev["checkpoint_sha"], prev["registry_sha"]) == (
            link["authority_sha"], cp["checkpoint_sha"], reg["registry_sha"]
        ):
            return "ALREADY_CURRENT"
        if prev["authority_sha"] != link["predecessor_authority_sha"]:
            return "REMOTE_PREDECESSOR_HOLD"
    return append_raw(svc, slot, row, tokens[slot], link["epoch"], link["authority_sha"],
                      cp["checkpoint_sha"], reg["registry_sha"])


def recover_poisoned(rt: dict, st: dict, boot: dict, services: dict, token: bytes,
                     registry_store: dict, slot: str) -> str:
    try:
        reg = get_registry(registry_store, rt["remote_registry_sha"])
        pred = get_registry(registry_store, reg["predecessor_registry_sha"])
    except Exception:
        return "REGISTRY_HOLD"
    row, old = reg["slots"][slot], pred["slots"][slot]
    if row["service_id"] != old["service_id"] or row["failure_domain_id"] != old["failure_domain_id"]:
        return "RECOVERY_IDENTITY_HOLD"
    if row["credential_hash"] == old["credential_hash"]:
        return "RECOVERY_ROTATION_REQUIRED"
    svc = services[slot]
    try:
        verify_service_identity(svc, slot, row)
        prev = verify_remote_full(svc, slot, row)
    except Exception:
        return "REMOTE_CORRUPT"
    status, link, cp = current_local(rt, st, boot)
    if status != "LOCAL_OK" or cp["state_sha"] != binding(rt["app_state_sha"], reg["registry_sha"]):
        return "LOCAL_HOLD"
    return append_raw(svc, slot, row, token, link["epoch"], link["authority_sha"], cp["checkpoint_sha"],
                      reg["registry_sha"], kind="RECOVERY", predecessor_registry_sha=pred["registry_sha"])


def advance_all(st, priv, boot, rt, services, tokens, registry_store, app_label: str) -> tuple:
    app = hashlib.sha256(app_label.encode()).hexdigest()
    cp, use, link, meta = prepare(rt, st, priv, boot, services, registry_store, app)
    if commit(rt, st, boot, link["authority_sha"], meta) != "COMMITTED":
        raise RuntimeError("local commit failed")
    for slot in REMOTE_IDS:
        if publish(rt, st, boot, services, tokens, registry_store, slot) not in ("APPENDED", "ALREADY_CURRENT"):
            raise RuntimeError("remote publish failed")
    if not authority(rt, st, boot, services, registry_store).startswith("AUTHORITATIVE"):
        raise RuntimeError("authority failed")
    return cp, use, link, meta


def build_depth(depth: int):
    st, priv, boot, rt, services, tokens, registry_store = fixture()
    snapshots = []
    for i in range(depth):
        advance_all(st, priv, boot, rt, services, tokens, registry_store, f"wave99-state-{i}")
        snapshots.append((deepcopy(rt), deepcopy(services), deepcopy(registry_store)))
    return st, priv, boot, rt, services, tokens, registry_store, snapshots


def bench(depths=(1, 4, 8), rounds=5):
    rows = []
    for depth in depths:
        st, priv, boot, rt, services, tokens, registry_store, _ = build_depth(depth)
        samples = []
        for _ in range(rounds):
            t0 = time.process_time_ns()
            verdict = authority(rt, st, boot, services, registry_store)
            samples.append(time.process_time_ns() - t0)
            if not verdict.startswith("AUTHORITATIVE"):
                raise RuntimeError("benchmark authority failed")
        rows.append({
            "depth": depth,
            "rounds": rounds,
            "authority_median_cpu_us": statistics.median(samples) / 1000.0,
        })
    return rows

