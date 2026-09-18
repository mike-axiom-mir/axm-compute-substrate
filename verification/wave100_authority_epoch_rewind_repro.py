#!/usr/bin/env python3
"""Independent Wave 100 adversarial reproducer.

This imports the unchanged builder modules. It demonstrates that registry lineage can remain
perfectly monotonic while two retained remote histories move authority_epoch backward by
appending fresh records after a local rollback.
"""
from __future__ import annotations

import json
from copy import deepcopy

import AXM_FLOWING_COMPUTE_REMOTE_REGISTRY_MONOTONICITY as m
import AXM_FLOWING_COMPUTE_REMOTE_WITNESS_REGISTRY_QUORUM as q


def run() -> dict:
    st, priv, boot, rt, services, tokens, registry_store = q.fixture()
    transition_store = {}

    cp1, use1, link1, tr1 = m.advance_all(
        st, priv, boot, rt, services, tokens, registry_store, transition_store,
        "verifier-wave100-epoch-1",
    )
    local_epoch1 = {
        "st": deepcopy(st),
        "rt": deepcopy(rt),
        "checkpoint_sha": cp1["checkpoint_sha"],
        "authority_sha": link1["authority_sha"],
        "authority_epoch": link1["epoch"],
        "registry_sha": rt["remote_registry_sha"],
    }

    cp2, use2, link2, tr2 = m.advance_all(
        st, priv, boot, rt, services, tokens, registry_store, transition_store,
        "verifier-wave100-epoch-2",
    )
    authority_epoch2 = m.authority(rt, st, boot, services, registry_store)
    if not authority_epoch2.startswith("AUTHORITATIVE_QUORUM_3"):
        raise AssertionError(f"epoch-2 control was not authoritative: {authority_epoch2}")

    # Roll back only the local authority state. Keep every remote epoch-2 record physically present.
    rolled_st = deepcopy(local_epoch1["st"])
    rolled_rt = deepcopy(local_epoch1["rt"])
    remote_after_epoch2 = deepcopy(services)

    before_attack = m.authority(rolled_rt, rolled_st, boot, remote_after_epoch2, registry_store)
    if before_attack.startswith("AUTHORITATIVE"):
        raise AssertionError(f"untouched remotes should expose local rollback, got: {before_attack}")

    # The guarded Wave 100 publish path notices that the remote head is not this old link's predecessor.
    guarded_services = deepcopy(remote_after_epoch2)
    guarded_publish = m.publish(
        rolled_rt, rolled_st, boot, guarded_services, tokens, registry_store, "remote-a"
    )
    if guarded_publish != "REMOTE_PREDECESSOR_HOLD":
        raise AssertionError(f"expected guarded publish to reject rollback, got: {guarded_publish}")

    # But the unchanged Wave 99 raw append primitive is explicitly part of Wave 100's adversarial
    # surface: Wave 100 claims retained remote history is a second defense when that primitive is
    # called directly. Append fresh records to A and B that point back to epoch 1 while seq increases.
    attack_services = deepcopy(remote_after_epoch2)
    reg = q.get_registry(registry_store, rolled_rt["remote_registry_sha"])
    raw_results = {}
    for slot in ("remote-a", "remote-b"):
        raw_results[slot] = q.append_raw(
            attack_services[slot],
            slot,
            reg["slots"][slot],
            tokens[slot],
            local_epoch1["authority_epoch"],
            local_epoch1["authority_sha"],
            local_epoch1["checkpoint_sha"],
            local_epoch1["registry_sha"],
        )
        if raw_results[slot] != "APPENDED":
            raise AssertionError(f"raw append failed for {slot}: {raw_results[slot]}")

    # Prove the newer epoch-2 evidence was not deleted or head-rewound: A/B now have seq 1,2,3 and
    # seq 2 still names epoch 2, while seq 3 freshly names old epoch 1. C remains at epoch 2.
    histories = {}
    for slot in q.REMOTE_IDS:
        rows = sorted(attack_services[slot]["records"].values(), key=lambda r: r["seq"])
        histories[slot] = [
            {
                "seq": row["seq"],
                "authority_epoch": row["authority_epoch"],
                "authority_sha": row["authority_sha"],
                "registry_sha": row["registry_sha"],
            }
            for row in rows
        ]

    for slot in ("remote-a", "remote-b"):
        if [r["authority_epoch"] for r in histories[slot]][-2:] != [link2["epoch"], link1["epoch"]]:
            raise AssertionError(f"{slot} did not retain epoch 2 then append epoch 1: {histories[slot]}")
        if len({r["registry_sha"] for r in histories[slot]}) != 1:
            raise AssertionError("attack should not use registry rollback")

    # Wave 100's registry-history checker accepts both attacked histories because registry identity
    # never moved backward; the authority epoch itself is not checked for monotonicity.
    for slot in ("remote-a", "remote-b"):
        m.verify_remote_registry_history(attack_services[slot], registry_store)

    final_authority = m.authority(
        rolled_rt, rolled_st, boot, attack_services, registry_store
    )
    if not final_authority.startswith("AUTHORITATIVE_QUORUM_2"):
        raise AssertionError(f"expected reproduced false rollback authority, got: {final_authority}")

    return {
        "verdict": "FAIL_REMOTE_SEQUENCE_CAN_ADVANCE_WHILE_AUTHORITY_EPOCH_REWINDS",
        "builder_wave": 100,
        "builder_head_verified": "0fb2caa805cebf29185d0b40c9f1bbd46199263b",
        "ci_tested_source_commit_reported_by_builder": "c235f8f0682a98f9d5777df12ef97dce8ca0560d",
        "wave100_tool_blob": "9fc2dc55c2d3973010b1804ad766cc632b89fa1f",
        "wave100_selftest_blob": "12491f9996bd7bada33ea742dacbb186dfd037c8",
        "control_epoch2_authority": authority_epoch2,
        "control_rolled_local_with_untouched_remotes": before_attack,
        "control_guarded_publish": guarded_publish,
        "raw_append_results": raw_results,
        "final_authority": final_authority,
        "epoch1": link1["epoch"],
        "epoch2": link2["epoch"],
        "remote_histories": histories,
        "registry_generation": reg["generation"],
        "registry_sha": reg["registry_sha"],
        "notes": [
            "No remote record was deleted.",
            "No remote head was manually rewound.",
            "No registry generation or registry SHA was rewound.",
            "Remote A/B sequence numbers move forward while authority_epoch moves backward from 2 to 1.",
            "Remote C remains on the newer epoch-2 record.",
            "Wave 100 still returns modeled 2-of-3 authority for the rolled-back local epoch.",
        ],
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
