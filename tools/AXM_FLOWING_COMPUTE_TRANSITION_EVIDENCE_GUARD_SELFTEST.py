#!/usr/bin/env python3
"""Wave 110 exact-API positive/negative self-test.

Includes the verifier-PR-34 stale-prefix attack, checks the unchanged Wave-109 failure first, then
requires Wave 110 to HOLD on the same retained transition evidence. Synthetic depth is correctness
only, not a performance benchmark.
"""
from __future__ import annotations

import argparse
import json
from copy import deepcopy

import AXM_FLOWING_COMPUTE_TRANSITION_EVIDENCE_GUARD as w
import AXM_FLOWING_COMPUTE_COMMIT_STATUS_AMBIGUITY_GUARD as w109
import AXM_FLOWING_COMPUTE_COMMITTED_HISTORY_MANIFEST as w108
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w104
import AXM_FLOWING_COMPUTE_REMOTE_REGISTRY_MONOTONICITY as w100

q = w.q
g = w.g


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
    w.adopt_genesis(rt, st, boot, services, rs, ts, cs, domain, bs)
    return st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs


def check(report: dict, name: str, ok: bool, detail=None):
    report["controls"].append({"name": name, "ok": bool(ok), "detail": detail})
    if not ok:
        report["failed"] += 1


def verifier34_attack():
    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world()

    w.advance_all(st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs, "w110-v34-e1")
    rt1 = deepcopy(rt)
    services1 = deepcopy(services)
    cs1 = deepcopy(cs)
    disks1 = domain.disk_snapshots()
    cert1_sha = cs1["head"]

    cp2, _use2, link2, transition2_sha, _body2, _cert2, _certbody2 = w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs, "w110-v34-e2"
    )
    cert2_sha = cs["head"]
    binding2_sha = rt["app_state_sha"]
    disks2 = domain.disk_snapshots()

    retained_transition = w100.get_transition(ts, transition2_sha)
    transition_exact = (
        retained_transition.get("target_authority_sha") == link2["authority_sha"]
        and retained_transition.get("target_checkpoint_sha") == cp2["checkpoint_sha"]
        and retained_transition.get("target_app_state_sha") == binding2_sha
    )

    attacked_st = deepcopy(st)
    commit2_sha, _ = row_at_seq(attacked_st[w108.COMMIT_STORE], 2)
    high2_sha, _ = row_at_seq(attacked_st[w108.HIGH_WATER_STORE], 2)
    attacked_st[w108.COMMIT_STORE].pop(commit2_sha)
    attacked_st[w108.HIGH_WATER_STORE].pop(high2_sha)
    attacked_rt = deepcopy(rt1)

    attacked_services = deepcopy(services)
    attacked_services["remote-b"] = deepcopy(services1["remote-b"])
    attacked_services["remote-c"] = deepcopy(services1["remote-c"])

    attacked_cs = deepcopy(cs)
    attacked_cs["records"].pop(cert2_sha)
    attacked_cs["head"] = cert1_sha

    mixed_disks = deepcopy(disks2)
    mixed_disks["cert-b"] = deepcopy(disks1["cert-b"])
    mixed_disks["cert-c"] = deepcopy(disks1["cert-c"])
    domain.restore_disks(mixed_disks)
    domain._endpoints["cert-a"].online = False

    damaged_st = deepcopy(attacked_st)
    damaged_st["L"].pop(link2["authority_sha"])
    damaged_st["C"].pop(link2["checkpoint_sha"])
    damaged_st["U"].pop(link2["use_sha"])
    damaged_bs = deepcopy(bs)
    damaged_bs.pop(binding2_sha)

    old_state = w109.commit_status_state(damaged_st, boot, attacked_rt, rs, damaged_bs)
    old_authority = w109.authority(
        attacked_rt, damaged_st, boot, attacked_services, rs, attacked_cs, domain, damaged_bs
    )
    new_state = w.commit_status_state(
        damaged_st, boot, attacked_rt, rs, damaged_bs, ts
    )
    new_authority = w.authority(
        attacked_rt,
        damaged_st,
        boot,
        attacked_services,
        rs,
        ts,
        attacked_cs,
        domain,
        damaged_bs,
    )
    return {
        "transition_exact": transition_exact,
        "transition_sha": transition2_sha,
        "old_state": old_state,
        "old_authority": old_authority,
        "new_state": new_state,
        "new_authority": new_authority,
    }


def run() -> dict:
    report = {
        "schema": "axm.flowing-compute.wave110.transition-evidence-guard-selftest/v1",
        "truth_boundary": {
            "synthetic_depth_is_correctness_only": True,
            "performance_claim": False,
            "energy_claim": False,
            "retained_incremental_dormant_compute_claim": False,
            "os_process_or_provider_independence_claim": False,
        },
        "controls": [],
        "failed": 0,
    }

    # Positive genesis and normal forward history.
    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world()
    genesis = w.commit_status_state(st, boot, rt, rs, bs, ts)
    check(report, "genesis-valid", genesis["status"] == w.HISTORY_VALID, genesis)
    check(report, "genesis-transition-store-empty", len(ts) == 0, len(ts))

    e1 = w.advance_all(st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs, "w110-e1")
    state1 = w.commit_status_state(st, boot, rt, rs, bs, ts)
    check(report, "epoch1-valid", state1["status"] == w.HISTORY_VALID, state1)
    check(report, "epoch1-one-transition", len(ts) == 1, len(ts))
    check(report, "epoch1-authoritative", w.authority(rt, st, boot, services, rs, ts, cs, domain, bs).startswith("AUTHORITATIVE"))

    e2 = w.advance_all(st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs, "w110-e2")
    state2 = w.commit_status_state(st, boot, rt, rs, bs, ts)
    check(report, "epoch2-valid", state2["status"] == w.HISTORY_VALID, state2)
    check(report, "epoch2-two-transitions", len(ts) == 2, len(ts))
    check(report, "epoch2-transition-lineage-count", len(state2.get("expected_transition_shas", [])) == 2, state2)

    # Prepared-only evidence remains deliberately unresolved; commit then clears it.
    cp3, use3, link3, tr3, body3 = w.prepare(
        rt, st, priv, boot, services, rs, ts, cs, domain, bs,
        target_user_app_state_sha="3" * 64,
    )
    prepared = w.commit_status_state(st, boot, rt, rs, bs, ts)
    check(report, "prepared-is-unresolved", prepared["status"] == w.HISTORY_UNRESOLVED, prepared)
    check(report, "prepared-authority-holds", w.authority(rt, st, boot, services, rs, ts, cs, domain, bs) == w.HOLD_UNRESOLVED)
    commit3 = w.commit(rt, st, boot, rs, ts, link3["authority_sha"], tr3, bs)
    after_commit3 = w.commit_status_state(st, boot, rt, rs, bs, ts)
    check(report, "prepared-commit-completes", commit3 == "COMMITTED", commit3)
    check(report, "commit-clears-ambiguity", after_commit3["status"] == w.HISTORY_VALID, after_commit3)

    # Missing a required transition is corruption/incompleteness, not a harmless old prefix.
    missing_ts = deepcopy(ts)
    missing_ts.pop(tr3)
    missing_state = w.commit_status_state(st, boot, rt, rs, bs, missing_ts)
    check(report, "missing-committed-transition-incomplete", missing_state["status"] == w.HISTORY_INCOMPLETE, missing_state)

    # Tamper is detected by the exact Wave-100 transition seal/key-body verifier.
    tampered_ts = deepcopy(ts)
    any_sha = next(iter(tampered_ts))
    tampered_ts[any_sha]["target_checkpoint_sha"] = "f" * 64
    tampered_state = w.commit_status_state(st, boot, rt, rs, bs, tampered_ts)
    check(report, "tampered-transition-incomplete", tampered_state["status"] == w.HISTORY_INCOMPLETE, tampered_state)

    # Exact verifier PR #34 failure first survives under unchanged Wave 109, then is blocked here.
    attack = verifier34_attack()
    report["verifier34_attack"] = attack
    check(report, "verifier34-transition-survives", attack["transition_exact"], attack)
    check(report, "wave109-exact-failure-reproduced", attack["old_state"].get("status") == w109.HISTORY_VALID and attack["old_authority"].startswith("AUTHORITATIVE"), attack)
    check(report, "wave110-classifies-surviving-transition-unresolved", attack["new_state"].get("status") == w.HISTORY_UNRESOLVED, attack)
    check(report, "wave110-blocks-stale-authority", attack["new_authority"] == w.HOLD_UNRESOLVED, attack)

    # Synthetic correctness-only retained depth. This is intentionally not timed.
    stx, privx, bootx, rtx, sx, tx, rsx, tsx, csx, dx, bsx = new_world()
    for i in range(1, 7):
        w.advance_all(stx, privx, bootx, rtx, sx, tx, rsx, tsx, csx, dx, bsx, f"w110-depth-{i}")
    depth = w.commit_status_state(stx, bootx, rtx, rsx, bsx, tsx)
    check(report, "synthetic-depth6-valid", depth["status"] == w.HISTORY_VALID, depth)
    check(report, "synthetic-depth6-transition-count", len(depth.get("expected_transition_shas", [])) == 6, depth)

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
