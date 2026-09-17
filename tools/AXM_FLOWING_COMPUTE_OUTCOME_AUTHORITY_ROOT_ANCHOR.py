#!/usr/bin/env python3
"""AXM Flowing Compute Wave 117: checkpoint-anchored outcome-authority root.

Independent verifier PR #41 showed that Wave 116's HMAC outcome credential is only as trustworthy as
its retained ``OUTCOME_BINDING``. A caller can create a fresh credential, replace that binding plus
the raw rejection/outcome rows, and obtain a new internally valid contradictory rejection history
without forging the original HMAC or rewriting the lower authority/certificate substrate.

Wave 117 is an additive experimental repair over exact Wave 116. It does not move the witness into a
new OS process yet. Instead it roots one exact outcome-authority identity into the already signed
Wave-105 authority/checkpoint path:

* a content-addressed outcome-root body names the exact Wave-116 outcome authority identity;
* a content-addressed application envelope names both the user/app-state SHA and that outcome root;
* the Wave-105 ``user_app_state_sha`` slot now points at the envelope SHA, so every accepted local
  authority checkpoint indirectly commits the exact outcome-authority root;
* all retained Wave-105 binding rows are checked back to genesis and must resolve to the same exact
  Wave-117 root while signer rotation is unsupported;
* the mutable Wave-116 binding must agree with that checkpoint-anchored root before outcome history
  is trusted.

This deliberately keeps signer rotation unsupported rather than guessing at it. A later wave must add
old-root-authorized rotation with lineage before process separation can be credited. The initial root
selection is still a bootstrap/configuration boundary before the first accepted checkpoint. All state,
credentials, remotes and witnesses are still modeled in one Python process; whole-domain rollback is
still a preserved counterexample. No merge/CANON, performance, energy, network, provider, or retained/
incremental/dormant-compute claim is made.
"""
from __future__ import annotations

import hashlib
from copy import deepcopy

import AXM_FLOWING_COMPUTE_AUTHENTICATED_REJECTION_OUTCOME as w116
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_ROOT_BINDING as w105
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w104
import AXM_FLOWING_COMPUTE_EXACT_TRANSITION_DECISION as w114

q = w116.q
g = w116.g

SRC = {
    "wave116_builder_head": "fc9d6b0f88d9acbfb1ff5b5fcbb2a4a50de5224b",
    "wave116_tested_source_commit": "b47136f228679ef72130d5e043e56743d00257f8",
    "wave116_tool_blob": "9b3459d84766cea56e293d4cdf573d8457c51b8f",
    "verifier_pr": 41,
    "verifier_head_at_wave117_start": "109071ef87ead838148a96395d8ed0d3cc6681ea",
    "verifier_verdict": "FAIL_OUTCOME_AUTHORITY_ROOT_SUBSTITUTION_ACCEPTS_RESEALED_CONTRADICTORY_HISTORY",
}

OutcomeAuthorityDomain = w116.OutcomeAuthorityDomain
new_outcome_authority_domain = w116.new_outcome_authority_domain

OUTCOME_ROOT_STORE = "flowing_compute_wave117_outcome_authority_roots"
OUTCOME_ROOT_SCHEMA = "axm.flowing-compute.outcome-authority-root/w117-v1"
OUTCOME_ROOT_FIELDS = {
    "schema",
    "generation",
    "predecessor_root_sha",
    "outcome_authority_id",
    "root_sha",
}
ENVELOPE_STORE = "flowing_compute_wave117_app_envelopes"
ENVELOPE_SCHEMA = "axm.flowing-compute.app-outcome-root-envelope/w117-v1"
ENVELOPE_FIELDS = {
    "schema",
    "user_app_state_sha",
    "outcome_root_sha",
    "envelope_sha",
}

HISTORY_NONE = w116.HISTORY_NONE
HISTORY_VALID = w116.HISTORY_VALID
HISTORY_INCOMPLETE = w116.HISTORY_INCOMPLETE
HISTORY_UNRESOLVED = w116.HISTORY_UNRESOLVED
HOLD_INCOMPLETE = w116.HOLD_INCOMPLETE
HOLD_UNRESOLVED = w116.HOLD_UNRESOLVED
STABLE_SEMANTIC_REJECTIONS = w116.STABLE_SEMANTIC_REJECTIONS


def _is_sha(value: object) -> bool:
    return w105._is_sha(value)


def _seal_root(outcome_authority_id: str) -> dict:
    if not _is_sha(outcome_authority_id):
        raise ValueError("outcome-authority-id-invalid")
    body = {
        "schema": OUTCOME_ROOT_SCHEMA,
        "generation": 0,
        "predecessor_root_sha": None,
        "outcome_authority_id": outcome_authority_id,
        "root_sha": "",
    }
    body["root_sha"] = w114._canonical_sha(body, "root_sha")
    return body


def _check_root(body: dict, key: str | None = None) -> dict:
    if not isinstance(body, dict) or set(body) != OUTCOME_ROOT_FIELDS:
        raise ValueError("outcome-root-field-set-mismatch")
    out = deepcopy(body)
    if out.get("schema") != OUTCOME_ROOT_SCHEMA:
        raise ValueError("outcome-root-schema-mismatch")
    if out.get("generation") != 0 or out.get("predecessor_root_sha") is not None:
        raise ValueError("wave117-outcome-root-rotation-unsupported")
    if not _is_sha(out.get("outcome_authority_id")):
        raise ValueError("outcome-root-authority-id-invalid")
    expected = w114._canonical_sha(out, "root_sha")
    if out.get("root_sha") != expected:
        raise ValueError("outcome-root-seal-mismatch")
    if key is not None and key != expected:
        raise ValueError("outcome-root-key-body-mismatch")
    return out


def _put_root(st: dict, body: dict) -> str:
    checked = _check_root(body)
    store = st.setdefault(OUTCOME_ROOT_STORE, {})
    if not isinstance(store, dict):
        raise ValueError("outcome-root-store-invalid")
    sha = checked["root_sha"]
    existing = store.get(sha)
    if existing is not None and existing != checked:
        raise ValueError("outcome-root-collision")
    store[sha] = deepcopy(checked)
    return sha


def _get_root(st: dict, sha: str) -> dict:
    store = st.get(OUTCOME_ROOT_STORE)
    if not isinstance(store, dict):
        raise ValueError("outcome-root-store-missing-or-invalid")
    raw = store.get(sha)
    if not isinstance(raw, dict):
        raise ValueError("checkpoint-anchored-outcome-root-body-missing")
    return _check_root(raw, sha)


def _seal_envelope(user_app_state_sha: str, outcome_root_sha: str) -> dict:
    if not _is_sha(user_app_state_sha):
        raise ValueError("user-app-state-sha-invalid")
    if not _is_sha(outcome_root_sha):
        raise ValueError("outcome-root-sha-invalid")
    body = {
        "schema": ENVELOPE_SCHEMA,
        "user_app_state_sha": user_app_state_sha,
        "outcome_root_sha": outcome_root_sha,
        "envelope_sha": "",
    }
    body["envelope_sha"] = w114._canonical_sha(body, "envelope_sha")
    return body


def _check_envelope(body: dict, key: str | None = None) -> dict:
    if not isinstance(body, dict) or set(body) != ENVELOPE_FIELDS:
        raise ValueError("outcome-root-envelope-field-set-mismatch")
    out = deepcopy(body)
    if out.get("schema") != ENVELOPE_SCHEMA:
        raise ValueError("outcome-root-envelope-schema-mismatch")
    if not _is_sha(out.get("user_app_state_sha")):
        raise ValueError("outcome-root-envelope-user-app-state-invalid")
    if not _is_sha(out.get("outcome_root_sha")):
        raise ValueError("outcome-root-envelope-root-sha-invalid")
    expected = w114._canonical_sha(out, "envelope_sha")
    if out.get("envelope_sha") != expected:
        raise ValueError("outcome-root-envelope-seal-mismatch")
    if key is not None and key != expected:
        raise ValueError("outcome-root-envelope-key-body-mismatch")
    return out


def _put_envelope(st: dict, body: dict) -> str:
    checked = _check_envelope(body)
    store = st.setdefault(ENVELOPE_STORE, {})
    if not isinstance(store, dict):
        raise ValueError("outcome-root-envelope-store-invalid")
    sha = checked["envelope_sha"]
    existing = store.get(sha)
    if existing is not None and existing != checked:
        raise ValueError("outcome-root-envelope-collision")
    store[sha] = deepcopy(checked)
    return sha


def _get_envelope(st: dict, sha: str) -> dict:
    store = st.get(ENVELOPE_STORE)
    if not isinstance(store, dict):
        raise ValueError("outcome-root-envelope-store-missing-or-invalid")
    raw = store.get(sha)
    if not isinstance(raw, dict):
        raise ValueError("checkpoint-anchored-outcome-envelope-body-missing")
    return _check_envelope(raw, sha)


def _current_anchor(
    rt: dict,
    st: dict,
    boot: dict,
    registry_store: dict,
    binding_store: dict,
    outcome_domain: OutcomeAuthorityDomain,
+) -> tuple[dict, dict, dict, str]:
    current, status = w105._current_binding(rt, st, boot, registry_store, binding_store)
    _head, retained_bindings = w105.verify_binding_chain(
        binding_store, registry_store, current["binding_sha"]
    )
    expected_root_sha = None
    expected_authority_id = None
    current_envelope = None
    current_root = None
    for binding in retained_bindings:
        envelope = _get_envelope(st, binding["user_app_state_sha"])
        root = _get_root(st, envelope["outcome_root_sha"])
        if expected_root_sha is None:
            expected_root_sha = root["root_sha"]
            expected_authority_id = root["outcome_authority_id"]
            current_envelope = envelope
            current_root = root
        elif root["root_sha"] != expected_root_sha or root["outcome_authority_id"] != expected_authority_id:
            raise ValueError("outcome-authority-root-changed-without-supported-rotation")
    if current_envelope is None or current_root is None:
        raise ValueError("outcome-authority-root-anchor-empty")
    if current_root["outcome_authority_id"] != outcome_domain.authority_id:
        raise ValueError("checkpoint-anchored-outcome-authority-credential-substitution")
    mutable = w116._check_binding(st, outcome_domain)
    if mutable.get("outcome_authority_id") != current_root["outcome_authority_id"]:
        raise ValueError("wave116-binding-disagrees-with-checkpoint-anchored-root")
    return current, current_envelope, current_root, status


def commit_status_state(
    st: dict,
    boot: dict,
    rt: dict | None,
    registry_store: dict,
    binding_store: dict,
    transition_store: dict,
    outcome_domain: OutcomeAuthorityDomain,
+) -> dict:
    if rt is None:
        return {
            "status": HISTORY_INCOMPLETE,
            "reason": "outcome-authority-root-anchor:runtime-required",
        }
    try:
        _binding, envelope, root, _status = _current_anchor(
            rt, st, boot, registry_store, binding_store, outcome_domain
        )
    except Exception as exc:
        return {
            "status": HISTORY_INCOMPLETE,
            "reason": f"outcome-authority-root-anchor:{type(exc).__name__}:{exc}",
        }
    base = w116.commit_status_state(
        st, boot, rt, registry_store, binding_store, transition_store, outcome_domain
    )
    return {
        **base,
        "wave116": base,
        "checkpoint_anchored_outcome_root_sha": root["root_sha"],
        "checkpoint_anchored_outcome_authority_id": root["outcome_authority_id"],
        "user_app_state_sha": envelope["user_app_state_sha"],
    }


def adopt_genesis(
    rt: dict,
    st: dict,
    boot: dict,
    services: dict,
    registry_store: dict,
    transition_store: dict,
    certificate_store: dict,
    certificate_domain: w104.CertificateWitnessDomain,
    binding_store: dict,
    outcome_domain: OutcomeAuthorityDomain,
+) -> str:
    if OUTCOME_ROOT_STORE in st or ENVELOPE_STORE in st:
        raise ValueError("wave117-root-anchor-state-already-present")
    original_app_state_sha = rt.get("app_state_sha")
    if not _is_sha(original_app_state_sha):
        raise ValueError("wave117-genesis-user-app-state-invalid")
    root_sha = _put_root(st, _seal_root(outcome_domain.authority_id))
    envelope_sha = _put_envelope(st, _seal_envelope(original_app_state_sha, root_sha))
    rt["app_state_sha"] = envelope_sha
    result = w116.adopt_genesis(
        rt,
        st,
        boot,
        services,
        registry_store,
        transition_store,
        certificate_store,
        certificate_domain,
        binding_store,
        outcome_domain,
    )
    state = commit_status_state(
        st, boot, rt, registry_store, binding_store, transition_store, outcome_domain
    )
    if state.get("status") not in (HISTORY_NONE, HISTORY_VALID):
        raise ValueError(f"Wave 117 genesis root anchor HOLD: {state}")
    return result


def authority(
    rt: dict,
    st: dict,
    boot: dict,
    services: dict,
    registry_store: dict,
    transition_store: dict,
    certificate_store: dict,
    certificate_domain: w104.CertificateWitnessDomain,
    binding_store: dict,
    outcome_domain: OutcomeAuthorityDomain,
    resolved_endpoints: dict | None = None,
+) -> str:
    state = commit_status_state(
        st, boot, rt, registry_store, binding_store, transition_store, outcome_domain
    )
    if state.get("status") == HISTORY_INCOMPLETE:
        return HOLD_INCOMPLETE
    if state.get("status") == HISTORY_UNRESOLVED:
        return HOLD_UNRESOLVED
    return w116.authority(
        rt,
        st,
        boot,
        services,
        registry_store,
        transition_store,
        certificate_store,
        certificate_domain,
        binding_store,
        outcome_domain,
        resolved_endpoints,
    )


def prepare(
    rt: dict,
    st: dict,
    priv: dict,
    boot: dict,
    services: dict,
    registry_store: dict,
    transition_store: dict,
    certificate_store: dict,
    certificate_domain: w104.CertificateWitnessDomain,
    binding_store: dict,
    outcome_domain: OutcomeAuthorityDomain,
    target_user_app_state_sha: str | None = None,
    target_remote_registry_sha: str | None = None,
+) -> tuple:
    verdict = authority(
        rt,
        st,
        boot,
        services,
        registry_store,
        transition_store,
        certificate_store,
        certificate_domain,
        binding_store,
        outcome_domain,
    )
    if not verdict.startswith("AUTHORITATIVE"):
        raise ValueError("Wave 117 predecessor HOLD")
    _binding, current_envelope, current_root, _status = _current_anchor(
        rt, st, boot, registry_store, binding_store, outcome_domain
    )
    user_app_state_sha = target_user_app_state_sha or current_envelope["user_app_state_sha"]
    envelope = _seal_envelope(user_app_state_sha, current_root["root_sha"])
    envelope_sha = _put_envelope(st, envelope)
    return w116.prepare(
        rt,
        st,
        priv,
        boot,
        services,
        registry_store,
        transition_store,
        certificate_store,
        certificate_domain,
        binding_store,
        outcome_domain,
        envelope_sha,
        target_remote_registry_sha,
    )


publish = w116.publish
certify_and_sync = w116.certify_and_sync


def commit(
    rt: dict,
    st: dict,
    boot: dict,
    registry_store: dict,
    transition_store: dict,
    link_sha: str,
    transition_sha: str,
    binding_store: dict,
    outcome_domain: OutcomeAuthorityDomain,
    n: int | None = None,
    **faults,
+) -> str:
    _current_anchor(rt, st, boot, registry_store, binding_store, outcome_domain)
    result = w116.commit(
        rt,
        st,
        boot,
        registry_store,
        transition_store,
        link_sha,
        transition_sha,
        binding_store,
        outcome_domain,
        n,
        **faults,
    )
    if result == "COMMITTED":
        try:
            _current_anchor(rt, st, boot, registry_store, binding_store, outcome_domain)
        except Exception:
            return "COMMITTED_OUTCOME_ROOT_POSTCHECK_HOLD"
    return result


def advance_all(
    st: dict,
    priv: dict,
    boot: dict,
    rt: dict,
    services: dict,
    tokens: dict,
    registry_store: dict,
    transition_store: dict,
    certificate_store: dict,
    certificate_domain: w104.CertificateWitnessDomain,
    binding_store: dict,
    outcome_domain: OutcomeAuthorityDomain,
    app_label: str,
+) -> tuple:
    app = hashlib.sha256(app_label.encode("utf-8")).hexdigest()
    cp, use, link, transition_sha, body = prepare(
        rt,
        st,
        priv,
        boot,
        services,
        registry_store,
        transition_store,
        certificate_store,
        certificate_domain,
        binding_store,
        outcome_domain,
        app,
    )
    result = commit(
        rt,
        st,
        boot,
        registry_store,
        transition_store,
        link["authority_sha"],
        transition_sha,
        binding_store,
        outcome_domain,
    )
    if result != "COMMITTED":
        raise RuntimeError(f"Wave 117 local commit failed: {result}")
    for slot in q.REMOTE_IDS:
        remote_result = publish(rt, st, boot, services, tokens, registry_store, slot)
        if remote_result not in ("APPENDED", "ALREADY_CURRENT"):
            raise RuntimeError(f"Wave 117 remote publish failed for {slot}: {remote_result}")
    cert_result, cert_body = certify_and_sync(
        rt,
        st,
        boot,
        services,
        registry_store,
        certificate_store,
        certificate_domain,
    )
    verdict = authority(
        rt,
        st,
        boot,
        services,
        registry_store,
        transition_store,
        certificate_store,
        certificate_domain,
        binding_store,
        outcome_domain,
    )
    if not verdict.startswith("AUTHORITATIVE"):
        raise RuntimeError(f"Wave 117 authority failed: {verdict}")
    state = commit_status_state(
        st, boot, rt, registry_store, binding_store, transition_store, outcome_domain
    )
    return cp, use, link, transition_sha, body, cert_result, cert_body, state
