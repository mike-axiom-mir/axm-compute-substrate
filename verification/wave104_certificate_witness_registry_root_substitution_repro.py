#!/usr/bin/env python3
"""Independent adversarial repro for Wave 104 certificate-witness registry-root substitution.

This imports the unchanged Wave 104 implementation from the exact builder head. It proves the
intended repair first: the original credential-bound certificate-witness domain retains certificate
2 and blocks a stale local/certificate/remote world.

It then changes no record, credential, or endpoint inside that original domain. Instead it supplies a
fresh, internally valid Wave 104 generation-0 witness domain, syncs that fresh domain only to the
legitimate stale certificate-1 store, and asks the unchanged authority API to verify the same stale
world. Because Wave 104 does not bind one exact witness-registry SHA into durable authority state,
certificate state, or an external trust anchor, the fresh registry can become the caller-selected
root and the stale world becomes authoritative while the original newer registered domain remains
online and intact.
"""
from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w  # noqa: E402
import AXM_FLOWING_COMPUTE_QUORUM_GLOBAL_MAXIMUM as g  # noqa: E402
import AXM_FLOWING_COMPUTE_REMOTE_WITNESS_REGISTRY_QUORUM as q  # noqa: E402

BUILDER_HEAD = "b0826840723b4d510f396c91e8f0c5de46a05a43"
TESTED_SOURCE_HEAD = "b33c8e0ae155d8e785b25ab608bdf8a3dbb14e65"
TOOL_BLOB = "64aef8c32e246f396ca8dc67dbf3b0460b077f77"
SELFTEST_BLOB = "c2ca76079adfbe9f44fd11c97689be61027a7760"


def endpoint_sequences(endpoint, registry_store: dict) -> list[int]:
    head = w.verify_endpoint_ledger(endpoint, registry_store)
    if head is None:
        return []
    return sorted(rec["certificate_seq"] for rec in endpoint.records.values())


def remote_epochs(service: dict) -> list[int]:
    return [
        rec["authority_epoch"]
        for rec in sorted(service["records"].values(), key=lambda row: row["seq"])
    ]


def must_authoritative(verdict: str) -> None:
    if not verdict.startswith("AUTHORITATIVE"):
        raise AssertionError(f"expected authoritative verdict, got {verdict}")


def run() -> dict:
    st, priv, boot, rt, services, tokens, registry_store = q.fixture()
    transition_store: dict = {}
    certificate_store = g.new_certificate_store()
    original_domain = w.new_certificate_witness_domain()

    # Epoch 1: fully legitimate state and fully synced original Wave 104 witness domain.
    g.advance_all(
        st,
        priv,
        boot,
        rt,
        services,
        tokens,
        registry_store,
        transition_store,
        certificate_store,
        "verifier-wave104-epoch1",
    )
    sync1 = w.sync_endpoints(certificate_store, original_domain, registry_store)
    if any(result != "WITNESS_SYNCED_1" for result in sync1.values()):
        raise AssertionError(f"epoch1 witness sync failed: {sync1}")
    must_authoritative(
        w.authority(rt, st, boot, services, registry_store, certificate_store, original_domain)
    )

    rt_epoch1 = deepcopy(rt)
    certificate_store_epoch1 = deepcopy(certificate_store)
    remote_b_epoch1 = deepcopy(services["remote-b"])

    # Epoch 2: make the newer state genuinely quorum-authoritative on remote A+B, then replicate its
    # quorum certificate to original cert-a + cert-b while original cert-c legitimately lags.
    app2 = hashlib.sha256(b"verifier-wave104-epoch2").hexdigest()
    _cp2, _use2, link2, transition2 = w.prepare(
        rt,
        st,
        priv,
        boot,
        services,
        registry_store,
        transition_store,
        certificate_store,
        original_domain,
        app2,
    )
    if g.commit(
        rt,
        st,
        boot,
        registry_store,
        transition_store,
        link2["authority_sha"],
        transition2,
    ) != "COMMITTED":
        raise AssertionError("epoch2 local commit failed")
    if g.publish(rt, st, boot, services, tokens, registry_store, "remote-a") != "APPENDED":
        raise AssertionError("epoch2 remote-a publish failed")
    if g.publish(rt, st, boot, services, tokens, registry_store, "remote-b") != "APPENDED":
        raise AssertionError("epoch2 remote-b publish failed")
    if g.certify_current_quorum(
        rt, st, boot, services, registry_store, certificate_store
    ) != "CERTIFIED":
        raise AssertionError("epoch2 quorum certification failed")
    if w.sync_endpoint(certificate_store, original_domain, registry_store, "cert-a") != "WITNESS_SYNCED_1":
        raise AssertionError("epoch2 original cert-a sync failed")
    if w.sync_endpoint(certificate_store, original_domain, registry_store, "cert-b") != "WITNESS_SYNCED_1":
        raise AssertionError("epoch2 original cert-b sync failed")

    current_verdict = w.authority(
        rt, st, boot, services, registry_store, certificate_store, original_domain
    )
    must_authoritative(current_verdict)
    if endpoint_sequences(original_domain._endpoints["cert-a"], registry_store) != [1, 2]:
        raise AssertionError("original cert-a did not retain certificate 2")
    if endpoint_sequences(original_domain._endpoints["cert-b"], registry_store) != [1, 2]:
        raise AssertionError("original cert-b did not retain certificate 2")
    if endpoint_sequences(original_domain._endpoints["cert-c"], registry_store) != [1]:
        raise AssertionError("original cert-c is not the intended laggard")

    # Recreate the stale lower-quorum world without touching the original certificate-witness domain:
    # local pointer + certificate store are epoch 1; remote A remains at epoch 2; remote B is restored
    # to its legitimate epoch-1 snapshot; remote C legitimately never left epoch 1.
    attacked_services = deepcopy(services)
    attacked_services["remote-b"] = deepcopy(remote_b_epoch1)

    honest_verdict = w.authority(
        rt_epoch1,
        st,
        boot,
        attacked_services,
        registry_store,
        certificate_store_epoch1,
        original_domain,
    )
    if honest_verdict != "HOLD_CERTIFICATE_WITNESS_MAXIMUM_AHEAD":
        raise AssertionError(
            "original registered domain should remember certificate 2 and block the stale world; got "
            + honest_verdict
        )

    # Adversarial step: create a second valid generation-0 Wave 104 witness registry/domain with
    # fresh identities and credentials. Nothing inside original_domain is changed or made unavailable.
    replacement_domain = w.new_certificate_witness_domain()
    if replacement_domain.registry_sha == original_domain.registry_sha:
        raise AssertionError("fresh witness registry unexpectedly reused original registry SHA")
    replacement_sync = w.sync_endpoints(
        certificate_store_epoch1, replacement_domain, registry_store
    )
    if any(result != "WITNESS_SYNCED_1" for result in replacement_sync.values()):
        raise AssertionError(f"replacement domain stale sync failed: {replacement_sync}")

    attacked_verdict = w.authority(
        rt_epoch1,
        st,
        boot,
        attacked_services,
        registry_store,
        certificate_store_epoch1,
        replacement_domain,
    )

    # Prove the original newer registered domain still exists online and still retains certificate 2.
    for slot in w.WITNESS_IDS:
        if not original_domain._endpoints[slot].online:
            raise AssertionError(f"original endpoint {slot} was made unavailable")
    if endpoint_sequences(original_domain._endpoints["cert-a"], registry_store) != [1, 2]:
        raise AssertionError("original cert-a was modified by registry substitution")
    if endpoint_sequences(original_domain._endpoints["cert-b"], registry_store) != [1, 2]:
        raise AssertionError("original cert-b was modified by registry substitution")

    if not attacked_verdict.startswith("AUTHORITATIVE_QUORUM_2_OF_3_MODELED"):
        raise AssertionError(
            "expected stale authority after replacing the caller-selected witness registry root, got "
            + attacked_verdict
        )

    return {
        "schema": "axm.verifier.wave104.certificate-witness-registry-root-substitution/v1",
        "builder_head": BUILDER_HEAD,
        "tested_source_head": TESTED_SOURCE_HEAD,
        "wave104_tool_blob": TOOL_BLOB,
        "wave104_selftest_blob": SELFTEST_BLOB,
        "control_current_epoch2": current_verdict,
        "control_stale_with_original_registered_domain": honest_verdict,
        "attacked_stale_with_fresh_registry_root": attacked_verdict,
        "original_registry_sha": original_domain.registry_sha,
        "replacement_registry_sha": replacement_domain.registry_sha,
        "registry_root_changed": replacement_domain.registry_sha != original_domain.registry_sha,
        "original_domain_after_attack": {
            slot: {
                "online": original_domain._endpoints[slot].online,
                "certificate_sequences": endpoint_sequences(
                    original_domain._endpoints[slot], registry_store
                ),
            }
            for slot in w.WITNESS_IDS
        },
        "replacement_domain": {
            slot: {
                "online": replacement_domain._endpoints[slot].online,
                "certificate_sequences": endpoint_sequences(
                    replacement_domain._endpoints[slot], registry_store
                ),
            }
            for slot in w.WITNESS_IDS
        },
        "remote_epochs_after_attack": {
            slot: remote_epochs(attacked_services[slot]) for slot in q.REMOTE_IDS
        },
        "verdict": "FAIL_CERTIFICATE_WITNESS_REGISTRY_ROOT_IS_CALLER_SUBSTITUTABLE",
        "note": (
            "Wave 104 validates integrity, endpoint identity, and credential possession inside the "
            "supplied CertificateWitnessDomain, but authority does not bind one exact witness-registry "
            "SHA as the durable trusted root. A fresh internally valid registry/domain can therefore "
            "be supplied for the stale world while the original newer registered domain remains online."
        ),
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
