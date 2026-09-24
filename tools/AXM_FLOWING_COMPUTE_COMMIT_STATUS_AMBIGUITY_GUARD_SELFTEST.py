#!/usr/bin/env python3
"""Wave 109 adversarial/self-test for fail-closed commit-status ambiguity."""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

import AXM_FLOWING_COMPUTE_COMMIT_STATUS_AMBIGUITY_GUARD as w
import AXM_FLOWING_COMPUTE_COMMITTED_HISTORY_MANIFEST as w108
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w104


g = w.g
q = w.q


def need(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def row_at_seq(store: dict, seq: int):
    for sha, body in store.items():
        if isinstance(body, dict) and body.get("seq") == seq:
            return sha, body
    raise KeyError(seq)


def new_world():
    st, priv, boot, rt, services, tokens, rs = q.fixture()
    ts = {}
    cs = g.new_certificate_store()
    domain = w104.new_certificate_witness_domain()
    bs = {}
    w.adopt_genesis(rt, st, boot, services, rs, cs, domain, bs)
    return st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs


def run() -> dict:
    controls = []
    add = lambda name, value, detail=None: controls.append(
        {"name": name, "pass": bool(value), **({"detail": detail} if detail is not None else {})}
    )

    add(
        "exact_sources",
        w.SRC["wave108_builder_head"] == "7573e1e97d026ed07065fcca46cc0d88a26e64b5"
        and w.SRC["wave108_tested_source_commit"] == "7b9ec8548bde69df1d8971567aaf04abd0fa2e5c"
        and w.SRC["wave108_tool_blob"] == "629318c9645649a29d7a4d4c97f106a0ba958f6d"
        and w.SRC["wave108_selftest_blob"] == "aeac803084fc05e82c626bb830cee48146c710e2"
        and w.SRC["verifier_pr"] == 33
        and w.SRC["verifier_head"] == "49a8bfe61d7e062c52e419d9670cb95e41730e98"
        and w.SRC["verifier_ci_head"] == "d2d5851a1bf3088d1d2c96af909777bc6ea2ed6f"
        and w.SRC["verifier_evidence_blob"] == "b69e34546378a0e7a38f550e89afb926a8909e21"
        and w.SRC["verifier_repro_blob"] == "196482bc43391d151508f70fa176f20ea7e8e72a"
        and w.SRC["verifier_ci_run"] == 35198901311
        and w.SRC["verifier_ci_normal_job"] == 105128625588
        and w.SRC["verifier_ci_optimized_job"] == 105128625455,
    )

    # Positive path: genesis -> epoch1 -> epoch2 remains authoritative and cross-evidence clean.
    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world()
    genesis_state = w.commit_status_state(st, boot, rt, rs, bs)
    add(
        "genesis_cross_evidence_valid",
        genesis_state["status"] == w.HISTORY_VALID
        and genesis_state.get("committed_count") == 0
        and w.authority(rt, st, boot, services, rs, cs, domain, bs)
        == "AUTHORITATIVE_GENESIS_MODELED",
        genesis_state,
    )

    w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs,
        "wave109-accepted-epoch1",
    )
    status1, link1, cp1 = q.current_local(rt, st, boot)
    need(status1 == "LOCAL_OK" and link1.get("epoch") == 1, f"bad epoch1 setup: {status1}")
    state1 = w.commit_status_state(st, boot, rt, rs, bs)
    add(
        "epoch1_manifest_and_binding_chain_agree",
        state1["status"] == w.HISTORY_VALID
        and state1.get("committed_count") == 1
        and state1.get("binding_chain_seqs") == [0, 1]
        and w.authority(rt, st, boot, services, rs, cs, domain, bs).startswith("AUTHORITATIVE"),
        state1,
    )

    # Preserve legitimate epoch-1 pieces for the exact verifier #33 stale-quorum reproduction.
    rt1 = deepcopy(rt)
    services1 = deepcopy(services)
    cs1 = deepcopy(cs)
    witness_disks1 = domain.disk_snapshots()
    cert1_sha = cs1.get("head")
    binding1_sha = rt1.get("app_state_sha")
    need(isinstance(cert1_sha, str), "epoch1 certificate head missing")
    need(isinstance(binding1_sha, str), "epoch1 binding head missing")

    w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs,
        "wave109-accepted-epoch2",
    )
    status2, link2, cp2 = q.current_local(rt, st, boot)
    need(status2 == "LOCAL_OK" and link2.get("epoch") == 2, f"bad epoch2 setup: {status2}")
    state2 = w.commit_status_state(st, boot, rt, rs, bs)
    add(
        "epoch2_manifest_and_binding_chain_agree",
        state2["status"] == w.HISTORY_VALID
        and state2.get("committed_count") == 2
        and state2.get("binding_chain_seqs") == [0, 1, 2]
        and w.authority(rt, st, boot, services, rs, cs, domain, bs).startswith("AUTHORITATIVE"),
        state2,
    )

    cert2_sha = cs.get("head")
    binding2_sha = rt.get("app_state_sha")
    witness_disks2 = domain.disk_snapshots()
    need(isinstance(cert2_sha, str) and cert2_sha != cert1_sha, "epoch2 certificate head missing")
    need(isinstance(binding2_sha, str) and binding2_sha != binding1_sha, "epoch2 binding head missing")

    # Positive crash-window semantics: a legitimate prepare is intentionally ambiguous to readers;
    # commit can still finish from its carried transaction identities and then clears the HOLD.
    p = new_world()
    pst, ppriv, pboot, prt, pservices, ptokens, prs, pts, pcs, pdomain, pbs = p
    w.advance_all(
        pst, ppriv, pboot, prt, pservices, ptokens, prs, pts, pcs, pdomain, pbs,
        "wave109-prepare-window-epoch1",
    )
    cp_p, use_p, link_p, transition_p, body_p = w.prepare(
        prt, pst, ppriv, pboot, pservices, prs, pts, pcs, pdomain, pbs,
        "a" * 64,
    )
    prepared_state = w.commit_status_state(pst, pboot, prt, prs, pbs)
    prepared_authority = w.authority(prt, pst, pboot, pservices, prs, pcs, pdomain, pbs)
    add(
        "legitimate_prepare_is_unresolved_not_silently_authoritative",
        prepared_state["status"] == w.HISTORY_UNRESOLVED
        and prepared_authority == w.HOLD_UNRESOLVED,
        {"state": prepared_state, "authority": prepared_authority},
    )
    commit_result = w.commit(
        prt, pst, pboot, prs, pts,
        link_p["authority_sha"], transition_p, pbs,
    )
    committed_state = w.commit_status_state(pst, pboot, prt, prs, pbs)
    add(
        "commit_marker_clears_prepare_ambiguity",
        commit_result == "COMMITTED"
        and committed_state["status"] == w.HISTORY_VALID
        and committed_state.get("committed_count") == 2,
        committed_state,
    )

    # Exact verifier #33 semantic trigger: delete only marker seq2, retain epoch2 L/C/U + binding2,
    # and restore only the mutable runtime pointer to epoch1.
    attacked_st = deepcopy(st)
    commit2_sha, _commit2 = row_at_seq(attacked_st[w108.COMMIT_STORE], 2)
    high2_sha, _high2 = row_at_seq(attacked_st[w108.HIGH_WATER_STORE], 2)
    attacked_st[w108.COMMIT_STORE].pop(commit2_sha)
    attacked_st[w108.HIGH_WATER_STORE].pop(high2_sha)
    attacked_rt = deepcopy(rt1)

    wave108_reclassified = w108.committed_history_state(attacked_st, boot, attacked_rt)
    link2_sha = link2["authority_sha"]
    cp2_sha = link2["checkpoint_sha"]
    use2_sha = link2["use_sha"]
    need(link2_sha in attacked_st["L"], "attack lost epoch2 link")
    need(cp2_sha in attacked_st["C"], "attack lost epoch2 checkpoint")
    need(use2_sha in attacked_st["U"], "attack lost epoch2 use")
    need(binding2_sha in bs, "attack lost epoch2 binding")
    add(
        "pr33_wave108_reclassification_reproduced",
        wave108_reclassified["status"] == w108.HISTORY_VALID
        and link2_sha in wave108_reclassified.get("prepared_authority_shas", [])
        and wave108_reclassified.get("committed_count") == 1,
        wave108_reclassified,
    )

    # Reproduce verifier #33's stronger partial stale quorum. Remote A and the genuine cert-A disk
    # keep epoch2, but B+C are restored to real epoch1 snapshots; cert-A is then unavailable.
    attacked_services = deepcopy(services)
    attacked_services["remote-b"] = deepcopy(services1["remote-b"])
    attacked_services["remote-c"] = deepcopy(services1["remote-c"])

    attacked_cs = deepcopy(cs)
    attacked_cs["records"].pop(cert2_sha)
    attacked_cs["head"] = cert1_sha

    mixed_disks = deepcopy(witness_disks2)
    mixed_disks["cert-b"] = deepcopy(witness_disks1["cert-b"])
    mixed_disks["cert-c"] = deepcopy(witness_disks1["cert-c"])
    domain.restore_disks(mixed_disks)
    domain._endpoints["cert-a"].online = False

    wave108_stale_authority = w108.authority(
        attacked_rt, attacked_st, boot, attacked_services, rs, attacked_cs, domain, bs
    )
    wave109_attack_state = w.commit_status_state(attacked_st, boot, attacked_rt, rs, bs)
    wave109_attack_authority = w.authority(
        attacked_rt, attacked_st, boot, attacked_services, rs, attacked_cs, domain, bs
    )
    add(
        "pr33_wave108_stale_quorum_reproduced",
        wave108_stale_authority.startswith("AUTHORITATIVE"),
        wave108_stale_authority,
    )
    add(
        "pr33_wave109_retained_epoch2_is_unresolved",
        wave109_attack_state["status"] == w.HISTORY_UNRESOLVED
        and link2_sha in wave109_attack_state.get("extra_authority_shas", [])
        and binding2_sha in wave109_attack_state.get("extra_binding_shas", []),
        wave109_attack_state,
    )
    add(
        "pr33_wave109_stale_quorum_holds",
        wave109_attack_authority == w.HOLD_UNRESOLVED,
        wave109_attack_authority,
    )

    # Negative cases: removing different portions of the newer local transaction may not convert it
    # to harmless absence while any retained transaction evidence remains.
    damaged_link = deepcopy(attacked_st)
    damaged_link["L"].pop(link2_sha)
    link_loss_state = w.commit_status_state(damaged_link, boot, attacked_rt, rs, bs)
    add(
        "marker_tail_plus_newest_link_loss_still_unresolved",
        link_loss_state["status"] == w.HISTORY_UNRESOLVED
        and (cp2_sha in link_loss_state.get("extra_checkpoint_shas", [])
             or binding2_sha in link_loss_state.get("extra_binding_shas", [])),
        link_loss_state,
    )

    damaged_lcu = deepcopy(attacked_st)
    damaged_lcu["L"].pop(link2_sha)
    damaged_lcu["C"].pop(cp2_sha)
    damaged_lcu["U"].pop(use2_sha)
    binding_only_state = w.commit_status_state(damaged_lcu, boot, attacked_rt, rs, bs)
    add(
        "binding_body_alone_keeps_commit_status_unresolved",
        binding_only_state["status"] == w.HISTORY_UNRESOLVED
        and binding2_sha in binding_only_state.get("extra_binding_shas", []),
        binding_only_state,
    )

    damaged_checkpoint = deepcopy(attacked_st)
    damaged_checkpoint["C"].pop(cp2_sha)
    checkpoint_loss_state = w.commit_status_state(damaged_checkpoint, boot, attacked_rt, rs, bs)
    add(
        "retained_unmanifested_link_with_missing_checkpoint_fails_closed",
        checkpoint_loss_state["status"] in (w.HISTORY_INCOMPLETE, w.HISTORY_UNRESOLVED),
        checkpoint_loss_state,
    )

    damaged_use = deepcopy(attacked_st)
    damaged_use["U"].pop(use2_sha)
    use_loss_state = w.commit_status_state(damaged_use, boot, attacked_rt, rs, bs)
    add(
        "retained_unmanifested_link_with_missing_use_fails_closed",
        use_loss_state["status"] in (w.HISTORY_INCOMPLETE, w.HISTORY_UNRESOLVED),
        use_loss_state,
    )

    # Preserve the stronger counterexample rather than hide it: if both Wave-108 markers AND every
    # newer local L/C/U/binding body are erased, the local evidence becomes a genuine older prefix.
    # With the same partial stale quorum and newer cert-A unavailable, this one-process model cannot
    # prove that epoch2 ever committed.
    erased_bs = deepcopy(bs)
    erased_bs.pop(binding2_sha)
    prefix_state = w.commit_status_state(damaged_lcu, boot, attacked_rt, rs, erased_bs)
    prefix_authority = w.authority(
        attacked_rt, damaged_lcu, boot, attacked_services, rs, attacked_cs, domain, erased_bs
    )
    add(
        "counterexample_complete_newer_local_evidence_erasure_becomes_valid_old_prefix",
        prefix_state["status"] == w.HISTORY_VALID
        and prefix_state.get("committed_count") == 1,
        {"state": prefix_state, "authority": prefix_authority},
    )
    add(
        "counterexample_partial_stale_quorum_can_authorize_after_complete_local_prefix_erasure",
        prefix_authority.startswith("AUTHORITATIVE"),
        prefix_authority,
    )

    # Marker corruption is still Wave-108 corruption, not downgraded to Wave-109 ambiguity.
    corrupt_marker = deepcopy(st)
    c2sha, _ = row_at_seq(corrupt_marker[w108.COMMIT_STORE], 2)
    corrupt_marker[w108.COMMIT_STORE][c2sha]["authority_sha"] = "0" * 64
    corrupt_state = w.commit_status_state(corrupt_marker, boot, rt, rs, bs)
    add(
        "marker_hash_corruption_remains_incomplete",
        corrupt_state["status"] == w.HISTORY_INCOMPLETE,
        corrupt_state,
    )

    # No synthetic speed claim. A small correctness-only retained-depth walk checks that clean marker
    # and binding chains remain accepted beyond two epochs; it is explicitly not a benchmark.
    d = new_world()
    dst, dpriv, dboot, drt, dservices, dtokens, drs, dts, dcs, ddomain, dbs = d
    for i in range(1, 7):
        w.advance_all(
            dst, dpriv, dboot, drt, dservices, dtokens, drs, dts, dcs, ddomain, dbs,
            f"wave109-correctness-depth-{i}",
        )
    depth_state = w.commit_status_state(dst, dboot, drt, drs, dbs)
    add(
        "synthetic_correctness_depth6_only",
        depth_state["status"] == w.HISTORY_VALID
        and depth_state.get("committed_count") == 6
        and depth_state.get("binding_chain_seqs") == list(range(0, 7)),
        depth_state,
    )

    passed = sum(1 for item in controls if item["pass"])
    report = {
        "schema": "axm.flowing_compute.wave109.commit_status_ambiguity_guard.report/v1",
        "verdict": "PASS" if passed == len(controls) else "FAIL",
        "controls_passed": passed,
        "controls_total": len(controls),
        "controls": controls,
        "source_identity": dict(w.SRC),
        "truth_boundary": {
            "pr33_exact_attack_closed": wave109_attack_authority == w.HOLD_UNRESOLVED,
            "legitimate_prepare_is_also_unresolved": prepared_state["status"] == w.HISTORY_UNRESOLVED,
            "complete_newer_local_transaction_erasure_detected": False,
            "process_independence_proven": False,
            "physical_monotonic_storage_proven": False,
            "fresh_axm_or_monolith_workload_claim": False,
            "performance_or_energy_claim": False,
            "retained_incremental_or_dormant_compute_win_claim": False,
            "synthetic_depth6_is_correctness_only": True,
        },
        "counterexample": {
            "name": "marker-tail-plus-complete-newer-local-transaction-erasure",
            "local_history_after_erasure": prefix_state,
            "authority_with_partial_stale_quorum_and_newer_cert_a_unavailable": prefix_authority,
            "meaning": (
                "Wave109 can fail closed while any unmanifested L/C/U/binding evidence survives, "
                "but it cannot recover a commit fact after all same-domain newer transaction evidence "
                "and both marker tails are erased. An independent durable commit-decision boundary is "
                "still required."
            ),
        },
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out")
    args = parser.parse_args()
    report = run()
    text = json.dumps(report, sort_keys=True, indent=2)
    print(text)
    if args.json_out:
        path = Path(args.json_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
