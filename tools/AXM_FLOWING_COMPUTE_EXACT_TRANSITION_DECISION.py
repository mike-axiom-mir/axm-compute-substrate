#!/usr/bin/env python3
"""AXM Flowing Compute Wave 114: exact transition decision binding.

Additive experiment over exact Wave 113. Independent verifier PR #38 showed that Wave 113's
one-row recovery could lose the genuine unprovenanced transition body after the lower commit,
accept a newly content-addressed semantically equivalent replacement, and then permanently bind
that replacement SHA into provenance.

Wave 114 adds a separate append-only commit-decision ledger inside the same modeled Python failure
domain. The exact (authority_sha, transition_sha) pair is sealed before the lower Wave-110 commit.
Recovery is allowed only for that exact pre-bound transition identity. Transition bodies are also
validated against the exact Wave-100 v1 field set so ignored extension fields cannot silently create
another accepted identity.

This is still same-process modeled durability, not an OS-process, power-loss, device, network, or
provider-independent witness. No performance, energy, retained/incremental/dormant-compute, merge,
or CANON claim is made.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy

import AXM_FLOWING_COMPUTE_RECOVERY_ATOMICITY as w113
import AXM_FLOWING_COMPUTE_TRANSITION_PROVENANCE_LEDGER as w111
import AXM_FLOWING_COMPUTE_TRANSITION_EVIDENCE_GUARD as w110
import AXM_FLOWING_COMPUTE_REMOTE_REGISTRY_MONOTONICITY as w100
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w104

q = w113.q
g = w113.g

SRC = {
    "wave113_builder_head": "3a2a19a9317291da82bda34d7dbe5fbc5d2a4ac7",
    "wave113_tested_source_commit": "dfedcab483ba6f798e0cd8e18a8a0c893397efd5",
    "wave113_tool_blob": "3d948226a00572f9e9ebca5062c395082dc6ec02",
    "wave113_selftest_blob": "aea9be7dbefb3dd5a1c60752b11b05d4980db96d",
    "verifier_pr": 38,
    "verifier_head_at_wave114_start": "ec9dbc94cb495e2d9530c5f222f4056cd033a10b",
    "verifier_verdict": "FAIL_RECOVERY_BINDS_SUBSTITUTED_TRANSITION_IDENTITY",
}

DECISION_STORE = "flowing_compute_wave114_commit_decisions"
DECISION_SCHEMA = "axm.flowing-compute.commit-decision/w114-v1"
HISTORY_NONE = w113.HISTORY_NONE
HISTORY_VALID = w113.HISTORY_VALID
HISTORY_INCOMPLETE = w113.HISTORY_INCOMPLETE
HISTORY_UNRESOLVED = w113.HISTORY_UNRESOLVED
HOLD_INCOMPLETE = w113.HOLD_INCOMPLETE
HOLD_UNRESOLVED = w113.HOLD_UNRESOLVED

TRANSITION_FIELDS = {
    "schema",
    "predecessor_authority_sha",
    "target_authority_sha",
    "target_checkpoint_sha",
    "current_registry_sha",
    "current_generation",
    "target_registry_sha",
    "target_generation",
    "transition_kind",
    "changed_slots",
    "changed_fields",
    "target_app_state_sha",
    "target_state_sha",
    "transition_sha",
}
DECISION_FIELDS = {
    "schema",
    "seq",
    "epoch",
    "predecessor_decision_sha",
    "predecessor_authority_sha",
    "authority_sha",
    "transition_sha",
    "checkpoint_sha",
    "target_state_sha",
    "current_registry_sha",
    "target_registry_sha",
    "decision",
    "decision_sha",
}


def _canonical_sha(body: dict, field: str) -> str:
    x = deepcopy(body)
    x[field] = ""
    raw = json.dumps(x, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _seal_decision(body: dict) -> dict:
    out = deepcopy(body)
    out["decision_sha"] = ""
    out["decision_sha"] = _canonical_sha(out, "decision_sha")
    return out


def _check_decision(body: dict, key: str | None = None) -> None:
    if set(body) != DECISION_FIELDS:
        raise ValueError("decision-field-set-mismatch")
    if body.get("schema") != DECISION_SCHEMA:
        raise ValueError("decision-schema-mismatch")
    if body.get("decision") != "COMMIT":
        raise ValueError("decision-kind-mismatch")
    expected = _canonical_sha(body, "decision_sha")
    if body.get("decision_sha") != expected:
        raise ValueError("decision-seal-mismatch")
    if key is not None and key != expected:
        raise ValueError("decision-key-body-mismatch")


def _strict_transition_get(store: dict, sha: str) -> dict:
    tr = w100.get_transition(store, sha)
    if set(tr) != TRANSITION_FIELDS:
        raise ValueError("transition-field-set-mismatch")
    if tr.get("schema") != w100.TRANSITION_SCHEMA:
        raise ValueError("transition-schema-mismatch")
    return tr


def _decision_rows(st: dict, *, allow_missing: bool = False) -> list[tuple[str, dict]] | None:
    store = st.get(DECISION_STORE)
    if store is None:
        if allow_missing:
            return None
        raise ValueError("decision-store-missing")
    if not isinstance(store, dict):
        raise ValueError("decision-store-invalid")
    rows = []
    seen_seq = set()
    for sha, raw in store.items():
        if not isinstance(sha, str) or not isinstance(raw, dict):
            raise ValueError("decision-store-entry-invalid")
        body = deepcopy(raw)
        _check_decision(body, sha)
        seq = body.get("seq")
        if not isinstance(seq, int) or seq < 1 or seq in seen_seq:
            raise ValueError("decision-sequence-invalid")
        seen_seq.add(seq)
        rows.append((sha, body))
    rows.sort(key=lambda row: row[1]["seq"])
    previous_sha = None
    previous_authority = None
    for expected_seq, (sha, body) in enumerate(rows, start=1):
        if body["seq"] != expected_seq or body["epoch"] != expected_seq:
            raise ValueError("decision-chain-sequence-gap")
        if body["predecessor_decision_sha"] != previous_sha:
            raise ValueError("decision-predecessor-sha-mismatch")
        if body["predecessor_authority_sha"] != previous_authority:
            raise ValueError("decision-predecessor-authority-mismatch")
        previous_sha = sha
        previous_authority = body["authority_sha"]
    return rows


def _ensure_commit_decision(st: dict, boot: dict, registry_store: dict,
                            transition_store: dict, link_sha: str,
                            transition_sha: str) -> str:
    transition = _strict_transition_get(transition_store, transition_sha)
    link, cp, _use = g.w98.resolve(st, link_sha, boot)
    if transition.get("target_authority_sha") != link_sha:
        raise ValueError("decision-transition-authority-mismatch")
    if transition.get("target_checkpoint_sha") != cp.get("checkpoint_sha"):
        raise ValueError("decision-transition-checkpoint-mismatch")
    if transition.get("target_state_sha") != cp.get("state_sha"):
        raise ValueError("decision-transition-state-mismatch")

    rows = _decision_rows(st)
    assert rows is not None
    by_authority = {body["authority_sha"]: (sha, body) for sha, body in rows}
    if link_sha in by_authority:
        sha, body = by_authority[link_sha]
        if body["transition_sha"] != transition_sha:
            raise ValueError("decision-authority-bound-to-different-transition")
        return sha

    previous_sha = rows[-1][0] if rows else None
    previous_authority = rows[-1][1]["authority_sha"] if rows else None
    if transition.get("predecessor_authority_sha") != previous_authority:
        raise ValueError("decision-transition-predecessor-mismatch")

    seq = len(rows) + 1
    body = _seal_decision({
        "schema": DECISION_SCHEMA,
        "seq": seq,
        "epoch": seq,
        "predecessor_decision_sha": previous_sha,
        "predecessor_authority_sha": previous_authority,
        "authority_sha": link_sha,
        "transition_sha": transition_sha,
        "checkpoint_sha": cp.get("checkpoint_sha"),
        "target_state_sha": transition.get("target_state_sha"),
        "current_registry_sha": transition.get("current_registry_sha"),
        "target_registry_sha": transition.get("target_registry_sha"),
        "decision": "COMMIT",
        "decision_sha": "",
    })
    store = st[DECISION_STORE]
    sha = body["decision_sha"]
    if sha in store and store[sha] != body:
        raise ValueError("decision-collision")
    store[sha] = body
    return sha


def _validate_decisions_against_valid_history(st: dict, boot: dict,
                                              registry_store: dict,
                                              transition_store: dict,
                                              base: dict) -> dict:
    try:
        rows = _decision_rows(st)
        assert rows is not None
        committed = list(base.get("committed_authority_shas", []))
        expected_transitions = list(base.get("expected_transition_shas", []))
        if len(rows) != len(committed):
            status = HISTORY_UNRESOLVED if len(rows) > len(committed) else HISTORY_INCOMPLETE
            return {
                "status": status,
                "reason": "commit-decision-count-does-not-match-committed-history",
                "wave113": base,
                "decision_count": len(rows),
                "committed_count": len(committed),
            }
        if expected_transitions and len(expected_transitions) != len(committed):
            raise ValueError("base-expected-transition-count-mismatch")
        for idx, ((decision_sha, decision), authority_sha) in enumerate(zip(rows, committed)):
            if decision["authority_sha"] != authority_sha:
                raise ValueError("decision-authority-order-mismatch")
            if expected_transitions and decision["transition_sha"] != expected_transitions[idx]:
                raise ValueError("decision-transition-provenance-mismatch")
            tr = _strict_transition_get(transition_store, decision["transition_sha"])
            link, cp, _use = g.w98.resolve(st, authority_sha, boot)
            if decision["checkpoint_sha"] != cp.get("checkpoint_sha"):
                raise ValueError("decision-checkpoint-mismatch")
            if decision["target_state_sha"] != tr.get("target_state_sha"):
                raise ValueError("decision-target-state-mismatch")
            if decision["current_registry_sha"] != tr.get("current_registry_sha"):
                raise ValueError("decision-current-registry-mismatch")
            if decision["target_registry_sha"] != tr.get("target_registry_sha"):
                raise ValueError("decision-target-registry-mismatch")
        return {
            **base,
            "status": HISTORY_VALID,
            "reason": "wave113-history-and-exact-commit-decisions-agree",
            "decision_count": len(rows),
            "decision_head_sha": rows[-1][0] if rows else "",
        }
    except Exception as exc:
        return {
            "status": HISTORY_INCOMPLETE,
            "reason": f"commit-decision-verification:{type(exc).__name__}:{exc}",
            "wave113": base,
        }


def commit_status_state(st: dict, boot: dict, rt: dict | None, registry_store: dict,
                        binding_store: dict, transition_store: dict) -> dict:
    base = w113.commit_status_state(st, boot, rt, registry_store, binding_store, transition_store)
    status = base.get("status")
    try:
        rows = _decision_rows(st, allow_missing=True)
    except Exception as exc:
        return {
            "status": HISTORY_INCOMPLETE,
            "reason": f"commit-decision-verification:{type(exc).__name__}:{exc}",
            "wave113": base,
        }

    if rows is None:
        return {
            "status": HISTORY_INCOMPLETE,
            "reason": "commit-decision-store-missing",
            "wave113": base,
        }

    if status == HISTORY_NONE:
        if rows:
            return {
                "status": HISTORY_UNRESOLVED,
                "reason": "lower-history-none-but-commit-decision-survives",
                "wave113": base,
                "decision_count": len(rows),
            }
        return base

    if status == HISTORY_VALID:
        return _validate_decisions_against_valid_history(
            st, boot, registry_store, transition_store, base
        )

    if status in (HISTORY_INCOMPLETE, HISTORY_UNRESOLVED):
        return {
            **base,
            "wave113": base,
            "decision_count": len(rows),
            "decision_head_sha": rows[-1][0] if rows else "",
        }

    return {
        "status": HISTORY_INCOMPLETE,
        "reason": "unexpected-wave113-history-status",
        "wave113": base,
    }


def _decision_for_authority(st: dict, authority_sha: str) -> dict:
    rows = _decision_rows(st)
    assert rows is not None
    matches = [body for _sha, body in rows if body["authority_sha"] == authority_sha]
    if len(matches) != 1:
        raise ValueError("recovery-exact-commit-decision-not-unique")
    return matches[0]


def _recover_missing_trailing_provenance(st: dict, boot: dict, rt: dict | None,
                                         registry_store: dict, transition_store: dict,
                                         binding_store: dict, link_sha: str,
                                         transition_sha: str,
                                         *, fault_after_append: bool = False) -> str | None:
    lower = w110.commit_status_state(st, boot, rt, registry_store, binding_store, transition_store)
    if lower.get("status") != HISTORY_VALID:
        return None
    committed = list(lower.get("committed_authority_shas", []))
    if link_sha not in committed:
        return None

    decision = _decision_for_authority(st, link_sha)
    if decision["transition_sha"] != transition_sha:
        raise ValueError("recovery-transition-does-not-match-durable-commit-decision")
    _strict_transition_get(transition_store, transition_sha)

    recovered = w113._recover_missing_trailing_provenance(
        st, boot, rt, registry_store, transition_store, binding_store,
        link_sha, transition_sha, fault_after_append=fault_after_append
    )
    if recovered is None:
        return None
    final = commit_status_state(
        st, boot, rt, registry_store, binding_store, transition_store
    )
    if final.get("status") != HISTORY_VALID:
        raise RuntimeError(f"Wave 114 recovery did not settle exact decision history: {final}")
    if recovered == "ALREADY_COMMITTED":
        return recovered
    return "COMMITTED_RECOVERED_EXACT_DECISION"


def adopt_genesis(rt: dict, st: dict, boot: dict, services: dict, registry_store: dict,
                  transition_store: dict, certificate_store: dict,
                  domain: w104.CertificateWitnessDomain, binding_store: dict) -> str:
    if DECISION_STORE in st:
        raise ValueError("decision-store-already-present")
    st[DECISION_STORE] = {}
    result = w113.adopt_genesis(
        rt, st, boot, services, registry_store, transition_store,
        certificate_store, domain, binding_store
    )
    state = commit_status_state(st, boot, rt, registry_store, binding_store, transition_store)
    if state.get("status") not in (HISTORY_NONE, HISTORY_VALID):
        raise ValueError(f"Wave 114 genesis evidence HOLD: {state}")
    return result


def authority(rt: dict, st: dict, boot: dict, services: dict, registry_store: dict,
              transition_store: dict, certificate_store: dict,
              domain: w104.CertificateWitnessDomain, binding_store: dict,
              resolved_endpoints: dict | None = None) -> str:
    state = commit_status_state(st, boot, rt, registry_store, binding_store, transition_store)
    if state.get("status") == HISTORY_INCOMPLETE:
        return HOLD_INCOMPLETE
    if state.get("status") == HISTORY_UNRESOLVED:
        return HOLD_UNRESOLVED
    return w113.authority(
        rt, st, boot, services, registry_store, transition_store,
        certificate_store, domain, binding_store, resolved_endpoints
    )


def prepare(rt: dict, st: dict, priv: dict, boot: dict, services: dict,
            registry_store: dict, transition_store: dict, certificate_store: dict,
            domain: w104.CertificateWitnessDomain, binding_store: dict,
            target_user_app_state_sha: str | None = None,
            target_remote_registry_sha: str | None = None) -> tuple:
    out = w113.prepare(
        rt, st, priv, boot, services, registry_store, transition_store,
        certificate_store, domain, binding_store,
        target_user_app_state_sha, target_remote_registry_sha
    )
    transition_sha = out[3]
    _strict_transition_get(transition_store, transition_sha)
    return out


def commit(rt: dict, st: dict, boot: dict, registry_store: dict, transition_store: dict,
           link_sha: str, transition_sha: str, binding_store: dict,
           n: int | None = None, *, fault_after_lower_commit: bool = False) -> str:
    recovered = _recover_missing_trailing_provenance(
        st, boot, rt, registry_store, transition_store, binding_store,
        link_sha, transition_sha
    )
    if recovered is not None:
        return recovered

    _strict_transition_get(transition_store, transition_sha)
    _ensure_commit_decision(
        st, boot, registry_store, transition_store, link_sha, transition_sha
    )

    result = w110.commit(
        rt, st, boot, registry_store, transition_store,
        link_sha, transition_sha, binding_store, n
    )
    if result != "COMMITTED":
        return result
    if fault_after_lower_commit:
        raise RuntimeError("injected-wave114-crash-after-lower-commit-before-provenance")

    marker = w111._append_provenance(
        st, boot, registry_store, transition_store, link_sha, transition_sha
    )
    if marker not in ("RECORDED", "ALREADY_RECORDED"):
        raise RuntimeError(f"unexpected Wave 114 provenance result: {marker}")
    state = commit_status_state(
        st, boot, rt, registry_store, binding_store, transition_store
    )
    if state.get("status") != HISTORY_VALID:
        raise RuntimeError(f"Wave 114 commit did not settle exact decision history: {state}")
    return "COMMITTED"


def publish(rt: dict, st: dict, boot: dict, services: dict, tokens: dict,
            registry_store: dict, slot: str) -> str:
    return w113.publish(rt, st, boot, services, tokens, registry_store, slot)


def certify_and_sync(rt: dict, st: dict, boot: dict, services: dict, registry_store: dict,
                     certificate_store: dict, domain: w104.CertificateWitnessDomain,
                     slots: tuple[str, ...] | list[str] | None = None) -> tuple[str, dict]:
    return w113.certify_and_sync(
        rt, st, boot, services, registry_store, certificate_store, domain, slots
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
        raise RuntimeError(f"Wave 114 local commit failed: {result}")
    for slot in q.REMOTE_IDS:
        remote_result = publish(rt, st, boot, services, tokens, registry_store, slot)
        if remote_result not in ("APPENDED", "ALREADY_CURRENT"):
            raise RuntimeError(f"Wave 114 remote publish failed for {slot}: {remote_result}")
    cert_result, cert_body = certify_and_sync(
        rt, st, boot, services, registry_store, certificate_store, domain
    )
    if not isinstance(cert_result, str):
        raise RuntimeError(f"Wave 114 certificate result invalid: {cert_result!r}")
    verdict = authority(
        rt, st, boot, services, registry_store, transition_store,
        certificate_store, domain, binding_store
    )
    if not verdict.startswith("AUTHORITATIVE"):
        raise RuntimeError(f"Wave 114 authority failed: {verdict}")
    return cp, use, link, transition_sha, body, cert_result, cert_body
