#!/usr/bin/env python3
"""Independent Wave 119 verifier: failed rotation prepares retain orphan root/envelope state.

This is verifier-only evidence. It intentionally injects a lower prepare exception *after* Wave 118/119
has persisted the candidate rotated root and envelope, then checks whether the public prepare path rolls
those pre-lower writes back. No builder file is modified and no CANON/merge claim is made.
"""
from __future__ import annotations

import argparse
import hashlib
import json

import AXM_FLOWING_COMPUTE_CRASH_RECOVERABLE_ROTATION_LINEAGE as w
import AXM_FLOWING_COMPUTE_CRASH_RECOVERABLE_ROTATION_LINEAGE_SELFTEST as t119


def encoded_bytes(store: dict, keys: set[str]) -> int:
    return sum(
        len(json.dumps(store[key], sort_keys=True, separators=(",", ":")).encode("utf-8"))
        for key in keys
    )


def run(attempts: int) -> dict:
    if attempts < 1:
        raise ValueError("attempts-must-be-positive")

    world = t119.new_world()
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world

    # Use the same normal builder path to establish one settled committed epoch before attacking prepare.
    w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring,
        "wave119-verifier-orphan-precondition",
    )
    baseline_authority = w.authority(
        rt, st, boot, services, rs, ts, cs, certificate_domain, bs, keyring
    )
    if not baseline_authority.startswith("AUTHORITATIVE"):
        raise RuntimeError(f"baseline-not-authoritative:{baseline_authority}")

    root_store = st[w.w117.OUTCOME_ROOT_STORE]
    envelope_store = st[w.w117.ENVELOPE_STORE]
    base_root_keys = set(root_store)
    base_envelope_keys = set(envelope_store)
    base_transition_keys = set(ts)
    base_binding_keys = set(bs)

    original_lower_prepare = w.w114.prepare

    def injected_lower_failure(*args, **kwargs):
        raise RuntimeError("injected-verifier-lower-prepare-failure")

    failures: list[dict] = []
    w.w114.prepare = injected_lower_failure
    try:
        for index in range(attempts):
            successor = w.new_outcome_authority_domain()
            target_user_state = hashlib.sha256(
                f"wave119-verifier-failed-rotation-{index}".encode("utf-8")
            ).hexdigest()
            before_roots = len(root_store)
            before_envelopes = len(envelope_store)
            before_transitions = len(ts)
            before_bindings = len(bs)
            error = None
            try:
                w.prepare_rotation(
                    rt, st, priv, boot, services, rs, ts, cs, certificate_domain, bs,
                    keyring, successor, target_user_state,
                )
            except Exception as exc:
                error = f"{type(exc).__name__}:{exc}"
            after_authority = w.authority(
                rt, st, boot, services, rs, ts, cs, certificate_domain, bs, keyring
            )
            failures.append(
                {
                    "index": index,
                    "error": error,
                    "root_delta": len(root_store) - before_roots,
                    "envelope_delta": len(envelope_store) - before_envelopes,
                    "transition_delta": len(ts) - before_transitions,
                    "binding_delta": len(bs) - before_bindings,
                    "authority_after_failure": after_authority,
                }
            )
    finally:
        w.w114.prepare = original_lower_prepare

    orphan_root_keys = set(root_store) - base_root_keys
    orphan_envelope_keys = set(envelope_store) - base_envelope_keys
    transition_delta = len(set(ts) - base_transition_keys)
    binding_delta = len(set(bs) - base_binding_keys)
    orphan_bytes = encoded_bytes(root_store, orphan_root_keys) + encoded_bytes(
        envelope_store, orphan_envelope_keys
    )

    # Control: the orphan residue is ignored by the accepted checkpoint lineage, so a clean rotation
    # prepare can still proceed. This makes the issue a retained-state cost/cleanup boundary rather
    # than a false authority takeover.
    authority_before_clean = w.authority(
        rt, st, boot, services, rs, ts, cs, certificate_domain, bs, keyring
    )
    clean_successor = w.new_outcome_authority_domain()
    clean_prepared = w.prepare_rotation(
        rt, st, priv, boot, services, rs, ts, cs, certificate_domain, bs,
        keyring, clean_successor,
        hashlib.sha256(b"wave119-verifier-clean-rotation").hexdigest(),
    )

    per_attempt_exact = all(
        item["error"] == "RuntimeError:injected-verifier-lower-prepare-failure"
        and item["root_delta"] == 1
        and item["envelope_delta"] == 1
        and item["transition_delta"] == 0
        and item["binding_delta"] == 0
        and item["authority_after_failure"].startswith("AUTHORITATIVE")
        for item in failures
    )
    reproduced = (
        per_attempt_exact
        and len(orphan_root_keys) == attempts
        and len(orphan_envelope_keys) == attempts
        and transition_delta == 0
        and binding_delta == 0
        and authority_before_clean.startswith("AUTHORITATIVE")
        and isinstance(clean_prepared, tuple)
        and len(clean_prepared) >= 4
    )

    report = {
        "schema": "axm.flowing-compute.verifier-wave119-orphan-rotation-prepare-retention/v1",
        "builder_base": "b39e89fa8e0e64df543ab8a593429e47fbc3a530",
        "wave119_tested_source_commit": "c96d679d7cb03935c821bbdff4ab3e1a19c99018",
        "wave119_tool_blob": "28c8c85b3377289b69d742990556e5429fca487f",
        "attempts": attempts,
        "baseline_authority": baseline_authority,
        "failed_prepare_results": failures,
        "orphan_root_count": len(orphan_root_keys),
        "orphan_envelope_count": len(orphan_envelope_keys),
        "orphan_serialized_bytes": orphan_bytes,
        "lower_transition_delta_during_failures": transition_delta,
        "lower_binding_delta_during_failures": binding_delta,
        "authority_before_clean_control": authority_before_clean,
        "clean_prepare_succeeded_after_orphans": bool(clean_prepared),
        "verdict": (
            "FAIL_FAILED_ROTATION_PREPARES_ACCUMULATE_UNREFERENCED_ROOT_AND_ENVELOPE_STATE"
            if reproduced
            else "NOT_REPRODUCED"
        ),
        "boundary": {
            "stale_authority_accepted": False,
            "hash_or_credential_forgery": False,
            "builder_files_modified": False,
            "timing_or_energy_benchmark": False,
            "claim": "retained-state cleanup/storage-amplification boundary only",
        },
    }
    if not reproduced:
        raise AssertionError(json.dumps(report, sort_keys=True))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempts", type=int, default=16)
    parser.add_argument("--json-out")
    args = parser.parse_args()
    report = run(args.attempts)
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")


if __name__ == "__main__":
    main()
