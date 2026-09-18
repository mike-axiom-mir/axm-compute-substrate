#!/usr/bin/env python3
"""Wave 103 adversarial/self-test for replicated quorum-certificate-maximum witnesses."""
from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy

import AXM_FLOWING_COMPUTE_CERTIFICATE_MAXIMUM_WITNESS as w
import AXM_FLOWING_COMPUTE_QUORUM_GLOBAL_MAXIMUM as g
import AXM_FLOWING_COMPUTE_REMOTE_WITNESS_REGISTRY_QUORUM as q


def expect_fail(fn, contains: str | None = None) -> bool:
    try:
        fn()
    except Exception as exc:
        return contains is None or contains in str(exc)
    return False


def epochs(service: dict) -> list[int]:
    return [r["authority_epoch"] for r in sorted(service["records"].values(), key=lambda x: x["seq"])]


def witness_seqs(service: dict) -> list[int]:
    return [r["certificate_seq"] for r in sorted(service["records"].values(), key=lambda x: x["seq"])]


def truncate_witness_to_seq(service: dict, keep: int) -> dict:
    out = deepcopy(service)
    out["records"] = {
        sha: body for sha, body in out["records"].items()
        if body["certificate_seq"] <= keep
    }
    return out


def run() -> dict:
    controls = []
    add = lambda name, value: controls.append({"name": name, "pass": bool(value)})

    add(
        "exact_sources",
        w.SRC["wave102_builder_head"] == "46fafcb3b13e5663337c01e185a8972ebc52dda5"
        and w.SRC["wave102_tool_blob"] == "8bd23cf3db02ba90161f4a7c38f36dca3f3b2733"
        and w.SRC["wave102_selftest_blob"] == "cc53bd23732acc31e8b85f0998187fba979c8a89"
        and w.SRC["verifier_pr"] == 27
        and w.SRC["verifier_head"] == "10eb40d2ccde3a8af34f19c75ab069e38e4b9048"
        and w.SRC["verifier_evidence_blob"] == "c05b1802e0aeebaf69ac2e553aff28e301b74e68"
        and w.SRC["verifier_repro_blob"] == "f0d868817bdb55c0343c2b422923e7ebd4457d2d",
    )

    st, priv, boot, rt, services, tokens, rs = q.fixture()
    ts = {}
    cs = g.new_certificate_store()
    ws = w.new_certificate_witnesses()
    add("genesis_authority", w.authority(rt, st, boot, services, rs, cs, ws) == "AUTHORITATIVE_GENESIS_MODELED")
    add("genesis_witnesses_empty", all(w.verify_certificate_witness(ws[s], s, rs) is None for s in w.WITNESS_IDS))

    # Epoch 1: establish the first accepted certificate and replicate it to all certificate witnesses.
    cp1, u1, l1, t1 = g.advance_all(st, priv, boot, rt, services, tokens, rs, ts, cs, "wave103-epoch1")
    sync1 = w.sync_witnesses(cs, ws, rs)
    add("epoch1_all_certificate_witnesses_synced", all(v == "WITNESS_SYNCED_1" for v in sync1.values()))
    add("epoch1_authoritative", w.authority(rt, st, boot, services, rs, cs, ws).startswith("AUTHORITATIVE_QUORUM_3"))
    rt1 = deepcopy(rt)
    st1 = deepcopy(st)
    services1 = deepcopy(services)
    cs1 = deepcopy(cs)
    ws1 = deepcopy(ws)
    remote_b1 = deepcopy(services["remote-b"])
    cert1_sha = cs["head"]

    # Epoch 2: exact verifier PR #27 setup — quorum on A+B, C remains a legitimate remote laggard.
    app2 = hashlib.sha256(b"wave103-epoch2").hexdigest()
    cp2, u2, l2, t2 = w.prepare(rt, st, priv, boot, services, rs, ts, cs, ws, app2)
    add("epoch2_local_commit", g.commit(rt, st, boot, rs, ts, l2["authority_sha"], t2) == "COMMITTED")
    add("epoch2_publish_a", g.publish(rt, st, boot, services, tokens, rs, "remote-a") == "APPENDED")
    add("epoch2_publish_b", g.publish(rt, st, boot, services, tokens, rs, "remote-b") == "APPENDED")
    add("epoch2_remote_c_stays_lagging", epochs(services["remote-c"]) == [1])
    add("epoch2_certificate", g.certify_current_quorum(rt, st, boot, services, rs, cs) == "CERTIFIED")
    sync2 = w.sync_witnesses(cs, ws, rs)
    add("epoch2_all_certificate_witnesses_synced", all(v == "WITNESS_SYNCED_1" for v in sync2.values()))
    add("epoch2_two_of_three_authority", w.authority(rt, st, boot, services, rs, cs, ws).startswith("AUTHORITATIVE_QUORUM_2"))
    cert2_sha = cs["head"]
    ws2 = deepcopy(ws)
    cs2 = deepcopy(cs)

    # Reproduce PR #27 against unchanged Wave 102 first, then run the exact attacked world through Wave 103.
    attacked_services = deepcopy(services)
    attacked_services["remote-b"] = deepcopy(remote_b1)
    attacked_cs = deepcopy(cs)
    del attacked_cs["records"][cert2_sha]
    attacked_cs["head"] = cert1_sha
    wave102_false = g.authority(rt1, st, boot, attacked_services, rs, attacked_cs)
    wave103_block = w.authority(rt1, st, boot, attacked_services, rs, attacked_cs, ws)
    add("pr27_wave102_false_authority_reproduced", wave102_false.startswith("AUTHORITATIVE_QUORUM_2"))
    add("pr27_remote_a_keeps_epoch2", epochs(attacked_services["remote-a"]) == [1, 2])
    add("pr27_only_remote_b_restored", epochs(attacked_services["remote-b"]) == [1])
    add("pr27_remote_c_legitimately_lagging", epochs(attacked_services["remote-c"]) == [1])
    add("pr27_newer_local_bodies_retained", l2["authority_sha"] in st["L"] and cp2["checkpoint_sha"] in st["C"])
    add("pr27_wave103_blocks_tail_truncation", wave103_block == "HOLD_CERTIFICATE_WITNESS_MAXIMUM_AHEAD")

    # One valid newer certificate witness is enough to prevent an older local certificate maximum from winning.
    two_stale_ws = deepcopy(ws)
    two_stale_ws["cert-b"] = truncate_witness_to_seq(two_stale_ws["cert-b"], 1)
    two_stale_ws["cert-c"] = truncate_witness_to_seq(two_stale_ws["cert-c"], 1)
    add("single_retained_newer_certificate_witness_blocks_old_world",
        w.authority(rt1, st, boot, attacked_services, rs, attacked_cs, two_stale_ws)
        == "HOLD_CERTIFICATE_WITNESS_MAXIMUM_AHEAD")

    # Availability: one certificate witness can be explicitly offline when the other two retain exact current finality.
    one_offline = deepcopy(ws)
    one_offline["cert-c"]["online"] = False
    add("one_certificate_witness_offline_two_current_still_authoritative",
        w.authority(rt, st, boot, services, rs, cs, one_offline).startswith("AUTHORITATIVE_QUORUM_2"))

    one_stale = deepcopy(ws)
    one_stale["cert-c"] = truncate_witness_to_seq(one_stale["cert-c"], 1)
    add("one_certificate_witness_stale_two_current_still_authoritative",
        w.authority(rt, st, boot, services, rs, cs, one_stale).startswith("AUTHORITATIVE_QUORUM_2"))

    # Invalid retained witness data fails closed rather than being silently treated as an outage.
    tampered_ws = deepcopy(ws)
    tamper_key = next(iter(tampered_ws["cert-c"]["records"]))
    tampered_ws["cert-c"]["records"][tamper_key]["authority_epoch"] = 999
    add("online_certificate_witness_tamper_holds",
        w.authority(rt, st, boot, services, rs, cs, tampered_ws) == "HOLD_CERTIFICATE_WITNESS_INVALID")

    missing_pred_ws = deepcopy(ws)
    oldest_key = min(
        missing_pred_ws["cert-c"]["records"],
        key=lambda sha: missing_pred_ws["cert-c"]["records"][sha]["certificate_seq"],
    )
    del missing_pred_ws["cert-c"]["records"][oldest_key]
    add("online_certificate_witness_missing_predecessor_holds",
        w.authority(rt, st, boot, services, rs, cs, missing_pred_ws) == "HOLD_CERTIFICATE_WITNESS_INVALID")

    alias_ws = deepcopy(ws)
    alias_ws["cert-c"]["witness_id"] = "cert-a"
    add("certificate_witness_identity_alias_holds",
        w.authority(rt, st, boot, services, rs, cs, alias_ws) == "HOLD_CERTIFICATE_WITNESS_INVALID")

    # Local certificate-store tail loss can be reconstructed explicitly from 2 matching witness ledgers.
    reconstructed = w.reconstruct_certificate_store(ws, rs)
    add("explicit_reconstruction_recovers_exact_certificate_head",
        reconstructed["head"] == cs2["head"] and set(reconstructed["records"]) == set(cs2["records"]))
    add("authority_read_did_not_mutate_attacked_store",
        attacked_cs["head"] == cert1_sha and cert2_sha not in attacked_cs["records"])

    # Epoch 3: crash/partial-fanout model. Local certificate exists, only one cert witness receives it => HOLD.
    app3 = hashlib.sha256(b"wave103-epoch3").hexdigest()
    cp3, u3, l3, t3 = w.prepare(rt, st, priv, boot, services, rs, ts, cs, ws, app3)
    add("epoch3_local_commit", g.commit(rt, st, boot, rs, ts, l3["authority_sha"], t3) == "COMMITTED")
    add("epoch3_publish_a", g.publish(rt, st, boot, services, tokens, rs, "remote-a") == "APPENDED")
    add("epoch3_publish_b", g.publish(rt, st, boot, services, tokens, rs, "remote-b") == "APPENDED")
    add("epoch3_certificate", g.certify_current_quorum(rt, st, boot, services, rs, cs) == "CERTIFIED")
    only_a = w.sync_witness(cs, ws, rs, "cert-a")
    add("partial_certificate_witness_fanout_one_append", only_a == "WITNESS_SYNCED_1")
    add("partial_certificate_witness_fanout_holds",
        w.authority(rt, st, boot, services, rs, cs, ws) == "HOLD_CERTIFICATE_WITNESS_QUORUM")
    add("explicit_second_witness_sync", w.sync_witness(cs, ws, rs, "cert-b") == "WITNESS_SYNCED_1")
    add("two_certificate_witnesses_restore_authority",
        w.authority(rt, st, boot, services, rs, cs, ws).startswith("AUTHORITATIVE_QUORUM_2"))
    add("third_witness_can_catch_up_later", w.sync_witness(cs, ws, rs, "cert-c") == "WITNESS_SYNCED_1")
    add("all_certificate_witnesses_reach_three",
        all(witness_seqs(ws[s]) == [1, 2, 3] for s in w.WITNESS_IDS))

    # Duplicate sequence in one retained witness ledger is rejected even when all record hashes are valid.
    dup_ws = deepcopy(ws)
    head = w.verify_certificate_witness(dup_ws["cert-c"], "cert-c", rs)
    duplicate = deepcopy(head)
    duplicate["previous_record_sha"] = "e" * 64
    duplicate["record_sha"] = ""
    duplicate = g.w98.seal(duplicate, "record_sha")
    dup_ws["cert-c"]["records"][duplicate["record_sha"]] = duplicate
    add("duplicate_certificate_witness_sequence_holds",
        w.authority(rt, st, boot, services, rs, cs, dup_ws) == "HOLD_CERTIFICATE_WITNESS_INVALID")

    # Tail truncation of one certificate witness is okay while two exact current witnesses remain.
    one_tail_cut = deepcopy(ws)
    one_tail_cut["cert-c"] = truncate_witness_to_seq(one_tail_cut["cert-c"], 2)
    add("single_certificate_witness_tail_cut_tolerated_by_two_current",
        w.authority(rt, st, boot, services, rs, cs, one_tail_cut).startswith("AUTHORITATIVE_QUORUM_2"))

    # Preserved counterexample: rollback the local/certificate/remote world AND all certificate witnesses together.
    full_modeled_rollback = w.authority(rt1, st1, boot, services1, rs, cs1, ws1)
    add("whole_modeled_certificate_domain_rollback_counterexample_preserved",
        full_modeled_rollback.startswith("AUTHORITATIVE"))

    # Availability counterexample: if the sole witness remembering a newer accepted cert is unavailable,
    # stale evidence cannot observe it. This stays explicit for the next durable/process-separated gate.
    hidden_newer = deepcopy(two_stale_ws)
    hidden_newer["cert-a"]["online"] = False
    hidden_newer_result = w.authority(rt1, st1, boot, services1, rs, cs1, hidden_newer)
    add("unavailable_only_newer_certificate_witness_counterexample_preserved",
        hidden_newer_result.startswith("AUTHORITATIVE"))

    passed = sum(row["pass"] for row in controls)
    return {
        "schema": "axm.flowing_compute.wave103.report/v1",
        "wave": 103,
        "source": w.SRC,
        "controls": {"passed": passed, "total": len(controls), "rows": controls},
        "pr27_reproduction": {
            "wave102_result": wave102_false,
            "wave103_result": wave103_block,
            "remote_a_epochs": epochs(attacked_services["remote-a"]),
            "remote_b_epochs": epochs(attacked_services["remote-b"]),
            "remote_c_epochs": epochs(attacked_services["remote-c"]),
            "certificate_store_max_after_attack": g.verify_certificate_store(attacked_cs, rs)["authority_epoch"],
            "certificate_witness_maxima": {
                slot: w.verify_certificate_witness(ws2[slot], slot, rs)["authority_epoch"]
                for slot in w.WITNESS_IDS
            },
        },
        "counterexamples_preserved": [
            "All three certificate-witness ledgers are still Python objects in one process; rolling them back together with local/certificate/remote state can recreate an internally valid old world.",
            "If the only certificate witness that still remembers a newer accepted certificate is unavailable while the other two have been restored to a valid stale state, the stale maximum can be accepted in this model.",
            "Certificate-witness records authenticate retained content only by hashes; they are not independent public-key attestations and do not prove physical/provider identity.",
            "Enough compromise of the underlying current quorum/signing surface can still create structurally valid competing evidence; Wave 103 is not a production Byzantine-consensus claim.",
            "Mechanical chronology/finality does not prove moral/root judgment correctness, consent, evaluator legitimacy, or canonical AXM authority.",
        ],
        "truth_boundary": [
            "Wave 103 directly repairs verifier PR #27 before OS-process separation.",
            "A valid retained certificate-witness row embeds an already-issued Wave 102 quorum certificate, so one such newer row blocks an older local certificate maximum instead of being treated as a mere ahead scout observation.",
            "Non-genesis authority requires at least two online certificate witnesses to match the exact current quorum certificate; one stale or explicitly offline certificate witness is tolerated when two exact current witnesses remain.",
            "Certificate-witness ledgers have no trusted mutable head; their maximum is derived from the complete retained record set.",
            "Authority reads never auto-repair. A separate explicit reconstruction function can produce an exact candidate certificate store from two matching witness maxima.",
            "No fresh AXM/monolith workload is read because the newest independent verifier exposed a narrower finality rollback defect that must be closed before deployment/performance claims.",
            "No merge, CANON promotion, physical/provider independence, network, energy, retained, incremental, or dormant-compute win is claimed.",
        ],
        "next_gate": (
            "Wave 104: move the repaired local authority, certificate store, and certificate-maximum witnesses into at least three real OS processes with separate durable stores and separately held credentials. "
            "Test kill/restart, stale-disk restore, certificate-tail truncation, crash between certificate creation and witness fanout, partition/reconnect, one witness unavailable, conflicting recovered tails, credential rotation, and rollback of a process's durable maximum. "
            "The unavailable-only-newer-witness counterexample must remain visible; process separation alone does not make storage monotonic or prove physical/provider independence."
        ),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--report")
    args = p.parse_args()
    report = run()
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    raise SystemExit(0 if report["controls"]["passed"] == report["controls"]["total"] else 1)


if __name__ == "__main__":
    main()
