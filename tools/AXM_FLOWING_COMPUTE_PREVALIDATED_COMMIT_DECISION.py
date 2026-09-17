#!/usr/bin/env python3
"""AXM Flowing Compute Wave 115: prevalidated exact commit decision.

Additive experiment over exact Wave 114. Independent verifier PR #39 showed that Wave 114
could append a sealed COMMIT decision before the lower transition semantic contract had accepted
that transition. A strict-field, correctly content-addressed but semantically invalid transition
could therefore poison the authority's durable decision identity even though the lower commit
returned HOLD.

Wave 115 changes that ordering inside the same modeled Python failure domain:
1. run the exact lower Wave-110 commit path against deep-copied state, including the exact
   Wave-114 decision that would be present during the real commit;
2. if the lower result is a stable semantic rejection, append an exact rejection receipt while
   leaving the real COMMIT-decision/provenance/runtime state untouched;
3. exclude only those explicitly rejected transition identities from later ambiguity scans;
4. only after successful semantic prevalidation bind the exact real Wave-114 COMMIT decision,
   then execute the lower commit and provenance path.

This is deterministic same-process prevalidation and append-only rejection evidence, not an
OS-process transaction, durable-device atomicity, concurrency proof, power-loss proof, network
proof, or provider-independent witness. No performance, energy, retained/incremental/dormant-
compute, merge, or CANON claim is made.
"""
from __future__ import annotations

import hashlib
from copy import deepcopy

import AXM_FLOWING_COMPUTE_EXACT_TRANSITION_DECISION as w114
import AXM_FLOWING_COMPUTE_RECOVERY_ATOMICITY as w113
import AXM_FLOWING_COMPUTE_TRANSITION_PROVENANCE_LEDGER as w111
import AXM_FLOWING_COMPUTE_TRANSITION_EVIDENCE_GUARD as w110
import AXM_FLOWING_COMPUTE_REMOTE_REGISTRY_MONOTONICITY as w100
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w104

q = w114.q
g = w114.g

SRC = {
    "wave114_builder_head": "e9b48d8e6b090ad73fe6f9d4443e741c308a70e6",
    "wave114_tested_source_commit": "cd946978f2c01ce719307c5bc025beccbcb1ec4f",
    "wave114_tool_blob": "2520a80b17624ac198d1e02999ef8ea906f246c5",
    "wave114_selftest_blob": "98afe1f6725f4c69f54639b1fd9c773d076bc976",
    "verifier_pr": 39,
    "verifier_head_at_wave115_start": "8bf3003ed765210cbbfbfc5cd0bc3ef044777987",
    "verifier_verdict":
        "FAIL_SEMANTICALLY_INVALID_TRANSITION_IS_DURABLY_COMMIT_DECIDED_BEFORE_LOWER_VALIDATION",
}

DECISION_STORE = w114.DECISION_STORE
DECISION_SCHEMA = w114.DECISION_SCHEMA
TRANSITION_FIELDS = w114.TRANSITION_FIELDS
DECISION_FIELDS = w114.DECISION_FIELDS
PROVENANCE_STORE = w113.PROVENANCE_STORE

REJECTION_STORE = "flowing_compute_wave115_transition_rejections"
REJECTION_SCHEMA = "axm.flowing-compute.transition-rejection/w115-v1"
REJECTION_FIELDS = {
    "schema",
    "seq",
    "predecessor_rejection_sha",
    "authority_sha",
    "transition_sha",
    "checkpoint_sha",
    "lower_result",
    "rejection_sha",
}
STABLE_SEMANTIC_REJECTIONS = {
    "TRANSITION_AUTHORITY_HOLD",
    "TRANSITION_CHECKPOINT_HOLD",
    "TRANSITION_GENERATION_HOLD",
    "TRANSITION_DELTA_HOLD",
    "TRANSITION_STATE_BINDING_HOLD",
    "TRANSITION_LINK_PREDECESSOR_HOLD",
}

HISTORY_NONE = w114.HISTORY_NONE
HISTORY_VALID = w114.HISTORY_VALID
HISTORY_INCOMPLETE = w114.HISTORY_INCOMPLETE
HISTORY_UNRESOLVED = w114.HISTORY_UNRESOLVED
HOLD_INCOMPLETE = w114.HOLD_INCOMPLETE
HOLD_UNRESOLVED = w114.HOLD_UNRESOLVED

_decision_rows = w114._decision_rows
_decision_for_authority = w114._decision_for_authority
_strict_transition_get = w114._strict_transition_get


def _seal_rejection(body: dict) -> dict:
    out = deepcopy(body)
    out["rejection_sha"] = ""
    out["rejection_sha"] = w114._canonical_sha(out, "rejection_sha")
    return out


def _check_rejection(body: dict, transition_store: dict, key: str | None = None) -> None:
    if set(body) != REJECTION_FIELDS:
        raise ValueError("rejection-field-set-mismatch")
    if body.get("schema") != REJECTION_SCHEMA:
        raise ValueError("rejection-schema-mismatch")
    if body.get("lower_result") not in STABLE_SEMANTIC_REJECTIONS:
        raise ValueError("rejection-result-not-stable-semantic")
    expected = w114._canonical_sha(body, "rejection_sha")
    if body.get("rejection_sha") != expected:
        raise ValueError("rejection-seal-mismatch")
    if key is not None and key != expected:
        raise ValueError("rejection-key-body-mismatch")
    transition = _strict_transition_get(transition_store, body["transition_sha"])
    if transition.get("target_authority_sha") != body.get("authority_sha"):
        raise ValueError("rejection-authority-mismatch")
    if transition.get("target_checkpoint_sha") != body.get("checkpoint_sha"):
        raise ValueError("rejection-checkpoint-mismatch")


def _rejection_rows(
    st: dict, transition_store: dict, *, allow_missing: bool = False
) -> list[tuple[str, dict]] | None:
    store = st.get(REJECTION_STORE)
    if store is None:
        if allow_missing:
            return None
        raise ValueError("rejection-store-missing")
    if not isinstance(store, dict):
        raise ValueError("rejection-store-invalid")
    rows = []
    seen_seq = set()
    for sha, raw in store.items():
        if not isinstance(sha, str) or not isinstance(raw, dict):
            raise ValueError("rejection-store-entry-invalid")
        body = deepcopy(raw)
        _check_rejection(body, transition_store, sha)
        seq = body.get("seq")
        if not isinstance(seq, int) or seq < 1 or seq in seen_seq:
            raise ValueError("rejection-sequence-invalid")
        seen_seq.add(seq)
        rows.append((sha, body))
    rows.sort(key=lambda row: row[1]["seq"])
    previous_sha = None
    for expected_seq, (sha, body) in enumerate(rows, start=1):
        if body["seq"] != expected_seq:
            raise ValueError("rejection-chain-sequence-gap")
        if body["predecessor_rejection_sha"] != previous_sha:
            raise ValueError("rejection-predecessor-sha-mismatch")
        previous_sha = sha
    return rows


def _append_rejection(
    st: dict,
    transition_store: dict,
    transition_sha: str,
    lower_result: str,
) -> str:
    if lower_result not in STABLE_SEMANTIC_REJECTIONS:
        return "NOT_STABLE_REJECTION"
    transition = _strict_transition_get(transition_store, transition_sha)
    rows = _rejection_rows(st, transition_store)
    assert rows is not None
    existing = [body for _sha, body in rows if body["transition_sha"] == transition_sha]
    if existing:
        if len(existing) != 1 or existing[0]["lower_result"] != lower_result:
            raise ValueError("rejection-transition-has-conflicting-result")
        return "ALREADY_REJECTED"

    predecessor = rows[-1][0] if rows else None
    body = _seal_rejection({
        "schema": REJECTION_SCHEMA,
        "seq": len(rows) + 1,
        "predecessor_rejection_sha": predecessor,
        "authority_sha": transition["target_authority_sha"],
        "transition_sha": transition_sha,
        "checkpoint_sha": transition["target_checkpoint_sha"],
        "lower_result": lower_result,
        "rejection_sha": "",
    })
    store = st[REJECTION_STORE]
    sha = body["rejection_sha"]
    if sha in store and store[sha] != body:
        raise ValueError("rejection-collision")
    store[sha] = body
    return "REJECTED_RECORDED"


def _effective_transition_store(st: dict, transition_store: dict) -> dict:
    rows = _rejection_rows(st, transition_store)
    assert rows is not None
    rejected = {body["transition_sha"] for _sha, body in rows}
    return {
        sha: deepcopy(body)
        for sha, body in transition_store.items()
        if sha not in rejected
    }


def commit_status_state(
    st: dict,
    boot: dict,
    rt: dict | None,
    registry_store: dict,
    binding_store: dict,
    transition_store: dict,
) -> dict:
    try:
        effective = _effective_transition_store(st, transition_store)
    except Exception as exc:
        return {
            "status": HISTORY_INCOMPLETE,
            "reason": f"transition-rejection-verification:{type(exc).__name__}:{exc}",
        }
    base = w114.commit_status_state(
        st, boot, rt, registry_store, binding_store, effective
    )
    rows = _rejection_rows(st, transition_store)
    assert rows is not None
    return {
        **base,
        "wave114": base,
        "rejected_transition_count": len(rows),
        "rejection_head_sha": rows[-1][0] if rows else "",
    }


def adopt_genesis(
    rt: dict,
    st: dict,
    boot: dict,
    services: dict,
    registry_store: dict,
    transition_store: dict,
    certificate_store: dict,
    domain: w104.CertificateWitnessDomain,
    binding_store: dict,
) -> str:
    if REJECTION_STORE in st:
        raise ValueError("rejection-store-already-present")
    result = w114.adopt_genesis(
        rt,
        st,
        boot,
        services,
        registry_store,
        transition_store,
        certificate_store,
        domain,
        binding_store,
    )
    st[REJECTION_STORE] = {}
    state = commit_status_state(
        st, boot, rt, registry_store, binding_store, transition_store
    )
    if state.get("status") not in (HISTORY_NONE, HISTORY_VALID):
        raise ValueError(f"Wave 115 genesis evidence HOLD: {state}")
    return result


def authority(
    rt: dict,
    st: dict,
    boot: dict,
    services: dict,
    registry_store: dict,
    transition_store: dict,
    certificate_store: dict,
    domain: w104.CertificateWitnessDomain,
    binding_store: dict,
    resolved_endpoints: dict | None = None,
) -> str:
    state = commit_status_state(
        st, boot, rt, registry_store, binding_store, transition_store
    )
    if state.get("status") == HISTORY_INCOMPLETE:
        return HOLD_INCOMPLETE
    if state.get("status") == HISTORY_UNRESOLVED:
        return HOLD_UNRESOLVED
    try:
        effective = _effective_transition_store(st, transition_store)
    except Exception:
        return HOLD_INCOMPLETE
    return w114.authority(
        rt,
        st,
        boot,
        services,
        registry_store,
        effective,
        certificate_store,
        domain,
        binding_store,
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
    domain: w104.CertificateWitnessDomain,
    binding_store: dict,
    target_user_app_state_sha: str | None = None,
    target_remote_registry_sha: str | None = None,
) -> tuple:
    verdict = authority(
        rt,
        st,
        boot,
        services,
        registry_store,
        transition_store,
        certificate_store,
        domain,
        binding_store,
    )
    if not verdict.startswith("AUTHORITATIVE"):
        raise ValueError("Wave 115 predecessor HOLD")
    effective = _effective_transition_store(st, transition_store)
    out = w114.prepare(
        rt,
        st,
        priv,
        boot,
        services,
        registry_store,
        effective,
        certificate_store,
        domain,
        binding_store,
        target_user_app_state_sha,
        target_remote_registry_sha,
    )
    transition_sha = out[3]
    transition = _strict_transition_get(effective, transition_sha)
    if transition_sha in transition_store and transition_store[transition_sha] != transition:
        raise ValueError("transition-collision-on-prepare-sync")
    transition_store[transition_sha] = deepcopy(transition)
    return out


publish = w114.publish
certify_and_sync = w114.certify_and_sync


def _prevalidate_lower_commit(
    rt: dict,
    st: dict,
    boot: dict,
    registry_store: dict,
    transition_store: dict,
    link_sha: str,
    transition_sha: str,
    binding_store: dict,
    n: int | None = None,
) -> str:
    probe_rt = deepcopy(rt)
    probe_st = deepcopy(st)
    probe_boot = deepcopy(boot)
    probe_registry_store = deepcopy(registry_store)
    probe_transition_store = deepcopy(transition_store)
    probe_binding_store = deepcopy(binding_store)

    _strict_transition_get(probe_transition_store, transition_sha)
    w114._ensure_commit_decision(
        probe_st,
        probe_boot,
        probe_registry_store,
        probe_transition_store,
        link_sha,
        transition_sha,
    )
    return w110.commit(
        probe_rt,
        probe_st,
        probe_boot,
        probe_registry_store,
        probe_transition_store,
        link_sha,
        transition_sha,
        probe_binding_store,
        n,
    )


def commit(
    rt: dict,
    st: dict,
    boot: dict,
    registry_store: dict,
    transition_store: dict,
    link_sha: str,
    transition_sha: str,
    binding_store: dict,
    n: int | None = None,
    *,
    fault_after_decision_before_lower_commit: bool = False,
    fault_after_lower_commit: bool = False,
) -> str:
    recovered = w114._recover_missing_trailing_provenance(
        st,
        boot,
        rt,
        registry_store,
        transition_store,
        binding_store,
        link_sha,
        transition_sha,
    )
    if recovered is not None:
        return recovered

    _strict_transition_get(transition_store, transition_sha)
    preflight = _prevalidate_lower_commit(
        rt,
        st,
        boot,
        registry_store,
        transition_store,
        link_sha,
        transition_sha,
        binding_store,
        n,
    )
    if preflight != "COMMITTED":
        _append_rejection(st, transition_store, transition_sha, preflight)
        return preflight

    w114._ensure_commit_decision(
        st,
        boot,
        registry_store,
        transition_store,
        link_sha,
        transition_sha,
    )
    if fault_after_decision_before_lower_commit:
        raise RuntimeError("injected-wave115-crash-after-decision-before-lower-commit")

    result = w110.commit(
        rt,
        st,
        boot,
        registry_store,
        transition_store,
        link_sha,
        transition_sha,
        binding_store,
        n,
    )
    if result != "COMMITTED":
        return f"HOLD_LOWER_CHANGED_AFTER_PREVALIDATION:{result}"

    if fault_after_lower_commit:
        raise RuntimeError("injected-wave115-crash-after-lower-commit-before-provenance")

    marker = w111._append_provenance(
        st,
        boot,
        registry_store,
        transition_store,
        link_sha,
        transition_sha,
    )
    if marker not in ("RECORDED", "ALREADY_RECORDED"):
        raise RuntimeError(f"unexpected Wave 115 provenance result: {marker}")

    state = commit_status_state(
        st,
        boot,
        rt,
        registry_store,
        binding_store,
        transition_store,
    )
    if state.get("status") != HISTORY_VALID:
        raise RuntimeError(f"Wave 115 commit did not settle exact decision history: {state}")
    return "COMMITTED"


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
    domain: w104.CertificateWitnessDomain,
    binding_store: dict,
    app_label: str,
) -> tuple:
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
        domain,
        binding_store,
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
    )
    if result != "COMMITTED":
        raise RuntimeError(f"Wave 115 local commit failed: {result}")
    for slot in q.REMOTE_IDS:
        remote_result = publish(rt, st, boot, services, tokens, registry_store, slot)
        if remote_result not in ("APPENDED", "ALREADY_CURRENT"):
            raise RuntimeError(f"Wave 115 remote publish failed for {slot}: {remote_result}")
    cert_result, cert_body = certify_and_sync(
        rt,
        st,
        boot,
        services,
        registry_store,
        certificate_store,
        domain,
    )
    if not isinstance(cert_result, str):
        raise RuntimeError(f"Wave 115 certificate result invalid: {cert_result!r}")
    verdict = authority(
        rt,
        st,
        boot,
        services,
        registry_store,
        transition_store,
        certificate_store,
        domain,
        binding_store,
    )
    if not verdict.startswith("AUTHORITATIVE"):
        raise RuntimeError(f"Wave 115 authority failed: {verdict}")
    return cp, use, link, transition_sha, body, cert_result, cert_body
