#!/usr/bin/env python3
"""Wave 102 adversarial/self-test for quorum-certified global authority maximum."""
from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy

import AXM_FLOWING_COMPUTE_QUORUM_GLOBAL_MAXIMUM as g
import AXM_FLOWING_COMPUTE_REMOTE_AUTHORITY_MONOTONICITY as a
import AXM_FLOWING_COMPUTE_REMOTE_WITNESS_REGISTRY_QUORUM as q


def expect_fail(fn, contains: str | None = None) -> bool:
    try:
        fn()
    except Exception as exc:
        return contains is None or contains in str(exc)
    return False


def epochs(service: dict) -> list[int]:
    return [r["authority_epoch"] for r in sorted(service["records"].values(), key=lambda x: x["seq"])]


def run(rounds: int) -> dict:
    controls = []
    add = lambda name, value: controls.append({"name": name, "pass": bool(value)})

    add(
        "exact_sources",
        g.SRC["wave101_builder_head"] == "08bed3007e118fdcc2499c873da85ed9355c96d2"
        and g.SRC["wave101_tool_blob"] == "9283b748aefcc1914eb763748674ee83a5ec3b15"
        and g.SRC["wave101_selftest_blob"] == "4bddbd849319b7475ac399dd96cd72ceb498545a"
        and g.SRC["verifier_pr"] == 26
        and g.SRC["verifier_head"] == "c0c5b718b1ad77f4685045e290d6c7021f4786ca"
        and g.SRC["verifier_evidence_blob"] == "4ce07288e73d9a288c026a771f598585c698c090"
        and g.SRC["verifier_repro_blob"] == "2d5fc38bd07ebe3c172f02496b41b7c7a469a6f0",
    )

    st, priv, boot, rt, services, tokens, rs = q.fixture()
    ts = {}
    cs = g.new_certificate_store()
    add("genesis_authority", g.authority(rt, st, boot, services, rs, cs) == "AUTHORITATIVE_GENESIS_MODELED")
    add("genesis_certificate_store_empty", g.verify_certificate_store(cs, rs) is None)

    cp1, u1, l1, t1 = g.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, "wave102-base-1"
    )
    rt1 = deepcopy(rt)
    st1 = deepcopy(st)
    services1 = deepcopy(services)
    cs1 = deepcopy(cs)
    add("epoch1_certified", g.verify_certificate_store(cs, rs)["authority_epoch"] == 1)
    add("epoch1_three_of_three", g.authority(rt, st, boot, services, rs, cs).startswith("AUTHORITATIVE_QUORUM_3"))

    app2 = hashlib.sha256(b"wave102-epoch-2").hexdigest()
    cp2, u2, l2, t2 = g.prepare(rt, st, priv, boot, services, rs, ts, cs, app2)
    add("epoch2_local_commit", g.commit(rt, st, boot, rs, ts, l2["authority_sha"], t2) == "COMMITTED")
    add("epoch2_publish_a_only", g.publish(rt, st, boot, services, tokens, rs, "remote-a") == "APPENDED")
    add("uncertified_newer_local_not_authoritative",
        not g.authority(rt, st, boot, services, rs, cs).startswith("AUTHORITATIVE"))
    add("uncertified_newer_cannot_certify_without_quorum",
        g.certify_current_quorum(rt, st, boot, services, rs, cs) == "CERTIFICATE_QUORUM_HOLD")

    never_quorum_services = deepcopy(services)
    never_quorum_old_world = g.authority(rt1, st, boot, never_quorum_services, rs, cs1)
    add("newer_but_never_quorum_does_not_raise_global_max",
        never_quorum_old_world.startswith("AUTHORITATIVE_QUORUM_2"))
    add("single_ahead_witness_does_not_poison_finality",
        epochs(never_quorum_services["remote-a"]) == [1, 2]
        and epochs(never_quorum_services["remote-b"]) == [1]
        and epochs(never_quorum_services["remote-c"]) == [1])

    add("epoch2_publish_b", g.publish(rt, st, boot, services, tokens, rs, "remote-b") == "APPENDED")
    wave101_epoch2 = a.authority(rt, st, boot, services, rs)
    add("wave101_epoch2_quorum_exists", wave101_epoch2.startswith("AUTHORITATIVE_QUORUM_2"))
    add("wave102_requires_explicit_certificate",
        g.authority(rt, st, boot, services, rs, cs) == "HOLD_QUORUM_CERTIFICATE_PENDING")
    add("epoch2_certificate_written", g.certify_current_quorum(rt, st, boot, services, rs, cs) == "CERTIFIED")
    max2 = g.verify_certificate_store(cs, rs)
    add("epoch2_global_maximum_is_two", max2["authority_epoch"] == 2 and max2["seq"] == 2)
    add("epoch2_two_of_three_authority", g.authority(rt, st, boot, services, rs, cs).startswith("AUTHORITATIVE_QUORUM_2"))
    add("certificate_support_is_real_quorum", len(max2["support_records"]) >= 2)

    stale = deepcopy(services)
    stale["remote-b"] = deepcopy(services1["remote-b"])
    wave101_false = a.authority(rt1, st, boot, stale, rs)
    wave102_block = g.authority(rt1, st, boot, stale, rs, cs)
    add("pr26_wave101_false_authority_reproduced", wave101_false.startswith("AUTHORITATIVE_QUORUM_2"))
    add("pr26_a_retains_newer_epoch", epochs(stale["remote-a"]) == [1, 2])
    add("pr26_b_restored_to_one", epochs(stale["remote-b"]) == [1])
    add("pr26_c_legitimately_lagging", epochs(stale["remote-c"]) == [1])
    add("pr26_wave102_old_quorum_blocked", wave102_block == "HOLD_QUORUM_GLOBAL_MAXIMUM_AHEAD")

    stale_a_offline = deepcopy(stale)
    stale_a_offline["remote-a"]["online"] = False
    add("previously_authoritative_max_survives_newer_witness_outage",
        g.authority(rt1, st, boot, stale_a_offline, rs, cs) == "HOLD_QUORUM_GLOBAL_MAXIMUM_AHEAD")

    add("newer_local_authority_body_retained", l2["authority_sha"] in st["L"])
    add("newer_local_checkpoint_body_retained", cp2["checkpoint_sha"] in st["C"])

    bad_head = deepcopy(cs)
    bad_head["head"] = cs1["head"]
    add("certificate_mutable_head_rewind_rejected",
        expect_fail(lambda: g.verify_certificate_store(bad_head, rs), "not maximal"))

    missing_old = deepcopy(cs)
    del missing_old["records"][cs1["head"]]
    add("certificate_missing_predecessor_rejected",
        expect_fail(lambda: g.verify_certificate_store(missing_old, rs)))

    tampered = deepcopy(cs)
    head_sha = tampered["head"]
    tampered["records"][head_sha]["authority_epoch"] = 1
    add("certificate_body_tamper_rejected",
        expect_fail(lambda: g.verify_certificate_store(tampered, rs)))

    support_tamper = deepcopy(cs)
    h = support_tamper["head"]
    slot = sorted(support_tamper["records"][h]["support_records"])[0]
    support_tamper["records"][h]["support_records"][slot]["authority_sha"] = "f" * 64
    add("certificate_support_tamper_rejected",
        expect_fail(lambda: g.verify_certificate_store(support_tamper, rs)))

    sibling_store = deepcopy(cs)
    sibling = deepcopy(max2)
    sibling["authority_sha"] = "e" * 64
    sibling["certificate_sha"] = ""
    sibling = g.w98.seal(sibling, "certificate_sha")
    sibling_store["records"][sibling["certificate_sha"]] = sibling
    sibling_store["head"] = sibling["certificate_sha"]
    add("same_sequence_sibling_certificate_rejected",
        expect_fail(lambda: g.verify_certificate_store(sibling_store, rs), "duplicate certificate sequence"))

    all_old_services = deepcopy(services1)
    modeled_domain_rollback = g.authority(rt1, st1, boot, all_old_services, rs, cs1)
    add("certificate_store_rollback_counterexample_preserved",
        modeled_domain_rollback.startswith("AUTHORITATIVE"))

    scaling = g.bench((1, 4, 8), rounds)
    add("synthetic_scaling_rows_present", [r["depth"] for r in scaling] == [1, 4, 8])

    passed = sum(row["pass"] for row in controls)
    return {
        "schema": "axm.flowing_compute.wave102.report/v1",
        "wave": 102,
        "source": g.SRC,
        "controls": {"passed": passed, "total": len(controls), "rows": controls},
        "synthetic_scaling": {
            "label": (
                "SYNTHETIC single-process quorum-certificate/remote-history bookkeeping only; "
                "not OS-process, provider, network, energy, AXM/monolith workload, retained, "
                "incremental, or dormant-compute evidence"
            ),
            "rows": scaling,
        },
        "counterexamples_preserved": [
            "The quorum-certificate store is still modeled local state in the same Python process as all three remote witness objects.",
            "Rolling local runtime, quorum-certificate store, and enough modeled remote stores back together can still recreate an internally valid old world.",
            "Certificate bodies are content-addressed integrity evidence, not independent public-key remote attestations; remote credentials remain symmetric test tokens.",
            "Two compromised current remote credentials can still participate in the existing modeled 2-of-3 acceptance surface or poison availability; Wave 102 does not claim Byzantine production consensus.",
            "A newer record visible on only one witness is intentionally not promoted to global finality; this avoids turning one compromised/ahead witness into unilateral authority or permanent finality poisoning.",
            "Mechanical quorum chronology does not prove moral/root judgment correctness, consent, evaluator legitimacy, or canonical AXM authority.",
        ],
        "truth_boundary": [
            "Wave 102 directly repairs verifier PR #26 before OS-process separation.",
            "The global maximum advances only after the exact current local authority is observed on at least the registered 2-of-3 remote quorum and an explicit append-only certificate is written.",
            "A previously certified newer epoch blocks authority for an older local world even when the witness retaining that newer record is unavailable.",
            "A newer epoch seen on only one witness but never certified by quorum does not become global finality; the last certified world can remain authoritative if its live quorum is exact.",
            "No fresh AXM/monolith workload is read because the newest independent verifier exposed a protocol rollback defect that must be closed before stronger deployment claims.",
            "No merge, CANON promotion, physical/provider independence, network, energy, retained, incremental, or dormant-compute win is claimed.",
        ],
        "next_gate": (
            "Wave 103: move the quorum-certificate maximum plus repaired registry/authority chronology across at least three real OS processes with separate durable stores and separately held credentials. "
            "Test kill/restart, stale durable-store restoration, partition/reconnect, partial publish before versus after quorum certification, certificate-store rollback, credential rotation, one-process quarantine, two-process compromise, and recovery with one certificate witness unavailable. "
            "Success would establish process-level evidence only, not physical/provider independence."
        ),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--benchmark-rounds", type=int, default=5)
    p.add_argument("--report")
    args = p.parse_args()
    report = run(args.benchmark_rounds)
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    raise SystemExit(0 if report["controls"]["passed"] == report["controls"]["total"] else 1)


if __name__ == "__main__":
    main()
