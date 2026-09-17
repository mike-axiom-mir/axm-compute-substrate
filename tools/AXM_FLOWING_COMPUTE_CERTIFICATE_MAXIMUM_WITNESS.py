#!/usr/bin/env python3
"""AXM Flowing Compute Wave 103: replicated witnesses for the quorum-certificate maximum.

Additive experiment over exact Wave 102. This wave directly repairs independent verifier PR #27
before OS-process separation.

Wave 102 made accepted quorum finality explicit, but its certificate store was still one modeled
failure domain. PR #27 showed that deleting only the newest certificate record/head, restoring one
remote witness, and restoring the mutable local pointer could resurrect an older world while newer
remote/local evidence remained visible.

Wave 103 adds three fixed certificate-maximum witness ledgers. Each witness record embeds the exact
validated quorum certificate, is content-addressed and predecessor-linked, and has no trusted mutable
head: the retained maximum is derived from the complete record set. Authority refuses to move behind
any valid online certificate witness that remembers a newer accepted certificate, and requires at
least 2-of-3 exact current certificate witnesses before a non-genesis world is authoritative.

Truth boundary:
- the three certificate witnesses are still modeled Python objects in one process, not independent
  OS processes, devices, providers, or independently durable media;
- witness availability is modeled with an ``online`` flag; this is not real networking;
- whole-domain rollback of the local state plus all certificate-witness ledgers remains a preserved
  counterexample;
- a newer accepted certificate remembered only by an unavailable witness cannot be observed;
- hashes prove retained-body integrity/lineage, not moral/canonical legitimacy or remote identity;
- no CANON, merge, energy, network, retained/incremental/dormant-compute win is claimed.
"""
from __future__ import annotations

from copy import deepcopy

import AXM_FLOWING_COMPUTE_QUORUM_GLOBAL_MAXIMUM as g
import AXM_FLOWING_COMPUTE_REMOTE_WITNESS_REGISTRY_QUORUM as q

SRC = {
    "wave102_builder_head": "46fafcb3b13e5663337c01e185a8972ebc52dda5",
    "wave102_tool_blob": "8bd23cf3db02ba90161f4a7c38f36dca3f3b2733",
    "wave102_selftest_blob": "cc53bd23732acc31e8b85f0998187fba979c8a89",
    "verifier_pr": 27,
    "verifier_head": "10eb40d2ccde3a8af34f19c75ab069e38e4b9048",
    "verifier_evidence_blob": "c05b1802e0aeebaf69ac2e553aff28e301b74e68",
    "verifier_repro_blob": "f0d868817bdb55c0343c2b422923e7ebd4457d2d",
}

WITNESS_IDS = ("cert-a", "cert-b", "cert-c")
WITNESS_SCHEMA = "axm-certificate-maximum-witness-store/w103-v1"
RECORD_SCHEMA = "axm-certificate-maximum-witness-record/w103-v1"


def new_certificate_witnesses() -> dict:
    return {
        slot: {
            "schema": WITNESS_SCHEMA,
            "witness_id": slot,
            "online": True,
            "records": {},
        }
        for slot in WITNESS_IDS
    }


def _certificate_copy(cert: dict) -> dict:
    return deepcopy(cert)


def _record_body(slot: str, cert: dict, previous_record_sha: str | None) -> dict:
    return g.w98.seal({
        "schema": RECORD_SCHEMA,
        "witness_id": slot,
        "seq": cert["seq"],
        "certificate_seq": cert["seq"],
        "authority_epoch": cert["authority_epoch"],
        "certificate_sha": cert["certificate_sha"],
        "authority_sha": cert["authority_sha"],
        "checkpoint_sha": cert["checkpoint_sha"],
        "registry_sha": cert["registry_sha"],
        "certificate": _certificate_copy(cert),
        "previous_record_sha": previous_record_sha,
        "record_sha": "",
    }, "record_sha")


def verify_certificate_witness(service: dict, slot: str, registry_store: dict) -> dict | None:
    """Validate a complete retained certificate-witness ledger and derive its maximum.

    There is deliberately no mutable ``head`` field. The maximum is derived from all retained
    records, so a pointer rewind alone cannot hide newer retained witness evidence.
    """
    if slot not in WITNESS_IDS:
        raise ValueError("unknown certificate witness")
    if not isinstance(service, dict):
        raise ValueError("certificate witness missing")
    if service.get("schema") != WITNESS_SCHEMA:
        raise ValueError("certificate witness schema mismatch")
    if service.get("witness_id") != slot:
        raise ValueError("certificate witness identity mismatch")
    records = service.get("records")
    if not isinstance(records, dict):
        raise ValueError("certificate witness records invalid")
    if not records:
        return None

    by_seq: dict[int, dict] = {}
    for key, raw in records.items():
        rec = deepcopy(raw)
        g.w98.chk(rec, "record_sha")
        if rec.get("record_sha") != key:
            raise ValueError("certificate witness key/body mismatch")
        if rec.get("schema") != RECORD_SCHEMA:
            raise ValueError("certificate witness record schema mismatch")
        if rec.get("witness_id") != slot:
            raise ValueError("certificate witness record identity mismatch")
        seq = rec.get("seq")
        if not isinstance(seq, int) or seq < 1:
            raise ValueError("certificate witness sequence invalid")
        if seq in by_seq:
            raise ValueError("duplicate certificate witness sequence")
        cert = rec.get("certificate")
        if not isinstance(cert, dict):
            raise ValueError("certificate witness embedded certificate missing")
        cert = g.verify_certificate(cert, registry_store, rec.get("certificate_sha"))
        if rec.get("certificate_seq") != cert["seq"] or seq != cert["seq"]:
            raise ValueError("certificate witness certificate sequence mismatch")
        if rec.get("authority_epoch") != cert["authority_epoch"]:
            raise ValueError("certificate witness authority epoch mismatch")
        for field in ("authority_sha", "checkpoint_sha", "registry_sha"):
            if rec.get(field) != cert.get(field):
                raise ValueError(f"certificate witness {field} mismatch")
        by_seq[seq] = rec

    n = len(by_seq)
    if set(by_seq) != set(range(1, n + 1)):
        raise ValueError("certificate witness sequence discontinuity")
    for seq in range(1, n + 1):
        rec = by_seq[seq]
        expected_prev = None if seq == 1 else by_seq[seq - 1]["record_sha"]
        if rec.get("previous_record_sha") != expected_prev:
            raise ValueError("certificate witness predecessor mismatch")
        cert = rec["certificate"]
        expected_cert_prev = None if seq == 1 else by_seq[seq - 1]["certificate_sha"]
        if cert.get("previous_certificate_sha") != expected_cert_prev:
            raise ValueError("certificate witness embedded certificate predecessor mismatch")
        if seq > 1:
            prev = by_seq[seq - 1]
            if rec["authority_epoch"] != prev["authority_epoch"] + 1:
                raise ValueError("certificate witness authority epoch discontinuity")
    return deepcopy(by_seq[n])


def _append_exact_certificate(service: dict, slot: str, registry_store: dict, cert: dict) -> str:
    if not service.get("online", True):
        return "WITNESS_OFFLINE"
    try:
        prior = verify_certificate_witness(service, slot, registry_store)
        cert = g.verify_certificate(deepcopy(cert), registry_store, cert.get("certificate_sha"))
    except Exception:
        return "WITNESS_VALIDATION_HOLD"

    if prior is not None:
        if cert["seq"] == prior["certificate_seq"]:
            return "ALREADY_WITNESSED" if cert["certificate_sha"] == prior["certificate_sha"] else "WITNESS_SIBLING_HOLD"
        if cert["seq"] != prior["certificate_seq"] + 1:
            return "WITNESS_SEQUENCE_HOLD"
        if cert["authority_epoch"] != prior["authority_epoch"] + 1:
            return "WITNESS_EPOCH_HOLD"
    elif cert["seq"] != 1:
        return "WITNESS_SEQUENCE_HOLD"

    rec = _record_body(slot, cert, None if prior is None else prior["record_sha"])
    sha = rec["record_sha"]
    existing = service["records"].get(sha)
    if existing is not None and existing != rec:
        return "WITNESS_COLLISION_HOLD"
    service["records"][sha] = deepcopy(rec)
    try:
        verify_certificate_witness(service, slot, registry_store)
    except Exception:
        return "WITNESS_POSTWRITE_HOLD"
    return "WITNESSED"


def sync_witness(certificate_store: dict, witnesses: dict, registry_store: dict, slot: str) -> str:
    """Explicitly append every missing local certificate to one witness; never rewrites old rows."""
    if slot not in WITNESS_IDS or slot not in witnesses:
        return "WITNESS_UNKNOWN"
    service = witnesses[slot]
    if not service.get("online", True):
        return "WITNESS_OFFLINE"
    try:
        maximum = g.verify_certificate_store(certificate_store, registry_store)
        prior = verify_certificate_witness(service, slot, registry_store)
    except Exception:
        return "WITNESS_VALIDATION_HOLD"
    if maximum is None:
        return "WITNESS_EMPTY"
    start = 1 if prior is None else prior["certificate_seq"] + 1
    if prior is not None and prior["certificate_seq"] > maximum["seq"]:
        return "WITNESS_AHEAD_HOLD"
    if prior is not None and prior["certificate_seq"] == maximum["seq"]:
        return "ALREADY_CURRENT" if prior["certificate_sha"] == maximum["certificate_sha"] else "WITNESS_SIBLING_HOLD"

    by_seq = {body["seq"]: deepcopy(body) for body in certificate_store["records"].values()}
    appended = 0
    for seq in range(start, maximum["seq"] + 1):
        cert = by_seq.get(seq)
        if cert is None:
            return "WITNESS_SOURCE_GAP_HOLD"
        result = _append_exact_certificate(service, slot, registry_store, cert)
        if result not in ("WITNESSED", "ALREADY_WITNESSED"):
            return result
        if result == "WITNESSED":
            appended += 1
    return f"WITNESS_SYNCED_{appended}"


def sync_witnesses(certificate_store: dict, witnesses: dict, registry_store: dict,
                   slots: tuple[str, ...] | list[str] | None = None) -> dict:
    chosen = WITNESS_IDS if slots is None else tuple(slots)
    return {
        slot: sync_witness(certificate_store, witnesses, registry_store, slot)
        for slot in chosen
    }


def _witness_heads(witnesses: dict, registry_store: dict) -> tuple[dict, list[str]]:
    heads: dict[str, dict | None] = {}
    offline: list[str] = []
    for slot in WITNESS_IDS:
        service = witnesses.get(slot)
        if service is None or not service.get("online", True):
            offline.append(slot)
            continue
        heads[slot] = verify_certificate_witness(service, slot, registry_store)
    return heads, offline


def authority(rt: dict, st: dict, boot: dict, services: dict, registry_store: dict,
              certificate_store: dict, witnesses: dict) -> str:
    """Require local accepted finality to agree with replicated certificate-witness evidence."""
    try:
        local_max = g.verify_certificate_store(certificate_store, registry_store)
        heads, _offline = _witness_heads(witnesses, registry_store)
    except Exception:
        return "HOLD_CERTIFICATE_WITNESS_INVALID"

    nonempty = {slot: head for slot, head in heads.items() if head is not None}
    if local_max is None:
        if nonempty:
            return "HOLD_CERTIFICATE_WITNESS_MAXIMUM_AHEAD"
        return g.authority(rt, st, boot, services, registry_store, certificate_store)

    # Any retained accepted-finality witness ahead of the local certificate store blocks stale use,
    # even if two other witnesses are stale. A certificate-witness row is not a mere "newer seen"
    # remote observation: it embeds a structurally valid quorum certificate that already existed.
    highest_seq = max((head["certificate_seq"] for head in nonempty.values()), default=0)
    if highest_seq > local_max["seq"]:
        return "HOLD_CERTIFICATE_WITNESS_MAXIMUM_AHEAD"

    same_seq = [head for head in nonempty.values() if head["certificate_seq"] == local_max["seq"]]
    if any(head["certificate_sha"] != local_max["certificate_sha"] for head in same_seq):
        return "HOLD_CERTIFICATE_WITNESS_CONFLICT"

    if highest_seq < local_max["seq"]:
        return "HOLD_CERTIFICATE_WITNESS_PENDING"

    exact = sum(
        1
        for head in same_seq
        if head["certificate_sha"] == local_max["certificate_sha"]
        and head["authority_sha"] == local_max["authority_sha"]
        and head["checkpoint_sha"] == local_max["checkpoint_sha"]
        and head["registry_sha"] == local_max["registry_sha"]
    )
    if exact < 2:
        return "HOLD_CERTIFICATE_WITNESS_QUORUM"
    return g.authority(rt, st, boot, services, registry_store, certificate_store)


def certify_and_sync(rt: dict, st: dict, boot: dict, services: dict, registry_store: dict,
                     certificate_store: dict, witnesses: dict,
                     slots: tuple[str, ...] | list[str] | None = None) -> tuple[str, dict]:
    cert_result = g.certify_current_quorum(rt, st, boot, services, registry_store, certificate_store)
    if cert_result not in ("CERTIFIED", "ALREADY_CERTIFIED"):
        return cert_result, {}
    return cert_result, sync_witnesses(certificate_store, witnesses, registry_store, slots)


def prepare(rt: dict, st: dict, priv: dict, boot: dict, services: dict,
            registry_store: dict, transition_store: dict, certificate_store: dict,
            witnesses: dict, target_app_state_sha: str | None = None,
            target_registry_sha: str | None = None) -> tuple:
    verdict = authority(rt, st, boot, services, registry_store, certificate_store, witnesses)
    if not verdict.startswith("AUTHORITATIVE"):
        raise ValueError("predecessor HOLD")
    return g.prepare(
        rt, st, priv, boot, services, registry_store, transition_store,
        certificate_store, target_app_state_sha, target_registry_sha,
    )


def advance_all(st, priv, boot, rt, services, tokens, registry_store, transition_store,
                certificate_store, witnesses, app_label: str) -> tuple:
    import hashlib
    app = hashlib.sha256(app_label.encode()).hexdigest()
    if g._local_parts(rt, st, boot)[0] == "GENESIS":
        cp, use, link, tr_sha = g.a.prepare(
            rt, st, priv, boot, services, registry_store, transition_store, app
        )
    else:
        cp, use, link, tr_sha = prepare(
            rt, st, priv, boot, services, registry_store, transition_store,
            certificate_store, witnesses, app,
        )
    if g.commit(rt, st, boot, registry_store, transition_store, link["authority_sha"], tr_sha) != "COMMITTED":
        raise RuntimeError("local commit failed")
    for slot in q.REMOTE_IDS:
        result = g.publish(rt, st, boot, services, tokens, registry_store, slot)
        if result not in ("APPENDED", "ALREADY_CURRENT"):
            raise RuntimeError(f"remote publish failed: {slot}: {result}")
    cert_result, witness_results = certify_and_sync(
        rt, st, boot, services, registry_store, certificate_store, witnesses
    )
    if cert_result not in ("CERTIFIED", "ALREADY_CERTIFIED"):
        raise RuntimeError(f"quorum certification failed: {cert_result}")
    if any(result not in ("ALREADY_CURRENT", "ALREADY_WITNESSED") and not result.startswith("WITNESS_SYNCED_")
           for result in witness_results.values()):
        raise RuntimeError(f"certificate witness sync failed: {witness_results}")
    verdict = authority(rt, st, boot, services, registry_store, certificate_store, witnesses)
    if not verdict.startswith("AUTHORITATIVE"):
        raise RuntimeError(f"authority failed: {verdict}")
    return cp, use, link, tr_sha


def reconstruct_certificate_store(witnesses: dict, registry_store: dict) -> dict:
    """Return, but do not install, an exact certificate-store reconstruction from 2 matching maxima.

    This is intentionally an explicit recovery primitive. Authority reads never mutate or repair
    state. The caller can preserve the damaged store and separately decide whether to install the
    reconstructed candidate.
    """
    heads, _offline = _witness_heads(witnesses, registry_store)
    nonempty = {slot: head for slot, head in heads.items() if head is not None}
    if not nonempty:
        raise ValueError("no certificate witness evidence")
    highest = max(head["certificate_seq"] for head in nonempty.values())
    top = {slot: head for slot, head in nonempty.items() if head["certificate_seq"] == highest}
    groups: dict[str, list[str]] = {}
    for slot, head in top.items():
        groups.setdefault(head["certificate_sha"], []).append(slot)
    matching = [(sha, slots) for sha, slots in groups.items() if len(slots) >= 2]
    if len(matching) != 1:
        raise ValueError("certificate witness recovery quorum missing or conflicting")
    _sha, slots = matching[0]
    source = witnesses[slots[0]]
    verified = verify_certificate_witness(source, slots[0], registry_store)
    if verified is None or verified["certificate_seq"] != highest:
        raise ValueError("certificate witness recovery source invalid")
    certs: dict[str, dict] = {}
    for raw in source["records"].values():
        rec = deepcopy(raw)
        cert = g.verify_certificate(rec["certificate"], registry_store, rec["certificate_sha"])
        certs[cert["certificate_sha"]] = cert
    candidate = {"schema": g.STORE_SCHEMA, "head": verified["certificate_sha"], "records": certs}
    g.verify_certificate_store(candidate, registry_store)
    return candidate
