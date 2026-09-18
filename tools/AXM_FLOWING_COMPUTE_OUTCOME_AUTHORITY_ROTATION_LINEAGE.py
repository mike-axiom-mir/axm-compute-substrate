#!/usr/bin/env python3
"""AXM Flowing Compute Wave 118: old-root-authorized outcome-authority rotation lineage.

Wave 117 made one exact Wave-116 outcome authority durable by anchoring its identity through the
already signed Wave-105 checkpoint/root-binding path, but deliberately refused signer rotation.
Wave 118 adds the smallest same-process rotation contract that does not silently replace that root:

* generation 0 remains the exact Wave-117 root;
* every rotated root names its exact predecessor root and predecessor authority identity;
* the predecessor outcome credential authenticates the successor root before it can be checkpointed;
* accepted checkpoints may repeat the current root or advance exactly one authorized root generation;
* historical rejection outcomes remain verifiable with the exact credential generation that signed
  them, and each rejected transition must point through its prepared Wave-105 binding/envelope to the
  same anchored root generation as its authenticated outcome;
* a crash after the successor root is committed but before live credential activation fails closed;
  recovery may activate only the exact successor already anchored by the committed checkpoint.

The keyring in this wave is deliberately a same-process credential registry. It retains predecessor
HMAC credentials so historical outcomes and rotation authorizations can be checked. This is not key
erasure, OS-process isolation, a durable external witness, hardware security, physical monotonicity,
network/provider independence, or a performance/energy/retained-compute result. Whole-domain rollback
and bootstrap root choice remain explicit counterexamples. Migration from arbitrary pre-Wave-117
worlds is not claimed. No merge, auto-merge, or CANON promotion is performed.
"""
from __future__ import annotations

import json
from copy import deepcopy

import AXM_FLOWING_COMPUTE_OUTCOME_AUTHORITY_ROOT_ANCHOR as w117
import AXM_FLOWING_COMPUTE_AUTHENTICATED_REJECTION_OUTCOME as w116

w115 = w116.w115
w114 = w116.w114
w111 = w116.w111
w110 = w116.w110
w105 = w117.w105
w104 = w117.w104
q = w117.q
g = w117.g

SRC = {
    "wave117_tested_source_commit": "1c033d96e792c9f8532bf2355c9f1ec958da969a",
    "wave117_tool_blob": "c2d3b7f9176f24dc9fd5599527bb3619f89f01e7",
    "wave117_selftest_blob": "859365b19e5cd9537b49144f9e43303affd281eb",
    "wave117_ci_run": 35249201898,
    "wave117_artifact_sha256": "cc4cdf2fea411835c63570be7b0e3408ed45a8377f1611ac334482705a8c16d1",
}

OutcomeAuthorityDomain = w116.OutcomeAuthorityDomain
new_outcome_authority_domain = w116.new_outcome_authority_domain

HISTORY_NONE = w116.HISTORY_NONE
HISTORY_VALID = w116.HISTORY_VALID
HISTORY_INCOMPLETE = w116.HISTORY_INCOMPLETE
HISTORY_UNRESOLVED = w116.HISTORY_UNRESOLVED
HOLD_INCOMPLETE = w116.HOLD_INCOMPLETE
HOLD_UNRESOLVED = w116.HOLD_UNRESOLVED
STABLE_SEMANTIC_REJECTIONS = w116.STABLE_SEMANTIC_REJECTIONS

ROTATED_ROOT_SCHEMA = "axm.flowing-compute.outcome-authority-root-rotation/w118-v1"
ROTATED_ROOT_FIELDS = {
    "schema",
    "generation",
    "predecessor_root_sha",
    "predecessor_authority_id",
    "outcome_authority_id",
    "predecessor_auth_tag",
    "root_sha",
}


class OutcomeAuthorityKeyring:
    """Same-process historical credential registry; not a hardware/process security boundary."""

    __slots__ = ("_domains", "current_authority_id")

    def __init__(self, initial: OutcomeAuthorityDomain):
        self._domains: dict[str, OutcomeAuthorityDomain] = {}
        self.current_authority_id = ""
        self.add(initial, make_current=True)

    def add(self, domain: OutcomeAuthorityDomain, *, make_current: bool = False) -> None:
        if not isinstance(domain, OutcomeAuthorityDomain):
            raise ValueError("outcome-authority-domain-invalid")
        authority_id = domain.authority_id
        existing = self._domains.get(authority_id)
        if existing is not None and existing is not domain:
            # Same authority_id implies same secret material for this model; refuse an opaque object
            # substitution instead of guessing that two credentials are interchangeable.
            probe = b"axm-wave118-keyring-identity-probe"
            if existing.sign(probe) != domain.sign(probe):
                raise ValueError("outcome-authority-id-collision-or-credential-substitution")
        self._domains[authority_id] = domain
        if make_current:
            self.current_authority_id = authority_id

    def domain(self, authority_id: str) -> OutcomeAuthorityDomain:
        domain = self._domains.get(authority_id)
        if domain is None:
            raise ValueError("outcome-authority-credential-not-in-keyring")
        return domain

    @property
    def current(self) -> OutcomeAuthorityDomain:
        return self.domain(self.current_authority_id)

    def set_current(self, authority_id: str) -> None:
        self.domain(authority_id)
        self.current_authority_id = authority_id

    def ids(self) -> set[str]:
        return set(self._domains)


def new_outcome_authority_keyring(initial: OutcomeAuthorityDomain) -> OutcomeAuthorityKeyring:
    return OutcomeAuthorityKeyring(initial)


def _rotation_payload(body: dict) -> bytes:
    payload = {
        key: body[key]
        for key in sorted(body)
        if key not in {"predecessor_auth_tag", "root_sha"}
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _seal_rotated_root(
    predecessor: dict,
    predecessor_domain: OutcomeAuthorityDomain,
    successor_domain: OutcomeAuthorityDomain,
) -> dict:
    if predecessor.get("outcome_authority_id") != predecessor_domain.authority_id:
        raise ValueError("rotation-predecessor-credential-root-mismatch")
    if successor_domain.authority_id == predecessor_domain.authority_id:
        raise ValueError("rotation-successor-must-change-authority")
    generation = predecessor.get("generation")
    if not isinstance(generation, int) or generation < 0:
        raise ValueError("rotation-predecessor-generation-invalid")
    body = {
        "schema": ROTATED_ROOT_SCHEMA,
        "generation": generation + 1,
        "predecessor_root_sha": predecessor["root_sha"],
        "predecessor_authority_id": predecessor_domain.authority_id,
        "outcome_authority_id": successor_domain.authority_id,
        "predecessor_auth_tag": "",
        "root_sha": "",
    }
    body["predecessor_auth_tag"] = predecessor_domain.sign(_rotation_payload(body))
    body["root_sha"] = w114._canonical_sha(body, "root_sha")
    return body


def _check_rotated_root_structural(body: dict, key: str | None = None) -> dict:
    if not isinstance(body, dict) or set(body) != ROTATED_ROOT_FIELDS:
        raise ValueError("rotated-outcome-root-field-set-mismatch")
    out = deepcopy(body)
    if out.get("schema") != ROTATED_ROOT_SCHEMA:
        raise ValueError("rotated-outcome-root-schema-mismatch")
    generation = out.get("generation")
    if not isinstance(generation, int) or generation < 1:
        raise ValueError("rotated-outcome-root-generation-invalid")
    for field in ("predecessor_root_sha", "predecessor_authority_id", "outcome_authority_id"):
        if not w117._is_sha(out.get(field)):
            raise ValueError(f"rotated-outcome-root-{field}-invalid")
    if out["predecessor_authority_id"] == out["outcome_authority_id"]:
        raise ValueError("rotated-outcome-root-authority-did-not-change")
    tag = out.get("predecessor_auth_tag")
    if not isinstance(tag, str) or len(tag) != 64:
        raise ValueError("rotated-outcome-root-auth-tag-invalid")
    expected = w114._canonical_sha(out, "root_sha")
    if out.get("root_sha") != expected:
        raise ValueError("rotated-outcome-root-seal-mismatch")
    if key is not None and key != expected:
        raise ValueError("rotated-outcome-root-key-body-mismatch")
    return out


def _root_body(st: dict, root_sha: str) -> dict:
    store = st.get(w117.OUTCOME_ROOT_STORE)
    if not isinstance(store, dict):
        raise ValueError("outcome-root-store-missing-or-invalid")
    raw = store.get(root_sha)
    if not isinstance(raw, dict):
        raise ValueError("checkpoint-anchored-outcome-root-body-missing")
    if raw.get("schema") == w117.OUTCOME_ROOT_SCHEMA:
        return w117._check_root(raw, root_sha)
    return _check_rotated_root_structural(raw, root_sha)


def _verify_direct_successor(
    predecessor: dict,
    successor: dict,
    keyring: OutcomeAuthorityKeyring,
) -> None:
    successor = _check_rotated_root_structural(successor, successor.get("root_sha"))
    if successor["generation"] != predecessor.get("generation") + 1:
        raise ValueError("outcome-root-rotation-generation-discontinuity")
    if successor["predecessor_root_sha"] != predecessor.get("root_sha"):
        raise ValueError("outcome-root-rotation-predecessor-mismatch")
    if successor["predecessor_authority_id"] != predecessor.get("outcome_authority_id"):
        raise ValueError("outcome-root-rotation-predecessor-authority-mismatch")
    domain = keyring.domain(successor["predecessor_authority_id"])
    if not domain.verify(_rotation_payload(successor), successor["predecessor_auth_tag"]):
        raise ValueError("outcome-root-rotation-predecessor-authentication-failed")


def _checkpoint_root_lineage(
    rt: dict,
    st: dict,
    boot: dict,
    registry_store: dict,
    binding_store: dict,
    keyring: OutcomeAuthorityKeyring,
) -> tuple[dict, dict, dict, str, list[dict]]:
    """Verify roots in accepted checkpoint order, without requiring live-current credential match."""
    current, status = w105._current_binding(rt, st, boot, registry_store, binding_store)
    _head, retained_desc = w105.verify_binding_chain(
        binding_store, registry_store, current["binding_sha"]
    )
    retained = list(reversed(retained_desc))
    lineage: list[dict] = []
    current_envelope = None
    previous = None
    for binding in retained:
        envelope = w117._get_envelope(st, binding["user_app_state_sha"])
        root = _root_body(st, envelope["outcome_root_sha"])
        if previous is None:
            if root.get("schema") != w117.OUTCOME_ROOT_SCHEMA:
                raise ValueError("outcome-root-lineage-must-start-at-wave117-generation-zero")
            if root.get("generation") != 0 or root.get("predecessor_root_sha") is not None:
                raise ValueError("outcome-root-lineage-genesis-invalid")
            lineage.append(root)
            previous = root
        elif root["root_sha"] == previous["root_sha"]:
            pass
        else:
            _verify_direct_successor(previous, root, keyring)
            lineage.append(root)
            previous = root
        if binding["binding_sha"] == current["binding_sha"]:
            current_envelope = envelope
    if previous is None or current_envelope is None:
        raise ValueError("outcome-root-lineage-empty")
    return current, current_envelope, previous, status, lineage


def _current_anchor(
    rt: dict,
    st: dict,
    boot: dict,
    registry_store: dict,
    binding_store: dict,
    keyring: OutcomeAuthorityKeyring,
) -> tuple[dict, dict, dict, str, list[dict]]:
    current, envelope, root, status, lineage = _checkpoint_root_lineage(
        rt, st, boot, registry_store, binding_store, keyring
    )
    current_domain = keyring.current
    if root["outcome_authority_id"] != current_domain.authority_id:
        raise ValueError("checkpoint-anchored-current-outcome-authority-mismatch")
    mutable = w116._check_binding(st, current_domain)
    if mutable.get("outcome_authority_id") != root["outcome_authority_id"]:
        raise ValueError("wave116-binding-disagrees-with-current-rotated-root")
    return current, envelope, root, status, lineage


def _transition_root(
    st: dict,
    registry_store: dict,
    binding_store: dict,
    transition_store: dict,
    transition_sha: str,
) -> dict:
    transition = w115._strict_transition_get(transition_store, transition_sha)
    binding = w105.get_binding(
        binding_store, registry_store, transition["target_app_state_sha"]
    )
    envelope = w117._get_envelope(st, binding["user_app_state_sha"])
    return _root_body(st, envelope["outcome_root_sha"])


def _outcome_rows(
    st: dict,
    keyring: OutcomeAuthorityKeyring,
    *,
    allow_missing: bool = False,
) -> list[tuple[str, dict]] | None:
    store = st.get(w116.OUTCOME_STORE)
    if store is None:
        if allow_missing:
            return None
        raise ValueError("outcome-store-missing")
    if not isinstance(store, dict):
        raise ValueError("outcome-store-invalid")
    rows: list[tuple[str, dict]] = []
    seen_seq: set[int] = set()
    for sha, raw in store.items():
        if not isinstance(sha, str) or not isinstance(raw, dict):
            raise ValueError("outcome-store-entry-invalid")
        body = deepcopy(raw)
        domain = keyring.domain(body.get("outcome_authority_id"))
        w116._check_outcome(body, domain, sha)
        seq = body.get("seq")
        if not isinstance(seq, int) or seq < 1 or seq in seen_seq:
            raise ValueError("outcome-sequence-invalid")
        seen_seq.add(seq)
        rows.append((sha, body))
    rows.sort(key=lambda row: row[1]["seq"])
    previous_sha = None
    for expected_seq, (sha, body) in enumerate(rows, start=1):
        if body["seq"] != expected_seq:
            raise ValueError("outcome-chain-sequence-gap")
        if body["predecessor_outcome_sha"] != previous_sha:
            raise ValueError("outcome-predecessor-sha-mismatch")
        previous_sha = sha
    return rows


def _validated_rejections(
    st: dict,
    registry_store: dict,
    binding_store: dict,
    transition_store: dict,
    keyring: OutcomeAuthorityKeyring,
    lineage: list[dict],
) -> list[tuple[str, dict, str, dict]]:
    raw_rows = w115._rejection_rows(st, transition_store)
    assert raw_rows is not None
    outcomes = _outcome_rows(st, keyring)
    assert outcomes is not None
    if len(outcomes) != len(raw_rows):
        raise ValueError("rejection-outcome-cardinality-mismatch")

    anchored_authority_ids = {root["outcome_authority_id"] for root in lineage}
    by_rejection: dict[str, list[tuple[str, dict]]] = {}
    for outcome_sha, body in outcomes:
        if body["outcome_authority_id"] not in anchored_authority_ids:
            raise ValueError("outcome-authority-not-in-accepted-root-lineage")
        by_rejection.setdefault(body["rejection_sha"], []).append((outcome_sha, body))

    paired: list[tuple[str, dict, str, dict]] = []
    terminal: dict[str, tuple[str, str]] = {}
    raw_shas = {sha for sha, _body in raw_rows}
    for rejection_sha, rejection in raw_rows:
        matching = by_rejection.get(rejection_sha, [])
        if len(matching) != 1:
            raise ValueError("rejection-does-not-have-exactly-one-authenticated-outcome")
        outcome_sha, outcome = matching[0]
        for field in ("authority_sha", "transition_sha", "checkpoint_sha", "lower_result"):
            if outcome.get(field) != rejection.get(field):
                raise ValueError(f"authenticated-outcome-{field}-mismatch")
        transition_sha = rejection["transition_sha"]
        transition_root = _transition_root(
            st, registry_store, binding_store, transition_store, transition_sha
        )
        if transition_root["outcome_authority_id"] != outcome["outcome_authority_id"]:
            raise ValueError("rejection-outcome-authority-does-not-match-transition-root")
        if transition_sha in terminal:
            raise ValueError("rejection-transition-terminal-outcome-not-unique")
        terminal[transition_sha] = (rejection_sha, rejection["lower_result"])
        paired.append((rejection_sha, rejection, outcome_sha, outcome))

    for _outcome_sha, outcome in outcomes:
        if outcome["rejection_sha"] not in raw_shas:
            raise ValueError("authenticated-outcome-references-unknown-rejection")

    decisions = w114._decision_rows(st, allow_missing=True) or []
    committed_transition_shas = {body.get("transition_sha") for _sha, body in decisions}
    if committed_transition_shas & set(terminal):
        raise ValueError("transition-has-both-commit-and-reject-terminal-outcome")
    return paired


def _effective_transition_store(
    st: dict,
    registry_store: dict,
    binding_store: dict,
    transition_store: dict,
    keyring: OutcomeAuthorityKeyring,
    lineage: list[dict],
) -> dict:
    paired = _validated_rejections(
        st, registry_store, binding_store, transition_store, keyring, lineage
    )
    rejected = {rejection["transition_sha"] for _rsha, rejection, _osha, _outcome in paired}
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
    keyring: OutcomeAuthorityKeyring,
) -> dict:
    if rt is None:
        return {"status": HISTORY_INCOMPLETE, "reason": "rotation-lineage:runtime-required"}
    try:
        _binding, envelope, root, _status, lineage = _current_anchor(
            rt, st, boot, registry_store, binding_store, keyring
        )
        effective = _effective_transition_store(
            st, registry_store, binding_store, transition_store, keyring, lineage
        )
        paired = _validated_rejections(
            st, registry_store, binding_store, transition_store, keyring, lineage
        )
    except Exception as exc:
        return {
            "status": HISTORY_INCOMPLETE,
            "reason": f"outcome-authority-rotation-lineage:{type(exc).__name__}:{exc}",
        }
    base = w114.commit_status_state(
        st, boot, rt, registry_store, binding_store, effective
    )
    outcomes = _outcome_rows(st, keyring) or []
    return {
        **base,
        "wave114": base,
        "authenticated_rejected_transition_count": len(paired),
        "outcome_head_sha": outcomes[-1][0] if outcomes else "",
        "current_outcome_authority_id": root["outcome_authority_id"],
        "current_outcome_root_sha": root["root_sha"],
        "current_outcome_root_generation": root["generation"],
        "accepted_outcome_root_lineage": [r["root_sha"] for r in lineage],
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
    keyring: OutcomeAuthorityKeyring,
) -> str:
    result = w117.adopt_genesis(
        rt,
        st,
        boot,
        services,
        registry_store,
        transition_store,
        certificate_store,
        certificate_domain,
        binding_store,
        keyring.current,
    )
    state = commit_status_state(
        st, boot, rt, registry_store, binding_store, transition_store, keyring
    )
    if state.get("status") not in (HISTORY_NONE, HISTORY_VALID):
        raise ValueError(f"Wave 118 genesis lineage HOLD: {state}")
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
    keyring: OutcomeAuthorityKeyring,
    resolved_endpoints: dict | None = None,
) -> str:
    state = commit_status_state(
        st, boot, rt, registry_store, binding_store, transition_store, keyring
    )
    if state.get("status") == HISTORY_INCOMPLETE:
        return HOLD_INCOMPLETE
    if state.get("status") == HISTORY_UNRESOLVED:
        return HOLD_UNRESOLVED
    try:
        _binding, _envelope, _root, _status, lineage = _current_anchor(
            rt, st, boot, registry_store, binding_store, keyring
        )
        effective = _effective_transition_store(
            st, registry_store, binding_store, transition_store, keyring, lineage
        )
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
        certificate_domain,
        binding_store,
        resolved_endpoints,
    )


def _sync_prepared_transition(original: dict, effective: dict, transition_sha: str) -> None:
    transition = w115._strict_transition_get(effective, transition_sha)
    if transition_sha in original and original[transition_sha] != transition:
        raise ValueError("transition-collision-on-prepare-sync")
    original[transition_sha] = deepcopy(transition)


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
    keyring: OutcomeAuthorityKeyring,
    target_user_app_state_sha: str | None = None,
    target_remote_registry_sha: str | None = None,
) -> tuple:
    verdict = authority(
        rt, st, boot, services, registry_store, transition_store, certificate_store,
        certificate_domain, binding_store, keyring
    )
    if not verdict.startswith("AUTHORITATIVE"):
        raise ValueError("Wave 118 predecessor HOLD")
    _binding, current_envelope, current_root, _status, lineage = _current_anchor(
        rt, st, boot, registry_store, binding_store, keyring
    )
    user_app_state_sha = target_user_app_state_sha or current_envelope["user_app_state_sha"]
    envelope = w117._seal_envelope(user_app_state_sha, current_root["root_sha"])
    envelope_sha = w117._put_envelope(st, envelope)
    effective = _effective_transition_store(
        st, registry_store, binding_store, transition_store, keyring, lineage
    )
    out = w114.prepare(
        rt, st, priv, boot, services, registry_store, effective, certificate_store,
        certificate_domain, binding_store, envelope_sha, target_remote_registry_sha
    )
    _sync_prepared_transition(transition_store, effective, out[3])
    return out


publish = w114.publish
certify_and_sync = w114.certify_and_sync


def _append_authenticated_rejection(
    st: dict,
    registry_store: dict,
    binding_store: dict,
    transition_store: dict,
    transition_sha: str,
    lower_result: str,
    keyring: OutcomeAuthorityKeyring,
    lineage: list[dict],
    current_root: dict,
    *,
    fault_after_raw_rejection_before_outcome: bool = False,
) -> str:
    if lower_result not in STABLE_SEMANTIC_REJECTIONS:
        return "NOT_STABLE_REJECTION"
    current_domain = keyring.current
    if current_root["outcome_authority_id"] != current_domain.authority_id:
        raise ValueError("rejection-current-root-credential-mismatch")
    transition_root = _transition_root(
        st, registry_store, binding_store, transition_store, transition_sha
    )
    if transition_root["root_sha"] != current_root["root_sha"]:
        raise ValueError("rejection-transition-not-prepared-under-current-outcome-root")

    raw_result = w115._append_rejection(st, transition_store, transition_sha, lower_result)
    raw_rows = w115._rejection_rows(st, transition_store) or []
    matches = [(sha, body) for sha, body in raw_rows if body["transition_sha"] == transition_sha]
    if len(matches) != 1 or matches[0][1]["lower_result"] != lower_result:
        raise ValueError("raw-rejection-not-single-valued-after-append")
    rejection_sha, rejection = matches[0]

    if fault_after_raw_rejection_before_outcome:
        raise RuntimeError("injected-wave118-crash-after-raw-rejection-before-authenticated-outcome")

    existing_outcomes = _outcome_rows(st, keyring) or []
    same = [body for _sha, body in existing_outcomes if body["rejection_sha"] == rejection_sha]
    if same:
        if len(same) != 1:
            raise ValueError("rejection-has-multiple-authenticated-outcomes")
        body = same[0]
        if body["transition_sha"] != transition_sha or body["lower_result"] != lower_result:
            raise ValueError("rejection-authenticated-outcome-conflict")
        return "ALREADY_AUTHENTICATED_REJECTED"

    predecessor = existing_outcomes[-1][0] if existing_outcomes else None
    outcome = w116._seal_outcome(
        {
            "schema": w116.OUTCOME_SCHEMA,
            "seq": len(existing_outcomes) + 1,
            "predecessor_outcome_sha": predecessor,
            "rejection_sha": rejection_sha,
            "authority_sha": rejection["authority_sha"],
            "transition_sha": transition_sha,
            "checkpoint_sha": rejection["checkpoint_sha"],
            "lower_result": lower_result,
            "outcome_authority_id": current_domain.authority_id,
            "outcome_auth_tag": "",
            "outcome_sha": "",
        },
        current_domain,
    )
    store = st[w116.OUTCOME_STORE]
    outcome_sha = outcome["outcome_sha"]
    if outcome_sha in store and store[outcome_sha] != outcome:
        raise ValueError("authenticated-outcome-collision")
    store[outcome_sha] = outcome
    _validated_rejections(
        st, registry_store, binding_store, transition_store, keyring, lineage
    )
    return "REJECTED_AUTHENTICATED" if raw_result == "REJECTED_RECORDED" else "RAW_REJECTION_RECOVERED_AND_AUTHENTICATED"


def commit(
    rt: dict,
    st: dict,
    boot: dict,
    registry_store: dict,
    transition_store: dict,
    link_sha: str,
    transition_sha: str,
    binding_store: dict,
    keyring: OutcomeAuthorityKeyring,
    n: int | None = None,
    *,
    fault_after_raw_rejection_before_outcome: bool = False,
    fault_after_decision_before_lower_commit: bool = False,
    fault_after_lower_commit: bool = False,
) -> str:
    _binding, _envelope, current_root, _status, lineage = _current_anchor(
        rt, st, boot, registry_store, binding_store, keyring
    )
    paired = _validated_rejections(
        st, registry_store, binding_store, transition_store, keyring, lineage
    )
    existing = [
        rejection for _rsha, rejection, _osha, _outcome in paired
        if rejection["transition_sha"] == transition_sha
    ]
    if existing:
        if len(existing) != 1:
            raise ValueError("transition-rejection-terminal-outcome-not-unique")
        return existing[0]["lower_result"]

    target_root = _transition_root(
        st, registry_store, binding_store, transition_store, transition_sha
    )
    if target_root["root_sha"] != current_root["root_sha"]:
        return "OUTCOME_ROOT_TRANSITION_HOLD"

    effective = _effective_transition_store(
        st, registry_store, binding_store, transition_store, keyring, lineage
    )
    recovered = w114._recover_missing_trailing_provenance(
        st, boot, rt, registry_store, effective, binding_store, link_sha, transition_sha
    )
    if recovered is not None:
        return recovered

    w115._strict_transition_get(effective, transition_sha)
    preflight = w115._prevalidate_lower_commit(
        rt, st, boot, registry_store, effective, link_sha, transition_sha, binding_store, n
    )
    if preflight != "COMMITTED":
        if preflight in STABLE_SEMANTIC_REJECTIONS:
            _append_authenticated_rejection(
                st, registry_store, binding_store, transition_store, transition_sha,
                preflight, keyring, lineage, current_root,
                fault_after_raw_rejection_before_outcome=fault_after_raw_rejection_before_outcome,
            )
        return preflight

    w114._ensure_commit_decision(
        st, boot, registry_store, effective, link_sha, transition_sha
    )
    if fault_after_decision_before_lower_commit:
        raise RuntimeError("injected-wave118-crash-after-decision-before-lower-commit")
    result = w110.commit(
        rt, st, boot, registry_store, effective, link_sha, transition_sha, binding_store, n
    )
    if result != "COMMITTED":
        return f"HOLD_LOWER_CHANGED_AFTER_PREVALIDATION:{result}"
    if fault_after_lower_commit:
        raise RuntimeError("injected-wave118-crash-after-lower-commit-before-provenance")
    marker = w111._append_provenance(
        st, boot, registry_store, effective, link_sha, transition_sha
    )
    if marker not in ("RECORDED", "ALREADY_RECORDED"):
        raise RuntimeError(f"unexpected Wave 118 provenance result: {marker}")
    state = commit_status_state(
        st, boot, rt, registry_store, binding_store, transition_store, keyring
    )
    if state.get("status") != HISTORY_VALID:
        raise RuntimeError(f"Wave 118 commit did not settle exact rotation lineage history: {state}")
    return "COMMITTED"


def prepare_rotation(
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
    keyring: OutcomeAuthorityKeyring,
    successor_domain: OutcomeAuthorityDomain,
    target_user_app_state_sha: str | None = None,
) -> tuple:
    verdict = authority(
        rt, st, boot, services, registry_store, transition_store, certificate_store,
        certificate_domain, binding_store, keyring
    )
    if not verdict.startswith("AUTHORITATIVE"):
        raise ValueError("Wave 118 rotation predecessor HOLD")
    _binding, current_envelope, current_root, _status, lineage = _current_anchor(
        rt, st, boot, registry_store, binding_store, keyring
    )
    if successor_domain.authority_id in {r["outcome_authority_id"] for r in lineage}:
        raise ValueError("rotation-successor-authority-already-used")
    rotated_root = _seal_rotated_root(current_root, keyring.current, successor_domain)
    w117._put_root(st, rotated_root) if rotated_root.get("schema") == w117.OUTCOME_ROOT_SCHEMA else None
    root_store = st.setdefault(w117.OUTCOME_ROOT_STORE, {})
    root_sha = rotated_root["root_sha"]
    existing = root_store.get(root_sha)
    if existing is not None and existing != rotated_root:
        raise ValueError("rotated-outcome-root-collision")
    root_store[root_sha] = deepcopy(rotated_root)

    user_app_state_sha = target_user_app_state_sha or current_envelope["user_app_state_sha"]
    envelope = w117._seal_envelope(user_app_state_sha, root_sha)
    envelope_sha = w117._put_envelope(st, envelope)
    effective = _effective_transition_store(
        st, registry_store, binding_store, transition_store, keyring, lineage
    )
    out = w114.prepare(
        rt, st, priv, boot, services, registry_store, effective, certificate_store,
        certificate_domain, binding_store, envelope_sha, None
    )
    _sync_prepared_transition(transition_store, effective, out[3])
    return (*out, deepcopy(rotated_root), deepcopy(envelope))


def _activate_successor(
    st: dict,
    keyring: OutcomeAuthorityKeyring,
    successor_domain: OutcomeAuthorityDomain,
) -> None:
    st[w116.OUTCOME_BINDING] = w116._seal_binding(successor_domain.authority_id)
    keyring.add(successor_domain, make_current=True)


def commit_rotation(
    rt: dict,
    st: dict,
    boot: dict,
    registry_store: dict,
    transition_store: dict,
    link_sha: str,
    transition_sha: str,
    binding_store: dict,
    keyring: OutcomeAuthorityKeyring,
    successor_domain: OutcomeAuthorityDomain,
    n: int | None = None,
    *,
    fault_after_checkpoint_before_activation: bool = False,
) -> str:
    _binding, _envelope, current_root, _status, lineage = _current_anchor(
        rt, st, boot, registry_store, binding_store, keyring
    )
    target_root = _transition_root(
        st, registry_store, binding_store, transition_store, transition_sha
    )
    _verify_direct_successor(current_root, target_root, keyring)
    if target_root["outcome_authority_id"] != successor_domain.authority_id:
        raise ValueError("rotation-successor-credential-does-not-match-target-root")

    effective = _effective_transition_store(
        st, registry_store, binding_store, transition_store, keyring, lineage
    )
    w115._strict_transition_get(effective, transition_sha)
    preflight = w115._prevalidate_lower_commit(
        rt, st, boot, registry_store, effective, link_sha, transition_sha, binding_store, n
    )
    if preflight != "COMMITTED":
        return preflight
    w114._ensure_commit_decision(
        st, boot, registry_store, effective, link_sha, transition_sha
    )
    result = w110.commit(
        rt, st, boot, registry_store, effective, link_sha, transition_sha, binding_store, n
    )
    if result != "COMMITTED":
        return f"HOLD_LOWER_CHANGED_AFTER_PREVALIDATION:{result}"
    marker = w111._append_provenance(
        st, boot, registry_store, effective, link_sha, transition_sha
    )
    if marker not in ("RECORDED", "ALREADY_RECORDED"):
        raise RuntimeError(f"unexpected Wave 118 rotation provenance result: {marker}")

    if fault_after_checkpoint_before_activation:
        raise RuntimeError("injected-wave118-crash-after-checkpoint-before-outcome-authority-activation")

    old_binding = deepcopy(st.get(w116.OUTCOME_BINDING))
    old_current = keyring.current_authority_id
    try:
        _activate_successor(st, keyring, successor_domain)
        state = commit_status_state(
            st, boot, rt, registry_store, binding_store, transition_store, keyring
        )
        if state.get("status") != HISTORY_VALID:
            raise RuntimeError(f"Wave 118 rotation activation did not settle: {state}")
    except Exception:
        if old_binding is None:
            st.pop(w116.OUTCOME_BINDING, None)
        else:
            st[w116.OUTCOME_BINDING] = old_binding
        keyring.set_current(old_current)
        raise
    return "COMMITTED_ROTATED"


def recover_rotation_activation(
    rt: dict,
    st: dict,
    boot: dict,
    registry_store: dict,
    transition_store: dict,
    binding_store: dict,
    keyring: OutcomeAuthorityKeyring,
    successor_domain: OutcomeAuthorityDomain,
) -> str:
    _binding, _envelope, latest_root, _status, lineage = _checkpoint_root_lineage(
        rt, st, boot, registry_store, binding_store, keyring
    )
    if len(lineage) < 2:
        raise ValueError("rotation-recovery-no-anchored-successor")
    predecessor = lineage[-2]
    _verify_direct_successor(predecessor, latest_root, keyring)
    if latest_root["outcome_authority_id"] != successor_domain.authority_id:
        raise ValueError("rotation-recovery-successor-credential-mismatch")

    old_binding = deepcopy(st.get(w116.OUTCOME_BINDING))
    old_current = keyring.current_authority_id
    had_successor = successor_domain.authority_id in keyring.ids()
    try:
        _activate_successor(st, keyring, successor_domain)
        state = commit_status_state(
            st, boot, rt, registry_store, binding_store, transition_store, keyring
        )
        if state.get("status") != HISTORY_VALID:
            raise RuntimeError(f"rotation recovery did not settle: {state}")
    except Exception:
        if old_binding is None:
            st.pop(w116.OUTCOME_BINDING, None)
        else:
            st[w116.OUTCOME_BINDING] = old_binding
        keyring.set_current(old_current)
        if not had_successor and successor_domain.authority_id != old_current:
            keyring._domains.pop(successor_domain.authority_id, None)
        raise
    return "RECOVERED_ROTATION_ACTIVATION"


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
    keyring: OutcomeAuthorityKeyring,
    app_label: str,
) -> tuple:
    import hashlib
    app = hashlib.sha256(app_label.encode("utf-8")).hexdigest()
    cp, use, link, transition_sha, body = prepare(
        rt, st, priv, boot, services, registry_store, transition_store, certificate_store,
        certificate_domain, binding_store, keyring, app
    )
    result = commit(
        rt, st, boot, registry_store, transition_store, link["authority_sha"],
        transition_sha, binding_store, keyring
    )
    if result != "COMMITTED":
        raise RuntimeError(f"Wave 118 local commit failed: {result}")
    for slot in q.REMOTE_IDS:
        remote_result = publish(rt, st, boot, services, tokens, registry_store, slot)
        if remote_result not in ("APPENDED", "ALREADY_CURRENT"):
            raise RuntimeError(f"Wave 118 remote publish failed for {slot}: {remote_result}")
    cert_result, cert_body = certify_and_sync(
        rt, st, boot, services, registry_store, certificate_store, certificate_domain
    )
    verdict = authority(
        rt, st, boot, services, registry_store, transition_store, certificate_store,
        certificate_domain, binding_store, keyring
    )
    if not verdict.startswith("AUTHORITATIVE"):
        raise RuntimeError(f"Wave 118 authority failed: {verdict}")
    state = commit_status_state(
        st, boot, rt, registry_store, binding_store, transition_store, keyring
    )
    return cp, use, link, transition_sha, body, cert_result, cert_body, state
