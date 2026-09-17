#!/usr/bin/env python3
"""Independent verifier: Wave 118 rotation lower-commit -> provenance crash.

This verifier does not rewrite builder evidence or promote CANON. It fault-injects the exact
boundary after Wave 118's lower commit has succeeded and before the Wave 111 provenance append has
written anything. The expected safety behavior is fail-closed. The adversarial question is whether
an exact public retry/recovery route exists from that legitimate durable state.
"""
from __future__ import annotations

import json

import AXM_FLOWING_COMPUTE_OUTCOME_AUTHORITY_ROTATION_LINEAGE as w


VERDICT = "FAIL_ROTATION_LOWER_COMMIT_TO_PROVENANCE_CRASH_HAS_NO_PUBLIC_RECOVERY"


def new_world():
    st, priv, boot, rt, services, tokens, registry_store = w.q.fixture()
    transition_store = {}
    certificate_store = w.g.new_certificate_store()
    certificate_domain = w.w104.new_certificate_witness_domain()
    binding_store = {}
    initial = w.new_outcome_authority_domain()
    keyring = w.new_outcome_authority_keyring(initial)
    genesis = w.adopt_genesis(
        rt,
        st,
        boot,
        services,
        registry_store,
        transition_store,
        certificate_store,
        certificate_domain,
        binding_store,
        keyring,
    )
    return (
        st,
        priv,
        boot,
        rt,
        services,
        tokens,
        registry_store,
        transition_store,
        certificate_store,
        certificate_domain,
        binding_store,
        keyring,
        genesis,
    )


def exc_text(fn):
    try:
        result = fn()
        return None, result
    except Exception as exc:  # verifier intentionally records exact public failure
        return f"{type(exc).__name__}:{exc}", None


def main() -> int:
    (
        st,
        priv,
        boot,
        rt,
        services,
        tokens,
        registry_store,
        transition_store,
        certificate_store,
        certificate_domain,
        binding_store,
        keyring,
        genesis,
    ) = new_world()

    pre = w.advance_all(
        st,
        priv,
        boot,
        rt,
        services,
        tokens,
        registry_store,
        transition_store,
        certificate_store,
        certificate_domain,
        binding_store,
        keyring,
        "wave118-verifier-before-rotation-provenance-crash",
    )
    pre_status = pre[-1]

    predecessor_id = keyring.current.authority_id
    successor = w.new_outcome_authority_domain()
    prepared = w.prepare_rotation(
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
        keyring,
        successor,
    )
    _cp, _use, link, transition_sha, _binding_body, prepared_root, _envelope = prepared
    link_sha = link["authority_sha"]

    original_append = w.w111._append_provenance

    def crash_before_provenance(*_args, **_kwargs):
        raise RuntimeError("injected-verifier-crash-after-lower-commit-before-provenance")

    w.w111._append_provenance = crash_before_provenance
    try:
        crash_error, crash_result = exc_text(
            lambda: w.commit_rotation(
                rt,
                st,
                boot,
                registry_store,
                transition_store,
                link_sha,
                transition_sha,
                binding_store,
                keyring,
                successor,
            )
        )
    finally:
        w.w111._append_provenance = original_append

    # The lower commit has already advanced the accepted checkpoint/root lineage to the successor,
    # but live outcome authority has not been activated yet.
    current_binding, current_envelope, latest_root, anchor_status, lineage = w._checkpoint_root_lineage(
        rt, st, boot, registry_store, binding_store, keyring
    )
    keyring_after_crash = keyring.current.authority_id
    status_after_crash = w.commit_status_state(
        st, boot, rt, registry_store, binding_store, transition_store, keyring
    )
    authority_after_crash = w.authority(
        rt,
        st,
        boot,
        services,
        registry_store,
        transition_store,
        certificate_store,
        certificate_domain,
        binding_store,
        keyring,
    )

    retry_rotation_error, retry_rotation_result = exc_text(
        lambda: w.commit_rotation(
            rt,
            st,
            boot,
            registry_store,
            transition_store,
            link_sha,
            transition_sha,
            binding_store,
            keyring,
            successor,
        )
    )
    generic_commit_error, generic_commit_result = exc_text(
        lambda: w.commit(
            rt,
            st,
            boot,
            registry_store,
            transition_store,
            link_sha,
            transition_sha,
            binding_store,
            keyring,
        )
    )
    activation_recovery_error, activation_recovery_result = exc_text(
        lambda: w.recover_rotation_activation(
            rt,
            st,
            boot,
            registry_store,
            transition_store,
            binding_store,
            keyring,
            successor,
        )
    )
    status_after_public_recovery_attempts = w.commit_status_state(
        st, boot, rt, registry_store, binding_store, transition_store, keyring
    )
    keyring_after_public_recovery_attempts = keyring.current.authority_id

    # Diagnosis/control: the exact older internal provenance recovery primitive can repair the
    # missing row if the verifier manually bypasses Wave 118's public current-anchor guard.
    # This is not offered as a user-facing recovery path; it proves the durable data is sufficient.
    _b2, _e2, _r2, _s2, lineage2 = w._checkpoint_root_lineage(
        rt, st, boot, registry_store, binding_store, keyring
    )
    effective = w._effective_transition_store(
        st, registry_store, binding_store, transition_store, keyring, lineage2
    )
    internal_provenance_recovery = w.w114._recover_missing_trailing_provenance(
        st,
        boot,
        rt,
        registry_store,
        effective,
        binding_store,
        link_sha,
        transition_sha,
    )
    exact_activation_after_internal_repair = w.recover_rotation_activation(
        rt,
        st,
        boot,
        registry_store,
        transition_store,
        binding_store,
        keyring,
        successor,
    )
    status_after_internal_repair = w.commit_status_state(
        st, boot, rt, registry_store, binding_store, transition_store, keyring
    )

    publish_results = {
        slot: w.publish(rt, st, boot, services, tokens, registry_store, slot)
        for slot in w.q.REMOTE_IDS
    }
    cert_result, _cert_body = w.certify_and_sync(
        rt,
        st,
        boot,
        services,
        registry_store,
        certificate_store,
        certificate_domain,
    )
    final_authority = w.authority(
        rt,
        st,
        boot,
        services,
        registry_store,
        transition_store,
        certificate_store,
        certificate_domain,
        binding_store,
        keyring,
    )

    public_gap_reproduced = all(
        [
            pre_status.get("status") == w.HISTORY_VALID,
            isinstance(crash_error, str)
            and "injected-verifier-crash-after-lower-commit-before-provenance" in crash_error,
            crash_result is None,
            latest_root["root_sha"] == prepared_root["root_sha"],
            latest_root["outcome_authority_id"] == successor.authority_id,
            keyring_after_crash == predecessor_id,
            keyring_after_crash != successor.authority_id,
            status_after_crash.get("status") == w.HISTORY_INCOMPLETE,
            authority_after_crash == w.HOLD_INCOMPLETE,
            isinstance(retry_rotation_error, str),
            retry_rotation_result is None,
            isinstance(generic_commit_error, str),
            generic_commit_result is None,
            isinstance(activation_recovery_error, str),
            activation_recovery_result is None,
            status_after_public_recovery_attempts.get("status") == w.HISTORY_INCOMPLETE,
            keyring_after_public_recovery_attempts == predecessor_id,
        ]
    )
    diagnostic_internal_repair_works = all(
        [
            internal_provenance_recovery in {
                "COMMITTED_RECOVERED_EXACT_DECISION",
                "ALREADY_COMMITTED",
            },
            exact_activation_after_internal_repair == "RECOVERED_ROTATION_ACTIVATION",
            status_after_internal_repair.get("status") == w.HISTORY_VALID,
            final_authority.startswith("AUTHORITATIVE"),
        ]
    )

    report = {
        "schema": "axm.flowing-compute.verifier.wave118-rotation-provenance-crash/v1",
        "builder_head": "24d89d57ac0aaffe77febec875e1d70109f703a8",
        "builder_tool_blob": "8db646560e512a9fef3c4e57dc60012126533f6f",
        "builder_selftest_blob": "e468ed84b2b3e9e654d5723cd4ffaeb61e08e6a4",
        "verdict": VERDICT if public_gap_reproduced else "NOT_REPRODUCED",
        "public_gap_reproduced": public_gap_reproduced,
        "diagnostic_internal_repair_works": diagnostic_internal_repair_works,
        "genesis_result": genesis,
        "pre_status": pre_status,
        "predecessor_id": predecessor_id,
        "successor_id": successor.authority_id,
        "prepared_rotation_root_sha": prepared_root["root_sha"],
        "crash_error": crash_error,
        "latest_checkpoint_root_after_crash": latest_root,
        "anchor_status_after_crash": anchor_status,
        "accepted_root_generations_after_crash": [root["generation"] for root in lineage],
        "current_binding_sha_after_crash": current_binding["binding_sha"],
        "current_envelope_after_crash": current_envelope,
        "keyring_current_after_crash": keyring_after_crash,
        "status_after_crash": status_after_crash,
        "authority_after_crash": authority_after_crash,
        "retry_rotation_error": retry_rotation_error,
        "retry_rotation_result": retry_rotation_result,
        "generic_commit_error": generic_commit_error,
        "generic_commit_result": generic_commit_result,
        "activation_recovery_error": activation_recovery_error,
        "activation_recovery_result": activation_recovery_result,
        "status_after_public_recovery_attempts": status_after_public_recovery_attempts,
        "keyring_current_after_public_recovery_attempts": keyring_after_public_recovery_attempts,
        "internal_provenance_recovery": internal_provenance_recovery,
        "exact_activation_after_internal_repair": exact_activation_after_internal_repair,
        "status_after_internal_repair": status_after_internal_repair,
        "publish_results_after_internal_repair": publish_results,
        "certificate_result_after_internal_repair": cert_result,
        "final_authority_after_internal_repair": final_authority,
        "boundary": {
            "stale_authority_accepted": False,
            "hash_or_hmac_forgery": False,
            "builder_files_rewritten": False,
            "public_api_recovery_claim": "rotation crash after lower commit and before provenance has no complete public recovery path",
            "internal_helper_used_only_as_diagnostic_control": True,
            "os_process_or_power_loss_claim": False,
            "performance_or_energy_claim": False,
            "retained_incremental_dormant_compute_claim": False,
        },
    }
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0 if public_gap_reproduced and diagnostic_internal_repair_works else 1


if __name__ == "__main__":
    raise SystemExit(main())
