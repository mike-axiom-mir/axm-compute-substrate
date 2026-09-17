#!/usr/bin/env python3
"""Wave 108 adversarial/self-test for multi-epoch committed-history completeness."""
from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path

import AXM_FLOWING_COMPUTE_COMMITTED_HISTORY_MANIFEST as w
import AXM_FLOWING_COMPUTE_BOOTSTRAP_PARTIAL_EVIDENCE_GUARD as w107
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w104


g = w.g
q = w.q


def add_world_108():
    st, priv, boot, rt, services, tokens, rs = q.fixture()
    ts = {}
    cs = g.new_certificate_store()
    domain = w104.new_certificate_witness_domain()
    bs = {}
    w.adopt_genesis(rt, st, boot, services, rs, cs, domain, bs)
    return st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs


def add_world_107():
    st, priv, boot, rt, services, tokens, rs = q.fixture()
    ts = {}
    cs = g.new_certificate_store()
    domain = w104.new_certificate_witness_domain()
    bs = {}
    w107.adopt_genesis(rt, st, boot, services, rs, cs, domain, bs)
    return st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs


def row_at_seq(store: dict, seq: int):
    for sha, body in store.items():
        if body.get("seq") == seq:
            return sha, body
    raise KeyError(seq)


def run() -> dict:
    controls = []
    add = lambda name, value: controls.append({"name": name, "pass": bool(value)})

    add(
        "exact_sources",
        w.SRC["wave107_builder_head"] == "22289521483fe8e171f6c9016f0bd0b10e54a235"
        and w.SRC["wave107_tested_source_commit"] == "9e4edc8c484d32f9210804dc25ca61fadf7aa835"
        and w.SRC["wave107_tool_blob"] == "7aeb0e6f6018d1708b5fe89a4fdbf8e024398deb"
        and w.SRC["wave107_selftest_blob"] == "66d676685b23fd5cbcc5ac8f06a0ec5e383fd295"
        and w.SRC["verifier_pr"] == 32
        and w.SRC["verifier_head"] == "3573711a726b527d43dd056ca2bfdbdd5be81c0a"
        and w.SRC["verifier_evidence_blob"] == "154cdc9cbc197d75a814a2b29e945d02e9d9f454"
        and w.SRC["verifier_repro_blob"] == "010c59d1de7f8ce3dac8029bf620b789b134ecf2"
        and w.SRC["verifier_ci_run"] == 35193912823,
    )

    s107 = add_world_107()
    st107, priv107, boot107, rt107, services107, tokens107, rs107, ts107, cs107, domain107, bs107 = s107
    w107.advance_all(st107, priv107, boot107, rt107, services107, tokens107, rs107, ts107, cs107, domain107, bs107, "wave108-pr32-epoch1")
    status, link107_1, _ = q.current_local(rt107, st107, boot107)
    if status != "LOCAL_OK":
        raise AssertionError(status)
    w107.advance_all(st107, priv107, boot107, rt107, services107, tokens107, rs107, ts107, cs107, domain107, bs107, "wave108-pr32-epoch2")
    status, link107_2, _ = q.current_local(rt107, st107, boot107)
    if status != "LOCAL_OK":
        raise AssertionError(status)
    attacked107 = deepcopy(st107)
    attacked107["L"].pop(link107_2["authority_sha"])
    pr32_guard = w107.retained_authority_history_state(attacked107, boot107)
    add("pr32_wave107_multiepoch_link_loss_reproduced", pr32_guard["status"] == w107.HISTORY_VALID)

    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = add_world_108()
    add("wave108_marker_stores_initialized_empty", st[w.COMMIT_STORE] == {} and st[w.HIGH_WATER_STORE] == {})
    add("wave108_genesis_authoritative", w.authority(rt, st, boot, services, rs, cs, domain, bs) == "AUTHORITATIVE_GENESIS_MODELED")

    w.advance_all(st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs, "wave108-accepted-epoch1")
    status, link1, cp1 = q.current_local(rt, st, boot)
    if status != "LOCAL_OK":
        raise AssertionError(status)
    # Wave 104 intentionally forbids deepcopy() of credential-bound endpoints. Preserve a real
    # modeled disk snapshot instead, then restore those exact registered endpoints for the rollback
    # counterexample at the end of the test.
    snapshot_epoch1 = (
        deepcopy(st), deepcopy(rt), deepcopy(services), deepcopy(rs),
        deepcopy(cs), domain.disk_snapshots(), deepcopy(bs)
    )
    state1 = w.committed_history_state(st, boot, rt)
    add("epoch1_manifested_and_authoritative", state1["status"] == w.HISTORY_VALID and state1["committed_count"] == 1 and w.authority(rt, st, boot, services, rs, cs, domain, bs).startswith("AUTHORITATIVE"))

    w.advance_all(st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs, "wave108-accepted-epoch2")
    status, link2, cp2 = q.current_local(rt, st, boot)
    if status != "LOCAL_OK":
        raise AssertionError(status)
    state2 = w.committed_history_state(st, boot, rt)
    add("epoch2_manifested_and_authoritative", state2["status"] == w.HISTORY_VALID and state2["committed_count"] == 2 and w.authority(rt, st, boot, services, rs, cs, domain, bs).startswith("AUTHORITATIVE"))

    clean_epoch2 = deepcopy(st)
    link2_sha = link2["authority_sha"]
    cp2_sha = link2["checkpoint_sha"]
    use2_sha = link2["use_sha"]

    attacked = deepcopy(clean_epoch2)
    attacked["L"].pop(link2_sha)
    attack_state = w.committed_history_state(attacked, boot, rt)
    attack_authority = w.authority(rt, attacked, boot, services, rs, cs, domain, bs)
    add("pr32_newest_link_loss_now_incomplete", attack_state["status"] == w.HISTORY_INCOMPLETE)
    add("pr32_newest_link_loss_authority_holds", attack_authority == w.HOLD_INCOMPLETE)

    for label, stores in (
        ("newest_link_plus_checkpoint", ("L", "C")),
        ("newest_link_plus_use", ("L", "U")),
        ("newest_link_checkpoint_use", ("L", "C", "U")),
    ):
        damaged = deepcopy(clean_epoch2)
        for key in stores:
            if key == "L":
                damaged[key].pop(link2_sha)
            elif key == "C":
                damaged[key].pop(cp2_sha)
            elif key == "U":
                damaged[key].pop(use2_sha)
        add(label + "_fails_closed", w.committed_history_state(damaged, boot, rt)["status"] == w.HISTORY_INCOMPLETE)

    middle = deepcopy(clean_epoch2)
    middle["L"].pop(link1["authority_sha"])
    add("middle_committed_link_loss_fails_closed", w.committed_history_state(middle, boot, rt)["status"] == w.HISTORY_INCOMPLETE)

    commit2_sha, commit2_row = row_at_seq(clean_epoch2[w.COMMIT_STORE], 2)
    high2_sha, high2_row = row_at_seq(clean_epoch2[w.HIGH_WATER_STORE], 2)

    missing_commit_marker = deepcopy(clean_epoch2)
    missing_commit_marker[w.COMMIT_STORE].pop(commit2_sha)
    add("missing_newest_commit_marker_detected", w.committed_history_state(missing_commit_marker, boot, rt)["status"] == w.HISTORY_INCOMPLETE)

    missing_high_marker = deepcopy(clean_epoch2)
    missing_high_marker[w.HIGH_WATER_STORE].pop(high2_sha)
    add("missing_newest_high_water_marker_detected", w.committed_history_state(missing_high_marker, boot, rt)["status"] == w.HISTORY_INCOMPLETE)

    tampered_marker = deepcopy(clean_epoch2)
    tampered_marker[w.COMMIT_STORE][commit2_sha]["authority_sha"] = "0" * 64
    add("tampered_commit_marker_hash_detected", w.committed_history_state(tampered_marker, boot, rt)["status"] == w.HISTORY_INCOMPLETE)

    prepared_st = deepcopy(clean_epoch2)
    prepared_rt = deepcopy(rt)
    prepared_services = deepcopy(services)
    prepared_cs = deepcopy(cs)
    # prepare()/authority() only read the registered domain. Reuse the genuine registered
    # endpoints instead of violating Wave 104 by cloning credentials into a fake endpoint set.
    prepared_domain = domain
    prepared_bs = deepcopy(bs)
    prepared_ts = deepcopy(ts)
    prepared_app = hashlib.sha256(b"wave108-prepared-only-epoch3").hexdigest()
    pcp, puse, plink, ptransition, pbody = w.prepare(
        prepared_rt, prepared_st, priv, boot, prepared_services, rs, prepared_ts,
        prepared_cs, prepared_domain, prepared_bs, prepared_app
    )
    prepared_state = w.committed_history_state(prepared_st, boot, prepared_rt)
    add("prepared_next_epoch_link_distinguished_from_committed", prepared_state["status"] == w.HISTORY_VALID and plink["authority_sha"] in prepared_state["prepared_authority_shas"] and prepared_state["committed_count"] == 2)
    add("prepared_next_epoch_keeps_previous_authority_readable", w.authority(prepared_rt, prepared_st, boot, prepared_services, rs, prepared_cs, prepared_domain, prepared_bs).startswith("AUTHORITATIVE"))

    cst, cpriv, cboot, crt, csvcs, ctokens, crs, cts, ccs, cdomain, cbs = add_world_108()
    w.advance_all(cst, cpriv, cboot, crt, csvcs, ctokens, crs, cts, ccs, cdomain, cbs, "wave108-crash-epoch1")
    crash_app = hashlib.sha256(b"wave108-crash-after-lower-commit").hexdigest()
    ccp, cuse, clink, ctransition, cbody = w107.prepare(crt, cst, cpriv, cboot, csvcs, crs, cts, ccs, cdomain, cbs, crash_app)
    lower_result = w107.commit(crt, cst, cboot, crs, cts, clink["authority_sha"], ctransition, cbs)
    crash_state = w.committed_history_state(cst, cboot, crt)
    add("lower_commit_without_wave108_marker_reproduced", lower_result == "COMMITTED")
    add("postcommit_marker_crash_window_fails_closed", crash_state["status"] == w.HISTORY_INCOMPLETE and w.authority(crt, cst, cboot, csvcs, crs, ccs, cdomain, cbs) == w.HOLD_INCOMPLETE)

    dst, dpriv, dboot, drt, dsvcs, dtokens, drs, dts, dcs, ddomain, dbs = add_world_108()
    dlinks = []
    for epoch in range(1, 9):
        w.advance_all(dst, dpriv, dboot, drt, dsvcs, dtokens, drs, dts, dcs, ddomain, dbs, f"wave108-depth8-{epoch}")
        status, dlink, dcp = q.current_local(drt, dst, dboot)
        if status != "LOCAL_OK":
            raise AssertionError(status)
        dlinks.append(deepcopy(dlink))
    add("depth8_clean_history_valid", w.committed_history_state(dst, dboot, drt)["committed_count"] == 8)
    dnew = deepcopy(dst)
    dnew["L"].pop(dlinks[-1]["authority_sha"])
    add("depth8_newest_link_loss_detected", w.committed_history_state(dnew, dboot, drt)["status"] == w.HISTORY_INCOMPLETE)
    dmid = deepcopy(dst)
    dmid["L"].pop(dlinks[3]["authority_sha"])
    add("depth8_middle_link_loss_detected", w.committed_history_state(dmid, dboot, drt)["status"] == w.HISTORY_INCOMPLETE)

    sst, spriv, sboot, srt, ssvcs, stokens, srs, sts, scs, sdomain, sbs = add_world_108()
    slinks = []
    for epoch in range(1, 17):
        w.advance_all(sst, spriv, sboot, srt, ssvcs, stokens, srs, sts, scs, sdomain, sbs, f"wave108-synthetic-depth16-{epoch}")
        status, slink, scp = q.current_local(srt, sst, sboot)
        if status != "LOCAL_OK":
            raise AssertionError(status)
        slinks.append(deepcopy(slink))
    add("synthetic_depth16_clean_history_valid", w.committed_history_state(sst, sboot, srt)["committed_count"] == 16)
    snew = deepcopy(sst)
    snew["L"].pop(slinks[-1]["authority_sha"])
    add("synthetic_depth16_newest_link_loss_detected", w.committed_history_state(snew, sboot, srt)["status"] == w.HISTORY_INCOMPLETE)
    smid = deepcopy(sst)
    smid["L"].pop(slinks[7]["authority_sha"])
    add("synthetic_depth16_middle_link_loss_detected", w.committed_history_state(smid, sboot, srt)["status"] == w.HISTORY_INCOMPLETE)

    migration_st = deepcopy(st107)
    migration_rt = deepcopy(rt107)
    migration_services = deepcopy(services107)
    migration_cs = deepcopy(cs107)
    # The explicit-migration guard fires before any replacement endpoint could be relevant.
    migration_domain = domain107
    migration_bs = deepcopy(bs107)
    migration_blocked = False
    try:
        w.adopt_genesis(migration_rt, migration_st, boot107, migration_services, rs107, migration_cs, migration_domain, migration_bs)
    except Exception as exc:
        migration_blocked = "migration" in str(exc) or w.HOLD_INCOMPLETE in str(exc)
    add("prewave108_history_requires_explicit_migration", migration_blocked)

    rst, rrt, rservices, rrs, rcs, rdomain_disks, rbs = snapshot_epoch1
    domain.restore_disks(rdomain_disks)
    rollback_verdict = w.authority(rrt, rst, boot, rservices, rrs, rcs, domain, rbs)
    add("coordinated_whole_world_prefix_rollback_counterexample_preserved", rollback_verdict.startswith("AUTHORITATIVE"))

    passed = sum(row["pass"] for row in controls)
    return {
        "schema": "axm.flowing_compute.wave108.report/v1",
        "wave": 108,
        "source": w.SRC,
        "controls": {"passed": passed, "total": len(controls), "rows": controls},
        "pr32_reproduction": {
            "wave107_depth2_guard_status_after_newest_link_loss": pr32_guard["status"],
            "wave108_depth2_guard_status_after_same_loss": attack_state["status"],
            "wave108_authority_after_same_loss": attack_authority,
        },
        "synthetic_scaling": {
            "label": "synthetic retained-depth correctness scaling only",
            "depths": [8, 16],
            "performance_claim": False,
        },
        "counterexamples_preserved": [
            "Coordinated rollback/truncation of the complete modeled authority, both Wave-108 marker chains, and all external-support state to an older genuine prefix remains internally self-consistent in one process.",
            "The lower-commit to Wave-108-marker persistence window is fail-closed but not atomically recoverable; a crash there causes HOLD until explicit recovery exists.",
            "Wave-107 histories that predate the new marker chains require an explicit verified migration procedure; Wave 108 refuses silent retroactive adoption.",
            "Both marker chains share the same modeled Python failure domain, so paired markers do not prove physical monotonicity.",
            "Symmetric modeled witness credentials and existing fixed certificate-witness-root limits remain unchanged.",
        ],
        "truth_boundary": [
            "Wave 108 repairs verifier PR #32 for tested multi-epoch newest/middle committed-link loss by binding accepted epochs to paired content-addressed commit/high-water ledgers.",
            "Prepared-but-uncommitted next-epoch evidence is distinguished from committed history while runtime remains on the last manifested epoch.",
            "Partial corruption/truncation of either marker chain fails closed, but coordinated rollback of both chains with the whole world is not solved.",
            "Depth 16 is synthetic correctness scaling only; no benchmark or retained/incremental/dormant-compute win is claimed.",
            "No fresh AXM/monolith workload, performance, energy, network, OS-process, device, or provider-independence result is claimed.",
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
