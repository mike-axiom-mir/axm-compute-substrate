#!/usr/bin/env python3
"""AXM Flowing Compute Wave 105: authority-bound certificate-witness registry root.

Additive experiment over exact Wave 104. Independent verifier PR #29 showed that Wave 104 validates
identity and credential possession inside whichever certificate-witness registry/domain the caller
supplies, but does not bind one exact witness-registry root into durable authority state.

Wave 105 inserts a small content-addressed root-binding body into the already signed local state path.
The lower Wave 99+ checkpoint signs ``state_sha = H(app_state_sha, remote_registry_sha)``. Wave 105
uses the lower ``app_state_sha`` slot as the SHA of a sealed binding body containing:
- the user/app state SHA;
- the exact remote-witness registry SHA for that authority epoch;
- the exact certificate-witness registry SHA;
- the predecessor binding SHA and sequence.

The current binding chain is cross-checked against every retained authority checkpoint. A fresh
internally valid certificate-witness registry therefore cannot replace the bound root after an
accepted authority transition without either changing a signed checkpoint or finding a hash collision.

Truth boundary:
- bootstrap root selection before the first accepted checkpoint is still an initialization/configuration
  boundary; this wave makes the selected root durable once authority history exists;
- certificate-witness registry rotation remains deliberately unsupported rather than being guessed at;
- all endpoint, remote, binding, certificate, and credential state is still modeled in one Python
  process; there is still no OS/device/provider independence or physically monotonic store;
- HMAC-SHA256 witness credentials remain test-only shared secrets, so credential theft still matters;
- whole modeled-domain rollback with the same already-bound root remains a preserved counterexample;
- no CANON, merge, energy, network, retained/incremental/dormant-compute win is claimed.
"""
from __future__ import annotations

import hashlib
from copy import deepcopy

import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w104

g = w104.g
q = w104.q

SRC = {
    "wave104_builder_head": "b0826840723b4d510f396c91e8f0c5de46a05a43",
    "wave104_tested_source_head": "b33c8e0ae155d8e785b25ab608bdf8a3dbb14e65",
    "wave104_tool_blob": "64aef8c32e246f396ca8dc67dbf3b0460b077f77",
    "wave104_selftest_blob": "c2ca76079adfbe9f44fd11c97689be61027a7760",
    "verifier_pr": 29,
    "verifier_head": "cc0ecfe2a40b0a39b20b85230578ddc3902c44ad",
    "verifier_evidence_blob": "afbfa47432c29ad41f5c0d56a1904ca94e996e30",
    "verifier_repro_blob": "51cc2266f47b4cfaeae32ad6744cead9f9d104b0",
}

BINDING_SCHEMA = "axm-certificate-witness-root-binding/w105-v1"


def _is_sha(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def make_binding(seq: int, user_app_state_sha: str, remote_registry_sha: str,
                 witness_registry_sha: str, predecessor_binding_sha: str | None) -> dict:
    return g.w98.seal({
        "schema": BINDING_SCHEMA,
        "seq": seq,
        "user_app_state_sha": user_app_state_sha,
        "remote_registry_sha": remote_registry_sha,
        "certificate_witness_registry_sha": witness_registry_sha,
        "predecessor_binding_sha": predecessor_binding_sha,
        "binding_sha": "",
    }, "binding_sha")


def verify_binding(binding: dict, binding_store: dict, registry_store: dict,
                   expected_sha: str | None = None) -> dict:
    body = deepcopy(binding)
    g.w98.chk(body, "binding_sha")
    if expected_sha is not None and body.get("binding_sha") != expected_sha:
        raise ValueError("root binding key/body mismatch")
    if body.get("schema") != BINDING_SCHEMA:
        raise ValueError("root binding schema mismatch")
    seq = body.get("seq")
    if not isinstance(seq, int) or seq < 0:
        raise ValueError("root binding sequence invalid")
    for field in ("user_app_state_sha", "remote_registry_sha",
                  "certificate_witness_registry_sha", "binding_sha"):
        if not _is_sha(body.get(field)):
            raise ValueError(f"root binding {field} invalid")
    q.get_registry(registry_store, body["remote_registry_sha"])
    pred = body.get("predecessor_binding_sha")
    if seq == 0:
        if pred is not None:
            raise ValueError("root binding genesis predecessor mismatch")
    elif not _is_sha(pred):
        raise ValueError("root binding predecessor missing")
    if expected_sha is not None and expected_sha not in binding_store:
        raise ValueError("root binding missing")
    return body


def put_binding(binding_store: dict, binding: dict, registry_store: dict) -> str:
    body = verify_binding(binding, binding_store, registry_store)
    sha = body["binding_sha"]
    existing = binding_store.get(sha)
    if existing is not None and existing != body:
        raise ValueError("root binding collision")
    binding_store[sha] = deepcopy(body)
    return sha


def get_binding(binding_store: dict, registry_store: dict, sha: str) -> dict:
    if sha not in binding_store:
        raise ValueError("root binding body missing")
    return verify_binding(binding_store[sha], binding_store, registry_store, sha)


def verify_binding_chain(binding_store: dict, registry_store: dict, head_sha: str) -> tuple[dict, list[dict]]:
    head = get_binding(binding_store, registry_store, head_sha)
    root = head["certificate_witness_registry_sha"]
    rows = []
    seen = set()
    cur = head
    expected_seq = head["seq"]
    while True:
        sha = cur["binding_sha"]
        if sha in seen:
            raise ValueError("root binding cycle")
        seen.add(sha)
        if cur["seq"] != expected_seq:
            raise ValueError("root binding sequence discontinuity")
        if cur["certificate_witness_registry_sha"] != root:
            raise ValueError("certificate witness registry root changed inside binding chain")
        rows.append(cur)
        if cur["seq"] == 0:
            if cur["predecessor_binding_sha"] is not None:
                raise ValueError("root binding genesis predecessor mismatch")
            break
        pred_sha = cur["predecessor_binding_sha"]
        cur = get_binding(binding_store, registry_store, pred_sha)
        expected_seq -= 1
    if expected_seq != 0:
        raise ValueError("root binding genesis sequence mismatch")
    return head, rows


def _current_binding(rt: dict, st: dict, boot: dict, registry_store: dict,
                     binding_store: dict) -> tuple[dict, str]:
    app_binding_sha = rt.get("app_state_sha")
    if not _is_sha(app_binding_sha):
        raise ValueError("runtime app/root binding pointer invalid")
    head, _rows = verify_binding_chain(binding_store, registry_store, app_binding_sha)
    if head["remote_registry_sha"] != rt.get("remote_registry_sha"):
        raise ValueError("root binding remote registry/current runtime mismatch")

    status, link, cp = q.current_local(rt, st, boot)
    expected_state = q.binding(head["binding_sha"], head["remote_registry_sha"])
    if rt.get("state_sha") != expected_state:
        raise ValueError("runtime state/root binding mismatch")

    if status == "GENESIS":
        if head["seq"] != 0 or cp is not None or link is not None:
            raise ValueError("genesis root binding mismatch")
        return head, status
    if status != "LOCAL_OK":
        raise ValueError(f"local authority status {status}")

    if head["seq"] != link.get("epoch"):
        raise ValueError("root binding/current authority epoch mismatch")
    if cp.get("state_sha") != expected_state:
        raise ValueError("root binding/current checkpoint mismatch")

    cur_binding = head
    cur_link = link
    cur_cp = cp
    while cur_link.get("predecessor_authority_sha") is not None:
        pred_binding = get_binding(binding_store, registry_store, cur_binding["predecessor_binding_sha"])
        prev_link, prev_cp, _ = g.w98.resolve(st, cur_link["predecessor_authority_sha"], boot)
        if pred_binding["seq"] != prev_link.get("epoch"):
            raise ValueError("root binding/predecessor authority epoch mismatch")
        expected_prev_state = q.binding(
            pred_binding["binding_sha"], pred_binding["remote_registry_sha"]
        )
        if prev_cp.get("state_sha") != expected_prev_state:
            raise ValueError("root binding/predecessor checkpoint mismatch")
        cur_binding = pred_binding
        cur_link = prev_link
        cur_cp = prev_cp

    if cur_link.get("epoch") != 1 or cur_binding.get("seq") != 1:
        raise ValueError("root binding authority genesis mismatch")
    genesis_binding = get_binding(
        binding_store, registry_store, cur_binding["predecessor_binding_sha"]
    )
    if genesis_binding["seq"] != 0 or genesis_binding["predecessor_binding_sha"] is not None:
        raise ValueError("root binding bootstrap predecessor mismatch")
    if genesis_binding["certificate_witness_registry_sha"] != head["certificate_witness_registry_sha"]:
        raise ValueError("root binding bootstrap registry mismatch")
    return head, status


def adopt_genesis(rt: dict, st: dict, boot: dict, services: dict, registry_store: dict,
                  certificate_store: dict, domain: w104.CertificateWitnessDomain,
                  binding_store: dict) -> str:
    """Bind the selected Wave-104 registry at genesis before any signed authority exists."""
    domain.verify_bindings()
    status, link, cp = q.current_local(rt, st, boot)
    if status != "GENESIS" or link is not None or cp is not None:
        raise ValueError("root binding adoption is genesis-only")
    if g.verify_certificate_store(certificate_store, registry_store) is not None:
        raise ValueError("cannot adopt root after quorum certificate history exists")

    existing = rt.get("app_state_sha")
    if existing in binding_store:
        body = get_binding(binding_store, registry_store, existing)
        if (
            body["seq"] == 0
            and body["certificate_witness_registry_sha"] == domain.registry_sha
            and body["remote_registry_sha"] == rt.get("remote_registry_sha")
        ):
            return body["binding_sha"]
        raise ValueError("runtime already points at a different root binding")

    if not _is_sha(existing):
        raise ValueError("genesis user app state invalid")
    body = make_binding(
        0,
        existing,
        rt["remote_registry_sha"],
        domain.registry_sha,
        None,
    )
    sha = put_binding(binding_store, body, registry_store)
    rt["app_state_sha"] = sha
    rt["state_sha"] = q.binding(sha, rt["remote_registry_sha"])
    return sha


def authority(rt: dict, st: dict, boot: dict, services: dict, registry_store: dict,
              certificate_store: dict, domain: w104.CertificateWitnessDomain,
              binding_store: dict, resolved_endpoints: dict | None = None) -> str:
    try:
        head, _status = _current_binding(rt, st, boot, registry_store, binding_store)
    except Exception:
        return "HOLD_CERTIFICATE_WITNESS_ROOT_BINDING_INVALID"
    try:
        domain.verify_bindings()
    except Exception:
        return "HOLD_CERTIFICATE_WITNESS_IDENTITY_OR_CREDENTIAL_INVALID"
    if head["certificate_witness_registry_sha"] != domain.registry_sha:
        return "HOLD_CERTIFICATE_WITNESS_REGISTRY_ROOT_MISMATCH"
    return w104.authority(
        rt, st, boot, services, registry_store, certificate_store, domain, resolved_endpoints
    )


def prepare(rt: dict, st: dict, priv: dict, boot: dict, services: dict,
            registry_store: dict, transition_store: dict, certificate_store: dict,
            domain: w104.CertificateWitnessDomain, binding_store: dict,
            target_user_app_state_sha: str | None = None,
            target_remote_registry_sha: str | None = None) -> tuple:
    verdict = authority(
        rt, st, boot, services, registry_store, certificate_store, domain, binding_store
    )
    if not verdict.startswith("AUTHORITATIVE"):
        raise ValueError("predecessor HOLD")

    current, _status = _current_binding(rt, st, boot, registry_store, binding_store)
    target_user_app_state_sha = target_user_app_state_sha or current["user_app_state_sha"]
    target_remote_registry_sha = target_remote_registry_sha or current["remote_registry_sha"]
    if not _is_sha(target_user_app_state_sha):
        raise ValueError("target user app state invalid")
    q.get_registry(registry_store, target_remote_registry_sha)

    body = make_binding(
        current["seq"] + 1,
        target_user_app_state_sha,
        target_remote_registry_sha,
        current["certificate_witness_registry_sha"],
        current["binding_sha"],
    )
    cp, use, link, transition_sha = g.prepare(
        rt,
        st,
        priv,
        boot,
        services,
        registry_store,
        transition_store,
        certificate_store,
        target_app_state_sha=body["binding_sha"],
        target_registry_sha=target_remote_registry_sha,
    )
    expected_state = q.binding(body["binding_sha"], target_remote_registry_sha)
    if cp.get("state_sha") != expected_state:
        raise ValueError("prepared checkpoint did not bind Wave 105 root body")
    put_binding(binding_store, body, registry_store)
    return cp, use, link, transition_sha, deepcopy(body)


def commit(rt: dict, st: dict, boot: dict, registry_store: dict, transition_store: dict,
           link_sha: str, transition_sha: str, binding_store: dict,
           n: int | None = None) -> str:
    result = g.commit(
        rt, st, boot, registry_store, transition_store, link_sha, transition_sha, n
    )
    if result == "COMMITTED":
        try:
            _current_binding(rt, st, boot, registry_store, binding_store)
        except Exception:
            return "COMMITTED_ROOT_BINDING_POSTCHECK_HOLD"
    return result


def publish(rt: dict, st: dict, boot: dict, services: dict, tokens: dict,
            registry_store: dict, slot: str) -> str:
    return g.publish(rt, st, boot, services, tokens, registry_store, slot)


def certify_and_sync(rt: dict, st: dict, boot: dict, services: dict, registry_store: dict,
                     certificate_store: dict, domain: w104.CertificateWitnessDomain,
                     slots: tuple[str, ...] | list[str] | None = None) -> tuple[str, dict]:
    result = g.certify_current_quorum(
        rt, st, boot, services, registry_store, certificate_store
    )
    if result not in ("CERTIFIED", "ALREADY_CERTIFIED"):
        return result, {}
    return result, w104.sync_endpoints(
        certificate_store, domain, registry_store, slots
    )


def advance_all(st: dict, priv: dict, boot: dict, rt: dict, services: dict, tokens: dict,
                registry_store: dict, transition_store: dict, certificate_store: dict,
                domain: w104.CertificateWitnessDomain, binding_store: dict,
                app_label: str) -> tuple:
    app = hashlib.sha256(app_label.encode("utf-8")).hexdigest()
    cp, use, link, transition_sha, body = prepare(
        rt, st, priv, boot, services, registry_store, transition_store,
        certificate_store, domain, binding_store, app
    )
    result = commit(
        rt, st, boot, registry_store, transition_store,
        link["authority_sha"], transition_sha, binding_store
    )
    if result != "COMMITTED":
        raise RuntimeError(f"local commit failed: {result}")
    for slot in q.REMOTE_IDS:
        remote_result = publish(
            rt, st, boot, services, tokens, registry_store, slot
        )
        if remote_result not in ("APPENDED", "ALREADY_CURRENT"):
            raise RuntimeError(f"remote publish failed: {slot}: {remote_result}")
    cert_result, sync = certify_and_sync(
        rt, st, boot, services, registry_store, certificate_store, domain
    )
    if cert_result not in ("CERTIFIED", "ALREADY_CERTIFIED"):
        raise RuntimeError(f"quorum certification failed: {cert_result}")
    if any(value not in ("ALREADY_CURRENT", "WITNESS_SYNCED_1") for value in sync.values()):
        raise RuntimeError(f"certificate witness sync failed: {sync}")
    verdict = authority(
        rt, st, boot, services, registry_store, certificate_store, domain, binding_store
    )
    if not verdict.startswith("AUTHORITATIVE"):
        raise RuntimeError(f"authority failed: {verdict}")
    return cp, use, link, transition_sha, body


def reconstruct_certificate_store(domain: w104.CertificateWitnessDomain,
                                  registry_store: dict) -> dict:
    return w104.reconstruct_certificate_store(domain, registry_store)
