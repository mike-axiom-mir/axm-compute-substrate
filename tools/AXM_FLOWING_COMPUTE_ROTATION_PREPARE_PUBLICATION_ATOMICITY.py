#!/usr/bin/env python3
"""AXM Flowing Compute Wave 121: staged rotation-prepare publication atomicity.

Independent verifier PR #45 found a fail-closed liveness/evidence hole in Wave 120. Wave 120 could
run the lower prepare against a temporary transition store while still giving it the public binding
store and public retained signer/checkpoint state. A fault after the lower prepare but before
transition sync therefore left a real binding/checkpoint/signature reservation in public state while
the exact prepared transition body existed only in the temporary store. Authority correctly HOLDed,
but the exact public retry could not pass the predecessor authority gate.

Wave 121 stages every lower-prepare mutation surface used by the modeled protocol (retained state,
private signer reservations/successors, transition store, and root-binding store) before exposing any
of it. The exact prepared transition is synchronized into the staged transition store first. The
staged deltas are then checked against the returned checkpoint/use/link/transition/binding/root/
envelope identities. Only after those checks does the call publish the staged state. Injected
same-process exceptions during publication restore the exact pre-call snapshots.

Truth boundary:
- this is same-process exception transactionality, not OS-process/power-loss atomicity;
- the successful publication still consists of multiple in-memory writes; a hard process kill between
  them remains an explicit next-gate counterexample;
- no missing transition is reconstructed from semantic similarity: the exact lower-produced
  transition SHA/body must exist in staged evidence before publication;
- whole-domain rollback remains a counterexample; all witnesses/stores still share one modeled Python
  failure domain;
- no performance, energy, network, retained/incremental/dormant-compute win is claimed;
- no merge, auto-merge, or CANON promotion is performed by this tool.
"""
from __future__ import annotations

from copy import deepcopy

import AXM_FLOWING_COMPUTE_ROTATION_PREPARE_TRANSACTION as w120

w119 = w120.w119
w118 = w120.w118
w117 = w120.w117
w116 = w120.w116
w115 = w120.w115
w114 = w120.w114
w111 = w120.w111
w110 = w120.w110
w105 = w120.w105
w104 = w120.w104
q = w120.q
g = w120.g

SRC = {
    "wave120_dependency_head": "d8d466181ffc80554549899c1dcafa115a27e7ec",
    "wave120_tool_blob": "cdf87ee52abb1c9381af38807cea73509ce9cd40",
    "wave120_selftest_blob": "51ee96c8a629ef696ce0abcc84f01e80b0a9b20d",
    "independent_verifier_pr": 45,
    "verifier_head": "ad230a162462fba3636b6e2a264b83a4d10a7295",
    "verifier_ci_run": 35269713222,
    "verifier_artifact_sha256": "c3cb43b205a442f124d7578414ba50f61a53a6300582467931a29e37439f7b44",
}

OutcomeAuthorityDomain = w120.OutcomeAuthorityDomain
OutcomeAuthorityKeyring = w120.OutcomeAuthorityKeyring
new_outcome_authority_domain = w120.new_outcome_authority_domain
new_outcome_authority_keyring = w120.new_outcome_authority_keyring

HISTORY_NONE = w120.HISTORY_NONE
HISTORY_VALID = w120.HISTORY_VALID
HISTORY_INCOMPLETE = w120.HISTORY_INCOMPLETE
HISTORY_UNRESOLVED = w120.HISTORY_UNRESOLVED
HOLD_INCOMPLETE = w120.HOLD_INCOMPLETE
HOLD_UNRESOLVED = w120.HOLD_UNRESOLVED

authority = w120.authority
commit_status_state = w120.commit_status_state
adopt_genesis = w120.adopt_genesis
prepare = w120.prepare
commit = w120.commit
commit_rotation = w120.commit_rotation
recover_rotation_commit = w120.recover_rotation_commit
recover_rotation_activation = w120.recover_rotation_activation
publish = w120.publish
certify_and_sync = w120.certify_and_sync
advance_all = w120.advance_all


def _replace_exact(dst: dict, src: dict) -> None:
    dst.clear()
    dst.update(deepcopy(src))


def _append_only(before: dict, after: dict, label: str) -> None:
    if not isinstance(before, dict) or not isinstance(after, dict):
        raise ValueError(f"wave121-{label}-store-shape-invalid")
    for key, body in before.items():
        if key not in after:
            raise ValueError(f"wave121-{label}-existing-key-removed")
        if after[key] != body:
            raise ValueError(f"wave121-{label}-existing-body-changed")


def _new_keys(before: dict, after: dict) -> set:
    return set(after) - set(before)


def _validate_staged_prepare(
    before_st: dict,
    staged_st: dict,
    before_priv: dict,
    staged_priv: dict,
    before_transition_store: dict,
    staged_transition_store: dict,
    before_binding_store: dict,
    staged_binding_store: dict,
    out: tuple,
    rotated_root: dict,
    envelope: dict,
) -> None:
    if not isinstance(out, tuple) or len(out) != 5:
        raise ValueError("wave121-lower-prepare-result-shape-invalid")
    cp, use, link, transition_sha, binding = out

    expected_stores = {
        "P": set(cp["next_signer_keys"].values()),
        "C": {cp["checkpoint_sha"]},
        "U": {use["use_sha"]},
        "L": {link["authority_sha"]},
        w117.OUTCOME_ROOT_STORE: {rotated_root["root_sha"]},
        w117.ENVELOPE_STORE: {envelope["envelope_sha"]},
    }
    allowed_changed = set(expected_stores)

    for key in set(before_st) | set(staged_st):
        if key not in before_st and key not in allowed_changed:
            raise ValueError(f"wave121-unexpected-new-retained-store:{key}")
        if key in before_st and key not in allowed_changed and staged_st.get(key) != before_st[key]:
            raise ValueError(f"wave121-unexpected-retained-state-mutation:{key}")

    for key, expected_identities in expected_stores.items():
        before_store = before_st.get(key, {})
        after_store = staged_st.get(key, {})
        _append_only(before_store, after_store, f"retained-{key}")
        expected_new = expected_identities - set(before_store)
        actual_new = _new_keys(before_store, after_store)
        if actual_new != expected_new:
            raise ValueError(f"wave121-retained-{key}-delta-mismatch")

    _append_only(before_transition_store, staged_transition_store, "transition")
    expected_transition_new = {transition_sha} - set(before_transition_store)
    if _new_keys(before_transition_store, staged_transition_store) != expected_transition_new:
        raise ValueError("wave121-transition-delta-mismatch")
    exact_transition = staged_transition_store.get(transition_sha)
    if not isinstance(exact_transition, dict) or exact_transition.get("transition_sha") != transition_sha:
        raise ValueError("wave121-exact-transition-body-missing")
    w120.w118.w114.w113.w112.w110.get_transition(staged_transition_store, transition_sha)

    _append_only(before_binding_store, staged_binding_store, "binding")
    binding_sha = binding.get("binding_sha")
    expected_binding_new = {binding_sha} - set(before_binding_store)
    if _new_keys(before_binding_store, staged_binding_store) != expected_binding_new:
        raise ValueError("wave121-binding-delta-mismatch")
    if staged_binding_store.get(binding_sha) != binding:
        raise ValueError("wave121-exact-binding-body-mismatch")
    if binding.get("user_app_state_sha") != envelope.get("envelope_sha"):
        raise ValueError("wave121-binding-envelope-crossbind-mismatch")

    signer_keys = set(cp["signer_keys"].values())
    next_keys = set(cp["next_signer_keys"].values())
    expected_new_priv = next_keys - set(before_priv)
    if _new_keys(before_priv, staged_priv) != expected_new_priv:
        raise ValueError("wave121-private-successor-delta-mismatch")
    for key, prior in before_priv.items():
        current = staged_priv.get(key)
        if key in signer_keys:
            expected = deepcopy(prior)
            expected["reserved"] = cp["checkpoint_sha"]
            if current != expected:
                raise ValueError("wave121-private-current-signer-reservation-mismatch")
        elif current != prior:
            raise ValueError("wave121-unexpected-existing-private-state-mutation")
    for key in expected_new_priv:
        body = staged_priv.get(key)
        if not isinstance(body, dict) or body.get("reserved") is not None or "seed" not in body:
            raise ValueError("wave121-private-successor-body-invalid")


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
    fault_after_lower_prepare_before_publish: bool = False,
    fault_after_transition_publish: bool = False,
    fault_after_retained_state_publish: bool = False,
    fault_after_binding_publish: bool = False,
    fault_after_private_state_publish: bool = False,
) -> tuple:
    """Prepare entirely off-public-state, then publish with exact same-process rollback."""
    verdict = authority(
        rt, st, boot, services, registry_store, transition_store, certificate_store,
        certificate_domain, binding_store, keyring
    )
    if not verdict.startswith("AUTHORITATIVE"):
        raise ValueError("Wave 121 rotation predecessor HOLD")

    _binding, current_envelope, current_root, _status, lineage = w118._current_anchor(
        rt, st, boot, registry_store, binding_store, keyring
    )
    if successor_domain.authority_id in {r["outcome_authority_id"] for r in lineage}:
        raise ValueError("rotation-successor-authority-already-used")

    before_st = deepcopy(st)
    before_priv = deepcopy(priv)
    before_transition_store = deepcopy(transition_store)
    before_binding_store = deepcopy(binding_store)
    before_rt = deepcopy(rt)
    before_services = deepcopy(services)
    before_registry_store = deepcopy(registry_store)
    before_certificate_store = deepcopy(certificate_store)

    staged_st = deepcopy(st)
    staged_priv = deepcopy(priv)
    staged_transition_store = deepcopy(transition_store)
    staged_binding_store = deepcopy(binding_store)
    staged_rt = deepcopy(rt)
    staged_services = deepcopy(services)
    staged_registry_store = deepcopy(registry_store)
    staged_certificate_store = deepcopy(certificate_store)

    rotated_root = w118._seal_rotated_root(current_root, keyring.current, successor_domain)
    root_sha, _root_created = w120._put_exact_rotated_root(staged_st, rotated_root)
    user_app_state_sha = target_user_app_state_sha or current_envelope["user_app_state_sha"]
    envelope = w117._seal_envelope(user_app_state_sha, root_sha)
    envelope_sha, _envelope_created = w120._put_exact_envelope(staged_st, envelope)

    effective = w118._effective_transition_store(
        staged_st, staged_registry_store, staged_binding_store,
        staged_transition_store, keyring, lineage
    )
    out = w114.prepare(
        staged_rt, staged_st, staged_priv, boot, staged_services, staged_registry_store,
        effective, staged_certificate_store, certificate_domain, staged_binding_store,
        envelope_sha, None
    )
    w118._sync_prepared_transition(staged_transition_store, effective, out[3])

    if staged_rt != before_rt:
        raise ValueError("wave121-lower-prepare-mutated-runtime")
    if staged_services != before_services:
        raise ValueError("wave121-lower-prepare-mutated-services")
    if staged_registry_store != before_registry_store:
        raise ValueError("wave121-lower-prepare-mutated-registry-store")
    if staged_certificate_store != before_certificate_store:
        raise ValueError("wave121-lower-prepare-mutated-certificate-store")

    _validate_staged_prepare(
        before_st, staged_st, before_priv, staged_priv,
        before_transition_store, staged_transition_store,
        before_binding_store, staged_binding_store,
        out, rotated_root, envelope,
    )

    if fault_after_lower_prepare_before_publish:
        raise RuntimeError("injected-wave121-fault-after-lower-prepare-before-publish")

    publication_started = False
    try:
        publication_started = True
        _replace_exact(transition_store, staged_transition_store)
        if fault_after_transition_publish:
            raise RuntimeError("injected-wave121-fault-after-transition-publish")

        _replace_exact(st, staged_st)
        if fault_after_retained_state_publish:
            raise RuntimeError("injected-wave121-fault-after-retained-state-publish")

        _replace_exact(binding_store, staged_binding_store)
        if fault_after_binding_publish:
            raise RuntimeError("injected-wave121-fault-after-binding-publish")

        _replace_exact(priv, staged_priv)
        if fault_after_private_state_publish:
            raise RuntimeError("injected-wave121-fault-after-private-state-publish")

        if transition_store != staged_transition_store or st != staged_st \
                or binding_store != staged_binding_store or priv != staged_priv:
            raise RuntimeError("wave121-publication-postcheck-mismatch")
        return (*out, deepcopy(rotated_root), deepcopy(envelope))
    except Exception:
        if publication_started:
            _replace_exact(transition_store, before_transition_store)
            _replace_exact(st, before_st)
            _replace_exact(binding_store, before_binding_store)
            _replace_exact(priv, before_priv)
        raise
