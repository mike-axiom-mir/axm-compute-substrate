#!/usr/bin/env python3
"""AXM Flowing Compute Wave 104: credential-bound certificate-witness registry.

Additive experiment over exact Wave 103. Independent verifier PR #28 showed that Wave 103's
``cert-a`` / ``cert-b`` / ``cert-c`` identities were only caller-supplied map slots plus string IDs:
a legitimate stale same-ID snapshot could stand in for a still-online newer witness.

Wave 104 adds a content-addressed immutable witness registry and credential-bound endpoint contract.
Each slot is bound to one fresh instance identity, one symmetric test credential identity, and one
modeled failure-domain identity. Every retained witness record binds that registry + instance. Every
authority read requires the exact registered resolver set and a fresh HMAC-SHA256 proof-of-possession
from each online resolved endpoint. A plain stale disk snapshot or a different same-name endpoint
therefore cannot silently replace the registered live instance.

Truth boundary:
- all endpoints, registry, credentials, remotes, and certificate stores are still Python objects in
  one process; this is protocol/identity modeling, not OS/process/device/provider separation;
- HMAC-SHA256 credentials are test-only shared secrets, not public-key remote identity;
- stealing a registered endpoint credential can authenticate a stale clone; that counterexample is
  intentionally preserved;
- restoring the same registered endpoints' durable ledgers together with local/remote/certificate
  state can still recreate an internally valid old world;
- witness-registry rotation/replacement is deliberately unsupported in this wave rather than being
  guessed at; a later explicit authority transition must own it;
- no CANON, merge, network, energy, retained/incremental/dormant-compute win is claimed.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from copy import deepcopy

import AXM_FLOWING_COMPUTE_CERTIFICATE_MAXIMUM_WITNESS as w103
import AXM_FLOWING_COMPUTE_QUORUM_GLOBAL_MAXIMUM as g
import AXM_FLOWING_COMPUTE_REMOTE_WITNESS_REGISTRY_QUORUM as q

SRC = {
    "wave103_builder_head": "8239c401a9d7ca1a330f76a7f537437fd141bbc6",
    "wave103_tool_blob": "0a5d6f09189719d705808fe1746c2f032688fd01",
    "wave103_selftest_blob": "6bf8df3d03dd189cfe700ac0f8fbf862593dd7c9",
    "verifier_pr": 28,
    "verifier_head": "2384c08109e0c1414921029e7f4f29577838a0da",
    "verifier_evidence_blob": "5b75cf95aa2203e9a5c57f529fdfcad00fa96aea",
    "verifier_repro_blob": "9031bcfaf13afaee4628db0c8d486d066c6efd04",
}

WITNESS_IDS = w103.WITNESS_IDS
REGISTRY_SCHEMA = "axm-certificate-witness-registry/w104-v1"
ENDPOINT_SCHEMA = "axm-certificate-witness-endpoint/w104-v1"
RECORD_SCHEMA = "axm-certificate-witness-record/w104-v1"
ATTESTATION_SCHEMA = "axm-certificate-witness-live-attestation/w104-v1"


def _canon(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _credential_commitment(secret: bytes) -> str:
    return _sha(b"axm-w104-credential-commitment\0" + secret)


def _credential_id(secret: bytes) -> str:
    return _sha(b"axm-w104-credential-id\0" + secret)


def _instance_id(slot: str, secret: bytes) -> str:
    return _sha(b"axm-w104-instance\0" + slot.encode("utf-8") + b"\0" + secret)


def _registry_body(entries: dict) -> dict:
    return g.w98.seal({
        "schema": REGISTRY_SCHEMA,
        "generation": 0,
        "predecessor_registry_sha": None,
        "witness_ids": list(WITNESS_IDS),
        "entries": deepcopy(entries),
        "registry_sha": "",
    }, "registry_sha")


def verify_registry(registry: dict) -> dict:
    registry = deepcopy(registry)
    g.w98.chk(registry, "registry_sha")
    if registry.get("schema") != REGISTRY_SCHEMA:
        raise ValueError("certificate witness registry schema mismatch")
    if registry.get("generation") != 0 or registry.get("predecessor_registry_sha") is not None:
        raise ValueError("Wave 104 registry must be fixed generation zero")
    if registry.get("witness_ids") != list(WITNESS_IDS):
        raise ValueError("certificate witness registry membership mismatch")
    entries = registry.get("entries")
    if not isinstance(entries, dict) or set(entries) != set(WITNESS_IDS):
        raise ValueError("certificate witness registry entries mismatch")
    instance_ids, credential_ids, domains = set(), set(), set()
    for slot in WITNESS_IDS:
        row = entries[slot]
        if not isinstance(row, dict) or row.get("slot") != slot or row.get("witness_id") != slot:
            raise ValueError("certificate witness registry slot mismatch")
        for field in ("instance_id", "credential_id", "credential_commitment", "failure_domain_id"):
            if not isinstance(row.get(field), str) or not row[field]:
                raise ValueError(f"certificate witness registry {field} missing")
        instance_ids.add(row["instance_id"])
        credential_ids.add(row["credential_id"])
        domains.add(row["failure_domain_id"])
    if len(instance_ids) != len(WITNESS_IDS):
        raise ValueError("certificate witness registry instance alias")
    if len(credential_ids) != len(WITNESS_IDS):
        raise ValueError("certificate witness registry credential alias")
    if len(domains) != len(WITNESS_IDS):
        raise ValueError("certificate witness registry failure-domain alias")
    return registry


class CertificateWitnessEndpoint:
    """A stable modeled endpoint whose disk can roll back but whose test credential is not in snapshots."""

    def __init__(self, registry_sha: str, slot: str, entry: dict, secret: bytes):
        self.schema = ENDPOINT_SCHEMA
        self.registry_sha = registry_sha
        self.slot = slot
        self.witness_id = entry["witness_id"]
        self.instance_id = entry["instance_id"]
        self.credential_id = entry["credential_id"]
        self.failure_domain_id = entry["failure_domain_id"]
        self.online = True
        self.records: dict[str, dict] = {}
        self._secret = bytes(secret)

    def __deepcopy__(self, memo):
        raise TypeError("credential-bound endpoint cannot be cloned by disk snapshot")

    def disk_snapshot(self) -> dict:
        return {
            "schema": ENDPOINT_SCHEMA,
            "registry_sha": self.registry_sha,
            "slot": self.slot,
            "witness_id": self.witness_id,
            "instance_id": self.instance_id,
            "credential_id": self.credential_id,
            "failure_domain_id": self.failure_domain_id,
            "records": deepcopy(self.records),
        }

    def restore_disk(self, snapshot: dict) -> None:
        expected = {
            "schema": self.schema,
            "registry_sha": self.registry_sha,
            "slot": self.slot,
            "witness_id": self.witness_id,
            "instance_id": self.instance_id,
            "credential_id": self.credential_id,
            "failure_domain_id": self.failure_domain_id,
        }
        for field, value in expected.items():
            if snapshot.get(field) != value:
                raise ValueError("certificate witness disk identity mismatch")
        if not isinstance(snapshot.get("records"), dict):
            raise ValueError("certificate witness disk records invalid")
        self.records = deepcopy(snapshot["records"])

    def live_attestation(self, nonce: str, registry_store: dict) -> dict:
        if not self.online:
            raise ConnectionError("certificate witness endpoint offline")
        head = verify_endpoint_ledger(self, registry_store)
        payload = {
            "schema": ATTESTATION_SCHEMA,
            "slot": self.slot,
            "witness_id": self.witness_id,
            "instance_id": self.instance_id,
            "credential_id": self.credential_id,
            "failure_domain_id": self.failure_domain_id,
            "witness_registry_sha": self.registry_sha,
            "nonce": nonce,
            "head": None if head is None else {
                "certificate_seq": head["certificate_seq"],
                "authority_epoch": head["authority_epoch"],
                "certificate_sha": head["certificate_sha"],
                "authority_sha": head["authority_sha"],
                "checkpoint_sha": head["checkpoint_sha"],
                "registry_sha": head["registry_sha"],
                "record_sha": head["record_sha"],
            },
        }
        payload["proof"] = hmac.new(self._secret, _canon(payload), hashlib.sha256).hexdigest()
        return payload


class CertificateWitnessDomain:
    """Fixed Wave-104 registry plus verifier-side test credentials and registered endpoints."""

    def __init__(self, registry: dict, endpoints: dict, verifier_secrets: dict):
        self.registry = verify_registry(registry)
        self.registry_sha = self.registry["registry_sha"]
        self._endpoints = dict(endpoints)
        self._verifier_secrets = {k: bytes(v) for k, v in verifier_secrets.items()}
        self.verify_bindings()

    def verify_bindings(self) -> None:
        registry = verify_registry(self.registry)
        if registry["registry_sha"] != self.registry_sha:
            raise ValueError("certificate witness registry pointer mismatch")
        if set(self._endpoints) != set(WITNESS_IDS) or set(self._verifier_secrets) != set(WITNESS_IDS):
            raise ValueError("certificate witness registered set mismatch")
        for slot in WITNESS_IDS:
            entry = registry["entries"][slot]
            endpoint = self._endpoints[slot]
            secret = self._verifier_secrets[slot]
            if _credential_commitment(secret) != entry["credential_commitment"]:
                raise ValueError("certificate witness verifier credential mismatch")
            if _credential_id(secret) != entry["credential_id"]:
                raise ValueError("certificate witness verifier credential id mismatch")
            _verify_endpoint_identity(endpoint, slot, registry)

    def resolved_endpoints(self) -> dict:
        return dict(self._endpoints)

    def disk_snapshots(self) -> dict:
        return {slot: self._endpoints[slot].disk_snapshot() for slot in WITNESS_IDS}

    def restore_disks(self, snapshots: dict) -> None:
        if set(snapshots) != set(WITNESS_IDS):
            raise ValueError("certificate witness disk snapshot set mismatch")
        for slot in WITNESS_IDS:
            self._endpoints[slot].restore_disk(snapshots[slot])


def new_certificate_witness_domain() -> CertificateWitnessDomain:
    entries, secrets_by_slot = {}, {}
    for slot in WITNESS_IDS:
        secret = secrets.token_bytes(32)
        secrets_by_slot[slot] = secret
        entries[slot] = {
            "slot": slot,
            "witness_id": slot,
            "instance_id": _instance_id(slot, secret),
            "credential_id": _credential_id(secret),
            "credential_commitment": _credential_commitment(secret),
            "failure_domain_id": f"modeled-cert-domain-{slot}",
        }
    registry = _registry_body(entries)
    endpoints = {
        slot: CertificateWitnessEndpoint(registry["registry_sha"], slot, entries[slot], secrets_by_slot[slot])
        for slot in WITNESS_IDS
    }
    return CertificateWitnessDomain(registry, endpoints, secrets_by_slot)


def _verify_endpoint_identity(endpoint, slot: str, registry: dict) -> None:
    if not isinstance(endpoint, CertificateWitnessEndpoint):
        raise ValueError("certificate witness endpoint type/credential boundary mismatch")
    entry = registry["entries"][slot]
    expected = {
        "schema": ENDPOINT_SCHEMA,
        "registry_sha": registry["registry_sha"],
        "slot": slot,
        "witness_id": slot,
        "instance_id": entry["instance_id"],
        "credential_id": entry["credential_id"],
        "failure_domain_id": entry["failure_domain_id"],
    }
    for field, value in expected.items():
        if getattr(endpoint, field, None) != value:
            raise ValueError(f"certificate witness endpoint {field} mismatch")


def _record_body(endpoint: CertificateWitnessEndpoint, cert: dict, previous_record_sha: str | None) -> dict:
    return g.w98.seal({
        "schema": RECORD_SCHEMA,
        "witness_registry_sha": endpoint.registry_sha,
        "witness_id": endpoint.witness_id,
        "instance_id": endpoint.instance_id,
        "credential_id": endpoint.credential_id,
        "failure_domain_id": endpoint.failure_domain_id,
        "seq": cert["seq"],
        "certificate_seq": cert["seq"],
        "authority_epoch": cert["authority_epoch"],
        "certificate_sha": cert["certificate_sha"],
        "authority_sha": cert["authority_sha"],
        "checkpoint_sha": cert["checkpoint_sha"],
        "registry_sha": cert["registry_sha"],
        "certificate": deepcopy(cert),
        "previous_record_sha": previous_record_sha,
        "record_sha": "",
    }, "record_sha")


def verify_endpoint_ledger(endpoint: CertificateWitnessEndpoint, registry_store: dict) -> dict | None:
    if not isinstance(endpoint.records, dict):
        raise ValueError("certificate witness endpoint records invalid")
    if not endpoint.records:
        return None
    by_seq: dict[int, dict] = {}
    for key, raw in endpoint.records.items():
        rec = deepcopy(raw)
        g.w98.chk(rec, "record_sha")
        if rec.get("record_sha") != key:
            raise ValueError("certificate witness record key/body mismatch")
        if rec.get("schema") != RECORD_SCHEMA:
            raise ValueError("certificate witness record schema mismatch")
        expected = {
            "witness_registry_sha": endpoint.registry_sha,
            "witness_id": endpoint.witness_id,
            "instance_id": endpoint.instance_id,
            "credential_id": endpoint.credential_id,
            "failure_domain_id": endpoint.failure_domain_id,
        }
        for field, value in expected.items():
            if rec.get(field) != value:
                raise ValueError(f"certificate witness record {field} mismatch")
        seq = rec.get("seq")
        if not isinstance(seq, int) or seq < 1 or seq in by_seq:
            raise ValueError("certificate witness record sequence invalid")
        cert = rec.get("certificate")
        if not isinstance(cert, dict):
            raise ValueError("certificate witness embedded certificate missing")
        cert = g.verify_certificate(cert, registry_store, rec.get("certificate_sha"))
        if seq != cert["seq"] or rec.get("certificate_seq") != cert["seq"]:
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
        expected_cert_prev = None if seq == 1 else by_seq[seq - 1]["certificate_sha"]
        if rec["certificate"].get("previous_certificate_sha") != expected_cert_prev:
            raise ValueError("certificate witness embedded certificate predecessor mismatch")
        if seq > 1 and rec["authority_epoch"] != by_seq[seq - 1]["authority_epoch"] + 1:
            raise ValueError("certificate witness authority epoch discontinuity")
    return deepcopy(by_seq[n])


def _append_exact_certificate(endpoint: CertificateWitnessEndpoint, registry_store: dict, cert: dict) -> str:
    if not endpoint.online:
        return "WITNESS_OFFLINE"
    try:
        prior = verify_endpoint_ledger(endpoint, registry_store)
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
    rec = _record_body(endpoint, cert, None if prior is None else prior["record_sha"])
    existing = endpoint.records.get(rec["record_sha"])
    if existing is not None and existing != rec:
        return "WITNESS_COLLISION_HOLD"
    endpoint.records[rec["record_sha"]] = deepcopy(rec)
    try:
        verify_endpoint_ledger(endpoint, registry_store)
    except Exception:
        return "WITNESS_POSTWRITE_HOLD"
    return "WITNESSED"


def sync_endpoint(certificate_store: dict, domain: CertificateWitnessDomain, registry_store: dict, slot: str) -> str:
    try:
        domain.verify_bindings()
    except Exception:
        return "WITNESS_REGISTRY_HOLD"
    if slot not in WITNESS_IDS:
        return "WITNESS_UNKNOWN"
    endpoint = domain._endpoints[slot]
    if not endpoint.online:
        return "WITNESS_OFFLINE"
    try:
        maximum = g.verify_certificate_store(certificate_store, registry_store)
        prior = verify_endpoint_ledger(endpoint, registry_store)
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
        result = _append_exact_certificate(endpoint, registry_store, cert)
        if result not in ("WITNESSED", "ALREADY_WITNESSED"):
            return result
        if result == "WITNESSED":
            appended += 1
    return f"WITNESS_SYNCED_{appended}"


def sync_endpoints(certificate_store: dict, domain: CertificateWitnessDomain, registry_store: dict,
                   slots: tuple[str, ...] | list[str] | None = None) -> dict:
    chosen = WITNESS_IDS if slots is None else tuple(slots)
    return {slot: sync_endpoint(certificate_store, domain, registry_store, slot) for slot in chosen}


def _verify_live_attestation(att: dict, slot: str, registry: dict, secret: bytes, nonce: str) -> dict | None:
    if not isinstance(att, dict) or att.get("schema") != ATTESTATION_SCHEMA:
        raise ValueError("certificate witness live attestation schema mismatch")
    entry = registry["entries"][slot]
    expected = {
        "slot": slot,
        "witness_id": slot,
        "instance_id": entry["instance_id"],
        "credential_id": entry["credential_id"],
        "failure_domain_id": entry["failure_domain_id"],
        "witness_registry_sha": registry["registry_sha"],
        "nonce": nonce,
    }
    for field, value in expected.items():
        if att.get(field) != value:
            raise ValueError(f"certificate witness live attestation {field} mismatch")
    proof = att.get("proof")
    if not isinstance(proof, str):
        raise ValueError("certificate witness live attestation proof missing")
    body = deepcopy(att)
    body.pop("proof", None)
    expected_proof = hmac.new(secret, _canon(body), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(proof, expected_proof):
        raise ValueError("certificate witness credential proof mismatch")
    head = att.get("head")
    if head is not None and not isinstance(head, dict):
        raise ValueError("certificate witness live head invalid")
    return deepcopy(head)


def _attested_heads(domain: CertificateWitnessDomain, registry_store: dict,
                    resolved_endpoints: dict | None = None) -> tuple[dict, list[str]]:
    domain.verify_bindings()
    resolved = domain.resolved_endpoints() if resolved_endpoints is None else dict(resolved_endpoints)
    if set(resolved) != set(WITNESS_IDS):
        raise ValueError("certificate witness resolver set mismatch")
    heads, offline = {}, []
    for slot in WITNESS_IDS:
        endpoint = resolved[slot]
        _verify_endpoint_identity(endpoint, slot, domain.registry)
        if not endpoint.online:
            offline.append(slot)
            continue
        nonce = secrets.token_hex(16)
        att = endpoint.live_attestation(nonce, registry_store)
        head = _verify_live_attestation(att, slot, domain.registry, domain._verifier_secrets[slot], nonce)
        ledger_head = verify_endpoint_ledger(endpoint, registry_store)
        compact = None if ledger_head is None else {
            "certificate_seq": ledger_head["certificate_seq"],
            "authority_epoch": ledger_head["authority_epoch"],
            "certificate_sha": ledger_head["certificate_sha"],
            "authority_sha": ledger_head["authority_sha"],
            "checkpoint_sha": ledger_head["checkpoint_sha"],
            "registry_sha": ledger_head["registry_sha"],
            "record_sha": ledger_head["record_sha"],
        }
        if head != compact:
            raise ValueError("certificate witness live head/ledger mismatch")
        heads[slot] = head
    return heads, offline


def authority(rt: dict, st: dict, boot: dict, services: dict, registry_store: dict,
              certificate_store: dict, domain: CertificateWitnessDomain,
              resolved_endpoints: dict | None = None) -> str:
    try:
        local_max = g.verify_certificate_store(certificate_store, registry_store)
        heads, _offline = _attested_heads(domain, registry_store, resolved_endpoints)
    except Exception:
        return "HOLD_CERTIFICATE_WITNESS_IDENTITY_OR_CREDENTIAL_INVALID"
    nonempty = {slot: head for slot, head in heads.items() if head is not None}
    if local_max is None:
        if nonempty:
            return "HOLD_CERTIFICATE_WITNESS_MAXIMUM_AHEAD"
        return g.authority(rt, st, boot, services, registry_store, certificate_store)
    highest_seq = max((head["certificate_seq"] for head in nonempty.values()), default=0)
    if highest_seq > local_max["seq"]:
        return "HOLD_CERTIFICATE_WITNESS_MAXIMUM_AHEAD"
    same_seq = [head for head in nonempty.values() if head["certificate_seq"] == local_max["seq"]]
    if any(head["certificate_sha"] != local_max["certificate_sha"] for head in same_seq):
        return "HOLD_CERTIFICATE_WITNESS_CONFLICT"
    if highest_seq < local_max["seq"]:
        return "HOLD_CERTIFICATE_WITNESS_PENDING"
    exact = sum(
        1 for head in same_seq
        if head["certificate_sha"] == local_max["certificate_sha"]
        and head["authority_sha"] == local_max["authority_sha"]
        and head["checkpoint_sha"] == local_max["checkpoint_sha"]
        and head["registry_sha"] == local_max["registry_sha"]
    )
    if exact < 2:
        return "HOLD_CERTIFICATE_WITNESS_QUORUM"
    return g.authority(rt, st, boot, services, registry_store, certificate_store)


def prepare(rt: dict, st: dict, priv: dict, boot: dict, services: dict,
            registry_store: dict, transition_store: dict, certificate_store: dict,
            domain: CertificateWitnessDomain, target_app_state_sha: str | None = None,
            target_registry_sha: str | None = None) -> tuple:
    verdict = authority(rt, st, boot, services, registry_store, certificate_store, domain)
    if not verdict.startswith("AUTHORITATIVE"):
        raise ValueError("predecessor HOLD")
    return g.prepare(rt, st, priv, boot, services, registry_store, transition_store,
                     certificate_store, target_app_state_sha, target_registry_sha)


def certify_and_sync(rt: dict, st: dict, boot: dict, services: dict, registry_store: dict,
                     certificate_store: dict, domain: CertificateWitnessDomain,
                     slots: tuple[str, ...] | list[str] | None = None) -> tuple[str, dict]:
    result = g.certify_current_quorum(rt, st, boot, services, registry_store, certificate_store)
    if result not in ("CERTIFIED", "ALREADY_CERTIFIED"):
        return result, {}
    return result, sync_endpoints(certificate_store, domain, registry_store, slots)


def reconstruct_certificate_store(domain: CertificateWitnessDomain, registry_store: dict) -> dict:
    heads, _offline = _attested_heads(domain, registry_store)
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
    _sha_value, slots = matching[0]
    endpoint = domain._endpoints[slots[0]]
    head = verify_endpoint_ledger(endpoint, registry_store)
    if head is None or head["certificate_seq"] != highest:
        raise ValueError("certificate witness recovery source invalid")
    certs = {}
    for rec in endpoint.records.values():
        cert = g.verify_certificate(rec["certificate"], registry_store, rec["certificate_sha"])
        certs[cert["certificate_sha"]] = cert
    candidate = {"schema": g.STORE_SCHEMA, "head": head["certificate_sha"], "records": certs}
    g.verify_certificate_store(candidate, registry_store)
    return candidate
