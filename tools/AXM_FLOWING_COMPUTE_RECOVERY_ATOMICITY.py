#!/usr/bin/env python3
"""AXM Flowing Compute Wave 113: recovery atomicity and honest idempotence.

Additive experiment over exact Wave 112. Independent verifier PR #37 found that Wave 112's
one-row provenance recovery could append the missing trailing row before validating the already
retained provenance prefix. If that older prefix was structurally intact but semantically damaged,
the retry failed only after mutating retained evidence; a second retry could then report
ALREADY_COMMITTED while full history remained INCOMPLETE.

Wave 113 makes the narrow recovery path mutation-safe inside the same modeled Python failure domain:

1. validate the complete retained provenance prefix semantically before any recovery write;
2. require the exact committed suffix and exact unique retained transition;
3. snapshot only the provenance store, append the one allowed trailing row, validate the complete
   Wave-112 history, and restore the exact pre-write provenance store on any append/validation error;
4. return ALREADY_COMMITTED only when the requested authority is bound to the requested transition
   *and* the complete Wave-112 history is currently VALID.

This is in-memory transaction/rollback evidence, not an independent durable commit-decision witness.
A process/power failure can still defeat an in-memory rollback. Whole-domain rollback can still erase
all newer facts. No performance, energy, retained/incremental/dormant-compute, OS-process, device,
network, physical, or provider-independence claim is made. No merge or CANON promotion is performed.
"""
from __future__ import annotations

import hashlib
from copy import deepcopy

import AXM_FLOWING_COMPUTE_RECOVERABLE_TRANSITION_PROVENANCE as w112
import AXM_FLOWING_COMPUTE_TRANSITION_PROVENANCE_LEDGER as w111
import AXM_FLOWING_COMPUTE_TRANSITION_EVIDENCE_GUARD as w110
import AXM_FLOWING_COMPUTE_REMOTE_REGISTRY_MONOTONICITY as w100
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w104

q = w112.q
g = w112.g

SRC = {
    "wave112_builder_head": "a1cf4ccb535142a63a328c4a0dadc86984deaa3b",
    "wave112_tested_source_commit": "1be9303bba0712869d40444f5cf1b0e878948ab7",
    "wave112_tool_blob": "41e73e8f042df974b161fa9b85b128c99b1bb819",
    "wave112_selftest_blob": "7a48968a851c23129b6ae31ef017483407e70e8f",
    "verifier_pr": 37,
    "verifier_base": "a1cf4ccb535142a63a328c4a0dadc86984deaa3b",
    "verifier_head_at_wave113_start": "64f8cbe681d7f06930249e65c6dee9f9d2e3495d",
    "verifier_verdict": "FAIL_FAILED_RECOVERY_MUTATES_LEDGER_AND_THEN_MISREPORTS_ALREADY_COMMITTED",
}

PROVENANCE_STORE = w112.PROVENANCE_STORE
HISTORY_NONE = w112.HISTORY_NONE
HISTORY_VALID = w112.HISTORY_VALID
HISTORY_INCOMPLETE = w112.HISTORY_INCOMPLETE
HISTORY_UNRESOLVED = w112.HISTORY_UNRESOLVED
HOLD_INCOMPLETE = w112.HOLD_INCOMPLETE
HOLD_UNRESOLVED = w112.HOLD_UNRESOLVED


def commit_status_state(st: dict, boot: dict, rt: dict | None, registry_store: dict,
                        binding_store: dict, transition_store: dict) -> dict:
    return w112.commit_status_state(st, boot, rt, registry_store, binding_store, transition_store)


def _validate_existing_recovery_prefix(
    st: dict,
    boot: dict,
    registry_store: dict,
    transition_store: dict,
    base: dict,
    committed: list[str],
    rows: list[tuple[str, dict]],
    recovery_authority_sha: str,
) -> None:
    """Fully validate the retained prefix *before* recovery is allowed to mutate provenance."""
    if len(committed) != len(rows) + 1 or not committed or committed[-1] != recovery_authority_sha:
        raise ValueError("recovery-requires-exactly-one-missing-trailing-provenance-row")

    markers = w112._indexed_marker_rows(st)
    if len(markers) != len(committed):
        raise ValueError("recovery-wave108-marker-count-does-not-match-committed-authorities")

    previous_authority: str | None = None
    previous_target_registry: str | None = None
    for seq, ((record_sha, record), authority_sha) in enumerate(zip(rows, committed[:-1]), start=1):
        if record.get("seq") != seq or record.get("epoch") != seq:
            raise ValueError("recovery-prefix-sequence-or-epoch-mismatch")
        if record.get("authority_sha") != authority_sha:
            raise ValueError("recovery-prefix-authority-mismatch")

        link, cp, _use = g.w98.resolve(st, authority_sha, boot)
        if record.get("checkpoint_sha") != link.get("checkpoint_sha") or record.get("checkpoint_sha") != cp.get("checkpoint_sha"):
            raise ValueError("recovery-prefix-checkpoint-mismatch")
        if record.get("use_sha") != link.get("use_sha"):
            raise ValueError("recovery-prefix-use-mismatch")

        transition_sha = record.get("transition_sha")
        if not isinstance(transition_sha, str) or len(transition_sha) != 64:
            raise ValueError("recovery-prefix-transition-sha-shape-invalid")
        transition = w100.get_transition(transition_store, transition_sha)
        w111._validate_transition_semantics(
            transition, registry_store, link, cp, previous_authority
        )
        if previous_target_registry is not None and transition.get("current_registry_sha") != previous_target_registry:
            raise ValueError("recovery-prefix-registry-lineage-not-contiguous")
        previous_target_registry = transition.get("target_registry_sha")

        if seq not in markers:
            raise ValueError("recovery-prefix-marker-sequence-missing")
        (commit_record_sha, commit_record), (high_water_sha, high_water) = markers[seq]
        if record.get("wave108_commit_record_sha") != commit_record_sha:
            raise ValueError("recovery-prefix-wave108-commit-record-mismatch")
        if record.get("wave108_high_water_sha") != high_water_sha:
            raise ValueError("recovery-prefix-wave108-high-water-mismatch")
        if commit_record.get("authority_sha") != authority_sha or high_water.get("authority_sha") != authority_sha:
            raise ValueError("recovery-prefix-wave108-authority-mismatch")

        if record.get("target_state_sha") != transition.get("target_state_sha"):
            raise ValueError("recovery-prefix-target-state-mismatch")
        if record.get("current_registry_sha") != transition.get("current_registry_sha"):
            raise ValueError("recovery-prefix-current-registry-mismatch")
        if record.get("target_registry_sha") != transition.get("target_registry_sha"):
            raise ValueError("recovery-prefix-target-registry-mismatch")
        if record.get("transition_kind") != transition.get("transition_kind"):
            raise ValueError("recovery-prefix-transition-kind-mismatch")

        previous_authority = authority_sha

    # The missing suffix itself must already be a real lower-layer committed authority.
    # Resolve it now so no recovery write can occur if its L/C/U evidence is broken.
    g.w98.resolve(st, recovery_authority_sha, boot)


def _transactional_provenance_append(
    st: dict,
    boot: dict,
    rt: dict | None,
    registry_store: dict,
    transition_store: dict,
    binding_store: dict,
    link_sha: str,
    transition_sha: str,
    *,
    fault_after_append: bool = False,
) -> str:
    """Append one provenance row and roll back the provenance store on any failed validation."""
    pstore = st.get(PROVENANCE_STORE)
    if not isinstance(pstore, dict):
        raise ValueError("provenance-store-missing-or-invalid")
    before = deepcopy(pstore)
    try:
        marker = w111._append_provenance(
            st, boot, registry_store, transition_store, link_sha, transition_sha
        )
        if marker not in ("RECORDED", "ALREADY_RECORDED"):
            raise RuntimeError(f"unexpected Wave 113 recovery provenance result: {marker}")
        if fault_after_append:
            raise RuntimeError("injected-wave113-fault-after-provenance-append")
        state = w112.commit_status_state(
            st, boot, rt, registry_store, binding_store, transition_store
        )
        if state.get("status") != HISTORY_VALID:
            raise RuntimeError(f"Wave 113 recovery did not settle exact committed history: {state}")
    except Exception:
        pstore.clear()
        pstore.update(before)
        raise
    return "COMMITTED_RECOVERED_PROVENANCE_ATOMIC"


def _recover_missing_trailing_provenance(
    st: dict,
    boot: dict,
    rt: dict | None,
    registry_store: dict,
    transition_store: dict,
    binding_store: dict,
    link_sha: str,
    transition_sha: str,
    *,
    fault_after_append: bool = False,
) -> str | None:
    """Recover one exact trailing row, with full prefix preflight and rollback-safe mutation."""
    base = w110.commit_status_state(st, boot, rt, registry_store, binding_store, transition_store)
    if base.get("status") != HISTORY_VALID:
        return None
    committed = list(base.get("committed_authority_shas", []))
    if link_sha not in committed:
        return None

    rows = w111._provenance_rows(st)
    assert rows is not None
    by_authority = {record.get("authority_sha"): record for _sha, record in rows}
    if link_sha in by_authority:
        if by_authority[link_sha].get("transition_sha") != transition_sha:
            raise ValueError("already-committed-authority-bound-to-different-transition")
        full = w112.commit_status_state(
            st, boot, rt, registry_store, binding_store, transition_store
        )
        if full.get("status") != HISTORY_VALID:
            raise ValueError("already-committed-provenance-present-but-history-not-valid")
        return "ALREADY_COMMITTED"

    _validate_existing_recovery_prefix(
        st, boot, registry_store, transition_store, base, committed, rows, link_sha
    )

    transitions = w110._validated_transitions(transition_store)
    candidates = [
        (sha, body) for sha, body in transitions.items()
        if body.get("target_authority_sha") == link_sha
    ]
    if len(candidates) != 1:
        raise ValueError("recovery-committed-authority-transition-match-not-unique")
    proven_transition_sha, transition = candidates[0]
    if proven_transition_sha != transition_sha:
        raise ValueError("recovery-transition-sha-does-not-match-lower-committed-evidence")

    link, cp, _use = g.w98.resolve(st, link_sha, boot)
    previous_authority = rows[-1][1]["authority_sha"] if rows else None
    w111._validate_transition_semantics(
        transition, registry_store, link, cp, previous_authority
    )
    if rows:
        previous_transition = w100.get_transition(transition_store, rows[-1][1]["transition_sha"])
        if transition.get("current_registry_sha") != previous_transition.get("target_registry_sha"):
            raise ValueError("recovery-target-transition-registry-lineage-not-contiguous")

    return _transactional_provenance_append(
        st, boot, rt, registry_store, transition_store, binding_store,
        link_sha, transition_sha, fault_after_append=fault_after_append
    )


def adopt_genesis(rt: dict, st: dict, boot: dict, services: dict, registry_store: dict,
                  transition_store: dict, certificate_store: dict,
                  domain: w104.CertificateWitnessDomain, binding_store: dict) -> str:
    return w112.adopt_genesis(
        rt, st, boot, services, registry_store, transition_store,
        certificate_store, domain, binding_store
    )


def authority(rt: dict, st: dict, boot: dict, services: dict, registry_store: dict,
              transition_store: dict, certificate_store: dict,
              domain: w104.CertificateWitnessDomain, binding_store: dict,
              resolved_endpoints: dict | None = None) -> str:
    return w112.authority(
        rt, st, boot, services, registry_store, transition_store,
        certificate_store, domain, binding_store, resolved_endpoints
    )


def prepare(rt: dict, st: dict, priv: dict, boot: dict, services: dict,
            registry_store: dict, transition_store: dict, certificate_store: dict,
            domain: w104.CertificateWitnessDomain, binding_store: dict,
            target_user_app_state_sha: str | None = None,
            target_remote_registry_sha: str | None = None) -> tuple:
    return w112.prepare(
        rt, st, priv, boot, services, registry_store, transition_store,
        certificate_store, domain, binding_store,
        target_user_app_state_sha, target_remote_registry_sha
    )


def commit(rt: dict, st: dict, boot: dict, registry_store: dict, transition_store: dict,
           link_sha: str, transition_sha: str, binding_store: dict,
           n: int | None = None) -> str:
    recovered = _recover_missing_trailing_provenance(
        st, boot, rt, registry_store, transition_store, binding_store,
        link_sha, transition_sha
    )
    if recovered is not None:
        return recovered

    # Deliberately bypass Wave 112's recovery helper here so no damaged already-committed state can
    # fall back into the verifier-identified mutate-then-fail path. New commits still use Wave 110's
    # lower durable transaction and Wave 111's provenance append, preserving the known crash boundary.
    result = w110.commit(
        rt, st, boot, registry_store, transition_store,
        link_sha, transition_sha, binding_store, n
    )
    if result == "COMMITTED":
        marker = w111._append_provenance(
            st, boot, registry_store, transition_store, link_sha, transition_sha
        )
        if marker not in ("RECORDED", "ALREADY_RECORDED"):
            raise RuntimeError(f"unexpected Wave 113 provenance result: {marker}")
    return result


def publish(rt: dict, st: dict, boot: dict, services: dict, tokens: dict,
            registry_store: dict, slot: str) -> str:
    return w112.publish(rt, st, boot, services, tokens, registry_store, slot)


def certify_and_sync(rt: dict, st: dict, boot: dict, services: dict, registry_store: dict,
                     certificate_store: dict, domain: w104.CertificateWitnessDomain,
                     slots: tuple[str, ...] | list[str] | None = None) -> tuple[str, dict]:
    return w112.certify_and_sync(
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
    unresolved = commit_status_state(
        st, boot, rt, registry_store, binding_store, transition_store
    )
    if unresolved.get("status") != HISTORY_UNRESOLVED:
        raise RuntimeError(f"Wave 113 prepare did not enter unresolved state: {unresolved}")
    result = commit(
        rt, st, boot, registry_store, transition_store,
        link["authority_sha"], transition_sha, binding_store
    )
    if result not in ("COMMITTED", "COMMITTED_RECOVERED_PROVENANCE_ATOMIC"):
        raise RuntimeError(f"Wave 113 local commit failed: {result}")
    resolved = commit_status_state(
        st, boot, rt, registry_store, binding_store, transition_store
    )
    if resolved.get("status") != HISTORY_VALID:
        raise RuntimeError(f"Wave 113 commit provenance did not settle: {resolved}")
    for slot in q.REMOTE_IDS:
        remote_result = publish(rt, st, boot, services, tokens, registry_store, slot)
        if remote_result not in ("APPENDED", "ALREADY_CURRENT"):
            raise RuntimeError(f"Wave 113 publish failed for {slot}: {remote_result}")
    certificate_sha, certificate = certify_and_sync(
        rt, st, boot, services, registry_store, certificate_store, domain
    )
    final = authority(
        rt, st, boot, services, registry_store, transition_store,
        certificate_store, domain, binding_store
    )
    if not final.startswith("AUTHORITATIVE"):
        raise RuntimeError(f"Wave 113 final authority failed: {final}")
    return cp, use, link, transition_sha, body, certificate_sha, certificate
