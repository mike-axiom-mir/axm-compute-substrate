#!/usr/bin/env python3
"""Independent adversarial verifier for Wave 121 publication rollback.

This lane does not modify builder code. It checks the builder's unchanged self-test, then
injects a real same-process KeyboardInterrupt immediately after the first public store
replacement. KeyboardInterrupt inherits BaseException, not Exception, so it challenges
whether the claimed same-process exception transactionality is broader than the actual
handler.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import sys

import AXM_FLOWING_COMPUTE_ROTATION_PREPARE_PUBLICATION_ATOMICITY as w
import AXM_FLOWING_COMPUTE_ROTATION_PREPARE_PUBLICATION_ATOMICITY_SELFTEST as t121


def keyboard_interrupt_after_first_public_write() -> dict:
    world = t121.prepared_world("verifier-wave121-keyboardinterrupt")
    st, priv, boot, rt, services, tokens, rs, ts, cs, certificate_domain, bs, keyring = world

    before_st = deepcopy(st)
    before_priv = deepcopy(priv)
    before_ts = deepcopy(ts)
    before_bs = deepcopy(bs)

    successor = w.new_outcome_authority_domain()
    target = hashlib.sha256(b"verifier-wave121-keyboardinterrupt-target").hexdigest()

    original_replace = w._replace_exact
    replace_calls = 0

    def interrupting_replace(dst: dict, src: dict) -> None:
        nonlocal replace_calls
        original_replace(dst, src)
        replace_calls += 1
        if replace_calls == 1:
            raise KeyboardInterrupt("verifier-interrupt-after-first-public-write")

    caught = None
    w._replace_exact = interrupting_replace
    try:
        w.prepare_rotation(
            rt, st, priv, boot, services, rs, ts, cs, certificate_domain, bs,
            keyring, successor, target,
        )
    except BaseException as exc:  # deliberately includes KeyboardInterrupt/SystemExit class
        caught = f"{type(exc).__name__}:{exc}"
    finally:
        w._replace_exact = original_replace

    transition_changed = ts != before_ts
    retained_unchanged = st == before_st
    binding_unchanged = bs == before_bs
    private_unchanged = priv == before_priv

    status = w.commit_status_state(st, boot, rt, rs, bs, ts, keyring)
    authority = w.authority(
        rt, st, boot, services, rs, ts, cs, certificate_domain, bs, keyring
    )

    retry = None
    retry_error = None
    try:
        retry = w.prepare_rotation(
            rt, st, priv, boot, services, rs, ts, cs, certificate_domain, bs,
            keyring, successor, target,
        )
    except BaseException as exc:
        retry_error = f"{type(exc).__name__}:{exc}"

    counterexample = (
        caught == "KeyboardInterrupt:verifier-interrupt-after-first-public-write"
        and transition_changed
        and retained_unchanged
        and binding_unchanged
        and private_unchanged
    )

    return {
        "verdict": (
            "FAIL_KEYBOARDINTERRUPT_BYPASSES_WAVE121_PUBLICATION_ROLLBACK"
            if counterexample else "COUNTEREXAMPLE_NOT_REPRODUCED"
        ),
        "counterexample_reproduced": counterexample,
        "caught": caught,
        "replace_calls_before_interrupt": replace_calls,
        "transition_store_changed": transition_changed,
        "retained_state_unchanged": retained_unchanged,
        "binding_store_unchanged": binding_unchanged,
        "private_signer_state_unchanged": private_unchanged,
        "commit_status_after_interrupt": status,
        "authority_after_interrupt": authority,
        "retry_is_tuple": isinstance(retry, tuple),
        "retry_error": retry_error,
        "stale_authority_accepted": authority.startswith("AUTHORITATIVE"),
        "note": (
            "This is a same-process termination-exception counterexample. It does not model a hard "
            "process kill or power loss and does not forge a hash, credential, or transition."
        ),
    }


def main() -> None:
    builder = t121.run()
    attack = keyboard_interrupt_after_first_public_write()
    report = {
        "schema": "axm.flowing-compute.independent-verifier.wave121-baseexception/v1",
        "builder_wave121_unchanged": {
            "passed": builder.get("passed"),
            "failed": builder.get("failed"),
        },
        "attack": attack,
        "truth_boundary": {
            "builder_runtimeerror_fault_controls_survive": builder.get("failed") == 0,
            "keyboardinterrupt_is_same_process": True,
            "keyboardinterrupt_is_Exception_subclass": False,
            "keyboardinterrupt_is_BaseException_subclass": True,
            "hard_process_kill_or_power_loss_tested": False,
            "performance_or_energy_tested": False,
            "retained_incremental_dormant_compute_win_tested": False,
            "canon_or_merge": False,
        },
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    if builder.get("failed") != 0 or not attack["counterexample_reproduced"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
