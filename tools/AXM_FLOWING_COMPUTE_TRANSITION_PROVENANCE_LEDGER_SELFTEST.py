#!/usr/bin/env python3
"""Wave 111 exact-API positive/negative self-test.

Reproduces verifier PR #35's two Wave-110 failures first, then requires the exact-transition
provenance ledger and semantic replay to fail closed. Synthetic retained depth is correctness-only;
there is no performance or energy benchmark in this self-test.
"""
from __future__ import annotations

import argparse
import json
from copy import deepcopy

import AXM_FLOWING_COMPUTE_TRANSITION_PROVENANCE_LEDGER as w
import AXM_FLOWING_COMPUTE_TRANSITION_EVIDENCE_GUARD as w110
import AXM_FLOWING_COMPUTE_COMMITTED_HISTORY_MANIFEST as w108
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w104
import AXM_FLOWING_COMPUTE_REMOTE_REGISTRY_MONOTONICITY as w100

q = w.q
g = w.g


def new_world():
    st, priv, boot, rt, services, tokens, rs = q.fixture()
    ts = {}
    cs = g.new_certificate_store()
    domain = w104.new_certificate_witness_domain()
    bs = {}
    w.adopt_genesis(rt, st, boot, services, rs, ts, cs, domain, bs)
    return st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs


def check(report: dict, name: str, ok: bool, detail=None):
    report["controls"].append({"name": name, "ok": bool(ok), "detail": detail})
    if not ok:
        report["failed"] += 1


def provenance_row_at_seq(st: dict, seq: int):
    rows = w._provenance_rows(st)
    assert rows is not None
    for sha, body in rows:
        if body.get("seq") == seq:
            return sha, body
    raise KeyError(seq)


def primary_substitution_case() -> dict:
    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world()
    cp1, _use1, link1, tr1_sha, _binding1, _cert1_sha, _cert1 = w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs,
        "wave111-pr35-primary",
    )
    legitimate = w100.get_transition(ts, tr1_sha)
    ts.pop(tr1_sha)

    fake = deepcopy(legitimate)
    fake["target_app_state_sha"] = "11" * 32
    fake["target_registry_sha"] = "22" * 32
    fake["target_state_sha"] = q.binding(fake["target_app_state_sha"], fake["target_registry_sha"])
    fake["current_registry_sha"] = "33" * 32
    fake["current_generation"] = 700
    fake["target_generation"] = 999
    fake["transition_kind"] = "VERIFIER_SYNTHETIC_SUBSTITUTION"
    fake["changed_slots"] = ["not-a-real-remote-slot"]
    fake["changed_fields"] = {"not-a-real-remote-slot": ["imaginary_field"]}
    fake["transition_sha"] = ""
    fake = w100._seal(fake, "transition_sha")
    fake_sha = w100.put_transition(ts, fake)

    old_state = w110.commit_status_state(st, boot, rt, rs, bs, ts)
    old_authority = w110.authority(rt, st, boot, services, rs, ts, cs, domain, bs)
    new_state = w.commit_status_state(st, boot, rt, rs, bs, ts)
    new_authority = w.authority(rt, st, boot, services, rs, ts, cs, domain, bs)
    return {
        "committed_authority_sha": link1["authority_sha"],
        "committed_checkpoint_sha": cp1["checkpoint_sha"],
        "removed_transition_sha": tr1_sha,
        "fake_transition_sha": fake_sha,
        "wave110_state": old_state,
        "wave110_authority": old_authority,
        "wave111_state": new_state,
        "wave111_authority": new_authority,
    }


def secondary_none_short_circuit_case() -> dict:
    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world()
    genesis_st = deepcopy(st)
    genesis_rt = deepcopy(rt)
    genesis_services = deepcopy(services)
    genesis_cs = deepcopy(cs)
    genesis_disks = domain.disk_snapshots()
    genesis_bs = deepcopy(bs)

    cp1, _use1, link1, tr1_sha, _binding1, _cert1_sha, _cert1 = w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs,
        "wave111-pr35-secondary",
    )
    retained = w100.get_transition(ts, tr1_sha)

    attacked_st = deepcopy(genesis_st)
    attacked_st.pop(w108.COMMIT_STORE, None)
    attacked_st.pop(w108.HIGH_WATER_STORE, None)
    attacked_rt = deepcopy(genesis_rt)
    attacked_services = deepcopy(genesis_services)
    attacked_cs = deepcopy(genesis_cs)
    attacked_bs = deepcopy(genesis_bs)
    domain.restore_disks(genesis_disks)

    old_state = w110.commit_status_state(attacked_st, boot, attacked_rt, rs, attacked_bs, ts)
    old_authority = w110.authority(
        attacked_rt, attacked_st, boot, attacked_services, rs, ts,
        attacked_cs, domain, attacked_bs,
    )
    new_state = w.commit_status_state(attacked_st, boot, attacked_rt, rs, attacked_bs, ts)
    new_authority = w.authority(
        attacked_rt, attacked_st, boot, attacked_services, rs, ts,
        attacked_cs, domain, attacked_bs,
    )
    return {
        "retained_transition_sha": tr1_sha,
        "retained_transition_names_accepted_epoch": (
            retained.get("target_authority_sha") == link1["authority_sha"]
            and retained.get("target_checkpoint_sha") == cp1["checkpoint_sha"]
        ),
        "wave110_state": old_state,
        "wave110_authority": old_authority,
        "wave111_state": new_state,
        "wave111_authority": new_authority,
    }


def run() -> dict:
    report = {
        "schema": "axm.flowing-compute.wave111.transition-provenance-ledger-selftest/v1",
        "truth_boundary": {
            "synthetic_depth_is_correctness_only": True,
            "performance_claim": False,
            "energy_claim": False,
            "retained_incremental_dormant_compute_claim": False,
            "os_process_or_provider_independence_claim": False,
            "same_domain_provenance_store": True,
        },
        "controls": [],
        "failed": 0,
    }

    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world()
    genesis = w.commit_status_state(st, boot, rt, rs, bs, ts)
    check(report, "genesis-valid", genesis.get("status") == w.HISTORY_VALID, genesis)
    check(report, "genesis-provenance-empty", st.get(w.PROVENANCE_STORE) == {}, st.get(w.PROVENANCE_STORE))

    w.advance_all(st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs, "wave111-e1")
    s1 = w.commit_status_state(st, boot, rt, rs, bs, ts)
    check(report, "epoch1-valid", s1.get("status") == w.HISTORY_VALID, s1)
    check(report, "epoch1-provenance-count", len(w._provenance_rows(st) or []) == 1, s1)
    check(report, "epoch1-authoritative", w.authority(rt, st, boot, services, rs, ts, cs, domain, bs).startswith("AUTHORITATIVE"))

    w.advance_all(st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs, "wave111-e2")
    s2 = w.commit_status_state(st, boot, rt, rs, bs, ts)
    check(report, "epoch2-valid", s2.get("status") == w.HISTORY_VALID, s2)
    check(report, "epoch2-provenance-count", len(w._provenance_rows(st) or []) == 2, s2)
    check(report, "epoch2-exact-transition-count", len(s2.get("expected_transition_shas", [])) == 2, s2)

    _cp3, _use3, link3, tr3, _body3 = w.prepare(
        rt, st, priv, boot, services, rs, ts, cs, domain, bs,
        target_user_app_state_sha="3" * 64,
    )
    prepared = w.commit_status_state(st, boot, rt, rs, bs, ts)
    check(report, "prepared-transition-is-unresolved", prepared.get("status") == w.HISTORY_UNRESOLVED, prepared)
    check(report, "prepared-transition-holds-authority", w.authority(rt, st, boot, services, rs, ts, cs, domain, bs) == w.HOLD_UNRESOLVED)
    c3 = w.commit(rt, st, boot, rs, ts, link3["authority_sha"], tr3, bs)
    after3 = w.commit_status_state(st, boot, rt, rs, bs, ts)
    check(report, "commit3-completes", c3 == "COMMITTED", c3)
    check(report, "commit3-provenance-settles", after3.get("status") == w.HISTORY_VALID, after3)

    stc, privc, bootc, rtc, svc, _tokc, rsc, tsc, csc, dc, bsc = new_world()
    _cpc, _usec, linkc, trc, _bodyc = w.prepare(
        rtc, stc, privc, bootc, svc, rsc, tsc, csc, dc, bsc,
        target_user_app_state_sha="4" * 64,
    )
    lower_commit = w110.commit(rtc, stc, bootc, rsc, tsc, linkc["authority_sha"], trc, bsc)
    crash_state = w.commit_status_state(stc, bootc, rtc, rsc, bsc, tsc)
    crash_authority = w.authority(rtc, stc, bootc, svc, rsc, tsc, csc, dc, bsc)
    check(report, "lower-commit-before-provenance-reproduced", lower_commit == "COMMITTED", lower_commit)
    check(report, "commit-to-provenance-crash-fails-closed", crash_state.get("status") == w.HISTORY_INCOMPLETE, crash_state)
    check(report, "commit-to-provenance-crash-holds-authority", crash_authority == w.HOLD_INCOMPLETE, crash_authority)

    primary = primary_substitution_case()
    report["verifier35_primary"] = primary
    check(report, "wave110-primary-failure-reproduced", primary["wave110_state"].get("status") == w110.HISTORY_VALID and primary["wave110_authority"].startswith("AUTHORITATIVE"), primary)
    check(report, "wave111-pins-exact-transition-sha", primary["wave111_state"].get("status") == w.HISTORY_INCOMPLETE, primary)
    check(report, "wave111-blocks-primary-stale-authority", primary["wave111_authority"] == w.HOLD_INCOMPLETE, primary)

    secondary = secondary_none_short_circuit_case()
    report["verifier35_secondary"] = secondary
    check(report, "wave110-secondary-failure-reproduced", secondary["retained_transition_names_accepted_epoch"] and secondary["wave110_state"].get("status") == w110.HISTORY_NONE and secondary["wave110_authority"].startswith("AUTHORITATIVE"), secondary)
    check(report, "wave111-none-still-inspects-transition-evidence", secondary["wave111_state"].get("status") == w.HISTORY_UNRESOLVED, secondary)
    check(report, "wave111-blocks-secondary-genesis-reentry", secondary["wave111_authority"] == w.HOLD_UNRESOLVED, secondary)

    sts, privs, boots, rts, svs, toks, rss, tss, css, ds, bss = new_world()
    _cps, _uses, _links, trs, _bodys, _certs, _certbodys = w.advance_all(
        sts, privs, boots, rts, svs, toks, rss, tss, css, ds, bss,
        "wave111-semantic-e1",
    )
    legit = w100.get_transition(tss, trs)
    tss.pop(trs)
    fake = deepcopy(legit)
    fake["target_app_state_sha"] = "aa" * 32
    fake["target_registry_sha"] = "bb" * 32
    fake["target_state_sha"] = q.binding(fake["target_app_state_sha"], fake["target_registry_sha"])
    fake["current_registry_sha"] = "cc" * 32
    fake["current_generation"] = 12
    fake["target_generation"] = 13
    fake["transition_kind"] = "FAKE"
    fake["changed_slots"] = []
    fake["changed_fields"] = {}
    fake["transition_sha"] = ""
    fake = w100._seal(fake, "transition_sha")
    fake_sha = w100.put_transition(tss, fake)
    old_prov_sha, old_prov = provenance_row_at_seq(sts, 1)
    sts[w.PROVENANCE_STORE].pop(old_prov_sha)
    new_prov = deepcopy(old_prov)
    new_prov["transition_sha"] = fake_sha
    new_prov["target_state_sha"] = fake["target_state_sha"]
    new_prov["current_registry_sha"] = fake["current_registry_sha"]
    new_prov["target_registry_sha"] = fake["target_registry_sha"]
    new_prov["transition_kind"] = fake["transition_kind"]
    new_prov_sha = w._sha(new_prov)
    sts[w.PROVENANCE_STORE][new_prov_sha] = new_prov
    semantic = w.commit_status_state(sts, boots, rts, rss, bss, tss)
    check(report, "semantic-replay-rejects-repointed-nonsense-transition", semantic.get("status") == w.HISTORY_INCOMPLETE, semantic)

    stm = deepcopy(st)
    prov_sha, _prov = provenance_row_at_seq(stm, 3)
    stm[w.PROVENANCE_STORE].pop(prov_sha)
    missing_prov = w.commit_status_state(stm, boot, rt, rs, bs, ts)
    check(report, "missing-provenance-incomplete", missing_prov.get("status") == w.HISTORY_INCOMPLETE, missing_prov)

    stt = deepcopy(st)
    prov_sha2, _prov2 = provenance_row_at_seq(stt, 1)
    stt[w.PROVENANCE_STORE][prov_sha2]["transition_kind"] = "TAMPER"
    tampered_prov = w.commit_status_state(stt, boot, rt, rs, bs, ts)
    check(report, "tampered-provenance-incomplete", tampered_prov.get("status") == w.HISTORY_INCOMPLETE, tampered_prov)

    std, privd, bootd, rtd, svd, tokd, rsd, tsd, csd, dd, bsd = new_world()
    for i in range(1, 7):
        w.advance_all(std, privd, bootd, rtd, svd, tokd, rsd, tsd, csd, dd, bsd, f"wave111-depth-{i}")
    depth = w.commit_status_state(std, bootd, rtd, rsd, bsd, tsd)
    check(report, "synthetic-depth6-valid", depth.get("status") == w.HISTORY_VALID, depth)
    check(report, "synthetic-depth6-provenance-count", len(w._provenance_rows(std) or []) == 6, depth)

    strb, privrb, bootrb, rtrb, svrb, tokrb, rsrb, tsrb, csrb, drb, bsrb = new_world()
    w.advance_all(strb, privrb, bootrb, rtrb, svrb, tokrb, rsrb, tsrb, csrb, drb, bsrb, "wave111-rb-e1")
    snap_st = deepcopy(strb)
    snap_rt = deepcopy(rtrb)
    snap_sv = deepcopy(svrb)
    snap_ts = deepcopy(tsrb)
    snap_cs = deepcopy(csrb)
    snap_bs = deepcopy(bsrb)
    snap_disks = drb.disk_snapshots()
    w.advance_all(strb, privrb, bootrb, rtrb, svrb, tokrb, rsrb, tsrb, csrb, drb, bsrb, "wave111-rb-e2")
    drb.restore_disks(snap_disks)
    rollback_authority = w.authority(
        snap_rt, snap_st, bootrb, snap_sv, rsrb, snap_ts, snap_cs, drb, snap_bs
    )
    report["preserved_counterexample"] = {
        "name": "whole-modeled-domain-rollback-to-genuine-prefix",
        "authority": rollback_authority,
        "expected_boundary": "still-authoritative-because-no-independent-newer-fact-survives",
    }
    check(report, "preserved-whole-domain-rollback-counterexample-visible", rollback_authority.startswith("AUTHORITATIVE"), report["preserved_counterexample"])

    report["passed"] = len(report["controls"]) - report["failed"]
    report["total"] = len(report["controls"])
    report["verdict"] = "PASS" if report["failed"] == 0 else "FAIL"
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out")
    args = parser.parse_args()
    report = run()
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
