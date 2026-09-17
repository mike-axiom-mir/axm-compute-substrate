#!/usr/bin/env python3
"""AXM Flowing Compute Wave 115: prevalidated exact commit decision.

Additive experiment over exact Wave 114. Independent verifier PR #39 showed that Wave 114
could append a sealed COMMIT decision before the lower transition semantic contract had accepted
that transition. A strict-field, correctly content-addressed but semantically invalid transition
could therefore poison the authority's durable decision identity even though the lower commit
returned HOLD.

Wave 115 changes only that ordering inside the same modeled Python failure domain:
1. run the exact lower Wave-110 commit path against deep-copied state, including the exact
   Wave-114 decision that would be present during the real commit;
2. if the lower result is anything except COMMITTED, return that result with the real decision
   ledger untouched;
3. only after successful semantic prevalidation append/bind the exact Wave-114 decision in the
   real state, then execute the lower commit and provenance path.

This is deterministic same-process prevalidation, not an OS-process transaction, durable-device
atomicity, concurrency proof, power-loss proof, network proof, or provider-independent witness.
No performance, energy, retained/incremental/dormant-compute, merge, or CANON claim is made.
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

HISTORY_NONE = w114.HISTORY_NONE
HISTORY_VALID = w114.HISTORY_VALID
HISTORY_INCOMPLETE = w114.HISTORY_INCOMPLETE
HISTORY_UNRESOLVED = w114.HISTORY_UNRESOLVED
HOLD_INCOMPLETE = w114.HOLD_INCOMPLETE
HOLD_UNRESOLVED = w114.HOLD_UNRESOLVED

# Reuse the already-tested exact history/recovery contract.
_decision_rows = w114._decision_rows
_decision_for_authority = w114._decision_for_authority
_strict_transition_get = w114._strict_transition_get
commit_status_state = w114.commit_status_state
adopt_genesis = w114.adopt_genesis
authority = w114.authority
prepare = w114.prepare
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
    """Run the exact lower commit semantics on isolated copies before real decision publication.

    The probe includes the exact Wave-114 decision row that would be present for the real lower
    commit. No probe mutation is copied back. Therefore a lower HOLD cannot mutate the real
    decision/provenance/runtime stores.
    """
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
    # Preserve Wave-114 exact crash recovery first. If the lower commit already happened,
    # the durable decision must already bind the exact transition used for recovery.
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

    # Critical Wave-115 ordering change: no real COMMIT decision is written unless the exact
    # lower semantic commit returns COMMITTED in an isolated deterministic preflight.
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
        # In this single-thread deterministic model, preflight and the real lower call see the
        # same lower-owned inputs. If that assumption is ever violated, keep the decision visible
        # and fail closed rather than deleting/relabeling append-only evidence.
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
