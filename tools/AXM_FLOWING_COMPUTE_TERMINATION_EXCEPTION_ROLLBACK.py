#!/usr/bin/env python3
"""AXM Flowing Compute Wave 122: termination-exception-safe publication rollback.

Independent verifier PR #46 found a narrower same-process truth defect in Wave 121. The staged
publication repair was rollback-safe for ordinary ``Exception`` failures, but ``KeyboardInterrupt``
and ``SystemExit`` inherit directly from ``BaseException``. A termination exception after the first
public write therefore escaped the Wave 121 handler, left a mixed caller-visible prepare state, and
made the exact legitimate retry HOLD.

Wave 122 keeps Wave 121's off-public-state staging and exact identity checks. The only protocol change
is at the publication boundary: it catches a single same-process ``BaseException`` after publication
has started, restores all four caller-visible stores through a private non-instrumented restore path,
and then re-raises the original termination exception. Ordinary exceptions keep the same behavior.

Truth boundary:
- this is still same-process Python rollback, not OS-process, SIGKILL, power-loss, filesystem, or
  hardware atomicity;
- the proof is bounded to one injected termination exception while the rollback path itself can run;
  repeated termination during rollback remains unproved;
- successful publication still consists of multiple in-memory writes and can be interrupted by a hard
  process kill, which remains the next process-boundary gate;
- whole-domain rollback remains a counterexample; all witnesses/stores still share one modeled Python
  failure domain;
- no performance, energy, network, retained/incremental/dormant-compute win is claimed;
- no merge, auto-merge, or CANON promotion is performed by this tool.
"""
from __future__ import annotations

from copy import deepcopy

import AXM_FLOWING_COMPUTE_ROTATION_PREPARE_PUBLICATION_ATOMICITY as w121

w120 = w121.w120
w119 = w121.w119
w118 = w121.w118
w117 = w121.w117
w116 = w121.w116
w115 = w121.w115
w114 = w121.w114
w111 = w121.w111
w110 = w121.w110
w105 = w121.w105
w104 = w121.w104
q = w121.q
g = w121.g

SRC = {
    "wave121_dependency_head": "85ca87b7eec6699957343f00203e6d25f2309c39",
    "wave121_tool_blob": "b0909097c6af1d6aa5dd522664aa9f8caaade587",
    "wave121_selftest_blob": "c73fc1b19f517927643ebb771bc8cd17d873776f",
    "independent_verifier_pr": 46,
    "verifier_head": "4fe827550c160e9155f5825eb5331cbfcca6f2f3",
    "verifier_ci_run": 35275924241,
    "verifier_artifact_sha256": "53da634a88895bf91c242c61f74f7e3b2f74532987be7a093fa39a85b325d342",
}

OutcomeAuthorityDomain = w121.OutcomeAuthorityDomain
OutcomeAuthorityKeyring = w121.OutcomeAuthorityKeyring
new_outcome_authority_domain = w121.new_outcome_authority_domain
new_outcome_authority_keyring = w121.new_outcome_authority_keyring

HISTORY_NONE = w121.HISTORY_NONE
HISTORY_VALID = w121.HISTORY_VALID
HISTORY_INCOMPLETE = w121.HISTORY_INCOMPLETE
HISTORY_UNRESOLVED = w121.HISTORY_UNRESOLVED
HOLD_INCOMPLETE = w121.HOLD_INCOMPLETE
HOLD_UNRESOLVED = w121.HOLD_UNRESOLVED

authority = w121.authority
commit_status_state = w121.commit_status_state
adopt_genesis = w121.adopt_genesis
prepare = w121.prepare
commit = w121.commit
commit_rotation = w121.commit_rotation
recover_rotation_commit = w121.recover_rotation_commit
recover_rotation_activation = w121.recover_rotation_activation
publish = w121.publish
certify_and_sync = w121.certify_and_sync
advance_all = w121.advance_all


def _publish_replace(dst: dict, src: dict) -> None:
    """Normal publication write; kept separate so adversarial tests can cut after each write."""
    w121._replace_exact(dst, src)


def _restore_exact(dst: dict, src: dict) -> None:
    """Private rollback path independent of the instrumentable publication helper."""
    snapshot = deepcopy(src)
    dict.clear(dst)
    dict.update(dst, snapshot)


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
    """Wave 121 staging plus exact rollback for one same-process BaseException."""
    verdict = authority(
        rt, st, boot, services, registry_store, transition_store, certificate_store,
        certificate_domain, binding_store, keyring
    )
    if not verdict.startswith("AUTHORITATIVE"):
        raise ValueError("Wave 122 rotation predecessor HOLD")

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
        raise ValueError("wave122-lower-prepare-mutated-runtime")
    if staged_services != before_services:
        raise ValueError("wave122-lower-prepare-mutated-services")
    if staged_registry_store != before_registry_store:
        raise ValueError("wave122-lower-prepare-mutated-registry-store")
    if staged_certificate_store != before_certificate_store:
        raise ValueError("wave122-lower-prepare-mutated-certificate-store")

    w121._validate_staged_prepare(
        before_st, staged_st, before_priv, staged_priv,
        before_transition_store, staged_transition_store,
        before_binding_store, staged_binding_store,
        out, rotated_root, envelope,
    )

    if fault_after_lower_prepare_before_publish:
        raise RuntimeError("injected-wave122-fault-after-lower-prepare-before-publish")

    publication_started = False
    try:
        publication_started = True
        _publish_replace(transition_store, staged_transition_store)
        if fault_after_transition_publish:
            raise RuntimeError("injected-wave122-fault-after-transition-publish")

        _publish_replace(st, staged_st)
        if fault_after_retained_state_publish:
            raise RuntimeError("injected-wave122-fault-after-retained-state-publish")

        _publish_replace(binding_store, staged_binding_store)
        if fault_after_binding_publish:
            raise RuntimeError("injected-wave122-fault-after-binding-publish")

        _publish_replace(priv, staged_priv)
        if fault_after_private_state_publish:
            raise RuntimeError("injected-wave122-fault-after-private-state-publish")

        if transition_store != staged_transition_store or st != staged_st \
                or binding_store != staged_binding_store or priv != staged_priv:
            raise RuntimeError("wave122-publication-postcheck-mismatch")
        return (*out, deepcopy(rotated_root), deepcopy(envelope))
    except BaseException:
        if publication_started:
            _restore_exact(transition_store, before_transition_store)
            _restore_exact(st, before_st)
            _restore_exact(binding_store, before_binding_store)
            _restore_exact(priv, before_priv)
        raise
