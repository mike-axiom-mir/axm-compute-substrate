#!/usr/bin/env python3
"""Wave 104 adversarial/self-test for credential-bound certificate-witness identity."""
from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy

import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w
import AXM_FLOWING_COMPUTE_CERTIFICATE_MAXIMUM_WITNESS as w103
import AXM_FLOWING_COMPUTE_QUORUM_GLOBAL_MAXIMUM as g
import AXM_FLOWING_COMPUTE_REMOTE_WITNESS_REGISTRY_QUORUM as q


def remote_epochs(service: dict) -> list[int]:
    return [r["authority_epoch"] for r in sorted(service["records"].values(), key=lambda x: x["seq"])]


def endpoint_seqs(endpoint, rs) -> list[int]:
    head = w.verify_endpoint_ledger(endpoint, rs)
    if head is None:
        return []
    return sorted(r["certificate_seq"] for r in endpoint.records.values())


def run() -> dict:
    controls = []
    add = lambda name, value: controls.append({"name": name, "pass": bool(value)})

    add("exact_sources",
        w.SRC["wave103_builder_head"] == "8239c401a9d7ca1a330f76a7f537437fd141bbc6"
        and w.SRC["wave103_tool_blob"] == "0a5d6f09189719d705808fe1746c2f032688fd01"
        and w.SRC["wave103_selftest_blob"] == "6bf8df3d03dd189cfe700ac0f8fbf862593dd7c9"
        and w.SRC["verifier_pr"] == 28
        and w.SRC["verifier_head"] == "2384c08109e0c1414921029e7f4f29577838a0da"
        and w.SRC["verifier_evidence_blob"] == "5b75cf95aa2203e9a5c57f529fdfcad00fa96aea"
        and w.SRC["verifier_repro_blob"] == "9031bcfaf13afaee4628db0c8d486d066c6efd04")

    st, priv, boot, rt, services, tokens, rs = q.fixture()
    ts = {}
    cs = g.new_certificate_store()
    domain = w.new_certificate_witness_domain()
    legacy = w103.new_certificate_witnesses()

    reg = w.verify_registry(domain.registry)
    add("registry_content_addressed", reg["registry_sha"] == domain.registry_sha)
    add("registry_exact_membership", set(reg["entries"]) == set(w.WITNESS_IDS))
    add("registry_distinct_instances", len({reg["entries"][s]["instance_id"] for s in w.WITNESS_IDS}) == 3)
    add("registry_distinct_credentials", len({reg["entries"][s]["credential_id"] for s in w.WITNESS_IDS}) == 3)
    add("registry_distinct_modeled_domains", len({reg["entries"][s]["failure_domain_id"] for s in w.WITNESS_IDS}) == 3)
    add("genesis_authority", w.authority(rt, st, boot, services, rs, cs, domain) == "AUTHORITATIVE_GENESIS_MODELED")

    # Epoch 1: accepted by the lower quorum contract, then copied to both Wave 103 and Wave 104 witnesses.
    g.advance_all(st, priv, boot, rt, services, tokens, rs, ts, cs, "wave104-epoch1")
    sync1 = w.sync_endpoints(cs, domain, rs)
    legacy_sync1 = w103.sync_witnesses(cs, legacy, rs)
    add("epoch1_registered_endpoints_synced", all(v == "WITNESS_SYNCED_1" for v in sync1.values()))
    add("epoch1_legacy_witnesses_synced", all(v == "WITNESS_SYNCED_1" for v in legacy_sync1.values()))
    add("epoch1_authoritative", w.authority(rt, st, boot, services, rs, cs, domain).startswith("AUTHORITATIVE"))

    rt1 = deepcopy(rt)
    st1 = deepcopy(st)
    services1 = deepcopy(services)
    cs1 = deepcopy(cs)
    remote_b1 = deepcopy(services["remote-b"])
    disk1 = domain.disk_snapshots()
    legacy1 = deepcopy(legacy)

    # Epoch 2: accepted on remote A+B. cert-c deliberately remains at certificate 1.
    app2 = hashlib.sha256(b"wave104-epoch2").hexdigest()
    cp2, _use2, link2, tr2 = w.prepare(rt, st, priv, boot, services, rs, ts, cs, domain, app2)
    add("epoch2_local_commit", g.commit(rt, st, boot, rs, ts, link2["authority_sha"], tr2) == "COMMITTED")
    add("epoch2_publish_a", g.publish(rt, st, boot, services, tokens, rs, "remote-a") == "APPENDED")
    add("epoch2_publish_b", g.publish(rt, st, boot, services, tokens, rs, "remote-b") == "APPENDED")
    add("epoch2_remote_c_lags", remote_epochs(services["remote-c"]) == [1])
    add("epoch2_certificate", g.certify_current_quorum(rt, st, boot, services, rs, cs) == "CERTIFIED")
    add("epoch2_sync_cert_a", w.sync_endpoint(cs, domain, rs, "cert-a") == "WITNESS_SYNCED_1")
    add("epoch2_sync_cert_b", w.sync_endpoint(cs, domain, rs, "cert-b") == "WITNESS_SYNCED_1")
    add("epoch2_sync_legacy_a", w103.sync_witness(cs, legacy, rs, "cert-a") == "WITNESS_SYNCED_1")
    add("epoch2_sync_legacy_b", w103.sync_witness(cs, legacy, rs, "cert-b") == "WITNESS_SYNCED_1")
    add("epoch2_cert_c_still_lags", endpoint_seqs(domain._endpoints["cert-c"], rs) == [1])
    add("epoch2_two_of_three_authority", w.authority(rt, st, boot, services, rs, cs, domain).startswith("AUTHORITATIVE_QUORUM_2"))
    disk2 = domain.disk_snapshots()

    # Exact PR #28 stale-world shape: local/certificate + remote B restored; remote A retains epoch 2;
    # cert-b unavailable; real cert-a remains online/current; cert-c is the legitimate laggard.
    attacked_services = deepcopy(services)
    attacked_services["remote-b"] = deepcopy(remote_b1)
    domain._endpoints["cert-b"].online = False
    honest = w.authority(rt1, st, boot, attacked_services, rs, cs1, domain)
    add("real_newer_cert_a_still_online", domain._endpoints["cert-a"].online)
    add("real_newer_cert_a_retains_two", endpoint_seqs(domain._endpoints["cert-a"], rs) == [1, 2])
    add("honest_registered_endpoint_blocks_stale_world", honest == "HOLD_CERTIFICATE_WITNESS_MAXIMUM_AHEAD")

    # Reproduce the independent verifier failure on unchanged Wave 103.
    attacked_legacy = dict(legacy)
    attacked_legacy["cert-b"]["online"] = False
    attacked_legacy["cert-a"] = deepcopy(legacy1["cert-a"])
    legacy_false = w103.authority(rt1, st, boot, attacked_services, rs, cs1, attacked_legacy)
    add("pr28_wave103_false_authority_reproduced", legacy_false.startswith("AUTHORITATIVE_QUORUM_2"))

    # The same caller substitution as a plain stale disk snapshot cannot cross Wave 104's endpoint boundary.
    resolved = domain.resolved_endpoints()
    resolved["cert-a"] = deepcopy(disk1["cert-a"])
    blocked_snapshot = w.authority(rt1, st, boot, attacked_services, rs, cs1, domain, resolved)
    add("pr28_plain_same_id_snapshot_substitution_blocked",
        blocked_snapshot == "HOLD_CERTIFICATE_WITNESS_IDENTITY_OR_CREDENTIAL_INVALID")
    add("pr28_attack_did_not_modify_real_cert_a", endpoint_seqs(domain._endpoints["cert-a"], rs) == [1, 2])

    # A new same-name endpoint without the registered secret also fails even if visible IDs are copied.
    entry_a = reg["entries"]["cert-a"]
    impostor = w.CertificateWitnessEndpoint(domain.registry_sha, "cert-a", entry_a, b"x" * 32)
    impostor.restore_disk(disk1["cert-a"])
    resolved2 = domain.resolved_endpoints()
    resolved2["cert-a"] = impostor
    add("same_visible_instance_wrong_credential_blocked",
        w.authority(rt1, st, boot, attacked_services, rs, cs1, domain, resolved2)
        == "HOLD_CERTIFICATE_WITNESS_IDENTITY_OR_CREDENTIAL_INVALID")

    # Exact registered set is mandatory; removing a slot is not treated as an innocent outage.
    missing_slot = domain.resolved_endpoints()
    del missing_slot["cert-a"]
    add("resolver_membership_shrink_blocked",
        w.authority(rt1, st, boot, attacked_services, rs, cs1, domain, missing_slot)
        == "HOLD_CERTIFICATE_WITNESS_IDENTITY_OR_CREDENTIAL_INVALID")

    # Availability still works when two exact current registered endpoints remain.
    domain._endpoints["cert-b"].online = True
    domain._endpoints["cert-c"].online = False
    add("one_registered_endpoint_offline_two_current_authoritative",
        w.authority(rt, st, boot, services, rs, cs, domain).startswith("AUTHORITATIVE_QUORUM_2"))
    domain._endpoints["cert-c"].online = True

    # Stale disk on one genuine registered endpoint is tolerated while two current endpoints remain.
    domain._endpoints["cert-c"].restore_disk(disk1["cert-c"])
    add("one_registered_endpoint_stale_two_current_authoritative",
        w.authority(rt, st, boot, services, rs, cs, domain).startswith("AUTHORITATIVE_QUORUM_2"))
    domain._endpoints["cert-c"].restore_disk(disk2["cert-c"])

    # Registry tamper fails closed; no silent registry rotation exists in this wave.
    saved_registry = deepcopy(domain.registry)
    domain.registry["entries"]["cert-a"]["failure_domain_id"] = "forged-domain"
    add("registry_body_tamper_holds",
        w.authority(rt, st, boot, services, rs, cs, domain)
        == "HOLD_CERTIFICATE_WITNESS_IDENTITY_OR_CREDENTIAL_INVALID")
    domain.registry = saved_registry
    domain.registry_sha = saved_registry["registry_sha"]
    add("registry_restored_after_test", w.authority(rt, st, boot, services, rs, cs, domain).startswith("AUTHORITATIVE"))

    # Partial certificate-witness fanout remains a fail-closed transaction boundary.
    app3 = hashlib.sha256(b"wave104-epoch3").hexdigest()
    cp3, _use3, link3, tr3 = w.prepare(rt, st, priv, boot, services, rs, ts, cs, domain, app3)
    add("epoch3_local_commit", g.commit(rt, st, boot, rs, ts, link3["authority_sha"], tr3) == "COMMITTED")
    add("epoch3_publish_a", g.publish(rt, st, boot, services, tokens, rs, "remote-a") == "APPENDED")
    add("epoch3_publish_b", g.publish(rt, st, boot, services, tokens, rs, "remote-b") == "APPENDED")
    add("epoch3_certificate", g.certify_current_quorum(rt, st, boot, services, rs, cs) == "CERTIFIED")
    add("epoch3_only_cert_a_synced", w.sync_endpoint(cs, domain, rs, "cert-a") == "WITNESS_SYNCED_1")
    add("epoch3_one_endpoint_not_enough",
        w.authority(rt, st, boot, services, rs, cs, domain) == "HOLD_CERTIFICATE_WITNESS_QUORUM")
    add("epoch3_second_endpoint_synced", w.sync_endpoint(cs, domain, rs, "cert-b") == "WITNESS_SYNCED_1")
    add("epoch3_two_endpoints_restore_authority",
        w.authority(rt, st, boot, services, rs, cs, domain).startswith("AUTHORITATIVE_QUORUM_2"))
    add("epoch3_third_endpoint_catches_up", w.sync_endpoint(cs, domain, rs, "cert-c") == "WITNESS_SYNCED_2")
    disk3 = domain.disk_snapshots()

    # Explicit recovery still reconstructs the exact certificate store from two credentialed heads.
    rebuilt = w.reconstruct_certificate_store(domain, rs)
    add("explicit_reconstruction_exact_head", rebuilt["head"] == cs["head"])

    # Preserved counterexample 1: if the registered credential is stolen, a stale clone can authenticate.
    # This deliberately crosses the underscored verifier-secret boundary to model credential compromise.
    stolen_secret = domain._verifier_secrets["cert-a"]
    stolen_clone = w.CertificateWitnessEndpoint(domain.registry_sha, "cert-a", reg["entries"]["cert-a"], stolen_secret)
    stolen_clone.restore_disk(disk1["cert-a"])
    domain._endpoints["cert-b"].online = False
    domain._endpoints["cert-c"].restore_disk(disk1["cert-c"])
    compromised_resolver = domain.resolved_endpoints()
    compromised_resolver["cert-a"] = stolen_clone
    compromised_result = w.authority(rt1, st1, boot, services1, rs, cs1, domain, compromised_resolver)
    add("stolen_credential_stale_clone_counterexample_preserved", compromised_result.startswith("AUTHORITATIVE"))

    # Preserved counterexample 2: whole modeled durable-state rollback on the genuine registered endpoints.
    domain._endpoints["cert-b"].online = True
    domain.restore_disks(disk1)
    whole_rollback = w.authority(rt1, st1, boot, services1, rs, cs1, domain)
    add("whole_registered_domain_rollback_counterexample_preserved", whole_rollback.startswith("AUTHORITATIVE"))

    # Put the live modeled domain back at the newest state before reporting; tests are not silent recovery.
    domain.restore_disks(disk3)
    domain._endpoints["cert-a"].online = True
    domain._endpoints["cert-b"].online = True
    domain._endpoints["cert-c"].online = True
    add("latest_state_restored_explicitly", w.authority(rt, st, boot, services, rs, cs, domain).startswith("AUTHORITATIVE"))

    passed = sum(row["pass"] for row in controls)
    return {
        "schema": "axm.flowing_compute.wave104.report/v1",
        "wave": 104,
        "source": w.SRC,
        "controls": {"passed": passed, "total": len(controls), "rows": controls},
        "pr28_reproduction": {
            "wave103_same_id_substitution": legacy_false,
            "wave104_same_plain_snapshot_substitution": blocked_snapshot,
            "honest_real_newer_endpoint": honest,
        },
        "registry": {
            "generation": reg["generation"],
            "registry_sha": reg["registry_sha"],
            "slots": list(w.WITNESS_IDS),
            "distinct_instances": 3,
            "distinct_credentials": 3,
            "distinct_modeled_failure_domains": 3,
        },
        "counterexamples_preserved": [
            "Stealing a registered Wave 104 symmetric witness credential lets a stale clone authenticate as that registered instance in this model.",
            "Restoring all genuine registered certificate-witness ledgers together with local/certificate/remote state can recreate an internally valid old world because no store is physically monotonic yet.",
            "All three witness endpoints, registry state, credential verifier material, and remote stores still exist in one Python process; modeled failure-domain labels are not process/device/provider independence.",
            "Wave 104 deliberately has no witness-registry rotation/replacement path; recovery/reconfiguration must become an explicit authority-bound transition instead of a mutable registry rewrite.",
            "HMAC-SHA256 challenge proofs authenticate possession of test credentials only; they do not prove hardware identity, operator legitimacy, moral/root correctness, consent, or CANON authority.",
        ],
        "truth_boundary": [
            "Wave 104 directly repairs verifier PR #28 before OS-process separation.",
            "Every authority read requires the exact three-slot registered resolver set; an outage is represented by the registered endpoint remaining present but explicitly offline, not by replacing or deleting its slot.",
            "Fresh per-read HMAC challenge proofs plus registry-bound instance IDs prevent a caller from substituting a plain stale same-ID disk snapshot while the real newer endpoint remains online.",
            "Every Wave 104 retained witness row binds the immutable witness-registry SHA, instance identity, credential identity, and modeled failure-domain identity.",
            "No performance, energy, networking, retained-state, incremental-state, dormant-state, physical-independence, merge, or CANON claim is made.",
        ],
        "next_gate": "Wave 105: move the repaired registered endpoint contract into three real OS processes with separate durable stores and separately held credentials, then attack stale process images, cloned disks, credential rollback/theft, kill-restart, partition-reconnect, one outage plus one stale clone, two-process restore, registry rollback, and explicit credential/instance rotation as an authority-bound transition.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out")
    args = parser.parse_args()
    result = run()
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2, sort_keys=True)
            fh.write("\n")
    if result["controls"]["passed"] != result["controls"]["total"]:
        raise SystemExit(1)
