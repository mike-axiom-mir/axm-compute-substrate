#!/usr/bin/env python3
"""AXM Flowing Compute Wave 120: reference-safe rotation-prepare rollback.

Independent verifier PR #44 showed that Wave 119 inherited Wave 118's rotation-prepare ordering:
a fresh successor outcome root and app envelope were persisted before the lower prepare, and a lower
prepare exception left both unreferenced objects resident. Repeated failed unique attempts therefore
created deterministic retained-state/storage amplification while authority itself stayed safe.

Wave 120 keeps the existing lineage/truth rules and changes only this bounded prepare boundary. The
candidate root and envelope may still need to exist while lower preparation validates them, but a
failed attempt removes only objects that were created by that call and remain unreferenced. Exact
pre-existing objects are never deleted. If lower preparation has already created a binding reference,
the candidate evidence is preserved rather than silently producing a dangling lower record.

This is same-process exception rollback and retained-state hygiene only. It is not power-loss
atomicity, process isolation, a durable external witness, physical finality, performance/energy
evidence, or proof that retained/incremental/dormant state wins. Whole-domain rollback remains a
counterexample. No merge, auto-merge, or CANON promotion.
"""
from __future__ import annotations

from copy import deepcopy

import AXM_FLOWING_COMPUTE_CRASH_RECOVERABLE_ROTATION_LINEAGE as w119

w118 = w119.w118
w117 = w119.w117
w116 = w119.w116
w115 = w119.w115
w114 = w119.w114
w111 = w119.w111
w110 = w119.w110
w105 = w119.w105
w104 = w119.w104
q = w119.q
g = w119.g

SRC = {
    "wave119_evidence_head": "b39e89fa8e0e64df543ab8a593429e47fbc3a530",
    "wave119_tested_source_commit": "c96d679d7cb03935c821bbdff4ab3e1a19c99018",
    "wave119_tool_blob": "28c8c85b3377289b69d742990556e5429fca487f",
    "independent_verifier_pr": 44,
    "verifier_head": "a9f116bc7025cda9ab8b0867ccb756fc9ef6a017",
    "verifier_artifact_sha256": "43651d4c13f131495aa76c388dd1839d5a434f18c7f4f29f2e00425172dcf1c6",
}

OutcomeAuthorityDomain = w119.OutcomeAuthorityDomain
OutcomeAuthorityKeyring = w119.OutcomeAuthorityKeyring
new_outcome_authority_domain = w119.new_outcome_authority_domain
new_outcome_authority_keyring = w119.new_outcome_authority_keyring

HISTORY_NONE = w119.HISTORY_NONE
HISTORY_VALID = w119.HISTORY_VALID
HISTORY_INCOMPLETE = w119.HISTORY_INCOMPLETE
HISTORY_UNRESOLVED = w119.HISTORY_UNRESOLVED
HOLD_INCOMPLETE = w119.HOLD_INCOMPLETE
HOLD_UNRESOLVED = w119.HOLD_UNRESOLVED

authority = w119.authority
commit_status_state = w119.commit_status_state
adopt_genesis = w119.adopt_genesis
prepare = w119.prepare
commit = w119.commit
commit_rotation = w119.commit_rotation
recover_rotation_commit = w119.recover_rotation_commit
recover_rotation_activation = w119.recover_rotation_activation
publish = w119.publish
certify_and_sync = w119.certify_and_sync
advance_all = w119.advance_all


def _binding_references_envelope(binding_store: dict, envelope_sha: str) -> bool:
    if not isinstance(binding_store, dict):
        return True
    for body in binding_store.values():
        if isinstance(body, dict) and body.get("user_app_state_sha") == envelope_sha:
            return True
    return False


def _envelope_references_root(st: dict, root_sha: str) -> bool:
    store = st.get(w117.ENVELOPE_STORE)
    if not isinstance(store, dict):
        return False
    for body in store.values():
        if isinstance(body, dict) and body.get("outcome_root_sha") == root_sha:
            return True
    return False


def _put_exact_rotated_root(st: dict, body: dict) -> tuple[str, bool]:
    root_store = st.setdefault(w117.OUTCOME_ROOT_STORE, {})
    if not isinstance(root_store, dict):
        raise ValueError("wave120-outcome-root-store-invalid")
    root_sha = body["root_sha"]
    existing = root_store.get(root_sha)
    if existing is not None:
        if existing != body:
            raise ValueError("wave120-rotated-outcome-root-collision")
        return root_sha, False
    root_store[root_sha] = deepcopy(body)
    return root_sha, True


def _put_exact_envelope(st: dict, body: dict) -> tuple[str, bool]:
    envelope_store = st.setdefault(w117.ENVELOPE_STORE, {})
    if not isinstance(envelope_store, dict):
        raise ValueError("wave120-envelope-store-invalid")
    envelope_sha = body["envelope_sha"]
    existing = envelope_store.get(envelope_sha)
    if existing is not None:
        if existing != body:
            raise ValueError("wave120-envelope-collision")
        return envelope_sha, False
    envelope_store[envelope_sha] = deepcopy(body)
    return envelope_sha, True


def _rollback_unreferenced_candidate(
    rt: dict,
    st: dict,
    binding_store: dict,
    root_sha: str,
    root_body: dict,
    root_created: bool,
    envelope_sha: str | None,
    envelope_body: dict | None,
    envelope_created: bool,
) -> dict:
    """Delete only exact objects created by this call that still have no lower/reference consumer."""
    removed_envelope = False
    removed_root = False
    envelope_preserved_reason = None
    root_preserved_reason = None

    if envelope_created and envelope_sha is not None and envelope_body is not None:
        envelope_store = st.get(w117.ENVELOPE_STORE)
        current = envelope_store.get(envelope_sha) if isinstance(envelope_store, dict) else None
        if current != envelope_body:
            envelope_preserved_reason = "candidate-envelope-changed-or-store-invalid"
        elif rt.get("app_state_sha") == envelope_sha:
            envelope_preserved_reason = "runtime-references-envelope"
        elif _binding_references_envelope(binding_store, envelope_sha):
            envelope_preserved_reason = "lower-binding-references-envelope"
        else:
            del envelope_store[envelope_sha]
            removed_envelope = True

    if root_created:
        root_store = st.get(w117.OUTCOME_ROOT_STORE)
        current = root_store.get(root_sha) if isinstance(root_store, dict) else None
        if current != root_body:
            root_preserved_reason = "candidate-root-changed-or-store-invalid"
        elif _envelope_references_root(st, root_sha):
            root_preserved_reason = "envelope-references-root"
        else:
            del root_store[root_sha]
            removed_root = True

    return {
        "removed_envelope": removed_envelope,
        "removed_root": removed_root,
        "envelope_preserved_reason": envelope_preserved_reason,
        "root_preserved_reason": root_preserved_reason,
    }


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
    *,
    fault_after_root_write: bool = False,
    fault_after_envelope_write: bool = False,
    fault_after_lower_prepare_before_sync: bool = False,
) -> tuple:
    """Prepare a rotation, rolling back only newly-created candidate objects that stay unreferenced."""
    verdict = authority(
        rt, st, boot, services, registry_store, transition_store, certificate_store,
        certificate_domain, binding_store, keyring
    )
    if not verdict.startswith("AUTHORITATIVE"):
        raise ValueError("Wave 120 rotation predecessor HOLD")

    _binding, current_envelope, current_root, _status, lineage = w118._current_anchor(
        rt, st, boot, registry_store, binding_store, keyring
    )
    if successor_domain.authority_id in {r["outcome_authority_id"] for r in lineage}:
        raise ValueError("rotation-successor-authority-already-used")

    rotated_root = w118._seal_rotated_root(current_root, keyring.current, successor_domain)
    root_sha = rotated_root["root_sha"]
    root_created = False
    envelope_sha = None
    envelope = None
    envelope_created = False

    try:
        root_sha, root_created = _put_exact_rotated_root(st, rotated_root)
        if fault_after_root_write:
            raise RuntimeError("injected-wave120-fault-after-root-write")

        user_app_state_sha = target_user_app_state_sha or current_envelope["user_app_state_sha"]
        envelope = w117._seal_envelope(user_app_state_sha, root_sha)
        envelope_sha, envelope_created = _put_exact_envelope(st, envelope)
        if fault_after_envelope_write:
            raise RuntimeError("injected-wave120-fault-after-envelope-write")

        effective = w118._effective_transition_store(
            st, registry_store, binding_store, transition_store, keyring, lineage
        )
        out = w114.prepare(
            rt, st, priv, boot, services, registry_store, effective, certificate_store,
            certificate_domain, binding_store, envelope_sha, None
        )
        if fault_after_lower_prepare_before_sync:
            raise RuntimeError("injected-wave120-fault-after-lower-prepare-before-sync")
        w118._sync_prepared_transition(transition_store, effective, out[3])
        return (*out, deepcopy(rotated_root), deepcopy(envelope))
    except Exception:
        _rollback_unreferenced_candidate(
            rt, st, binding_store, root_sha, rotated_root, root_created,
            envelope_sha, envelope, envelope_created,
        )
        raise
