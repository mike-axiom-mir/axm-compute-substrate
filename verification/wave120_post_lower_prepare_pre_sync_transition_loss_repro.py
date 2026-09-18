#!/usr/bin/env python3
"""Independent Wave 120 verifier: lower prepare can succeed before its transition is synced.

Verifier-only evidence. This uses Wave 120's own fault_after_lower_prepare_before_sync boundary.
The attack does not modify builder files, forge hashes/credentials, or promote CANON.
"""
from __future__ import annotations

import argparse
import hashlib
import json

import AXM_FLOWING_COMPUTE_ROTATION_PREPARE_TRANSACTION as w
import AXM_FLOWING_COMPUTE_CRASH_RECOVERABLE_ROTATION_LINEAGE_SELFTEST as t119


def run() -> dict:
    world = t119.new_world()
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world

    # Establish a normal settled predecessor through the builder's public path.
    w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring,
        "wave120-verifier-pre-sync-loss-precondition",
    )
    baseline_authority = w.authority(
        rt, st, boot, services, rs, ts, cs, certificate_domain, bs, keyring
    )
    if not baseline_authority.startswith("AUTHORITATIVE"):
        raise RuntimeError(f"baseline-not-authoritative:{baseline_authority}")

    roots = st[w.w117.OUTCOME_ROOT_STORE]
    envelopes = st[w.w117.ENVELOPE_STORE]
    base_roots = set(roots)
    base_envelopes = set(envelopes)
    base_transitions = set(ts)
    base_bindings = set(bs)

    successor = w.new_outcome_authority_domain()
    target = hashlib.sha256(b"wave120-verifier-post-lower-pre-sync-target").hexdigest()

    first_error = None
    try:
        w.prepare_rotation(
            rt, st, priv, boot, services, rs, ts, cs, certificate_domain, bs,
            keyring, successor, target,
            fault_after_lower_prepare_before_sync=True,
        )
    except Exception as exc:
        first_error = f"{type(exc).__name__}:{exc}"

    new_roots = set(roots) - base_roots
    new_envelopes = set(envelopes) - base_envelopes
    new_transitions = set(ts) - base_transitions
    new_bindings = set(bs) - base_bindings

    referencing_bindings = [
        key for key, body in bs.items()
        if isinstance(body, dict) and body.get("user_app_state_sha") in new_envelopes
    ]

    status_after_fault = w.commit_status_state(
        st, boot, rt, rs, bs, ts, keyring
    )
    authority_after_fault = w.authority(
        rt, st, boot, services, rs, ts, cs, certificate_domain, bs, keyring
    )

    # Retry the exact same public rotation request. A recoverable transaction boundary should not
    # permanently strand the world merely because the transition lived only in the temporary
    # filtered transition dictionary before _sync_prepared_transition.
    retry_error = None
    retry_result = None
    try:
        retry_result = w.prepare_rotation(
            rt, st, priv, boot, services, rs, ts, cs, certificate_domain, bs,
            keyring, successor, target,
        )
    except Exception as exc:
        retry_error = f"{type(exc).__name__}:{exc}"

    status_after_retry = w.commit_status_state(
        st, boot, rt, rs, bs, ts, keyring
    )
    authority_after_retry = w.authority(
        rt, st, boot, services, rs, ts, cs, certificate_domain, bs, keyring
    )

    reproduced = (
        first_error == "RuntimeError:injected-wave120-fault-after-lower-prepare-before-sync"
        and len(new_roots) == 1
        and len(new_envelopes) == 1
        and len(new_transitions) == 0
        and len(referencing_bindings) >= 1
        and len(new_bindings) >= 1
        and not authority_after_fault.startswith("AUTHORITATIVE")
        and retry_result is None
        and retry_error is not None
        and not authority_after_retry.startswith("AUTHORITATIVE")
    )

    report = {
        "schema": "axm.flowing-compute.verifier-wave120-post-lower-pre-sync-transition-loss/v1",
        "builder_head": "f0d171e65fcc3d0618915bd7d9d79a4deabda7cb",
        "wave120_tool_blob": "cdf87ee52abb1c9381af38807cea73509ce9cd40",
        "wave120_selftest_blob": "b763c7123494d777d969475e58b5640009f526c6",
        "baseline_authority": baseline_authority,
        "first_error": first_error,
        "new_root_count": len(new_roots),
        "new_envelope_count": len(new_envelopes),
        "new_transition_count_in_public_store": len(new_transitions),
        "new_binding_count": len(new_bindings),
        "binding_references_new_envelope": bool(referencing_bindings),
        "referencing_binding_keys": sorted(referencing_bindings),
        "status_after_fault": status_after_fault,
        "authority_after_fault": authority_after_fault,
        "exact_retry_result": retry_result,
        "exact_retry_error": retry_error,
        "status_after_retry": status_after_retry,
        "authority_after_retry": authority_after_retry,
        "verdict": (
            "FAIL_LOWER_PREPARE_SUCCEEDS_BUT_TRANSITION_IS_LOST_BEFORE_SYNC_AND_PUBLIC_RETRY_HOLDS"
            if reproduced else "NOT_REPRODUCED"
        ),
        "boundary": {
            "stale_authority_accepted": False,
            "hash_or_credential_forgery": False,
            "builder_files_modified": False,
            "power_loss_claim": False,
            "timing_or_energy_benchmark": False,
            "failure_domain": "same-process injected exception at builder-exposed post-lower/pre-sync boundary",
            "claim": "prepare atomicity/liveness and evidence synchronization only",
        },
    }
    if not reproduced:
        raise AssertionError(json.dumps(report, sort_keys=True))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out")
    args = parser.parse_args()
    report = run()
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")


if __name__ == "__main__":
    main()
