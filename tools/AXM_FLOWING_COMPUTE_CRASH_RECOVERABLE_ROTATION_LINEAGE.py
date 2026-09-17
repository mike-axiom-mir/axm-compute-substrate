#!/usr/bin/env python3
"""AXM Flowing Compute Wave 119: crash-recoverable bootstrap and rotation lineage.

Wave 118 proved old-root-authorized outcome-authority rotation, but independent verifier work exposed
two bounded liveness/evidence-atomicity gaps that remained fail-closed:

* Wave 117/118 bootstrap could persist the exact root (and optionally its exact envelope) before the
  lower genesis adoption, then reject every public retry merely because that prefix already existed.
* Wave 118 rotation could durably commit the successor checkpoint/root and lower commit decision, then
  crash before transition provenance. The retained evidence was sufficient for the older exact
  provenance recovery helper, but no Wave-118 public route composed provenance recovery with
  successor-credential activation.

Wave 119 adds only conservative public retry/recovery for those exact boundaries. It never infers a
new root, transition, outcome, or terminal decision from ambiguous residue. Existing whole-domain
rollback remains a counterexample. This is still one modeled Python failure domain, not process,
device, network, provider, hardware, energy, or performance evidence. No merge/CANON promotion.
"""
from __future__ import annotations

from copy import deepcopy

import AXM_FLOWING_COMPUTE_OUTCOME_AUTHORITY_ROTATION_LINEAGE as w118

w117 = w118.w117
w116 = w118.w116
w115 = w118.w115
w114 = w118.w114
w111 = w118.w111
w110 = w118.w110
w105 = w118.w105
w104 = w118.w104
q = w118.q
g = w118.g

SRC = {
    "wave118_tested_source_commit": "24d89d57ac0aaffe77febec875e1d70109f703a8",
    "wave118_tool_blob": "8db646560e512a9fef3c4e57dc60012126533f6f",
    "wave118_selftest_blob": "e468ed84b2b3e9e654d5723cd4ffaeb61e08e6a4",
    "wave118_workflow_blob": "1ece9ee72ba3fa128829800bdfbbbd3607a5afb1",
    "wave118_ci_run": 35255168576,
    "wave118_ci_artifact_id": 10513560709,
    "wave118_ci_artifact_sha256": "1edde7fe57fa1abb9e4b7cb7bd96de0a4e1e09380a9c8d027ddf0f4807b784d5",
    "verifier_prs": [42, 43],
}

OutcomeAuthorityDomain = w118.OutcomeAuthorityDomain
OutcomeAuthorityKeyring = w118.OutcomeAuthorityKeyring
new_outcome_authority_domain = w118.new_outcome_authority_domain
new_outcome_authority_keyring = w118.new_outcome_authority_keyring

HISTORY_NONE = w118.HISTORY_NONE
HISTORY_VALID = w118.HISTORY_VALID
HISTORY_INCOMPLETE = w118.HISTORY_INCOMPLETE
HISTORY_UNRESOLVED = w118.HISTORY_UNRESOLVED
HOLD_INCOMPLETE = w118.HOLD_INCOMPLETE
HOLD_UNRESOLVED = w118.HOLD_UNRESOLVED

authority = w118.authority
commit_status_state = w118.commit_status_state
prepare = w118.prepare
commit = w118.commit
prepare_rotation = w118.prepare_rotation
publish = w118.publish
certify_and_sync = w118.certify_and_sync
advance_all = w118.advance_all


def _exact_singleton_or_absent(store: object, expected_sha: str, expected_body: dict, label: str) -> bool:
    """Accept no store or exactly one expected content-addressed body; reject all ambiguous residue."""
    if store is None:
        return False
    if not isinstance(store, dict):
        raise ValueError(f"{label}-store-invalid")
    if set(store) != {expected_sha}:
        raise ValueError(f"{label}-store-not-exact-retry-prefix")
    if store[expected_sha] != expected_body:
        raise ValueError(f"{label}-body-does-not-match-exact-retry-prefix")
    return True


def _lower_genesis_present(st: dict) -> bool:
    return (
        w116.OUTCOME_BINDING in st
        or w116.OUTCOME_STORE in st
        or w114.DECISION_STORE in st
    )


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
    """Adopt genesis or resume only the exact Wave-117 pre-lower-genesis durable prefix."""
    if _lower_genesis_present(st):
        state = w118.commit_status_state(
            st, boot, rt, registry_store, binding_store, transition_store, keyring
        )
        if state.get("status") not in (HISTORY_NONE, HISTORY_VALID):
            raise ValueError(f"wave119-existing-genesis-not-valid:{state}")
        _binding, _envelope, root, _status, lineage = w118._current_anchor(
            rt, st, boot, registry_store, binding_store, keyring
        )
        if len(lineage) != 1 or root.get("generation") != 0:
            raise ValueError("wave119-existing-genesis-lineage-not-generation-zero")
        if root.get("outcome_authority_id") != keyring.current.authority_id:
            raise ValueError("wave119-existing-genesis-authority-mismatch")
        return "ALREADY_GENESIS_ADOPTED"

    if binding_store:
        raise ValueError("wave119-bootstrap-retry-lower-binding-evidence-already-present")
    if transition_store:
        raise ValueError("wave119-bootstrap-retry-transition-evidence-already-present")

    original_app_state_sha = rt.get("app_state_sha")
    if not w117._is_sha(original_app_state_sha):
        raise ValueError("wave119-genesis-user-app-state-invalid")

    expected_root = w117._seal_root(keyring.current.authority_id)
    root_sha = expected_root["root_sha"]
    root_present = _exact_singleton_or_absent(
        st.get(w117.OUTCOME_ROOT_STORE), root_sha, expected_root, "wave119-bootstrap-root"
    )
    if not root_present:
        w117._put_root(st, expected_root)

    expected_envelope = w117._seal_envelope(original_app_state_sha, root_sha)
    envelope_sha = expected_envelope["envelope_sha"]
    envelope_present = _exact_singleton_or_absent(
        st.get(w117.ENVELOPE_STORE), envelope_sha, expected_envelope, "wave119-bootstrap-envelope"
    )
    if not envelope_present:
        w117._put_envelope(st, expected_envelope)

    rt["app_state_sha"] = envelope_sha
    try:
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
            keyring.current,
        )
    except Exception:
        if not _lower_genesis_present(st) and not binding_store and not transition_store:
            rt["app_state_sha"] = original_app_state_sha
        raise

    state = w118.commit_status_state(
        st, boot, rt, registry_store, binding_store, transition_store, keyring
    )
    if state.get("status") not in (HISTORY_NONE, HISTORY_VALID):
        raise ValueError(f"wave119-genesis-recovery-did-not-settle:{state}")
    return result


def _rotation_recovery_context(
    rt: dict,
    st: dict,
    boot: dict,
    registry_store: dict,
    transition_store: dict,
    binding_store: dict,
    keyring: OutcomeAuthorityKeyring,
    successor_domain: OutcomeAuthorityDomain,
    transition_sha: str,
) -> tuple[list[dict], dict, dict]:
    _binding, _envelope, latest_root, _status, lineage = w118._checkpoint_root_lineage(
        rt, st, boot, registry_store, binding_store, keyring
    )
    if len(lineage) < 2:
        raise ValueError("wave119-rotation-recovery-no-anchored-successor")
    predecessor = lineage[-2]
    w118._verify_direct_successor(predecessor, latest_root, keyring)
    if latest_root.get("outcome_authority_id") != successor_domain.authority_id:
        raise ValueError("wave119-rotation-recovery-successor-credential-mismatch")
    if keyring.current.authority_id not in {
        predecessor.get("outcome_authority_id"),
        latest_root.get("outcome_authority_id"),
    }:
        raise ValueError("wave119-rotation-recovery-live-credential-outside-accepted-tail")

    target_root = w118._transition_root(
        st, registry_store, binding_store, transition_store, transition_sha
    )
    if target_root.get("root_sha") != latest_root.get("root_sha"):
        raise ValueError("wave119-rotation-recovery-transition-root-not-accepted-tail")
    if target_root.get("outcome_authority_id") != successor_domain.authority_id:
        raise ValueError("wave119-rotation-recovery-transition-successor-mismatch")

    effective = w118._effective_transition_store(
        st, registry_store, binding_store, transition_store, keyring, lineage
    )
    w115._strict_transition_get(effective, transition_sha)
    return lineage, latest_root, effective


def recover_rotation_commit(
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
) -> str:
    """Recover exact lower-committed rotation provenance, then exact successor activation."""
    _lineage, latest_root, effective = _rotation_recovery_context(
        rt,
        st,
        boot,
        registry_store,
        transition_store,
        binding_store,
        keyring,
        successor_domain,
        transition_sha,
    )

    before_rows = w111._provenance_rows(st)
    before_count = len(before_rows or [])
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
    if recovered is None:
        raise ValueError("wave119-rotation-recovery-lower-commit-not-proven")

    after_rows = w111._provenance_rows(st)
    after_count = len(after_rows or [])
    provenance_added = after_count == before_count + 1

    if keyring.current.authority_id == successor_domain.authority_id:
        mutable = w116._check_binding(st, keyring.current)
        if mutable.get("outcome_authority_id") != latest_root.get("outcome_authority_id"):
            raise ValueError("wave119-rotation-recovery-live-binding-successor-mismatch")
        state = w118.commit_status_state(
            st, boot, rt, registry_store, binding_store, transition_store, keyring
        )
        if state.get("status") != HISTORY_VALID:
            raise RuntimeError(f"wave119-already-activated-rotation-not-valid:{state}")
        return "RECOVERED_ROTATION_COMMIT" if provenance_added else "ALREADY_COMMITTED_ROTATED"

    activated = w118.recover_rotation_activation(
        rt,
        st,
        boot,
        registry_store,
        transition_store,
        binding_store,
        keyring,
        successor_domain,
    )
    if activated != "RECOVERED_ROTATION_ACTIVATION":
        raise RuntimeError(f"wave119-unexpected-rotation-activation-result:{activated}")

    state = w118.commit_status_state(
        st, boot, rt, registry_store, binding_store, transition_store, keyring
    )
    if state.get("status") != HISTORY_VALID:
        raise RuntimeError(f"wave119-rotation-recovery-did-not-settle:{state}")
    return "RECOVERED_ROTATION_COMMIT" if provenance_added else activated


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
    """Commit normally, but make an exact public retry resume already checkpointed rotation tails."""
    target_root = w118._transition_root(
        st, registry_store, binding_store, transition_store, transition_sha
    )
    _binding, _envelope, latest_root, _status, _lineage = w118._checkpoint_root_lineage(
        rt, st, boot, registry_store, binding_store, keyring
    )
    if target_root.get("root_sha") == latest_root.get("root_sha"):
        return recover_rotation_commit(
            rt,
            st,
            boot,
            registry_store,
            transition_store,
            link_sha,
            transition_sha,
            binding_store,
            keyring,
            successor_domain,
        )

    return w118.commit_rotation(
        rt,
        st,
        boot,
        registry_store,
        transition_store,
        link_sha,
        transition_sha,
        binding_store,
        keyring,
        successor_domain,
        n,
        fault_after_checkpoint_before_activation=fault_after_checkpoint_before_activation,
    )


recover_rotation_activation = w118.recover_rotation_activation
