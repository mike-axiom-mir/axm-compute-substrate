#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import AXM_FLOWING_COMPUTE_QUORUM_GLOBAL_MAXIMUM as g
import AXM_FLOWING_COMPUTE_REMOTE_WITNESS_REGISTRY_QUORUM as q


def epochs(service: dict) -> list[int]:
    return [r["authority_epoch"] for r in sorted(service["records"].values(), key=lambda x: x["seq"])]


def main() -> int:
    st, priv, boot, rt, services, tokens, registry_store = q.fixture()
    transition_store = {}
    certificate_store = g.new_certificate_store()

    # Establish epoch 1 normally and keep only the specific old pieces later needed for the attack.
    cp1, use1, link1, tr1 = g.advance_all(
        st, priv, boot, rt, services, tokens, registry_store, transition_store,
        certificate_store, "verifier-wave102-epoch1",
    )
    rt_epoch1 = deepcopy(rt)
    remote_b_epoch1 = deepcopy(services["remote-b"])
    cert1_sha = certificate_store["head"]

    # Advance epoch 2 normally, but only publish to A+B. This is enough for a real 2-of-3
    # authoritative quorum and an explicit Wave 102 certificate; C remains a legitimate laggard.
    app2 = hashlib.sha256(b"verifier-wave102-epoch2").hexdigest()
    cp2, use2, link2, tr2 = g.prepare(
        rt, st, priv, boot, services, registry_store, transition_store,
        certificate_store, app2,
    )
    commit2 = g.commit(rt, st, boot, registry_store, transition_store, link2["authority_sha"], tr2)
    pub_a = g.publish(rt, st, boot, services, tokens, registry_store, "remote-a")
    pub_b = g.publish(rt, st, boot, services, tokens, registry_store, "remote-b")
    cert2 = g.certify_current_quorum(rt, st, boot, services, registry_store, certificate_store)
    authority2 = g.authority(rt, st, boot, services, registry_store, certificate_store)
    cert2_sha = certificate_store["head"]

    # Narrow rollback: preserve newer local content-addressed bodies and intact remote A [1,2].
    # Only (1) restore the mutable local current pointer to epoch 1, (2) restore remote B's store
    # to its old epoch-1 snapshot, and (3) truncate exactly the newest certificate record and
    # point the certificate head back to the still-retained cert1. Remote C was never changed.
    attacked_services = deepcopy(services)
    attacked_services["remote-b"] = deepcopy(remote_b_epoch1)

    attacked_certificate_store = deepcopy(certificate_store)
    del attacked_certificate_store["records"][cert2_sha]
    attacked_certificate_store["head"] = cert1_sha

    verifier_store_head = g.verify_certificate_store(attacked_certificate_store, registry_store)
    attacked_authority = g.authority(
        rt_epoch1, st, boot, attacked_services, registry_store, attacked_certificate_store
    )

    newer_local_bodies_retained = (
        link2["authority_sha"] in st["L"] and cp2["checkpoint_sha"] in st["C"]
    )
    intact_a_keeps_epoch2 = epochs(attacked_services["remote-a"]) == [1, 2]
    lagging_c_stays_epoch1 = epochs(attacked_services["remote-c"]) == [1]
    only_b_is_restored = epochs(attacked_services["remote-b"]) == [1]
    cert_store_was_only_tail_truncated = (
        verifier_store_head is not None
        and verifier_store_head["authority_epoch"] == 1
        and cert1_sha in attacked_certificate_store["records"]
        and cert2_sha not in attacked_certificate_store["records"]
    )

    reproduced = (
        commit2 == "COMMITTED"
        and pub_a == "APPENDED"
        and pub_b == "APPENDED"
        and cert2 == "CERTIFIED"
        and authority2.startswith("AUTHORITATIVE_QUORUM_2")
        and newer_local_bodies_retained
        and intact_a_keeps_epoch2
        and lagging_c_stays_epoch1
        and only_b_is_restored
        and cert_store_was_only_tail_truncated
        and attacked_authority.startswith("AUTHORITATIVE_QUORUM_2")
    )

    report = {
        "schema": "axm.verifier.wave102.certificate-truncation/v1",
        "builder_head": "46fafcb3b13e5663337c01e185a8972ebc52dda5",
        "builder_tool_blob": "8bd23cf3db02ba90161f4a7c38f36dca3f3b2733",
        "builder_selftest_blob": "cc53bd23732acc31e8b85f0998187fba979c8a89",
        "epoch2_commit": commit2,
        "epoch2_publish_a": pub_a,
        "epoch2_publish_b": pub_b,
        "epoch2_certificate": cert2,
        "epoch2_authority": authority2,
        "remote_a_epochs_after_attack": epochs(attacked_services["remote-a"]),
        "remote_b_epochs_after_attack": epochs(attacked_services["remote-b"]),
        "remote_c_epochs_after_attack": epochs(attacked_services["remote-c"]),
        "newer_local_authority_body_retained": link2["authority_sha"] in st["L"],
        "newer_local_checkpoint_body_retained": cp2["checkpoint_sha"] in st["C"],
        "cert1_retained": cert1_sha in attacked_certificate_store["records"],
        "cert2_tail_deleted": cert2_sha not in attacked_certificate_store["records"],
        "attacked_certificate_max_epoch": verifier_store_head["authority_epoch"] if verifier_store_head else None,
        "attacked_authority": attacked_authority,
        "verdict": (
            "FAIL_GLOBAL_MAXIMUM_CAN_BE_REWOUND_BY_CERTIFICATE_TAIL_TRUNCATION_PLUS_ONE_STALE_WITNESS"
            if reproduced else
            "NOT_REPRODUCED"
        ),
        "scope": (
            "This is narrower than restoring the whole modeled world: remote A remains intact at epoch 2, "
            "remote C is only naturally lagging at epoch 1, and newer local content-addressed authority/checkpoint "
            "bodies remain present. The attack changes the mutable local pointer, restores only remote B to epoch 1, "
            "and truncates only the newest quorum-certificate record/head."
        ),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if reproduced else 1


if __name__ == "__main__":
    raise SystemExit(main())
