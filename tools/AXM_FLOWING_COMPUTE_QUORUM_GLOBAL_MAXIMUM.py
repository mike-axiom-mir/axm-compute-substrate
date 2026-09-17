#!/usr/bin/env python3
"""AXM Flowing Compute Wave 102: quorum-certified global authority maximum.

Additive experiment over exact Wave 101. This wave directly repairs independent verifier PR #26
before process-level failure-domain work.

The key distinction is deliberate:
- a newer remote record seen on only one witness is *not* automatically final/authoritative;
- once the exact local authority is observed on a registered 2-of-3 remote quorum, an append-only
  quorum certificate remembers that accepted maximum;
- later authority at an older epoch is rejected even if two stale/lagging witnesses match it;
- certificate history is content-addressed and predecessor-linked, but still modeled local state,
  not a physically independent or cryptographically remote failure domain.

Truth boundary:
- all remotes and the certificate store are still modeled Python objects in one process;
- remote credentials remain symmetric test tokens;
- content hashes prove object integrity/lineage, not moral/canonical legitimacy or remote identity;
- no CANON, merge, energy, network, retained/incremental/dormant-compute claim.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from copy import deepcopy

import AXM_FLOWING_COMPUTE_REMOTE_AUTHORITY_MONOTONICITY as a
import AXM_FLOWING_COMPUTE_REMOTE_WITNESS_REGISTRY_QUORUM as q
import AXM_FLOWING_COMPUTE_DUAL_REMOTE_WITNESS as w98

SRC = {
    "wave101_builder_head": "08bed3007e118fdcc2499c873da85ed9355c96d2",
    "wave101_tool_blob": "9283b748aefcc1914eb763748674ee83a5ec3b15",
    "wave101_selftest_blob": "4bddbd849319b7475ac399dd96cd72ceb498545a",
    "verifier_pr": 26,
    "verifier_head": "c0c5b718b1ad77f4685045e290d6c7021f4786ca",
    "verifier_evidence_blob": "4ce07288e73d9a288c026a771f598585c698c090",
    "verifier_repro_blob": "2d5fc38bd07ebe3c172f02496b41b7c7a469a6f0",
}

CERT_SCHEMA = "axm-quorum-global-maximum/w102-v1"
STORE_SCHEMA = "axm-quorum-certificate-store/w102-v1"


def new_certificate_store() -> dict:
    return {"schema": STORE_SCHEMA, "head": None, "records": {}}


def _record_copy(rec: dict) -> dict:
    """Keep only the exact sealed remote record body needed as compact quorum evidence."""
    return deepcopy(rec)


def _cert_body(seq: int, authority_epoch: int, authority_sha: str, checkpoint_sha: str,
               registry_sha: str, support_records: dict, previous_certificate_sha: str | None) -> dict:
    return w98.seal({
        "schema": CERT_SCHEMA,
        "seq": seq,
        "authority_epoch": authority_epoch,
        "authority_sha": authority_sha,
        "checkpoint_sha": checkpoint_sha,
        "registry_sha": registry_sha,
        "support_records": deepcopy(support_records),
        "previous_certificate_sha": previous_certificate_sha,
        "certificate_sha": "",
    }, "certificate_sha")


def _verify_support_record(slot: str, rec: dict, cert: dict, registry: dict) -> None:
    w98.chk(rec, "record_sha")
    if slot not in q.REMOTE_IDS or slot not in registry["slots"]:
        raise ValueError("certificate supporter outside registry")
    if rec.get("schema") != "axm-remote-anchor/w99-v1":
        raise ValueError("certificate support schema mismatch")
    if rec.get("service_id") != slot or registry["slots"][slot].get("service_id") != slot:
        raise ValueError("certificate support identity mismatch")
    if rec.get("authority_epoch") != cert.get("authority_epoch"):
        raise ValueError("certificate support epoch mismatch")
    if rec.get("authority_sha") != cert.get("authority_sha"):
        raise ValueError("certificate support authority mismatch")
    if rec.get("checkpoint_sha") != cert.get("checkpoint_sha"):
        raise ValueError("certificate support checkpoint mismatch")
    if rec.get("registry_sha") != cert.get("registry_sha"):
        raise ValueError("certificate support registry mismatch")


def verify_certificate(cert: dict, registry_store: dict, expected_sha: str | None = None) -> dict:
    w98.chk(cert, "certificate_sha")
    if expected_sha is not None and cert.get("certificate_sha") != expected_sha:
        raise ValueError("certificate key/body mismatch")
    if cert.get("schema") != CERT_SCHEMA:
        raise ValueError("certificate schema mismatch")
    seq = cert.get("seq")
    epoch = cert.get("authority_epoch")
    if not isinstance(seq, int) or seq < 1:
        raise ValueError("certificate sequence invalid")
    if not isinstance(epoch, int) or epoch < 1:
        raise ValueError("certificate epoch invalid")
    for field in ("authority_sha", "checkpoint_sha", "registry_sha"):
        value = cert.get(field)
        if not isinstance(value, str) or len(value) != 64:
            raise ValueError(f"certificate {field} invalid")
    registry = q.get_registry(registry_store, cert["registry_sha"])
    support = cert.get("support_records")
    if not isinstance(support, dict) or len(support) < registry["quorum"]:
        raise ValueError("certificate quorum support missing")
    if len(support) != len(set(support)):
        raise ValueError("certificate duplicate supporter")
    for slot, rec in support.items():
        _verify_support_record(slot, rec, cert, registry)
    return deepcopy(cert)


def verify_certificate_store(store: dict, registry_store: dict) -> dict | None:
    if store.get("schema") != STORE_SCHEMA or not isinstance(store.get("records"), dict):
        raise ValueError("certificate store shape mismatch")
    records = store["records"]
    if not records:
        if store.get("head") is not None:
            raise ValueError("empty certificate store head mismatch")
        return None

    by_seq = {}
    for key, body in records.items():
        cert = verify_certificate(deepcopy(body), registry_store, key)
        seq = cert["seq"]
        if seq in by_seq:
            raise ValueError("duplicate certificate sequence")
        by_seq[seq] = cert
    n = len(by_seq)
    if set(by_seq) != set(range(1, n + 1)):
        raise ValueError("certificate sequence discontinuity")
    for seq in range(1, n + 1):
        cert = by_seq[seq]
        expected_prev = None if seq == 1 else by_seq[seq - 1]["certificate_sha"]
        if cert.get("previous_certificate_sha") != expected_prev:
            raise ValueError("certificate predecessor mismatch")
        if seq > 1:
            prev = by_seq[seq - 1]
            if cert["authority_epoch"] != prev["authority_epoch"] + 1:
                raise ValueError("certificate authority epoch discontinuity")
    head = by_seq[n]
    if store.get("head") != head["certificate_sha"]:
        raise ValueError("certificate head is not maximal retained record")
    return deepcopy(head)


def _local_parts(rt: dict, st: dict, boot: dict):
    return q.current_local(rt, st, boot)


def _exact_support(rt: dict, st: dict, boot: dict, services: dict,
                   registry_store: dict) -> tuple[dict, dict, dict, dict]:
    status, link, cp = _local_parts(rt, st, boot)
    if status != "LOCAL_OK":
        raise ValueError("local authority not commit-ready")
    registry = q.get_registry(registry_store, rt["remote_registry_sha"])
    support = {}
    for slot in q.REMOTE_IDS:
        svc = services.get(slot)
        if svc is None or not svc.get("online"):
            continue
        try:
            a.verify_remote_authority_history(svc, registry_store)
            head = q.verify_remote_full(svc, slot, registry["slots"][slot])
        except Exception:
            continue
        if head is None:
            continue
        if (
            head.get("authority_epoch") == link.get("epoch")
            and head.get("authority_sha") == link.get("authority_sha")
            and head.get("checkpoint_sha") == cp.get("checkpoint_sha")
            and head.get("registry_sha") == registry.get("registry_sha")
        ):
            support[slot] = _record_copy(head)
    return link, cp, registry, support


def certify_current_quorum(rt: dict, st: dict, boot: dict, services: dict,
                           registry_store: dict, certificate_store: dict) -> str:
    """Append one certificate only after exact current authority has live registered quorum support."""
    try:
        prior = verify_certificate_store(certificate_store, registry_store)
        link, cp, registry, support = _exact_support(rt, st, boot, services, registry_store)
    except Exception:
        return "CERTIFICATE_VALIDATION_HOLD"
    if len(support) < registry["quorum"]:
        return "CERTIFICATE_QUORUM_HOLD"

    if prior is not None:
        if link["epoch"] == prior["authority_epoch"]:
            same = (
                link["authority_sha"] == prior["authority_sha"]
                and cp["checkpoint_sha"] == prior["checkpoint_sha"]
                and registry["registry_sha"] == prior["registry_sha"]
            )
            return "ALREADY_CERTIFIED" if same else "CERTIFICATE_SIBLING_HOLD"
        if link["epoch"] != prior["authority_epoch"] + 1:
            return "CERTIFICATE_EPOCH_HOLD"
    seq = 1 if prior is None else prior["seq"] + 1
    cert = _cert_body(
        seq,
        link["epoch"],
        link["authority_sha"],
        cp["checkpoint_sha"],
        registry["registry_sha"],
        support,
        None if prior is None else prior["certificate_sha"],
    )
    sha = cert["certificate_sha"]
    if sha in certificate_store["records"] and certificate_store["records"][sha] != cert:
        return "CERTIFICATE_COLLISION_HOLD"
    certificate_store["records"][sha] = deepcopy(cert)
    certificate_store["head"] = sha
    try:
        verify_certificate_store(certificate_store, registry_store)
    except Exception:
        return "CERTIFICATE_POSTWRITE_HOLD"
    return "CERTIFIED"


def authority(rt: dict, st: dict, boot: dict, services: dict, registry_store: dict,
              certificate_store: dict) -> str:
    """Require the candidate local world to equal the retained quorum-certified maximum.

    An ahead *uncertified* single witness is intentionally not promoted to global finality. The
    certificate store answers the verifier's distinction between "newer seen" and "newer accepted
    by quorum". A later process-level wave can move this store into independent failure domains.
    """
    try:
        maximum = verify_certificate_store(certificate_store, registry_store)
    except Exception:
        return "HOLD_QUORUM_CERTIFICATE_STORE"

    status, link, cp = _local_parts(rt, st, boot)
    if status == "GENESIS":
        if maximum is not None:
            return "HOLD_QUORUM_GLOBAL_MAXIMUM_AHEAD"
        return a.authority(rt, st, boot, services, registry_store)
    if status != "LOCAL_OK":
        return status

    if maximum is None:
        base = a.authority(rt, st, boot, services, registry_store)
        if base.startswith("AUTHORITATIVE"):
            return "HOLD_QUORUM_CERTIFICATE_MISSING"
        return base

    local_epoch = link.get("epoch")
    if local_epoch < maximum["authority_epoch"]:
        return "HOLD_QUORUM_GLOBAL_MAXIMUM_AHEAD"
    if local_epoch > maximum["authority_epoch"]:
        base = a.authority(rt, st, boot, services, registry_store)
        if base.startswith("AUTHORITATIVE"):
            return "HOLD_QUORUM_CERTIFICATE_PENDING"
        return base

    if (
        link.get("authority_sha") != maximum["authority_sha"]
        or cp.get("checkpoint_sha") != maximum["checkpoint_sha"]
        or rt.get("remote_registry_sha") != maximum["registry_sha"]
    ):
        return "HOLD_QUORUM_CERTIFICATE_CONFLICT"
    return a.authority(rt, st, boot, services, registry_store)


def prepare(rt: dict, st: dict, priv: dict, boot: dict, services: dict,
            registry_store: dict, transition_store: dict, certificate_store: dict,
            target_app_state_sha: str | None = None,
            target_registry_sha: str | None = None) -> tuple:
    verdict = authority(rt, st, boot, services, registry_store, certificate_store)
    if not verdict.startswith("AUTHORITATIVE"):
        raise ValueError("predecessor HOLD")
    return a.prepare(
        rt, st, priv, boot, services, registry_store, transition_store,
        target_app_state_sha=target_app_state_sha,
        target_registry_sha=target_registry_sha,
    )


def commit(rt: dict, st: dict, boot: dict, registry_store: dict, transition_store: dict,
           link_sha: str, transition_sha: str, n: int | None = None) -> str:
    return a.commit(rt, st, boot, registry_store, transition_store, link_sha, transition_sha, n)


def publish(rt: dict, st: dict, boot: dict, services: dict, tokens: dict,
            registry_store: dict, slot: str) -> str:
    return a.publish(rt, st, boot, services, tokens, registry_store, slot)


def advance_all(st, priv, boot, rt, services, tokens, registry_store, transition_store,
                certificate_store, app_label: str) -> tuple:
    import hashlib
    app = hashlib.sha256(app_label.encode()).hexdigest()
    if _local_parts(rt, st, boot)[0] == "GENESIS":
        cp, use, link, tr_sha = a.prepare(
            rt, st, priv, boot, services, registry_store, transition_store, app
        )
    else:
        cp, use, link, tr_sha = prepare(
            rt, st, priv, boot, services, registry_store, transition_store,
            certificate_store, app,
        )
    if commit(rt, st, boot, registry_store, transition_store, link["authority_sha"], tr_sha) != "COMMITTED":
        raise RuntimeError("local commit failed")
    for slot in q.REMOTE_IDS:
        result = publish(rt, st, boot, services, tokens, registry_store, slot)
        if result not in ("APPENDED", "ALREADY_CURRENT"):
            raise RuntimeError(f"remote publish failed: {slot}: {result}")
    if certify_current_quorum(rt, st, boot, services, registry_store, certificate_store) not in (
        "CERTIFIED", "ALREADY_CERTIFIED"
    ):
        raise RuntimeError("quorum certification failed")
    verdict = authority(rt, st, boot, services, registry_store, certificate_store)
    if not verdict.startswith("AUTHORITATIVE"):
        raise RuntimeError(f"authority failed: {verdict}")
    return cp, use, link, tr_sha


def build_depth(depth: int):
    st, priv, boot, rt, services, tokens, registry_store = q.fixture()
    transition_store = {}
    certificate_store = new_certificate_store()
    for i in range(depth):
        advance_all(
            st, priv, boot, rt, services, tokens, registry_store, transition_store,
            certificate_store, f"wave102-state-{i}",
        )
    return st, priv, boot, rt, services, tokens, registry_store, transition_store, certificate_store


def bench(depths=(1, 4, 8), rounds=5):
    rows = []
    for depth in depths:
        st, priv, boot, rt, services, tokens, registry_store, transition_store, certificate_store = build_depth(depth)
        samples = []
        for _ in range(rounds):
            t0 = time.process_time_ns()
            verdict = authority(rt, st, boot, services, registry_store, certificate_store)
            samples.append(time.process_time_ns() - t0)
            if not verdict.startswith("AUTHORITATIVE"):
                raise RuntimeError("benchmark authority failed")
        rows.append({
            "depth": depth,
            "rounds": rounds,
            "authority_median_cpu_us": statistics.median(samples) / 1000.0,
        })
    return rows


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--benchmark-rounds", type=int, default=5)
    p.add_argument("--report")
    args = p.parse_args()
    report = {
        "schema": "axm.flowing_compute.wave102.protocol-smoke/v1",
        "source": SRC,
        "synthetic_scaling": bench(rounds=args.benchmark_rounds),
    }
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")


if __name__ == "__main__":
    main()
