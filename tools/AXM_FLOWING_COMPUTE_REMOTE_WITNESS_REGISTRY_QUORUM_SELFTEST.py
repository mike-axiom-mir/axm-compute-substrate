#!/usr/bin/env python3
"""Wave 99 adversarial/self-test for AXM remote-witness registry quorum."""
from __future__ import annotations
import argparse, hashlib, json, secrets
from copy import deepcopy
import AXM_FLOWING_COMPUTE_REMOTE_WITNESS_REGISTRY_QUORUM as q
from AXM_FLOWING_COMPUTE_REMOTE_WITNESS_REGISTRY_QUORUM import *

def run(rounds: int) -> dict:
    controls = []
    add = lambda name, value: controls.append({"name": name, "pass": bool(value)})
    add("exact_sources", SRC["wave98_head"] == "56bb92218f9af62aceacee1ee625755b8ef54789"
        and SRC["wave98_tool_blob"] == "bc4347a75f04f6d9ff97e58128d2f5f0a16c85a1"
        and SRC["verifier_head"] == "ac4929e3404a14b6fe6d902f4c923b16a31427b5")

    st, priv, boot, rt, services, tokens, rs = fixture()
    reg0 = get_registry(rs, rt["remote_registry_sha"])
    add("registry_genesis_valid", reg0["generation"] == 0 and reg0["quorum"] == 2)
    bad = deepcopy(reg0); bad["slots"]["remote-b"]["credential_hash"] = bad["slots"]["remote-a"]["credential_hash"]
    bad = w98.seal(bad, "registry_sha")
    add("duplicate_credential_registry_rejected", w98.fail(lambda: validate_registry(bad, {reg0["registry_sha"]: reg0}), "duplicate credential"))
    bad2 = deepcopy(reg0); bad2["slots"]["remote-b"]["failure_domain_id"] = bad2["slots"]["remote-a"]["failure_domain_id"]
    bad2 = w98.seal(bad2, "registry_sha")
    add("duplicate_failure_domain_registry_rejected", w98.fail(lambda: validate_registry(bad2, {reg0["registry_sha"]: reg0}), "duplicate failure-domain"))
    add("genesis_authority", authority(rt, st, boot, services, rs) == "AUTHORITATIVE_GENESIS_MODELED")

    cp1, u1, l1, m1 = prepare(rt, st, priv, boot, services, rs, hashlib.sha256(b"app-1").hexdigest())
    add("candidate1_registry_bound", cp1["state_sha"] == binding(m1["target_app_state_sha"], reg0["registry_sha"]))
    add("partial_local_commit", commit(rt, st, boot, l1["authority_sha"], m1, 1) == "PARTIAL")
    add("partial_local_holds", authority(rt, st, boot, services, rs) == "HOLD_PARTIAL")
    add("complete_local_commit", commit(rt, st, boot, l1["authority_sha"], m1) == "COMMITTED")
    add("no_remote_quorum_holds", authority(rt, st, boot, services, rs) == "HOLD_REMOTE_DIVERGED_QUORUM")
    add("publish_a", publish(rt, st, boot, services, tokens, rs, "remote-a") == "APPENDED")
    add("one_remote_not_quorum", authority(rt, st, boot, services, rs) == "HOLD_REMOTE_DIVERGED_QUORUM")
    add("publish_b", publish(rt, st, boot, services, tokens, rs, "remote-b") == "APPENDED")
    add("two_of_three_authoritative", authority(rt, st, boot, services, rs).startswith("AUTHORITATIVE_QUORUM_2"))
    add("publish_c", publish(rt, st, boot, services, tokens, rs, "remote-c") == "APPENDED")
    add("three_of_three_authoritative", authority(rt, st, boot, services, rs).startswith("AUTHORITATIVE_QUORUM_3"))

    aliased = dict(services); aliased["remote-b"] = aliased["remote-a"]
    add("pr23_duplicate_service_alias_rejected", authority(rt, st, boot, aliased, rs) == "HOLD_REMOTE_ALIAS")
    swapped = deepcopy(services); swapped["remote-a"], swapped["remote-b"] = swapped["remote-b"], swapped["remote-a"]
    add("service_slot_swap_rejected", authority(rt, st, boot, swapped, rs) == "HOLD_REMOTE_IDENTITY")

    # Signed checkpoint binds the registry; changing only runtime registry metadata cannot silently retarget authority.
    shadow_reg = make_registry(deepcopy(reg0["slots"]), 1, reg0["registry_sha"]); put_registry(rs, shadow_reg)
    rebound = deepcopy(rt); rebound["remote_registry_sha"] = shadow_reg["registry_sha"]; rebound["state_sha"] = binding(rebound["app_state_sha"], shadow_reg["registry_sha"])
    add("unsigned_runtime_registry_swap_holds", authority(rebound, st, boot, services, rs) == "HOLD_STATE_BINDING")

    rt1, services1, rs1 = deepcopy(rt), deepcopy(services), deepcopy(rs)
    cp2, u2, l2, m2 = prepare(rt, st, priv, boot, services, rs, hashlib.sha256(b"app-2").hexdigest())
    add("epoch2_commit", commit(rt, st, boot, l2["authority_sha"], m2) == "COMMITTED")
    services["remote-c"]["online"] = False
    add("publish_a_epoch2", publish(rt, st, boot, services, tokens, rs, "remote-a") == "APPENDED")
    add("publish_b_epoch2", publish(rt, st, boot, services, tokens, rs, "remote-b") == "APPENDED")
    add("one_remote_offline_still_authoritative", authority(rt, st, boot, services, rs).startswith("AUTHORITATIVE_QUORUM_2"))
    services["remote-c"]["online"] = True
    add("reconnected_stale_third_still_quorum", authority(rt, st, boot, services, rs).startswith("AUTHORITATIVE_QUORUM_2"))
    add("reconnect_catchup", publish(rt, st, boot, services, tokens, rs, "remote-c") == "APPENDED")
    add("reconnect_restores_three", authority(rt, st, boot, services, rs).startswith("AUTHORITATIVE_QUORUM_3"))

    # PR #23 head rewind: keep epoch-2 records but select epoch-1 heads. Full-store verification rejects it.
    rewound = deepcopy(services)
    for slot in REMOTE_IDS:
        epoch1 = min(rewound[slot]["records"].values(), key=lambda r: r["seq"])
        rewound[slot]["head"] = epoch1["record_sha"]
    add("pr23_mutable_head_rewind_rejected", authority(rt1, st, boot, rewound, rs) == "HOLD_REMOTE_CORRUPT_QUORUM")
    add("local_rollback_detected", not authority(rt1, st, boot, services, rs).startswith("AUTHORITATIVE"))

    # One credential can poison one witness; two honest exact witnesses still anchor the local current state.
    poisoned = deepcopy(services)
    fake_sha = "e" * 64
    reg = get_registry(rs, rt["remote_registry_sha"])
    poison_result = append_raw(poisoned["remote-c"], "remote-c", reg["slots"]["remote-c"], tokens["remote-c"],
                               99, fake_sha, "d" * 64, reg["registry_sha"])
    add("one_compromised_remote_can_poison_its_head", poison_result == "APPENDED")
    add("one_poisoned_remote_no_false_authority", authority(rt, st, boot, poisoned, rs).startswith("AUTHORITATIVE_QUORUM_2"))
    poison_offline = deepcopy(poisoned); poison_offline["remote-a"]["online"] = False
    add("one_offline_plus_one_poisoned_holds", not authority(rt, st, boot, poison_offline, rs).startswith("AUTHORITATIVE"))
    wrong = secrets.token_bytes(32)
    add("wrong_credential_rejected", append_raw(services["remote-a"], "remote-a", reg["slots"]["remote-a"], wrong,
                                                 3, fake_sha, "d" * 64, reg["registry_sha"]) == "AUTH_FAIL")

    # Poisoned witness recovery requires a predecessor-linked credential rotation bound into a new local checkpoint.
    rst, rpriv, rboot, rrt, rservices, rtokens, rrs = fixture()
    advance_all(rst, rpriv, rboot, rrt, rservices, rtokens, rrs, "recovery-1")
    rreg0 = get_registry(rrs, rrt["remote_registry_sha"])
    poison = append_raw(rservices["remote-c"], "remote-c", rreg0["slots"]["remote-c"], rtokens["remote-c"],
                        77, "f" * 64, "c" * 64, rreg0["registry_sha"])
    add("recovery_fixture_poisoned", poison == "APPENDED" and authority(rrt, rst, rboot, rservices, rrs).startswith("AUTHORITATIVE_QUORUM_2"))
    new_token = secrets.token_bytes(32)
    rreg1 = rotate_registry_credential(rrs, rreg0["registry_sha"], "remote-c", H(new_token))
    cpR, uR, lR, mR = prepare(rrt, rst, rpriv, rboot, rservices, rrs,
                              hashlib.sha256(b"recovery-2").hexdigest(), rreg1["registry_sha"])
    add("credential_rotation_checkpoint_commit", commit(rrt, rst, rboot, lR["authority_sha"], mR) == "COMMITTED")
    # A/B retain same credentials but must publish under the newly signed registry identity.
    add("rotation_publish_a", publish(rrt, rst, rboot, rservices, rtokens, rrs, "remote-a") == "APPENDED")
    add("rotation_publish_b", publish(rrt, rst, rboot, rservices, rtokens, rrs, "remote-b") == "APPENDED")
    # C service switches to the new credential identity only after local authority commits the new registry.
    rservices["remote-c"]["credential_hash"] = H(new_token); rtokens["remote-c"] = new_token
    add("poisoned_recovery_requires_rotated_credential",
        recover_poisoned(rrt, rst, rboot, rservices, new_token, rrs, "remote-c") == "APPENDED")
    add("poisoned_recovery_restores_three", authority(rrt, rst, rboot, rservices, rrs).startswith("AUTHORITATIVE_QUORUM_3"))
    old_token_result = append_raw(rservices["remote-c"], "remote-c", rreg1["slots"]["remote-c"], tokens["remote-c"],
                                  88, "a" * 64, "b" * 64, rreg1["registry_sha"])
    add("retired_remote_credential_rejected", old_token_result == "AUTH_FAIL")

    # Whole-world rollback remains a real counterexample if local + all remote stores + registry state rewind together.
    add("whole_modeled_domain_rollback_counterexample", authority(rt1, st, boot, services1, rs1).startswith("AUTHORITATIVE"))
    add("inherited_all_current_signer_compromise_counterexample", w98.stolen_all_dual_counterexample())

    passed = sum(row["pass"] for row in controls)
    return {
        "schema": "axm.flowing_compute.wave99.report/v1",
        "wave": 99,
        "source": SRC,
        "controls": {"passed": passed, "total": len(controls), "rows": controls},
        "synthetic_scaling": {
            "label": "SYNTHETIC single-process three-witness registry/quorum + full-store verification; not physical failure-domain, network latency, distributed-consensus, energy, monolith-compute, retained, incremental, or dormant-compute evidence",
            "rows": bench((1, 4, 8), rounds),
        },
        "counterexamples_preserved": [
            "All three remote witnesses are still modeled inside one Python process. Distinct service/credential/failure-domain identities are mechanically checked, but physical independence is not demonstrated.",
            "Two-of-three keeps authority with one unavailable OR one poisoned/stale witness, but one unavailable plus one non-current witness correctly loses quorum and HOLDs.",
            "Remote append credentials are symmetric test access-control tokens; historical remote records are content-addressed but are not independently public-key signed remote attestations.",
            "Compromise of enough local checkpoint signer secrets plus a remote quorum can still create a competing structurally valid world; quorum does not prove root judgment legitimacy or canonical authority.",
            "Rolling the local runtime, all three modeled remote stores, and registry state back together remains internally self-consistent.",
            "The registry transition here proves predecessor linkage and local-checkpoint binding for credential rotation; it does not yet prove a physically independent registry authority or real-provider credential lifecycle."
        ],
        "truth_boundary": [
            "Wave 99 directly repairs verifier PR #23 before physical deployment: slot->service->credential->failure-domain identity is registry-bound and unique, duplicate service aliasing is rejected, and a selected remote head must be the maximal record in the complete retained store.",
            "The current registry SHA is included in the Wave 98 signed checkpoint state binding, so changing only runtime registry metadata cannot silently retarget a committed checkpoint.",
            "A predecessor-linked registry successor can rotate one remote credential; after the new registry is signed into local authority, a poisoned witness can append an explicit recovery record without deleting the bad record.",
            "No fresh AXM/monolith workload is read because the newest verifier found authority-boundary defects that must be closed before stronger failure-domain claims.",
            "No merge, CANON promotion, automatic aesthetic/root judgment, energy, network, retained, incremental, or dormant-compute win is claimed."
        ],
        "next_gate": "Wave 100: deploy the exact registry/record/quorum contract across three genuinely separate processes/providers or devices with independently held credentials. Test real partition/reconnect, credential rotation, poisoned-witness recovery, stale-store restoration, two-provider compromise, and durable anti-rollback of each provider's maximal head. Keep whole-domain rollback and signer-compromise counterexamples visible; do not call modeled identity fields physical independence."
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
