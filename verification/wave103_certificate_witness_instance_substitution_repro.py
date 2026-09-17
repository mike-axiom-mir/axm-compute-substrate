#!/usr/bin/env python3
"""Independent adversarial repro for Wave 103 certificate-witness instance substitution.

This imports the unchanged Wave 103 implementation.  It first proves the intended protection:
with one current certificate witness online, one current certificate witness unavailable, and one
legitimate laggard, a stale local/certificate/remote world is blocked because the online current
witness remembers the newer accepted certificate.

It then changes only the caller-supplied mapping for that still-online current witness so the same
slot name points at a legitimate stale same-ID snapshot.  The real newer witness object remains
online and unmodified.  Wave 103 accepts the substitute as the fixed witness identity and the stale
world becomes authoritative.
"""
from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import AXM_FLOWING_COMPUTE_CERTIFICATE_MAXIMUM_WITNESS as w  # noqa: E402
import AXM_FLOWING_COMPUTE_QUORUM_GLOBAL_MAXIMUM as g  # noqa: E402
import AXM_FLOWING_COMPUTE_REMOTE_WITNESS_REGISTRY_QUORUM as q  # noqa: E402

BUILDER_HEAD = "8239c401a9d7ca1a330f76a7f537437fd141bbc6"
TOOL_BLOB = "0a5d6f09189719d705808fe1746c2f032688fd01"


def remote_epochs(service: dict) -> list[int]:
    return [
        row["authority_epoch"]
        for row in sorted(service["records"].values(), key=lambda row: row["seq"])
    ]


def witness_sequences(service: dict) -> list[int]:
    return [
        row["certificate_seq"]
        for row in sorted(service["records"].values(), key=lambda row: row["seq"])
    ]


def must_authoritative(verdict: str) -> None:
    if not verdict.startswith("AUTHORITATIVE"):
        raise AssertionError(f"expected authoritative verdict, got {verdict}")


def run() -> dict:
    st, priv, boot, rt, services, tokens, registry_store = q.fixture()
    transition_store: dict = {}
    certificate_store = g.new_certificate_store()
    witnesses = w.new_certificate_witnesses()

    # Epoch 1: fully legitimate state, including all three Wave 103 certificate witnesses.
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
        "verifier-wave103-epoch1",
    )
    sync1 = w.sync_witnesses(certificate_store, witnesses, registry_store)
    if any(result != "WITNESS_SYNCED_1" for result in sync1.values()):
        raise AssertionError(f"epoch1 witness sync failed: {sync1}")
    must_authoritative(
        w.authority(rt, st, boot, services, registry_store, certificate_store, witnesses)
    )

    rt_epoch1 = deepcopy(rt)
    certificate_store_epoch1 = deepcopy(certificate_store)
    witnesses_epoch1 = deepcopy(witnesses)
    remote_b_epoch1 = deepcopy(services["remote-b"])

    # Epoch 2: make the new authority genuinely quorum-authoritative on remote A+B, and replicate
    # the new quorum certificate to cert-a + cert-b.  cert-c is intentionally a legitimate laggard.
    app2 = hashlib.sha256(b"verifier-wave103-epoch2").hexdigest()
    cp2, _use2, link2, transition2 = w.prepare(
        rt,
        st,
        priv,
        boot,
        services,
        registry_store,
        transition_store,
        certificate_store,
        witnesses,
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
    if w.sync_witness(certificate_store, witnesses, registry_store, "cert-a") != "WITNESS_SYNCED_1":
        raise AssertionError("epoch2 cert-a sync failed")
    if w.sync_witness(certificate_store, witnesses, registry_store, "cert-b") != "WITNESS_SYNCED_1":
        raise AssertionError("epoch2 cert-b sync failed")

    current_verdict = w.authority(
        rt, st, boot, services, registry_store, certificate_store, witnesses
    )
    must_authoritative(current_verdict)
    if witness_sequences(witnesses["cert-a"]) != [1, 2]:
        raise AssertionError("cert-a did not retain epoch2 certificate")
    if witness_sequences(witnesses["cert-b"]) != [1, 2]:
        raise AssertionError("cert-b did not retain epoch2 certificate")
    if witness_sequences(witnesses["cert-c"]) != [1]:
        raise AssertionError("cert-c is not the intended laggard")

    # Build the same stale local/remote/certificate world Wave 103 is meant to reject.  Remote A
    # stays at epoch 2; B is restored to epoch 1; C legitimately never left epoch 1.  The certificate
    # store is the legitimate epoch-1 snapshot.  No certificate-witness record is altered here.
    attacked_services = deepcopy(services)
    attacked_services["remote-b"] = deepcopy(remote_b_epoch1)

    # Simulate one actual certificate-witness outage.  cert-a remains the one live newer witness.
    witnesses["cert-b"]["online"] = False

    real_cert_a_head = w.verify_certificate_witness(
        witnesses["cert-a"], "cert-a", registry_store
    )
    if real_cert_a_head is None or real_cert_a_head["certificate_seq"] != 2:
        raise AssertionError("real cert-a newer witness missing")
    if not witnesses["cert-a"].get("online"):
        raise AssertionError("real cert-a must remain online")

    honest_verdict = w.authority(
        rt_epoch1,
        st,
        boot,
        attacked_services,
        registry_store,
        certificate_store_epoch1,
        witnesses,
    )
    if honest_verdict != "HOLD_CERTIFICATE_WITNESS_MAXIMUM_AHEAD":
        raise AssertionError(f"Wave 103 control did not block stale world: {honest_verdict}")

    # The adversarial step: do NOT truncate, mutate, or offline the real cert-a.  Only replace the
    # caller's map entry with a legitimate stale same-ID cert-a instance captured at epoch 1.
    substituted_witnesses = dict(witnesses)
    substituted_witnesses["cert-a"] = deepcopy(witnesses_epoch1["cert-a"])

    substituted_head = w.verify_certificate_witness(
        substituted_witnesses["cert-a"], "cert-a", registry_store
    )
    if substituted_head is None or substituted_head["certificate_seq"] != 1:
        raise AssertionError("stale same-ID substitute was not accepted as a valid cert-a ledger")

    attacked_verdict = w.authority(
        rt_epoch1,
        st,
        boot,
        attacked_services,
        registry_store,
        certificate_store_epoch1,
        substituted_witnesses,
    )

    # Prove the original newer witness still exists, is online, and still retains certificate 2.
    real_cert_a_after = w.verify_certificate_witness(
        witnesses["cert-a"], "cert-a", registry_store
    )
    if real_cert_a_after is None or real_cert_a_after["certificate_seq"] != 2:
        raise AssertionError("real cert-a was modified by the attack")
    if not witnesses["cert-a"].get("online"):
        raise AssertionError("real cert-a was made unavailable by the attack")

    if not attacked_verdict.startswith("AUTHORITATIVE_QUORUM_2_OF_3_MODELED"):
        raise AssertionError(
            "expected stale authority after same-ID witness substitution, got " + attacked_verdict
        )

    return {
        "schema": "axm.verifier.wave103.certificate-witness-instance-substitution/v1",
        "builder_head": BUILDER_HEAD,
        "wave103_tool_blob": TOOL_BLOB,
        "control_current_epoch2": current_verdict,
        "control_stale_with_real_newer_witness": honest_verdict,
        "attacked_stale_with_same_id_substitute": attacked_verdict,
        "remote_epochs_after_attack": {
            slot: remote_epochs(attacked_services[slot]) for slot in q.REMOTE_IDS
        },
        "certificate_store_epoch_after_attack": g.verify_certificate_store(
            certificate_store_epoch1, registry_store
        )["authority_epoch"],
        "real_cert_a": {
            "online": witnesses["cert-a"]["online"],
            "certificate_sequences": witness_sequences(witnesses["cert-a"]),
        },
        "supplied_cert_a_substitute": {
            "online": substituted_witnesses["cert-a"]["online"],
            "certificate_sequences": witness_sequences(substituted_witnesses["cert-a"]),
            "witness_id": substituted_witnesses["cert-a"]["witness_id"],
        },
        "cert_b": {
            "online": witnesses["cert-b"]["online"],
            "certificate_sequences_retained": witness_sequences(witnesses["cert-b"]),
        },
        "cert_c": {
            "online": witnesses["cert-c"]["online"],
            "certificate_sequences": witness_sequences(witnesses["cert-c"]),
        },
        "verdict": "FAIL_FIXED_CERTIFICATE_WITNESS_IDENTITY_IS_CALLER_SUBSTITUTABLE",
        "note": (
            "The real cert-a remains online and retains certificate 2. Authority accepts a stale "
            "same-ID cert-a snapshot supplied in its place because the fixed witness slot is not "
            "bound to a durable instance identity/credential/registry entry."
        ),
    }


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2, sort_keys=True))
