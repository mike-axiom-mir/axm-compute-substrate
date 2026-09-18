#!/usr/bin/env python3
"""AXM Flowing Compute Wave 110: include transition-store evidence in commit-status truth.

Additive experiment over exact Wave 109. Independent verifier PR #34 showed that Wave 109 could
classify an older retained prefix VALID while a sealed Wave-100 transition still named the exact
newer authority/checkpoint/root-binding transaction. That transition does not prove commit, but it is
retained transaction evidence. Wave 109's safety rule already says ambiguous surviving transaction
evidence must HOLD rather than be guessed away; omitting transition_store made that rule incomplete.

Wave 110 therefore treats the transition store as a first-class evidence family. It does not invent a
commit bit and it does not claim durability independence. A transition not exactly accounted for by
the committed marker lineage is UNRESOLVED_COMMIT_STATUS. A committed authority missing its exact
transition, or a malformed/tampered transition body, is INCOMPLETE_OR_CORRUPT.

Truth boundary: all stores/credentials are still modeled Python state in one process. Whole-domain
rollback can still erase every newer fact. This is a semantic completeness repair, not a performance,
energy, retained/incremental/dormant-compute, OS-process, device, or provider-independence result.
No merge or CANON promotion is performed by this tool.
"""
from __future__ import annotations

import hashlib

import AXM_FLOWING_COMPUTE_COMMIT_STATUS_AMBIGUITY_GUARD as w109
import AXM_FLOWING_COMPUTE_REMOTE_REGISTRY_MONOTONICITY as w100
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w104

q = w109.q
g = w109.g

SRC = {
    "wave109_builder_head": "84c5f53f4a6e9ffafc013db634adba485cd44479",
    "wave109_tested_source_commit": "1747e087d3ab07312484980da987b88f8e8f56cd",
    "wave109_tool_blob": "6dbb03509100fdd724c3576a4938a9406e0eaf3e",
    "wave109_selftest_blob": "f2142dc67475eba86d4c20975d53551cfb1170b0",
    "verifier_pr": 34,
    "verifier_verdict": "FAIL_SURVIVING_TRANSITION_RECORD_IGNORED_BY_COMMIT_STATUS_GUARD",
}

HISTORY_NONE = w109.HISTORY_NONE
HISTORY_VALID = w109.HISTORY_VALID
HISTORY_INCOMPLETE = w109.HISTORY_INCOMPLETE
HISTORY_UNRESOLVED = w109.HISTORY_UNRESOLVED
HOLD_INCOMPLETE = w109.HOLD_INCOMPLETE
HOLD_UNRESOLVED = w109.HOLD_UNRESOLVED


def _dict_store(value, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label}-store-shape-invalid")
    return value


def _validated_transitions(transition_store: dict) -> dict[str, dict]:
    store = _dict_store(transition_store, "transition")
    rows: dict[str, dict] = {}
    for sha, body in store.items():
        if not isinstance(sha, str) or len(sha) != 64 or not isinstance(body, dict):
            raise ValueError("transition-row-shape-invalid")
        tr = w100.get_transition(store, sha)
        expected_state = q.binding(tr["target_app_state_sha"], tr["target_registry_sha"])
        if tr.get("target_state_sha") != expected_state:
            raise ValueError("transition-target-state-binding-invalid")
        rows[sha] = tr
    return rows


def _committed_authorities(base: dict) -> list[str]:
    rows = base.get("committed_authority_shas")
    if isinstance(rows, list):
        return list(rows)
    nested = base.get("wave108", {})
    rows = nested.get("committed_authority_shas") if isinstance(nested, dict) else None
    return list(rows) if isinstance(rows, list) else []


def commit_status_state(
    st: dict,
    boot: dict,
    rt: dict | None,
    registry_store: dict,
    binding_store: dict,
    transition_store: dict,
) -> dict:
    """Classify commit history using Wave 109 plus the retained transition evidence family."""
    base = w109.commit_status_state(st, boot, rt, registry_store, binding_store)
    status = base.get("status")
    if status in (HISTORY_NONE, HISTORY_INCOMPLETE):
        return {
            "status": status,
            "reason": "wave109-base-" + str(base.get("reason")),
            "wave109": base,
        }

    try:
        transitions = _validated_transitions(transition_store)
    except Exception as exc:
        return {
            "status": HISTORY_INCOMPLETE,
            "reason": f"transition-evidence-verification:{type(exc).__name__}:{exc}",
            "wave109": base,
        }

    # If Wave 109 already sees unmanifested L/C/U/binding evidence, preserve that HOLD. Add the
    # transition identities to the report instead of trying to reinterpret the lower-layer reason.
    if status == HISTORY_UNRESOLVED:
        return {
            "status": HISTORY_UNRESOLVED,
            "reason": str(base.get("reason")),
            "wave109": base,
            "transition_count": len(transitions),
            "transition_shas": sorted(transitions),
        }
    if status != HISTORY_VALID:
        return {
            "status": HISTORY_INCOMPLETE,
            "reason": "unexpected-wave109-history-status",
            "wave109": base,
        }

    committed = _committed_authorities(base)
    by_target: dict[str, list[tuple[str, dict]]] = {}
    for sha, tr in transitions.items():
        target = tr.get("target_authority_sha")
        if not isinstance(target, str):
            return {
                "status": HISTORY_INCOMPLETE,
                "reason": "transition-target-authority-invalid",
                "wave109": base,
            }
        by_target.setdefault(target, []).append((sha, tr))

    expected_transition_shas: set[str] = set()
    previous_authority: str | None = None
    try:
        for authority_sha in committed:
            candidates = by_target.get(authority_sha, [])
            if len(candidates) != 1:
                raise ValueError("committed-authority-transition-match-not-unique")
            transition_sha, tr = candidates[0]
            link, cp, _use = g.w98.resolve(st, authority_sha, boot)
            if tr.get("target_checkpoint_sha") != cp.get("checkpoint_sha"):
                raise ValueError("transition-checkpoint-mismatch")
            if tr.get("predecessor_authority_sha") != previous_authority:
                raise ValueError("transition-predecessor-authority-mismatch")
            if tr.get("target_authority_sha") != link.get("authority_sha"):
                raise ValueError("transition-authority-mismatch")
            expected_transition_shas.add(transition_sha)
            previous_authority = authority_sha
    except Exception as exc:
        return {
            "status": HISTORY_INCOMPLETE,
            "reason": f"committed-transition-lineage:{type(exc).__name__}:{exc}",
            "wave109": base,
        }

    extra_transitions = sorted(set(transitions) - expected_transition_shas)
    if extra_transitions:
        return {
            "status": HISTORY_UNRESOLVED,
            "reason": "retained-unmanifested-transition-evidence",
            "wave109": base,
            "committed_count": len(committed),
            "committed_authority_shas": committed,
            "expected_transition_shas": sorted(expected_transition_shas),
            "extra_transition_shas": extra_transitions,
            "extra_transition_targets": [
                transitions[sha].get("target_authority_sha") for sha in extra_transitions
            ],
        }

    return {
        "status": HISTORY_VALID,
        "reason": "markers-retained-transaction-and-transition-evidence-agree",
        "wave109": base,
        "committed_count": len(committed),
        "committed_authority_shas": committed,
        "expected_transition_shas": sorted(expected_transition_shas),
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
    result = w109.adopt_genesis(
        rt, st, boot, services, registry_store, certificate_store, domain, binding_store
    )
    state = commit_status_state(
        st, boot, rt, registry_store, binding_store, transition_store
    )
    if state["status"] != HISTORY_VALID:
        raise ValueError(f"Wave 110 genesis evidence HOLD: {state['status']}")
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
    if state["status"] == HISTORY_INCOMPLETE:
        return HOLD_INCOMPLETE
    if state["status"] == HISTORY_UNRESOLVED:
        return HOLD_UNRESOLVED
    return w109.authority(
        rt,
        st,
        boot,
        services,
        registry_store,
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
        raise ValueError("Wave 110 predecessor HOLD")
    return w109.prepare(
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
        target_user_app_state_sha,
        target_remote_registry_sha,
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
) -> str:
    return w109.commit(
        rt, st, boot, registry_store, transition_store, link_sha, transition_sha, binding_store, n
    )


def publish(
    rt: dict,
    st: dict,
    boot: dict,
    services: dict,
    tokens: dict,
    registry_store: dict,
    slot: str,
) -> str:
    return w109.publish(rt, st, boot, services, tokens, registry_store, slot)


def certify_and_sync(
    rt: dict,
    st: dict,
    boot: dict,
    services: dict,
    registry_store: dict,
    certificate_store: dict,
    domain: w104.CertificateWitnessDomain,
    slots: tuple[str, ...] | list[str] | None = None,
) -> tuple[str, dict]:
    return w109.certify_and_sync(
        rt, st, boot, services, registry_store, certificate_store, domain, slots
    )


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
    unresolved = commit_status_state(
        st, boot, rt, registry_store, binding_store, transition_store
    )
    if unresolved["status"] != HISTORY_UNRESOLVED:
        raise RuntimeError(f"Wave 110 prepare did not enter unresolved state: {unresolved}")
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
        raise RuntimeError(f"Wave 110 local commit failed: {result}")
    resolved = commit_status_state(
        st, boot, rt, registry_store, binding_store, transition_store
    )
    if resolved["status"] != HISTORY_VALID:
        raise RuntimeError(f"Wave 110 commit ambiguity did not clear: {resolved}")
    for slot in q.REMOTE_IDS:
        remote_result = publish(rt, st, boot, services, tokens, registry_store, slot)
        if remote_result not in ("APPENDED", "ALREADY_CURRENT"):
            raise RuntimeError(f"Wave 110 publish failed for {slot}: {remote_result}")
    certificate_sha, certificate = certify_and_sync(
        rt, st, boot, services, registry_store, certificate_store, domain
    )
    final = authority(
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
    if not final.startswith("AUTHORITATIVE"):
        raise RuntimeError(f"Wave 110 final authority failed: {final}")
    return cp, use, link, transition_sha, body, certificate_sha, certificate
