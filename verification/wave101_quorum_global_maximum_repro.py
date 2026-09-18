#!/usr/bin/env python3
"""Independent Wave 101 verifier: stale quorum can forget a previously authoritative newer epoch.

This imports the unchanged Wave 101 builder code. It does not patch builder behavior.
All checks are explicit rather than Python ``assert`` so ``python -O`` exercises the same path.
"""
from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import AXM_FLOWING_COMPUTE_REMOTE_AUTHORITY_MONOTONICITY as a
import AXM_FLOWING_COMPUTE_REMOTE_WITNESS_REGISTRY_QUORUM as q


def need(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def epochs(service: dict) -> list[int]:
    return [r["authority_epoch"] for r in sorted(service["records"].values(), key=lambda x: x["seq"])]


def main() -> None:
    st, priv, boot, rt, services, tokens, registry_store = q.fixture()
    transition_store = {}

    # Establish epoch 1 on all three witnesses.
    cp1, use1, link1, tr1 = a.advance_all(
        st, priv, boot, rt, services, tokens, registry_store, transition_store,
        "wave101-verifier-epoch-1",
    )
    rt_epoch1 = deepcopy(rt)
    remote_b_epoch1 = deepcopy(services["remote-b"])

    # Establish epoch 2 locally and on A+B only. This is already a valid 2-of-3
    # authoritative Wave 101 state; C intentionally remains at epoch 1.
    app2 = hashlib.sha256(b"wave101-verifier-epoch-2").hexdigest()
    cp2, use2, link2, tr2 = a.prepare(
        rt, st, priv, boot, services, registry_store, transition_store, app2
    )
    commit_result = a.commit(
        rt, st, boot, registry_store, transition_store,
        link2["authority_sha"], tr2,
    )
    need(commit_result == "COMMITTED", f"epoch2 local commit failed: {commit_result}")

    publish_a = a.publish(rt, st, boot, services, tokens, registry_store, "remote-a")
    publish_b = a.publish(rt, st, boot, services, tokens, registry_store, "remote-b")
    need(publish_a == "APPENDED", f"epoch2 publish A failed: {publish_a}")
    need(publish_b == "APPENDED", f"epoch2 publish B failed: {publish_b}")

    epoch2_verdict = a.authority(rt, st, boot, services, registry_store)
    need(epoch2_verdict.startswith("AUTHORITATIVE_QUORUM_2"), f"epoch2 not authoritative: {epoch2_verdict}")
    need(epochs(services["remote-a"]) == [1, 2], "remote A did not retain epochs 1,2")
    need(epochs(services["remote-b"]) == [1, 2], "remote B did not retain epochs 1,2")
    need(epochs(services["remote-c"]) == [1], "remote C was expected to remain at epoch 1")

    # Control: rewinding only the mutable local pointer/runtime to epoch 1 is caught
    # while A+B still retain epoch 2.
    local_rollback_control = a.authority(
        rt_epoch1, st, boot, services, registry_store
    )
    need(
        not local_rollback_control.startswith("AUTHORITATIVE"),
        f"local-pointer-only rollback unexpectedly authoritative: {local_rollback_control}",
    )

    # Attack: restore only remote B to its old epoch-1 store snapshot. A remains
    # intact at epoch 2, C was merely lagging at epoch 1, and the local content-addressed
    # store still contains epoch-2 bodies. No append, reseal, registry change, record
    # deletion on A, or whole-domain rollback is used.
    stale_services = deepcopy(services)
    stale_services["remote-b"] = deepcopy(remote_b_epoch1)

    attack_verdict = a.authority(
        rt_epoch1, st, boot, stale_services, registry_store
    )

    # The intact A witness still proves a newer authority epoch existed.
    need(epochs(stale_services["remote-a"]) == [1, 2], "intact remote A lost newer evidence")
    need(epochs(stale_services["remote-b"]) == [1], "remote B stale restore did not land at epoch 1")
    need(epochs(stale_services["remote-c"]) == [1], "remote C no longer represents the lagging witness")
    need(link2["authority_sha"] in st["L"], "newer local authority body unexpectedly missing")
    need(cp2["checkpoint_sha"] in st["C"], "newer local checkpoint body unexpectedly missing")

    result = {
        "schema": "axm.flowing_compute.wave101.independent-verifier/v1",
        "builder_head": "08bed3007e118fdcc2499c873da85ed9355c96d2",
        "wave101_source_blob": "9283b748aefcc1914eb763748674ee83a5ec3b15",
        "epoch2_was_authoritative": epoch2_verdict,
        "local_pointer_only_rollback_control": local_rollback_control,
        "attack": {
            "local_runtime_restored_to_epoch": link1["epoch"],
            "remote_a_epochs_intact": epochs(stale_services["remote-a"]),
            "remote_b_epochs_after_stale_restore": epochs(stale_services["remote-b"]),
            "remote_c_epochs_lagging": epochs(stale_services["remote-c"]),
            "newer_local_authority_body_still_present": link2["authority_sha"] in st["L"],
            "newer_local_checkpoint_body_still_present": cp2["checkpoint_sha"] in st["C"],
            "wave101_verdict": attack_verdict,
        },
        "verdict": (
            "FAIL_PREVIOUSLY_AUTHORITATIVE_NEWER_EPOCH_CAN_BE_FORGOTTEN_BY_"
            "ONE_STALE_REMOTE_PLUS_ONE_LAGGING_REMOTE"
        ),
    }
    print(json.dumps(result, indent=2, sort_keys=True))

    need(
        attack_verdict.startswith("AUTHORITATIVE_QUORUM_2"),
        f"counterexample did not reproduce: {attack_verdict}",
    )


if __name__ == "__main__":
    main()
