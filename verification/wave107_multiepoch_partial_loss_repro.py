#!/usr/bin/env python3
"""Independent Wave 107 adversarial reproducer.

This does not modify builder state or CANON. It checks whether the Wave 107 tri-state
bootstrap-history guard treats loss of one retained authority-link body consistently
once more than one accepted authority epoch is retained.
"""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import AXM_FLOWING_COMPUTE_BOOTSTRAP_PARTIAL_EVIDENCE_GUARD as w  # noqa: E402
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w104  # noqa: E402


g = w.g
q = w.q


def new_world():
    st, priv, boot, rt, services, tokens, rs = q.fixture()
    ts = {}
    cs = g.new_certificate_store()
    domain = w104.new_certificate_witness_domain()
    bs = {}
    w.adopt_genesis(rt, st, boot, services, rs, cs, domain, bs)
    return st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs


def run() -> dict:
    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world()

    w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs,
        domain, bs, "verifier-wave107-epoch1"
    )
    status1, link1, cp1 = q.current_local(rt, st, boot)
    if status1 != "LOCAL_OK" or link1.get("epoch") != 1:
        raise RuntimeError(f"unexpected epoch-1 state: {status1} {link1}")
    rt_epoch1 = deepcopy(rt)

    # Control: at retained depth 1, deleting the only authority-link body is detected.
    depth1 = deepcopy(st)
    depth1["L"].pop(link1["authority_sha"])
    depth1_guard = w.retained_authority_history_state(depth1, boot)

    # Advance the real world normally to a second accepted authority epoch.
    w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs,
        domain, bs, "verifier-wave107-epoch2"
    )
    status2, link2, cp2 = q.current_local(rt, st, boot)
    if status2 != "LOCAL_OK" or link2.get("epoch") != 2:
        raise RuntimeError(f"unexpected epoch-2 state: {status2} {link2}")

    link2_sha = link2["authority_sha"]
    cp2_sha = link2["checkpoint_sha"]
    use2_sha = link2["use_sha"]

    # Adversarial mutation: delete exactly one body -- the newest retained authority link.
    # Keep its signed checkpoint and signer-use evidence, the older valid link, the lineage
    # store, certificate store, witness domain, remotes, bindings and runtime untouched.
    attacked = deepcopy(st)
    removed = attacked["L"].pop(link2_sha)
    if removed.get("authority_sha") != link2_sha:
        raise RuntimeError("removed unexpected authority-link body")

    depth2_guard = w.retained_authority_history_state(attacked, boot)
    cp2_preserved = cp2_sha in attacked.get("C", {})
    use2_preserved = use2_sha in attacked.get("U", {})
    older_link_preserved = link1["authority_sha"] in attacked.get("L", {})

    # Check the full authority path too. The primary finding is guard misclassification;
    # if stale authority also becomes accepted, promote the severity automatically.
    current_runtime_verdict = w.authority(
        rt, attacked, boot, services, rs, cs, domain, bs
    )
    stale_runtime_verdict = w.authority(
        rt_epoch1, attacked, boot, services, rs, cs, domain, bs
    )

    depth1_detected = depth1_guard["status"] == w.HISTORY_INCOMPLETE
    depth2_misclassified = (
        depth2_guard["status"] == w.HISTORY_VALID
        and cp2_preserved
        and use2_preserved
        and older_link_preserved
        and link2_sha not in attacked["L"]
    )

    if not depth1_detected:
        raise RuntimeError(
            "control failed: Wave 107 did not detect sole-link loss at depth 1"
        )
    if not depth2_misclassified:
        raise RuntimeError(
            "counterexample did not reproduce: newest-link loss was not classified VALID"
        )

    if stale_runtime_verdict.startswith("AUTHORITATIVE"):
        verdict = "FAIL_MULTIEPOCH_LINK_LOSS_PERMITS_STALE_AUTHORITY"
    else:
        verdict = "FAIL_MULTIEPOCH_AUTHORITY_LINK_LOSS_CLASSIFIED_VALID"

    return {
        "schema": "axm.flowing_compute.verifier.wave107.multiepoch_partial_loss/v1",
        "verdict": verdict,
        "builder_head_tested": "22289521483fe8e171f6c9016f0bd0b10e54a235",
        "builder_tested_source_commit": "9e4edc8c484d32f9210804dc25ca61fadf7aa835",
        "builder_tool_blob": "7aeb0e6f6018d1708b5fe89a4fdbf8e024398deb",
        "builder_selftest_blob": "66d676685b23fd5cbcc5ac8f06a0ec5e383fd295",
        "mutation": {
            "deleted_only": f"L[{link2_sha}]",
            "deleted_epoch": link2.get("epoch"),
            "checkpoint_body_preserved": cp2_preserved,
            "signer_use_body_preserved": use2_preserved,
            "older_authority_link_preserved": older_link_preserved,
            "wave106_lineage_store_preserved": "W106_BOOTSTRAP_LINEAGE" in attacked,
            "certificate_store_preserved": True,
            "remote_services_preserved": True,
            "binding_store_preserved": True,
        },
        "control_depth1": {
            "mutation": "delete sole retained authority-link body",
            "guard_status": depth1_guard["status"],
            "guard_reason": depth1_guard["reason"],
        },
        "attack_depth2": {
            "mutation": "delete newest of two retained authority-link bodies",
            "guard_status": depth2_guard["status"],
            "guard_reason": depth2_guard["reason"],
            "remaining_link_keys": depth2_guard["link_keys"],
            "resolved_links": depth2_guard["resolved_links"],
            "checkpoint_count": depth2_guard["checkpoint_count"],
            "use_count": depth2_guard["use_count"],
            "deleted_link_checkpoint_sha": cp2_sha,
            "deleted_link_use_sha": use2_sha,
        },
        "full_authority_path": {
            "current_epoch2_runtime_verdict": current_runtime_verdict,
            "rolled_back_epoch1_runtime_verdict_with_newer_external_state_intact": stale_runtime_verdict,
        },
        "bounded_interpretation": [
            "This falsifies the broad Wave 107 claim that loss of one authority-link body is mechanically classified incomplete/corrupt at the bootstrap guard for retained histories in general.",
            "The exact PR #31 signer-use-loss repair still survives this reproducer.",
            "This reproducer does not delete the Wave-106 lineage store, certificate store, witness domain, remote services, bindings, signed checkpoint, or signer-use row for epoch 2.",
            "Unless the full_authority_path field is AUTHORITATIVE, this is a guard/history-completeness failure, not a demonstrated stale-authority acceptance.",
            "No performance, energy, retained/incremental/dormant-compute, process, device, or provider claim is made by this verifier.",
        ],
    }


def main() -> None:
    report = run()
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
