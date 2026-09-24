#!/usr/bin/env python3
"""Wave 105 adversarial/self-test for authority-bound certificate-witness registry roots."""
from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path

import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_ROOT_BINDING as w
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w104

g = w.g
q = w.q


def H(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def endpoint_seqs(endpoint, registry_store: dict) -> list[int]:
    head = w104.verify_endpoint_ledger(endpoint, registry_store)
    if head is None:
        return []
    return sorted(rec["certificate_seq"] for rec in endpoint.records.values())


def run() -> dict:
    controls = []
    add = lambda name, value: controls.append({"name": name, "pass": bool(value)})

    add(
        "exact_sources",
        w.SRC["wave104_builder_head"] == "b0826840723b4d510f396c91e8f0c5de46a05a43"
        and w.SRC["wave104_tested_source_head"] == "b33c8e0ae155d8e785b25ab608bdf8a3dbb14e65"
        and w.SRC["wave104_tool_blob"] == "64aef8c32e246f396ca8dc67dbf3b0460b077f77"
        and w.SRC["wave104_selftest_blob"] == "c2ca76079adfbe9f44fd11c97689be61027a7760"
        and w.SRC["verifier_pr"] == 29
        and w.SRC["verifier_head"] == "cc0ecfe2a40b0a39b20b85230578ddc3902c44ad"
        and w.SRC["verifier_evidence_blob"] == "afbfa47432c29ad41f5c0d56a1904ca94e996e30"
        and w.SRC["verifier_repro_blob"] == "51cc2266f47b4cfaeae32ad6744cead9f9d104b0",
    )

    st, priv, boot, rt, services, tokens, rs = q.fixture()
    ts = {}
    cs = g.new_certificate_store()
    domain = w104.new_certificate_witness_domain()
    bs = {}

    initial_user_app = rt["app_state_sha"]
    root0 = w.adopt_genesis(rt, st, boot, services, rs, cs, domain, bs)
    b0 = w.get_binding(bs, rs, root0)
    add("genesis_binding_seq_zero", b0["seq"] == 0 and b0["predecessor_binding_sha"] is None)
    add("genesis_binding_preserves_user_app", b0["user_app_state_sha"] == initial_user_app)
    add("genesis_binding_exact_remote_registry", b0["remote_registry_sha"] == rt["remote_registry_sha"])
    add("genesis_binding_exact_certificate_registry", b0["certificate_witness_registry_sha"] == domain.registry_sha)
    add("genesis_authority", w.authority(rt, st, boot, services, rs, cs, domain, bs) == "AUTHORITATIVE_GENESIS_MODELED")

    replacement_domain = w104.new_certificate_witness_domain()
    add("fresh_registry_is_distinct", replacement_domain.registry_sha != domain.registry_sha)
    add(
        "fresh_registry_blocked_immediately_after_adoption",
        w.authority(rt, st, boot, services, rs, cs, replacement_domain, bs)
        == "HOLD_CERTIFICATE_WITNESS_REGISTRY_ROOT_MISMATCH",
    )

    # Authority epoch 1: first signed checkpoint now transitively commits the exact Wave 105 binding SHA.
    w.advance_all(st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs, "wave105-epoch1")
    add("epoch1_authoritative", w.authority(rt, st, boot, services, rs, cs, domain, bs).startswith("AUTHORITATIVE"))
    b1 = w.get_binding(bs, rs, rt["app_state_sha"])
    status1, link1, cp1 = q.current_local(rt, st, boot)
    add("epoch1_binding_seq_matches_authority", status1 == "LOCAL_OK" and b1["seq"] == link1["epoch"] == 1)
    add("epoch1_checkpoint_binds_binding_sha", cp1["state_sha"] == q.binding(b1["binding_sha"], b1["remote_registry_sha"]))
    add("epoch1_binding_predecessor_is_genesis", b1["predecessor_binding_sha"] == b0["binding_sha"])

    rt1 = deepcopy(rt)
    services1 = deepcopy(services)
    cs1 = deepcopy(cs)
    remote_b1 = deepcopy(services["remote-b"])
    disk1 = domain.disk_snapshots()

    # Authority epoch 2: publish/certify on remote A+B and sync cert-a + cert-b only.
    cp2, _use2, link2, tr2, b2 = w.prepare(
        rt, st, priv, boot, services, rs, ts, cs, domain, bs, H("wave105-epoch2")
    )
    add(
        "epoch2_local_commit",
        w.commit(rt, st, boot, rs, ts, link2["authority_sha"], tr2, bs) == "COMMITTED",
    )
    add("epoch2_publish_a", w.publish(rt, st, boot, services, tokens, rs, "remote-a") == "APPENDED")
    add("epoch2_publish_b", w.publish(rt, st, boot, services, tokens, rs, "remote-b") == "APPENDED")
    add("epoch2_certificate", g.certify_current_quorum(rt, st, boot, services, rs, cs) == "CERTIFIED")
    add("epoch2_sync_cert_a", w104.sync_endpoint(cs, domain, rs, "cert-a") == "WITNESS_SYNCED_1")
    add("epoch2_sync_cert_b", w104.sync_endpoint(cs, domain, rs, "cert-b") == "WITNESS_SYNCED_1")
    add("epoch2_cert_c_lags", endpoint_seqs(domain._endpoints["cert-c"], rs) == [1])
    add("epoch2_authoritative_two_of_three", w.authority(rt, st, boot, services, rs, cs, domain, bs).startswith("AUTHORITATIVE_QUORUM_2"))
    add("epoch2_binding_seq_matches_authority", b2["seq"] == 2 and b2["binding_sha"] == rt["app_state_sha"])
    disk2 = domain.disk_snapshots()

    # Exact PR #29 shape: local/certificate at epoch1, remote A remains newer, remote B restored,
    # original certificate-witness domain remains online and remembers certificate 2.
    attacked_services = deepcopy(services)
    attacked_services["remote-b"] = deepcopy(remote_b1)
    honest = w.authority(rt1, st, boot, attacked_services, rs, cs1, domain, bs)
    add("original_newer_domain_blocks_stale_world", honest == "HOLD_CERTIFICATE_WITNESS_MAXIMUM_AHEAD")
    add("original_cert_a_still_newer", endpoint_seqs(domain._endpoints["cert-a"], rs) == [1, 2])
    add("original_cert_b_still_newer", endpoint_seqs(domain._endpoints["cert-b"], rs) == [1, 2])

    replacement_sync = w104.sync_endpoints(cs1, replacement_domain, rs)
    add("fresh_replacement_domain_syncs_stale_certificate", all(v == "WITNESS_SYNCED_1" for v in replacement_sync.values()))

    # Reproduce the independent finding against unchanged Wave 104 first.
    wave104_false = w104.authority(
        rt1, st, boot, attacked_services, rs, cs1, replacement_domain
    )
    add("pr29_wave104_false_authority_reproduced", wave104_false.startswith("AUTHORITATIVE_QUORUM_2"))

    # Same stale world + same fresh registry replacement now fails before its witnesses can count.
    wave105_blocked = w.authority(
        rt1, st, boot, attacked_services, rs, cs1, replacement_domain, bs
    )
    add(
        "pr29_fresh_registry_root_substitution_blocked",
        wave105_blocked == "HOLD_CERTIFICATE_WITNESS_REGISTRY_ROOT_MISMATCH",
    )
    add("pr29_attack_did_not_modify_original_domain", endpoint_seqs(domain._endpoints["cert-a"], rs) == [1, 2])

    # Missing/tampered binding evidence fails closed.
    missing_bs = deepcopy(bs)
    del missing_bs[rt1["app_state_sha"]]
    add(
        "missing_current_root_binding_holds",
        w.authority(rt1, st, boot, services1, rs, cs1, domain, missing_bs)
        == "HOLD_CERTIFICATE_WITNESS_ROOT_BINDING_INVALID",
    )
    tampered_bs = deepcopy(bs)
    tampered_bs[rt1["app_state_sha"]]["certificate_witness_registry_sha"] = replacement_domain.registry_sha
    add(
        "tampered_current_root_binding_holds",
        w.authority(rt1, st, boot, services1, rs, cs1, domain, tampered_bs)
        == "HOLD_CERTIFICATE_WITNESS_ROOT_BINDING_INVALID",
    )

    # A caller cannot evade the upper contract by preparing/committing a complete fresh parallel
    # replacement-root binding chain through the older lower primitive after authority history exists.
    stx = deepcopy(st)
    privx = deepcopy(priv)
    rtx = deepcopy(rt)
    servicesx = deepcopy(services)
    rsx = deepcopy(rs)
    tsx = deepcopy(ts)
    csx = deepcopy(cs)
    bsx = deepcopy(bs)
    fake0 = w.make_binding(0, H("parallel-0"), rtx["remote_registry_sha"], replacement_domain.registry_sha, None)
    w.put_binding(bsx, fake0, rsx)
    fake1 = w.make_binding(1, H("parallel-1"), rtx["remote_registry_sha"], replacement_domain.registry_sha, fake0["binding_sha"])
    w.put_binding(bsx, fake1, rsx)
    fake2 = w.make_binding(2, H("parallel-2"), rtx["remote_registry_sha"], replacement_domain.registry_sha, fake1["binding_sha"])
    w.put_binding(bsx, fake2, rsx)
    fake3 = w.make_binding(3, H("parallel-3"), rtx["remote_registry_sha"], replacement_domain.registry_sha, fake2["binding_sha"])
    w.put_binding(bsx, fake3, rsx)
    _cpx, _ux, lx, trx = g.prepare(
        rtx, stx, privx, boot, servicesx, rsx, tsx, csx,
        target_app_state_sha=fake3["binding_sha"],
        target_registry_sha=rtx["remote_registry_sha"],
    )
    lower_commit = g.commit(rtx, stx, boot, rsx, tsx, lx["authority_sha"], trx)
    add("lower_primitive_parallel_root_commit_occurs", lower_commit == "COMMITTED")
    add(
        "parallel_root_chain_rejected_by_checkpoint_crossbind",
        w.authority(rtx, stx, boot, servicesx, rsx, csx, replacement_domain, bsx)
        == "HOLD_CERTIFICATE_WITNESS_ROOT_BINDING_INVALID",
    )

    # Preserved failure 1: stealing a credential for the already-bound root can still authenticate
    # a stale clone. Wave 105 fixes root substitution, not compromised endpoint credentials.
    stolen_secret = domain._verifier_secrets["cert-a"]
    entry_a = domain.registry["entries"]["cert-a"]
    stolen_clone = w104.CertificateWitnessEndpoint(
        domain.registry_sha, "cert-a", entry_a, stolen_secret
    )
    stolen_clone.restore_disk(disk1["cert-a"])
    domain._endpoints["cert-b"].online = False
    domain._endpoints["cert-c"].restore_disk(disk1["cert-c"])
    compromised = domain.resolved_endpoints()
    compromised["cert-a"] = stolen_clone
    stolen_result = w.authority(
        rt1, st, boot, services1, rs, cs1, domain, bs, compromised
    )
    add("stolen_bound_root_credential_counterexample_preserved", stolen_result.startswith("AUTHORITATIVE"))

    # Preserved failure 2: whole same-root modeled durable-state rollback still looks self-consistent.
    domain._endpoints["cert-b"].online = True
    domain.restore_disks(disk1)
    whole_rollback = w.authority(rt1, st, boot, services1, rs, cs1, domain, bs)
    add("whole_bound_domain_rollback_counterexample_preserved", whole_rollback.startswith("AUTHORITATIVE"))

    # Restore newest modeled domain explicitly; tests never silently repair state.
    domain.restore_disks(disk2)
    for slot in w104.WITNESS_IDS:
        domain._endpoints[slot].online = True
    add("latest_state_restored_explicitly", w.authority(rt, st, boot, services, rs, cs, domain, bs).startswith("AUTHORITATIVE"))

    passed = sum(row["pass"] for row in controls)
    return {
        "schema": "axm.flowing_compute.wave105.report/v1",
        "wave": 105,
        "source": w.SRC,
        "controls": {"passed": passed, "total": len(controls), "rows": controls},
        "pr29_reproduction": {
            "wave104_fresh_registry_replacement": wave104_false,
            "wave105_same_replacement": wave105_blocked,
            "original_bound_domain_on_stale_world": honest,
        },
        "binding": {
            "schema": w.BINDING_SCHEMA,
            "genesis_binding_sha": b0["binding_sha"],
            "epoch1_binding_sha": b1["binding_sha"],
            "epoch2_binding_sha": b2["binding_sha"],
            "bound_certificate_witness_registry_sha": domain.registry_sha,
        },
        "counterexamples_preserved": [
            "Bootstrap registry-root selection before the first accepted checkpoint is still an initialization/configuration boundary.",
            "Stealing a symmetric credential for an already-bound Wave 104 endpoint can authenticate a stale clone in this model.",
            "Rolling back the local/certificate/remote state and all genuine endpoints together under the same already-bound root can still recreate an internally valid old world.",
            "All stores, endpoints, credentials, and failure-domain labels still live inside one Python process; this is not OS/device/provider separation.",
            "Certificate-witness registry rotation remains unsupported; Wave 105 rejects root change rather than inventing a transition policy.",
        ],
        "truth_boundary": [
            "Wave 105 repairs verifier PR #29 by transitively binding the exact certificate-witness registry SHA into the signed checkpoint state through a content-addressed predecessor-linked binding body.",
            "Every retained authority checkpoint is cross-checked against its exact binding predecessor; a new parallel root chain cannot silently attach after accepted history.",
            "No fresh AXM/monolith performance, energy, retained-compute, incremental-compute, dormant-compute, network, process, device, or provider-independence result is claimed.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out")
    args = parser.parse_args()
    report = run()
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    if report["controls"]["passed"] != report["controls"]["total"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
