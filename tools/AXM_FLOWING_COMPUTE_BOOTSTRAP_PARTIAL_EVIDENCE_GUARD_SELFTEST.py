#!/usr/bin/env python3
"""Wave 107 adversarial/self-test for fail-closed partial authority evidence."""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

import AXM_FLOWING_COMPUTE_BOOTSTRAP_PARTIAL_EVIDENCE_GUARD as w
import AXM_FLOWING_COMPUTE_BOOTSTRAP_LINEAGE_CLOSURE as w106
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w104


g = w.g
q = w.q


def expect_raises(fn) -> bool:
    try:
        fn()
    except Exception:
        return True
    return False


def fresh_domain_state(rt: dict, services: dict) -> tuple:
    return (
        deepcopy(rt),
        deepcopy(services),
        g.new_certificate_store(),
        w104.new_certificate_witness_domain(),
        {},
    )


def run() -> dict:
    controls = []
    add = lambda name, value: controls.append({"name": name, "pass": bool(value)})

    add(
        "exact_sources",
        w.SRC["wave106_builder_head"] == "eb8ac4d23a3399af82885afc435dae6de0aa28b6"
        and w.SRC["wave106_tested_source_commit"] == "652f3da1acd88e02f085cf1ace92c6bfb412e065"
        and w.SRC["wave106_tool_blob"] == "daaa9e33b3418138972701bac1cecca928378a17"
        and w.SRC["wave106_selftest_blob"] == "3da3ebd06bed5b756ca58d5b77ac9eb5de12bbc6"
        and w.SRC["verifier_pr"] == 31
        and w.SRC["verifier_head"] == "06beba92c188879d65ebd970bbaaa529ca095660"
        and w.SRC["verifier_evidence_blob"] == "d0e6c230bc11f04811748d36b3400ca597c9ffc6"
        and w.SRC["verifier_repro_blob"] == "c3342d4561ba10ea8deaeb878ffead870edde252",
    )

    st, priv, boot, rt, services, tokens, rs = q.fixture()
    st_pre_adoption = deepcopy(st)
    rt_genesis = deepcopy(rt)
    services_genesis = deepcopy(services)
    ts = {}
    cs = g.new_certificate_store()
    domain = w104.new_certificate_witness_domain()
    bs = {}

    initial_guard = w.retained_authority_history_state(st, boot)
    add("fresh_fixture_has_no_authority_history", initial_guard["status"] == w.HISTORY_NONE)

    root0 = w.adopt_genesis(rt, st, boot, services, rs, cs, domain, bs)
    add(
        "genesis_still_authoritative",
        w.authority(rt, st, boot, services, rs, cs, domain, bs)
        == "AUTHORITATIVE_GENESIS_MODELED",
    )
    add(
        "adoption_without_authority_rows_remains_history_none",
        w.retained_authority_history_state(st, boot)["status"] == w.HISTORY_NONE,
    )

    w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs,
        domain, bs, "wave107-accepted-epoch1"
    )
    original_verdict = w.authority(rt, st, boot, services, rs, cs, domain, bs)
    add("epoch1_authoritative", original_verdict.startswith("AUTHORITATIVE"))

    status, link, cp = q.current_local(rt, st, boot)
    if status != "LOCAL_OK":
        raise AssertionError(f"expected LOCAL_OK, got {status}")
    authority_sha = link["authority_sha"]
    checkpoint_sha = cp["checkpoint_sha"]
    use_sha = link["use_sha"]
    valid_history = w.retained_authority_history_state(st, boot)
    add(
        "complete_retained_history_classified_valid",
        valid_history["status"] == w.HISTORY_VALID
        and authority_sha in valid_history["resolved_links"],
    )

    # Exact PR #31 reproduction against unchanged Wave 106.
    attacked106 = deepcopy(st)
    del attacked106[w106.STORE_KEY]
    del attacked106["U"][use_sha]
    add(
        "pr31_wave106_scanner_drops_unresolved_link",
        w106._retained_authority_evidence(attacked106, boot) == [],
    )
    a_rt, a_services, a_cs, a_domain, a_bs = fresh_domain_state(rt_genesis, services_genesis)
    replacement_root = w106.adopt_genesis(
        a_rt, attacked106, boot, a_services, rs, a_cs, a_domain, a_bs
    )
    wave106_false = w106.authority(
        a_rt, attacked106, boot, a_services, rs, a_cs, a_domain, a_bs
    )
    add(
        "pr31_wave106_false_parallel_genesis_reproduced",
        replacement_root != root0 and wave106_false == "AUTHORITATIVE_GENESIS_MODELED",
    )

    # Same retained-world attack under Wave 107 must be corruption/HOLD, never absence.
    attacked107 = deepcopy(st)
    del attacked107[w106.STORE_KEY]
    del attacked107["U"][use_sha]
    guard107 = w.retained_authority_history_state(attacked107, boot)
    b_rt, b_services, b_cs, b_domain, b_bs = fresh_domain_state(rt_genesis, services_genesis)
    add(
        "pr31_partial_use_loss_classified_incomplete",
        guard107["status"] == w.HISTORY_INCOMPLETE
        and any(row["sha"] == authority_sha for row in guard107["unresolved_links"]),
    )
    add(
        "pr31_wave107_readoption_blocked",
        expect_raises(lambda: w.adopt_genesis(
            b_rt, attacked107, boot, b_services, rs, b_cs, b_domain, b_bs
        )),
    )
    add(
        "pr31_wave107_parallel_genesis_holds",
        w.authority(
            b_rt, attacked107, boot, b_services, rs, b_cs, b_domain, b_bs
        ) == w.HOLD_INCOMPLETE,
    )

    # Delete one signed checkpoint body while retaining its authority link.
    missing_cp = deepcopy(st)
    del missing_cp["C"][checkpoint_sha]
    add(
        "missing_checkpoint_body_fails_closed",
        w.retained_authority_history_state(missing_cp, boot)["status"] == w.HISTORY_INCOMPLETE,
    )
    c_rt, c_services, c_cs, c_domain, c_bs = fresh_domain_state(rt_genesis, services_genesis)
    add(
        "missing_checkpoint_cannot_rebootstrap",
        expect_raises(lambda: w.adopt_genesis(
            c_rt, missing_cp, boot, c_services, rs, c_cs, c_domain, c_bs
        )),
    )

    # Delete the authority link itself while checkpoint/use evidence remains.
    missing_link = deepcopy(st)
    missing_link["L"].pop(authority_sha)
    link_guard = w.retained_authority_history_state(missing_link, boot)
    add(
        "checkpoint_use_without_link_is_incomplete_not_none",
        link_guard["status"] == w.HISTORY_INCOMPLETE
        and (link_guard["checkpoint_count"] or link_guard["use_count"]),
    )

    # Key/body mismatch and store-shape corruption must fail closed before lower authority code.
    tampered_link = deepcopy(st)
    tampered_link["L"][authority_sha]["authority_sha"] = "0" * 64
    add(
        "authority_link_key_body_mismatch_fails_closed",
        w.retained_authority_history_state(tampered_link, boot)["status"] == w.HISTORY_INCOMPLETE,
    )
    malformed_store = deepcopy(st)
    malformed_store["U"] = []
    malformed_guard = w.retained_authority_history_state(malformed_store, boot)
    add(
        "authority_store_shape_corruption_fails_closed",
        malformed_guard["status"] == w.HISTORY_INCOMPLETE
        and w.authority(rt, malformed_store, boot, services, rs, cs, domain, bs) == w.HOLD_INCOMPLETE,
    )

    # Losing only the Wave-106 lineage store remains a distinct complete-history HOLD.
    missing_lineage = deepcopy(st)
    del missing_lineage[w106.STORE_KEY]
    complete_without_lineage = w.retained_authority_history_state(missing_lineage, boot)
    add(
        "missing_lineage_with_complete_authority_history_stays_detectable",
        complete_without_lineage["status"] == w.HISTORY_VALID,
    )
    add(
        "missing_lineage_complete_history_uses_wave106_hold",
        w.authority(rt, missing_lineage, boot, services, rs, cs, domain, bs)
        == "HOLD_BOOTSTRAP_LINEAGE_MISSING_WITH_AUTHORITY_HISTORY",
    )

    # Binding loss is already fail-closed in Wave 106 lineage verification; Wave 107 preserves it.
    missing_binding = deepcopy(bs)
    current_binding_sha = rt["app_state_sha"]
    missing_binding.pop(current_binding_sha, None)
    binding_loss_verdict = w.authority(
        rt, st, boot, services, rs, cs, domain, missing_binding
    )
    add(
        "binding_lineage_loss_remains_fail_closed",
        not binding_loss_verdict.startswith("AUTHORITATIVE"),
    )

    # Normal forward progress still works with the stricter preflight guard.
    w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs,
        domain, bs, "wave107-accepted-epoch2"
    )
    add(
        "epoch2_forward_progress_authoritative",
        w.authority(rt, st, boot, services, rs, cs, domain, bs).startswith("AUTHORITATIVE"),
    )
    add(
        "epoch2_history_still_valid",
        w.retained_authority_history_state(st, boot)["status"] == w.HISTORY_VALID,
    )

    # Preserved counterexample: whole retained-state rollback to pre-adoption removes every local fact.
    rolled_st = deepcopy(st_pre_adoption)
    rolled_rt = deepcopy(rt_genesis)
    rolled_services = deepcopy(services_genesis)
    rolled_cs = g.new_certificate_store()
    rolled_domain = w104.new_certificate_witness_domain()
    rolled_bs = {}
    rolled_root = w.adopt_genesis(
        rolled_rt, rolled_st, boot, rolled_services, rs,
        rolled_cs, rolled_domain, rolled_bs
    )
    rolled_verdict = w.authority(
        rolled_rt, rolled_st, boot, rolled_services, rs,
        rolled_cs, rolled_domain, rolled_bs
    )
    add(
        "whole_retained_store_rollback_counterexample_preserved",
        rolled_root != root0 and rolled_verdict == "AUTHORITATIVE_GENESIS_MODELED",
    )

    passed = sum(row["pass"] for row in controls)
    return {
        "schema": "axm.flowing_compute.wave107.report/v1",
        "wave": 107,
        "source": w.SRC,
        "controls": {"passed": passed, "total": len(controls), "rows": controls},
        "pr31_reproduction": {
            "wave106_parallel_genesis": wave106_false,
            "wave107_guard_status": guard107["status"],
            "wave107_parallel_genesis": w.authority(
                b_rt, attacked107, boot, b_services, rs, b_cs, b_domain, b_bs
            ),
            "preserved_authority_link_sha": authority_sha,
            "preserved_checkpoint_sha": checkpoint_sha,
            "deleted_signer_use_sha": use_sha,
        },
        "counterexamples_preserved": [
            "Rolling back or substituting the entire retained authority state to a pre-adoption image still removes every local bootstrap/history fact and can make a fresh genesis look valid in this one-process model.",
            "A prepared-but-uncommitted authority body remains conservatively bootstrap-closing; this is an explicit safety-over-availability tradeoff.",
            "Crash atomicity between lower commit and Wave-106 closure persistence remains unsolved.",
            "All stores/endpoints/credentials remain Python objects in one process; no OS/device/provider independence is claimed.",
            "Symmetric modeled witness credentials and fixed certificate-witness root limitations remain unchanged.",
        ],
        "truth_boundary": [
            "Wave 107 repairs verifier PR #31 by mechanically separating no retained authority history from retained authority history that is incomplete or corrupt.",
            "Loss of one signer-use body, one signed checkpoint body, an authority-link body, link key/body identity, or authority-store shape now fails closed at the bootstrap guard.",
            "Wave 107 does not claim that local content-addressed stores are physically monotonic or independently durable.",
            "No fresh AXM/monolith workload, performance, energy, network, retained/incremental/dormant-compute, process, device, or provider-independence result is claimed.",
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
