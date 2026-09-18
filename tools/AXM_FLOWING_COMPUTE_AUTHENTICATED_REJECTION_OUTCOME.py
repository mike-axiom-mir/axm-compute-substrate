#!/usr/bin/env python3
"""AXM Flowing Compute Wave 116: authenticated single-valued rejection outcomes.

Independent verifier PR #40 showed that Wave 115's rejection chain verified each row's content
identity and predecessor linkage but did not make the terminal outcome single-valued per exact
transition. A second correctly self-sealed row could claim a different stable lower result for the
same transition SHA and the retained history could still classify VALID.

Wave 116 is an additive experimental repair over exact Wave 115:
1. preserve the Wave-115 append-only rejection body as the raw rejection fact;
2. require a second append-only outcome attestation signed by one bound outcome-authority
   credential before that rejection is trusted for history filtering;
3. require an exact one-to-one mapping between raw rejection rows and authenticated outcome rows;
4. require exactly one terminal REJECT outcome per exact transition identity, and reject any
   transition that simultaneously has a COMMIT decision and a REJECT outcome;
5. keep retriable HOLD results unpersisted as terminal outcomes.

The credential is an HMAC-backed same-process model. It demonstrates that a self-seal is not enough
and gives later process-separation work an explicit credential boundary. It is NOT proof of OS-
process isolation, hardware-key security, durable-device atomicity, power-loss safety, network or
provider independence. No merge/CANON, performance, energy, or retained/incremental/dormant-
compute claim is made.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from copy import deepcopy

import AXM_FLOWING_COMPUTE_PREVALIDATED_COMMIT_DECISION as w115
import AXM_FLOWING_COMPUTE_EXACT_TRANSITION_DECISION as w114
import AXM_FLOWING_COMPUTE_TRANSITION_PROVENANCE_LEDGER as w111
import AXM_FLOWING_COMPUTE_TRANSITION_EVIDENCE_GUARD as w110
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w104

q = w115.q
g = w115.g

SRC = {
    "wave115_builder_head": "8f183d61e9874fd821ec2c03c222f13711d7b8ff",
    "wave115_tested_source_commit": "ad03fc8582a8ac6d8b294c494fa8b2fabb142dc6",
    "wave115_tool_blob": "7279d1aa84df3efec5848ea98fe601a590ffc2a9",
    "wave115_selftest_blob": "f31881af1fa976fa1c125f4d84f613b1af1cd680",
    "verifier_pr": 40,
    "verifier_head_at_wave116_start": "fb478e4b5bdf040250ac1ad950bbd1fc81123e8e",
    "verifier_verdict": "FAIL_CONTRADICTORY_REJECTION_OUTCOMES_ACCEPTED_AS_VALID_HISTORY",
}

DECISION_STORE = w115.DECISION_STORE
PROVENANCE_STORE = w115.PROVENANCE_STORE
REJECTION_STORE = w115.REJECTION_STORE
REJECTION_SCHEMA = w115.REJECTION_SCHEMA
STABLE_SEMANTIC_REJECTIONS = w115.STABLE_SEMANTIC_REJECTIONS

OUTCOME_BINDING = "flowing_compute_wave116_outcome_authority_binding"
OUTCOME_BINDING_SCHEMA = "axm.flowing-compute.outcome-authority-binding/w116-v1"
OUTCOME_BINDING_FIELDS = {"schema", "outcome_authority_id", "binding_sha"}
OUTCOME_STORE = "flowing_compute_wave116_authenticated_rejection_outcomes"
OUTCOME_SCHEMA = "axm.flowing-compute.authenticated-rejection-outcome/w116-v1"
OUTCOME_FIELDS = {
    "schema",
    "seq",
    "predecessor_outcome_sha",
    "rejection_sha",
    "authority_sha",
    "transition_sha",
    "checkpoint_sha",
    "lower_result",
    "outcome_authority_id",
    "outcome_auth_tag",
    "outcome_sha",
}

HISTORY_NONE = w115.HISTORY_NONE
HISTORY_VALID = w115.HISTORY_VALID
HISTORY_INCOMPLETE = w115.HISTORY_INCOMPLETE
HISTORY_UNRESOLVED = w115.HISTORY_UNRESOLVED
HOLD_INCOMPLETE = w115.HOLD_INCOMPLETE
HOLD_UNRESOLVED = w115.HOLD_UNRESOLVED
_strict_transition_get = w115._strict_transition_get


class OutcomeAuthorityDomain:
    """Same-process credential model for outcome assertions.

    The secret deliberately lives outside retained state. Python introspection is not a security
    boundary; Wave 116 only establishes an explicit credential contract that Wave 117 can move to
    a separate process/store.
    """

    __slots__ = ("authority_id", "__secret")

    def __init__(self, secret: bytes | None = None):
        material = secret if secret is not None else secrets.token_bytes(32)
        if not isinstance(material, bytes) or len(material) < 32:
            raise ValueError("outcome-authority-secret-invalid")
        self.__secret = material
        self.authority_id = hashlib.sha256(
            b"axm-flowing-compute-wave116-outcome-authority\x00" + material
        ).hexdigest()

    def sign(self, payload: bytes) -> str:
        return hmac.new(self.__secret, payload, hashlib.sha256).hexdigest()

    def verify(self, payload: bytes, tag: str) -> bool:
        if not isinstance(tag, str):
            return False
        expected = self.sign(payload)
        return hmac.compare_digest(expected, tag)


def new_outcome_authority_domain() -> OutcomeAuthorityDomain:
    return OutcomeAuthorityDomain()


def _seal_binding(authority_id: str) -> dict:
    body = {
        "schema": OUTCOME_BINDING_SCHEMA,
        "outcome_authority_id": authority_id,
        "binding_sha": "",
    }
    body["binding_sha"] = w114._canonical_sha(body, "binding_sha")
    return body


def _check_binding(st: dict, outcome_domain: OutcomeAuthorityDomain) -> dict:
    raw = st.get(OUTCOME_BINDING)
    if not isinstance(raw, dict) or set(raw) != OUTCOME_BINDING_FIELDS:
        raise ValueError("outcome-authority-binding-missing-or-invalid")
    body = deepcopy(raw)
    if body.get("schema") != OUTCOME_BINDING_SCHEMA:
        raise ValueError("outcome-authority-binding-schema-mismatch")
    expected = w114._canonical_sha(body, "binding_sha")
    if body.get("binding_sha") != expected:
        raise ValueError("outcome-authority-binding-seal-mismatch")
    if body.get("outcome_authority_id") != outcome_domain.authority_id:
        raise ValueError("outcome-authority-credential-substitution")
    return body


def _outcome_payload(body: dict) -> bytes:
    payload = {
        key: body[key]
        for key in sorted(body)
        if key not in {"outcome_auth_tag", "outcome_sha"}
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _seal_outcome(body: dict, outcome_domain: OutcomeAuthorityDomain) -> dict:
    out = deepcopy(body)
    out["outcome_auth_tag"] = ""
    out["outcome_sha"] = ""
    out["outcome_auth_tag"] = outcome_domain.sign(_outcome_payload(out))
    out["outcome_sha"] = w114._canonical_sha(out, "outcome_sha")
    return out


def _check_outcome(
    body: dict,
    outcome_domain: OutcomeAuthorityDomain,
    key: str | None = None,
) -> None:
    if set(body) != OUTCOME_FIELDS:
        raise ValueError("outcome-field-set-mismatch")
    if body.get("schema") != OUTCOME_SCHEMA:
        raise ValueError("outcome-schema-mismatch")
    if body.get("lower_result") not in STABLE_SEMANTIC_REJECTIONS:
        raise ValueError("outcome-result-not-stable-rejection")
    if body.get("outcome_authority_id") != outcome_domain.authority_id:
        raise ValueError("outcome-authority-id-mismatch")
    if not outcome_domain.verify(_outcome_payload(body), body.get("outcome_auth_tag")):
        raise ValueError("outcome-authentication-failed")
    expected = w114._canonical_sha(body, "outcome_sha")
    if body.get("outcome_sha") != expected:
        raise ValueError("outcome-seal-mismatch")
    if key is not None and key != expected:
        raise ValueError("outcome-key-body-mismatch")


def _outcome_rows(
    st: dict,
    outcome_domain: OutcomeAuthorityDomain,
    *,
    allow_missing: bool = False,
) -> list[tuple[str, dict]] | None:
    _check_binding(st, outcome_domain)
    store = st.get(OUTCOME_STORE)
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
        _check_outcome(body, outcome_domain, sha)
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
    transition_store: dict,
    outcome_domain: OutcomeAuthorityDomain,
) -> list[tuple[str, dict, str, dict]]:
    """Return exact raw+authenticated rejection pairs or fail closed."""
    shadow = w115._rejection_rows(st, transition_store)
    assert shadow is not None
    outcomes = _outcome_rows(st, outcome_domain)
    assert outcomes is not None

    by_rejection: dict[str, list[tuple[str, dict]]] = {}
    for outcome_sha, body in outcomes:
        by_rejection.setdefault(body["rejection_sha"], []).append((outcome_sha, body))
    if len(outcomes) != len(shadow):
        raise ValueError("rejection-outcome-cardinality-mismatch")

    paired: list[tuple[str, dict, str, dict]] = []
    transition_terminal: dict[str, tuple[str, str]] = {}
    for rejection_sha, rejection in shadow:
        matching = by_rejection.get(rejection_sha, [])
        if len(matching) != 1:
            raise ValueError("rejection-does-not-have-exactly-one-authenticated-outcome")
        outcome_sha, outcome = matching[0]
        for field in ("authority_sha", "transition_sha", "checkpoint_sha", "lower_result"):
            if outcome.get(field) != rejection.get(field):
                raise ValueError(f"authenticated-outcome-{field}-mismatch")
        transition_sha = rejection["transition_sha"]
        terminal = (rejection_sha, rejection["lower_result"])
        if transition_sha in transition_terminal:
            raise ValueError("rejection-transition-terminal-outcome-not-unique")
        transition_terminal[transition_sha] = terminal
        paired.append((rejection_sha, rejection, outcome_sha, outcome))

    for outcome_sha, outcome in outcomes:
        if outcome["rejection_sha"] not in {sha for sha, _body in shadow}:
            raise ValueError("authenticated-outcome-references-unknown-rejection")

    decisions = w114._decision_rows(st, allow_missing=True) or []
    committed_transition_shas = {body.get("transition_sha") for _sha, body in decisions}
    overlap = committed_transition_shas & set(transition_terminal)
    if overlap:
        raise ValueError("transition-has-both-commit-and-reject-terminal-outcome")
    return paired


def _effective_transition_store(
    st: dict,
    transition_store: dict,
    outcome_domain: OutcomeAuthorityDomain,
) -> dict:
    paired = _validated_rejections(st, transition_store, outcome_domain)
    rejected = {rejection["transition_sha"] for _rsha, rejection, _osha, _outcome in paired}
    return {
        sha: deepcopy(body)
        for sha, body in transition_store.items()
        if sha not in rejected
    }


def _append_authenticated_rejection(
    st: dict,
    transition_store: dict,
    transition_sha: str,
    lower_result: str,
    outcome_domain: OutcomeAuthorityDomain,
    *,
    fault_after_raw_rejection_before_outcome: bool = False,
) -> str:
    if lower_result not in STABLE_SEMANTIC_REJECTIONS:
        return "NOT_STABLE_REJECTION"
    _check_binding(st, outcome_domain)
    transition = _strict_transition_get(transition_store, transition_sha)

    raw_result = w115._append_rejection(st, transition_store, transition_sha, lower_result)
    raw_rows = w115._rejection_rows(st, transition_store) or []
    matches = [(sha, body) for sha, body in raw_rows if body["transition_sha"] == transition_sha]
    if len(matches) != 1 or matches[0][1]["lower_result"] != lower_result:
        raise ValueError("raw-rejection-not-single-valued-after-append")
    rejection_sha, rejection = matches[0]

    if fault_after_raw_rejection_before_outcome:
        raise RuntimeError("injected-wave116-crash-after-raw-rejection-before-authenticated-outcome")

    existing_outcomes = _outcome_rows(st, outcome_domain) or []
    same_rejection = [body for _sha, body in existing_outcomes if body["rejection_sha"] == rejection_sha]
    if same_rejection:
        if len(same_rejection) != 1:
            raise ValueError("rejection-has-multiple-authenticated-outcomes")
        body = same_rejection[0]
        if body["transition_sha"] != transition_sha or body["lower_result"] != lower_result:
            raise ValueError("rejection-authenticated-outcome-conflict")
        return "ALREADY_AUTHENTICATED_REJECTED"

    predecessor = existing_outcomes[-1][0] if existing_outcomes else None
    outcome = _seal_outcome(
        {
            "schema": OUTCOME_SCHEMA,
            "seq": len(existing_outcomes) + 1,
            "predecessor_outcome_sha": predecessor,
            "rejection_sha": rejection_sha,
            "authority_sha": transition["target_authority_sha"],
            "transition_sha": transition_sha,
            "checkpoint_sha": transition["target_checkpoint_sha"],
            "lower_result": lower_result,
            "outcome_authority_id": outcome_domain.authority_id,
            "outcome_auth_tag": "",
            "outcome_sha": "",
        },
        outcome_domain,
    )
    store = st[OUTCOME_STORE]
    outcome_sha = outcome["outcome_sha"]
    if outcome_sha in store and store[outcome_sha] != outcome:
        raise ValueError("authenticated-outcome-collision")
    store[outcome_sha] = outcome
    _validated_rejections(st, transition_store, outcome_domain)
    return "REJECTED_AUTHENTICATED" if raw_result == "REJECTED_RECORDED" else "RAW_REJECTION_RECOVERED_AND_AUTHENTICATED"


def commit_status_state(
    st: dict,
    boot: dict,
    rt: dict | None,
    registry_store: dict,
    binding_store: dict,
    transition_store: dict,
    outcome_domain: OutcomeAuthorityDomain,
) -> dict:
    try:
        effective = _effective_transition_store(st, transition_store, outcome_domain)
        paired = _validated_rejections(st, transition_store, outcome_domain)
    except Exception as exc:
        return {
            "status": HISTORY_INCOMPLETE,
            "reason": f"authenticated-rejection-verification:{type(exc).__name__}:{exc}",
        }
    base = w114.commit_status_state(st, boot, rt, registry_store, binding_store, effective)
    outcomes = _outcome_rows(st, outcome_domain) or []
    return {
        **base,
        "wave114": base,
        "authenticated_rejected_transition_count": len(paired),
        "outcome_head_sha": outcomes[-1][0] if outcomes else "",
        "outcome_authority_id": outcome_domain.authority_id,
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
) -> str:
    if OUTCOME_STORE in st or OUTCOME_BINDING in st:
        raise ValueError("wave116-outcome-state-already-present")
    result = w115.adopt_genesis(
        rt,
        st,
        boot,
        services,
        registry_store,
        transition_store,
        certificate_store,
        certificate_domain,
        binding_store,
    )
    st[OUTCOME_BINDING] = _seal_binding(outcome_domain.authority_id)
    st[OUTCOME_STORE] = {}
    state = commit_status_state(
        st, boot, rt, registry_store, binding_store, transition_store, outcome_domain
    )
    if state.get("status") not in (HISTORY_NONE, HISTORY_VALID):
        raise ValueError(f"Wave 116 genesis evidence HOLD: {state}")
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
) -> str:
    state = commit_status_state(
        st, boot, rt, registry_store, binding_store, transition_store, outcome_domain
    )
    if state.get("status") == HISTORY_INCOMPLETE:
        return HOLD_INCOMPLETE
    if state.get("status") == HISTORY_UNRESOLVED:
        return HOLD_UNRESOLVED
    try:
        effective = _effective_transition_store(st, transition_store, outcome_domain)
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
) -> tuple:
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
        raise ValueError("Wave 116 predecessor HOLD")
    effective = _effective_transition_store(st, transition_store, outcome_domain)
    out = w114.prepare(
        rt,
        st,
        priv,
        boot,
        services,
        registry_store,
        effective,
        certificate_store,
        certificate_domain,
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
    *,
    fault_after_raw_rejection_before_outcome: bool = False,
    fault_after_decision_before_lower_commit: bool = False,
    fault_after_lower_commit: bool = False,
) -> str:
    paired = _validated_rejections(st, transition_store, outcome_domain)
    existing = [
        rejection
        for _rsha, rejection, _osha, _outcome in paired
        if rejection["transition_sha"] == transition_sha
    ]
    if existing:
        if len(existing) != 1:
            raise ValueError("transition-rejection-terminal-outcome-not-unique")
        return existing[0]["lower_result"]

    effective = _effective_transition_store(st, transition_store, outcome_domain)
    recovered = w114._recover_missing_trailing_provenance(
        st,
        boot,
        rt,
        registry_store,
        effective,
        binding_store,
        link_sha,
        transition_sha,
    )
    if recovered is not None:
        return recovered

    _strict_transition_get(effective, transition_sha)
    preflight = w115._prevalidate_lower_commit(
        rt,
        st,
        boot,
        registry_store,
        effective,
        link_sha,
        transition_sha,
        binding_store,
        n,
    )
    if preflight != "COMMITTED":
        if preflight in STABLE_SEMANTIC_REJECTIONS:
            _append_authenticated_rejection(
                st,
                transition_store,
                transition_sha,
                preflight,
                outcome_domain,
                fault_after_raw_rejection_before_outcome=fault_after_raw_rejection_before_outcome,
            )
        return preflight

    w114._ensure_commit_decision(
        st,
        boot,
        registry_store,
        effective,
        link_sha,
        transition_sha,
    )
    if fault_after_decision_before_lower_commit:
        raise RuntimeError("injected-wave116-crash-after-decision-before-lower-commit")

    result = w110.commit(
        rt,
        st,
        boot,
        registry_store,
        effective,
        link_sha,
        transition_sha,
        binding_store,
        n,
    )
    if result != "COMMITTED":
        return f"HOLD_LOWER_CHANGED_AFTER_PREVALIDATION:{result}"

    if fault_after_lower_commit:
        raise RuntimeError("injected-wave116-crash-after-lower-commit-before-provenance")

    marker = w111._append_provenance(
        st,
        boot,
        registry_store,
        effective,
        link_sha,
        transition_sha,
    )
    if marker not in ("RECORDED", "ALREADY_RECORDED"):
        raise RuntimeError(f"unexpected Wave 116 provenance result: {marker}")

    state = commit_status_state(
        st, boot, rt, registry_store, binding_store, transition_store, outcome_domain
    )
    if state.get("status") != HISTORY_VALID:
        raise RuntimeError(f"Wave 116 commit did not settle exact outcome history: {state}")
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
    certificate_domain: w104.CertificateWitnessDomain,
    binding_store: dict,
    outcome_domain: OutcomeAuthorityDomain,
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
        raise RuntimeError(f"Wave 116 local commit failed: {result}")
    for slot in q.REMOTE_IDS:
        remote_result = publish(rt, st, boot, services, tokens, registry_store, slot)
        if remote_result not in ("APPENDED", "ALREADY_CURRENT"):
            raise RuntimeError(f"Wave 116 remote publish failed for {slot}: {remote_result}")
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
        raise RuntimeError(f"Wave 116 authority failed: {verdict}")
    return cp, use, link, transition_sha, body, cert_result, cert_body
