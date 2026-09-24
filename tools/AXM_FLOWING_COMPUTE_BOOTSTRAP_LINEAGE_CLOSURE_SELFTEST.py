#!/usr/bin/env python3
"""Wave 106 adversarial/self-test for durable bootstrap-lineage closure."""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

import AXM_FLOWING_COMPUTE_BOOTSTRAP_LINEAGE_CLOSURE as w
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_ROOT_BINDING as w105
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w104

g = w.g
q = w.q


def expect_raises(fn) -> bool:
    try:
        fn()
    except Exception:
        return True
    return False


def run() -> dict:
    controls = []
    add = lambda name, value: controls.append({"name": name, "pass": bool(value)})

    add(
        "exact_sources",
        w.SRC["wave105_builder_head"] == "5c683032e0834e8a57e1bb780f624eb1cb312d3c"
        and w.SRC["wave105_tool_blob"] == "1e0e543c57f880c3e631619fa1859c24ace5ff79"
        and w.SRC["wave105_selftest_blob"] == "c6d39f469e98590823af3a576c4efbb18957d00b"
        and w.SRC["verifier_pr"] == 30
        and w.SRC["verifier_head"] == "ddefa0f3bc1aff5de804efaac1192433a6595ee1"
        and w.SRC["verifier_evidence_blob"] == "847fb896cb5d4d3c5ac7d7ab264c94833c49225b"
        and w.SRC["verifier_repro_blob"] == "975258a690ae9d8756797666be56ee29b5118051",
    )

    st, priv, boot, rt, services, tokens, rs = q.fixture()
    st_pre_adoption = deepcopy(st)
    rt_genesis = deepcopy(rt)
    services_genesis = deepcopy(services)
    ts = {}
    cs = g.new_certificate_store()
    domain = w104.new_certificate_witness_domain()
    bs = {}

    initial_user_app = rt["app_state_sha"]
    root0 = w.adopt_genesis(rt, st, boot, services, rs, cs, domain, bs)
    adoption, closure = w._records(st, boot, rs, bs)
    add("adoption_record_created", adoption is not None and closure is None)
    add("adoption_binds_exact_root", adoption["genesis_binding_sha"] == root0)
    add("adoption_binds_initial_user_app", adoption["genesis_user_app_state_sha"] == initial_user_app)
    add("adoption_binds_certificate_registry", adoption["certificate_witness_registry_sha"] == domain.registry_sha)
    add("adoption_store_append_only_single_record", len(st[w.STORE_KEY]) == 1)
    add(
        "genesis_authoritative",
        w.authority(rt, st, boot, services, rs, cs, domain, bs)
        == "AUTHORITATIVE_GENESIS_MODELED",
    )

    # Same-root genesis recovery is idempotent while no signed authority body exists.
    before_store = deepcopy(st[w.STORE_KEY])
    same_root = w.adopt_genesis(rt, st, boot, services, rs, cs, domain, bs)
    add("same_root_genesis_adoption_idempotent", same_root == root0 and st[w.STORE_KEY] == before_store)

    # A different legitimate witness registry cannot replace the adopted root even before closure.
    replacement_pre = w104.new_certificate_witness_domain()
    add(
        "different_root_blocked_after_first_adoption",
        expect_raises(lambda: w.adopt_genesis(
            rt, st, boot, services, rs, cs, replacement_pre, bs
        )),
    )

    # First accepted authority appends a one-way closure record into retained authority state.
    w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs,
        domain, bs, "wave106-accepted-epoch1"
    )
    original_authority = w.authority(rt, st, boot, services, rs, cs, domain, bs)
    adoption1, closure1 = w._records(st, boot, rs, bs)
    add("epoch1_authoritative", original_authority.startswith("AUTHORITATIVE"))
    add("closure_record_created", closure1 is not None)
    add("closure_binds_adoption", closure1["adoption_sha"] == adoption1["adoption_sha"])
    status1, link1, cp1 = q.current_local(rt, st, boot)
    add("closure_binds_first_authority", status1 == "LOCAL_OK" and closure1["first_authority_sha"] == link1["authority_sha"])
    add("closure_binds_first_checkpoint", closure1["first_checkpoint_sha"] == cp1["checkpoint_sha"])
    add("closure_binds_first_binding", closure1["first_binding_sha"] == rt["app_state_sha"])
    add("lineage_store_now_two_records", len(st[w.STORE_KEY]) == 2)

    original_certificate_head = cs.get("head")
    original_domain_heads = {
        slot: sorted(rec["certificate_seq"] for rec in ep.records.values())
        for slot, ep in domain._endpoints.items()
    }
    original_signed_checkpoint_count = len(st.get("C", {}))
    original_authority_body_count = len(st.get("L", {}))

    # Reproduce verifier PR #30 against unchanged Wave 105 from the exact same accepted world.
    attacked_rt = deepcopy(rt_genesis)
    attacked_services = deepcopy(services_genesis)
    attacked_cs = g.new_certificate_store()
    attacked_bs = deepcopy(bs)
    replacement_domain = w104.new_certificate_witness_domain()
    wave105_replacement_root = w105.adopt_genesis(
        attacked_rt, st, boot, attacked_services, rs, attacked_cs,
        replacement_domain, attacked_bs
    )
    wave105_false = w105.authority(
        attacked_rt, st, boot, attacked_services, rs, attacked_cs,
        replacement_domain, attacked_bs
    )
    add(
        "pr30_wave105_false_parallel_genesis_reproduced",
        wave105_false == "AUTHORITATIVE_GENESIS_MODELED"
        and wave105_replacement_root != root0,
    )

    # The exact post-history re-entry attempt now fails against the durable adoption/closure record.
    blocked_rt = deepcopy(rt_genesis)
    blocked_services = deepcopy(services_genesis)
    blocked_cs = g.new_certificate_store()
    blocked_bs = deepcopy(bs)
    replacement_domain2 = w104.new_certificate_witness_domain()
    add(
        "pr30_wave106_readoption_blocked",
        expect_raises(lambda: w.adopt_genesis(
            blocked_rt, st, boot, blocked_services, rs, blocked_cs,
            replacement_domain2, blocked_bs
        )),
    )
    add(
        "pr30_wave106_parallel_genesis_not_authoritative",
        not w.authority(
            blocked_rt, st, boot, blocked_services, rs, blocked_cs,
            replacement_domain2, blocked_bs
        ).startswith("AUTHORITATIVE"),
    )

    # Even the original root cannot turn a saved genesis pointer into authority after closure.
    same_root_stale_rt = deepcopy(rt_genesis)
    same_root_stale_services = deepcopy(services_genesis)
    same_root_stale_cs = g.new_certificate_store()
    same_root_stale_bs = deepcopy(bs)
    same_root_result = w.authority(
        same_root_stale_rt, st, boot, same_root_stale_services, rs,
        same_root_stale_cs, domain, same_root_stale_bs
    )
    add("same_root_saved_genesis_blocked_after_closure", same_root_result == "HOLD_BOOTSTRAP_CLOSED")
    add(
        "same_root_saved_genesis_readoption_blocked",
        expect_raises(lambda: w.adopt_genesis(
            same_root_stale_rt, st, boot, same_root_stale_services, rs,
            same_root_stale_cs, domain, same_root_stale_bs
        )),
    )

    # Original accepted world and all original external evidence remain untouched.
    original_after = w.authority(rt, st, boot, services, rs, cs, domain, bs)
    domain_heads_after = {
        slot: sorted(rec["certificate_seq"] for rec in ep.records.values())
        for slot, ep in domain._endpoints.items()
    }
    add("original_world_remains_authoritative", original_after.startswith("AUTHORITATIVE"))
    add("original_certificate_store_unchanged", cs.get("head") == original_certificate_head)
    add("original_certificate_witnesses_unchanged", domain_heads_after == original_domain_heads)
    add("signed_checkpoint_bodies_preserved", len(st.get("C", {})) == original_signed_checkpoint_count)
    add("authority_bodies_preserved", len(st.get("L", {})) == original_authority_body_count)

    # Loss/tamper of the Wave-106 store fails closed when retained authority bodies remain.
    missing_store_st = deepcopy(st)
    del missing_store_st[w.STORE_KEY]
    missing_store_verdict = w.authority(
        rt, missing_store_st, boot, services, rs, cs, domain, bs
    )
    add(
        "missing_lineage_store_with_history_holds",
        missing_store_verdict == "HOLD_BOOTSTRAP_LINEAGE_MISSING_WITH_AUTHORITY_HISTORY",
    )
    add(
        "missing_lineage_store_cannot_rebootstrap",
        expect_raises(lambda: w.adopt_genesis(
            deepcopy(rt_genesis), missing_store_st, boot, deepcopy(services_genesis),
            rs, g.new_certificate_store(), w104.new_certificate_witness_domain(),
            deepcopy(bs)
        )),
    )

    tampered_st = deepcopy(st)
    adoption_sha = adoption1["adoption_sha"]
    tampered_st[w.STORE_KEY][adoption_sha]["certificate_witness_registry_sha"] = replacement_domain2.registry_sha
    add(
        "tampered_adoption_record_holds",
        w.authority(rt, tampered_st, boot, services, rs, cs, domain, bs)
        == "HOLD_BOOTSTRAP_LINEAGE_INVALID",
    )

    # Crash-window simulation: bypass the Wave-106 post-commit closure append.
    cst, cpriv, cboot, crt, cservices, ctokens, crs = q.fixture()
    cts = {}
    ccs = g.new_certificate_store()
    cdomain = w104.new_certificate_witness_domain()
    cbs = {}
    w.adopt_genesis(crt, cst, cboot, cservices, crs, ccs, cdomain, cbs)
    _cp, _use, clink, ctransition, _body = w.prepare(
        crt, cst, cpriv, cboot, cservices, crs, cts, ccs, cdomain, cbs,
        target_user_app_state_sha="1" * 64
    )
    lower_only_commit = w105.commit(
        crt, cst, cboot, crs, cts, clink["authority_sha"], ctransition, cbs
    )
    add("simulated_crash_window_lower_commit_occurs", lower_only_commit == "COMMITTED")
    add(
        "missing_postcommit_closure_fails_closed",
        w.authority(crt, cst, cboot, cservices, crs, ccs, cdomain, cbs)
        == "HOLD_BOOTSTRAP_CLOSURE_MISSING",
    )

    # Conservative migration guard: a structurally valid prepared authority body in retained st
    # closes re-bootstrap even when no Wave-106 lineage store exists. This may trade availability
    # for safety after an abandoned pre-Wave-106 prepare.
    mst, mpriv, mboot, mrt, mservices, mtokens, mrs = q.fixture()
    mrt_genesis = deepcopy(mrt)
    mservices_genesis = deepcopy(mservices)
    mts = {}
    mcs = g.new_certificate_store()
    mdomain = w104.new_certificate_witness_domain()
    mbs = {}
    w105.adopt_genesis(mrt, mst, mboot, mservices, mrs, mcs, mdomain, mbs)
    w105.prepare(
        mrt, mst, mpriv, mboot, mservices, mrs, mts, mcs, mdomain, mbs,
        target_user_app_state_sha="2" * 64
    )
    add("prepared_uncommitted_authority_body_retained", len(mst.get("L", {})) > 0 and w.STORE_KEY not in mst)
    add(
        "prepared_uncommitted_history_conservatively_blocks_rebootstrap",
        expect_raises(lambda: w.adopt_genesis(
            mrt_genesis, mst, mboot, mservices_genesis, mrs,
            g.new_certificate_store(), w104.new_certificate_witness_domain(), deepcopy(mbs)
        )),
    )

    # Normal forward progress still works after closure and reuses the single closure record.
    w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs,
        domain, bs, "wave106-accepted-epoch2"
    )
    add("epoch2_forward_progress_authoritative", w.authority(rt, st, boot, services, rs, cs, domain, bs).startswith("AUTHORITATIVE"))
    _adoption2, closure2 = w._records(st, boot, rs, bs)
    add("closure_remains_single_after_epoch2", closure2["closure_sha"] == closure1["closure_sha"] and len(st[w.STORE_KEY]) == 2)

    # Preserved failure: restore the entire retained authority store to a pre-adoption image.
    # With every Wave-106 lineage/authority record erased together, this one-process model has no
    # external monotonic fact that can distinguish the restored world from first boot.
    rolled_st = deepcopy(st_pre_adoption)
    rolled_rt = deepcopy(rt_genesis)
    rolled_services = deepcopy(services_genesis)
    rolled_cs = g.new_certificate_store()
    rolled_domain = w104.new_certificate_witness_domain()
    rolled_bs = {}
    rolled_root = w.adopt_genesis(
        rolled_rt, rolled_st, boot, rolled_services, rs, rolled_cs, rolled_domain, rolled_bs
    )
    rolled_verdict = w.authority(
        rolled_rt, rolled_st, boot, rolled_services, rs, rolled_cs, rolled_domain, rolled_bs
    )
    add(
        "whole_retained_store_rollback_counterexample_preserved",
        rolled_root != root0 and rolled_verdict == "AUTHORITATIVE_GENESIS_MODELED",
    )

    passed = sum(row["pass"] for row in controls)
    return {
        "schema": "axm.flowing_compute.wave106.report/v1",
        "wave": 106,
        "source": w.SRC,
        "controls": {"passed": passed, "total": len(controls), "rows": controls},
        "pr30_reproduction": {
            "wave105_parallel_genesis": wave105_false,
            "wave106_parallel_genesis": w.authority(
                blocked_rt, st, boot, blocked_services, rs, blocked_cs,
                replacement_domain2, blocked_bs
            ),
            "same_root_saved_genesis": same_root_result,
            "original_world_after_attack": original_after,
        },
        "lineage": {
            "store_key": w.STORE_KEY,
            "adoption_sha": adoption1["adoption_sha"],
            "bootstrap_id": adoption1["bootstrap_id"],
            "genesis_binding_sha": adoption1["genesis_binding_sha"],
            "closure_sha": closure1["closure_sha"],
            "first_authority_sha": closure1["first_authority_sha"],
            "first_checkpoint_sha": closure1["first_checkpoint_sha"],
            "certificate_witness_registry_sha": adoption1["certificate_witness_registry_sha"],
        },
        "counterexamples_preserved": [
            "Initial Wave-106 root selection is still a local configuration/bootstrap trust boundary; the adoption record is content-addressed but not independently signed or physically monotonic.",
            "Rolling back or substituting the entire retained authority state st to a pre-adoption image removes the Wave-106 memory and can make a fresh genesis root look authoritative again.",
            "A crash after the lower authority commit but before the Wave-106 closure append can cause a safe availability HOLD; this model does not provide an atomic durable transaction across those writes.",
            "A prepared-but-uncommitted retained authority body conservatively blocks re-bootstrap if the Wave-106 store is absent; that is an explicit safety-over-availability migration tradeoff.",
            "Stealing symmetric credentials for already-bound witness endpoints remains outside this repair.",
            "All authority stores, remotes, certificate witnesses, credentials, and failure-domain labels still live inside one Python process; there is no OS/device/provider independence claim.",
            "Certificate-witness registry rotation remains unsupported; Wave 106 preserves the Wave-105 fixed-root policy.",
        ],
        "truth_boundary": [
            "Wave 106 repairs verifier PR #30 for the same retained authority state by making first root adoption and first accepted-authority closure append-only facts inside st, independent of caller-supplied runtime and certificate-store views.",
            "Fresh empty certificate stores, saved genesis runtime pointers, and fresh legitimate certificate-witness domains cannot reopen bootstrap while the retained Wave-106 authority state is present.",
            "Loss of the Wave-106 lineage records while signed authority bodies remain fails closed; the system does not silently invent a replacement root.",
            "No fresh AXM/monolith workload, performance, energy, retained-compute, incremental-compute, dormant-compute, network, process, device, or provider-independence result is claimed.",
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
