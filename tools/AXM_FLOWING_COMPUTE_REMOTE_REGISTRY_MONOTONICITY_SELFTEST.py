#!/usr/bin/env python3
"""Wave 100 adversarial/self-test for monotonic live registry transitions."""
from __future__ import annotations

import argparse
import hashlib
import json
import secrets
from copy import deepcopy

import AXM_FLOWING_COMPUTE_REMOTE_REGISTRY_MONOTONICITY as m
import AXM_FLOWING_COMPUTE_REMOTE_WITNESS_REGISTRY_QUORUM as q


def expect_fail(fn, contains: str | None = None) -> bool:
    try:
        fn()
    except Exception as exc:
        return contains is None or contains in str(exc)
    return False


def raw_move_registry(st, priv, boot, rt, services, tokens, rs, target_reg, label: str) -> None:
    cp, use, link, meta = q.prepare(
        rt, st, priv, boot, services, rs,
        hashlib.sha256(label.encode()).hexdigest(),
        target_reg["registry_sha"],
    )
    if q.commit(rt, st, boot, link["authority_sha"], meta) != "COMMITTED":
        raise RuntimeError("raw local move failed")
    for slot in q.REMOTE_IDS:
        result = q.publish(rt, st, boot, services, tokens, rs, slot)
        if result not in ("APPENDED", "ALREADY_CURRENT"):
            raise RuntimeError(f"raw publish failed: {slot} {result}")
    if not q.authority(rt, st, boot, services, rs).startswith("AUTHORITATIVE"):
        raise RuntimeError("raw move did not regain Wave 99 authority")


def run(rounds: int) -> dict:
    controls = []
    add = lambda name, value: controls.append({"name": name, "pass": bool(value)})

    add(
        "exact_sources",
        m.SRC["wave99_head"] == "0c3ea28b4d731cde942d337c87a046f363d496c2"
        and m.SRC["wave99_tool_blob"] == "c4c0a6bcabeafcf19502303857d1fc4da6fe8ea5"
        and m.SRC["verifier_head"] == "0c13b87882df2a6a18bd3dff032b47b92a36a3a6"
        and m.SRC["verifier_evidence_blob"] == "367d8627679e76114a1dd767e95b4b92090447ad",
    )

    st, priv, boot, rt, services, tokens, rs = q.fixture()
    ts = {}
    add("genesis_authority", m.authority(rt, st, boot, services, rs) == "AUTHORITATIVE_GENESIS_MODELED")
    cp1, u1, l1, t1 = m.prepare(
        rt, st, priv, boot, services, rs, ts, hashlib.sha256(b"base-1").hexdigest()
    )
    add("sealed_transition_created", t1 in ts and ts[t1]["transition_kind"] == "SAME")
    add("partial_commit", m.commit(rt, st, boot, rs, ts, l1["authority_sha"], t1, 1) == "PARTIAL")
    add("partial_state_holds", m.authority(rt, st, boot, services, rs) == "HOLD_PARTIAL")
    add("partial_resume_exact_transition", m.commit(rt, st, boot, rs, ts, l1["authority_sha"], t1) == "COMMITTED")
    add("publish_a_base", m.publish(rt, st, boot, services, tokens, rs, "remote-a") == "APPENDED")
    add("publish_b_base", m.publish(rt, st, boot, services, tokens, rs, "remote-b") == "APPENDED")
    add("two_of_three_base_authority", m.authority(rt, st, boot, services, rs).startswith("AUTHORITATIVE_QUORUM_2"))
    add("publish_c_base", m.publish(rt, st, boot, services, tokens, rs, "remote-c") == "APPENDED")
    add("three_of_three_base_authority", m.authority(rt, st, boot, services, rs).startswith("AUTHORITATIVE_QUORUM_3"))

    tampered_store = deepcopy(ts)
    tampered_store[t1]["target_generation"] = 999
    add(
        "tampered_transition_body_rejected",
        m.commit(rt, st, boot, rs, tampered_store, l1["authority_sha"], t1) == "TRANSITION_VALIDATION_HOLD",
    )

    reg0 = q.get_registry(rs, rt["remote_registry_sha"])
    noop = q.make_registry(deepcopy(reg0["slots"]), reg0["generation"] + 1, reg0["registry_sha"])
    q.put_registry(rs, noop)
    add(
        "noop_registry_successor_rejected",
        expect_fail(
            lambda: m.prepare(rt, st, priv, boot, services, rs, ts,
                              hashlib.sha256(b"noop").hexdigest(), noop["registry_sha"]),
            "exactly one slot",
        ),
    )

    old_a_token = tokens["remote-a"]
    new_a_token = secrets.token_bytes(32)
    reg1a = q.rotate_registry_credential(rs, reg0["registry_sha"], "remote-a", q.H(new_a_token))
    step = m.validate_live_registry_step(rs, reg0["registry_sha"], reg1a["registry_sha"])
    add(
        "direct_credential_successor_valid",
        step["delta"]["kind"] == "CREDENTIAL_ROTATION"
        and step["delta"]["changed_slots"] == ["remote-a"],
    )

    new_b_token = secrets.token_bytes(32)
    sibling1b = q.rotate_registry_credential(rs, reg0["registry_sha"], "remote-b", q.H(new_b_token))
    reg2 = q.rotate_registry_credential(rs, reg1a["registry_sha"], "remote-a", q.H(secrets.token_bytes(32)))
    add(
        "skipped_generation_target_rejected",
        expect_fail(lambda: m.validate_live_registry_step(rs, reg0["registry_sha"], reg2["registry_sha"]),
                    "exact direct successor"),
    )
    add(
        "sibling_registry_jump_rejected",
        expect_fail(lambda: m.validate_live_registry_step(rs, reg1a["registry_sha"], sibling1b["registry_sha"]),
                    "exact direct successor"),
    )

    old_snapshot = (
        deepcopy(st), deepcopy(priv), deepcopy(boot), deepcopy(rt),
        deepcopy(services), deepcopy(tokens), deepcopy(rs), deepcopy(ts),
    )
    cpR, uR, lR, tR = m.prepare(
        rt, st, priv, boot, services, rs, ts,
        hashlib.sha256(b"rotate-a").hexdigest(), reg1a["registry_sha"]
    )
    add("rotation_transition_bound", ts[tR]["current_registry_sha"] == reg0["registry_sha"]
        and ts[tR]["target_registry_sha"] == reg1a["registry_sha"])
    add("rotation_local_commit", m.commit(rt, st, boot, rs, ts, lR["authority_sha"], tR) == "COMMITTED")
    services["remote-a"]["credential_hash"] = q.H(new_a_token)
    tokens["remote-a"] = new_a_token
    stale_c = deepcopy(services["remote-c"])

    add("rotation_publish_a", m.publish(rt, st, boot, services, tokens, rs, "remote-a") == "APPENDED")
    add("one_current_remote_not_quorum", not m.authority(rt, st, boot, services, rs).startswith("AUTHORITATIVE"))
    add("rotation_publish_b", m.publish(rt, st, boot, services, tokens, rs, "remote-b") == "APPENDED")
    add("partial_registry_fanout_two_of_three", m.authority(rt, st, boot, services, rs).startswith("AUTHORITATIVE_QUORUM_2"))
    add("rotation_publish_c", m.publish(rt, st, boot, services, tokens, rs, "remote-c") == "APPENDED")
    add("registry_rotation_three_of_three", m.authority(rt, st, boot, services, rs).startswith("AUTHORITATIVE_QUORUM_3"))
    add(
        "direct_generation_rollback_from_valid_current_rejected",
        expect_fail(
            lambda: m.prepare(
                rt, st, priv, boot, services, rs, ts,
                hashlib.sha256(b"direct-rollback").hexdigest(), reg0["registry_sha"]
            ),
            "exact direct successor",
        ),
    )

    add(
        "retired_credential_rejected",
        q.append_raw(
            services["remote-a"], "remote-a", reg1a["slots"]["remote-a"], old_a_token,
            999, "a" * 64, "b" * 64, reg1a["registry_sha"]
        ) == "AUTH_FAIL",
    )

    stale_one = deepcopy(services)
    stale_one["remote-c"] = stale_c
    add("one_witness_stale_restore_still_two_of_three",
        m.authority(rt, st, boot, stale_one, rs).startswith("AUTHORITATIVE_QUORUM_2"))
    stale_one_offline = deepcopy(stale_one)
    stale_one_offline["remote-a"]["online"] = False
    add("one_offline_plus_one_stale_loses_quorum",
        not m.authority(rt, st, boot, stale_one_offline, rs).startswith("AUTHORITATIVE"))

    disagreement = deepcopy(services)
    row_b_current = reg1a["slots"]["remote-b"]
    raw_sibling = q.append_raw(
        disagreement["remote-b"], "remote-b", row_b_current, tokens["remote-b"],
        lR["epoch"], lR["authority_sha"], cpR["checkpoint_sha"], sibling1b["registry_sha"]
    )
    add("raw_sibling_remote_append_old_primitive_accepts", raw_sibling == "APPENDED")
    add("sibling_remote_history_fails_closed",
        m.authority(rt, st, boot, disagreement, rs) == "HOLD_REMOTE_REGISTRY_LINEAGE")

    ast, apriv, aboot, art, aservices, atokens, ars = q.fixture()
    q.advance_all(ast, apriv, aboot, art, aservices, atokens, ars, "attack-base")
    areg0 = q.get_registry(ars, art["remote_registry_sha"])
    areg1 = q.make_registry(deepcopy(areg0["slots"]), 1, areg0["registry_sha"]); q.put_registry(ars, areg1)
    raw_move_registry(ast, apriv, aboot, art, aservices, atokens, ars, areg1, "attack-g1")
    areg2 = q.make_registry(deepcopy(areg1["slots"]), 2, areg1["registry_sha"]); q.put_registry(ars, areg2)
    raw_move_registry(ast, apriv, aboot, art, aservices, atokens, ars, areg2, "attack-g2")

    add(
        "wave100_prepare_blocks_pr24_registry_rewind",
        expect_fail(
            lambda: m.prepare(
                art, ast, apriv, aboot, aservices, ars, {},
                hashlib.sha256(b"blocked-rewind").hexdigest(), areg0["registry_sha"]
            ),
        ),
    )

    acp, au, alink, ameta = q.prepare(
        art, ast, apriv, aboot, aservices, ars,
        hashlib.sha256(b"raw-rewind").hexdigest(), areg0["registry_sha"]
    )
    add("pr24_old_prepare_still_reproducible", ameta["target_registry_sha"] == areg0["registry_sha"])
    add("pr24_old_commit_still_reproducible",
        q.commit(art, ast, aboot, alink["authority_sha"], ameta) == "COMMITTED")
    add("pr24_old_publish_a", q.publish(art, ast, aboot, aservices, atokens, ars, "remote-a") == "APPENDED")
    add("pr24_old_publish_b", q.publish(art, ast, aboot, aservices, atokens, ars, "remote-b") == "APPENDED")
    add("pr24_wave99_false_authority_reproduced",
        q.authority(art, ast, aboot, aservices, ars).startswith("AUTHORITATIVE_QUORUM_2"))
    add("pr24_wave100_remote_lineage_rejects_reproduced_world",
        m.authority(art, ast, aboot, aservices, ars) == "HOLD_REMOTE_REGISTRY_LINEAGE")

    ost, opriv, oboot, ort, oservices, otokens, ors, ots = old_snapshot
    add("whole_modeled_domain_rollback_counterexample",
        m.authority(ort, ost, oboot, oservices, ors).startswith("AUTHORITATIVE"))
    add("inherited_current_signer_compromise_counterexample", q.w98.stolen_all_dual_counterexample())

    passed = sum(row["pass"] for row in controls)
    return {
        "schema": "axm.flowing_compute.wave100.report/v1",
        "wave": 100,
        "source": m.SRC,
        "controls": {"passed": passed, "total": len(controls), "rows": controls},
        "synthetic_scaling": {
            "label": (
                "SYNTHETIC single-process registry-transition/quorum bookkeeping only; "
                "not physical failure-domain, network, energy, monolith-compute, retained, incremental, "
                "or dormant-compute evidence"
            ),
            "rows": m.bench((1, 4, 8), rounds),
        },
        "counterexamples_preserved": [
            "Three remote witnesses remain modeled Python objects in one process; Wave 100 does not demonstrate physical failure-domain independence.",
            "Rolling local runtime, all modeled remote stores, registry store, and transition store back together remains internally self-consistent.",
            "A restored stale witness cannot outvote two exact current witnesses, but there is still no independent durable maximum that proves the restored provider itself was rolled back.",
            "Remote append credentials are symmetric test tokens, not independent public-key service attestations.",
            "Enough current local signer compromise plus a remote quorum can still create a competing structurally valid world.",
            "Mechanically valid registry/signer/quorum evidence does not prove moral/root judgment correctness, consent, evaluator legitimacy, or canonical AXM authority."
        ],
        "truth_boundary": [
            "Wave 100 directly addresses verifier PR #24 before physical deployment.",
            "Normal state-only checkpoints must keep the exact current registry SHA; registry-changing checkpoints must use the exact direct successor at current generation+1.",
            "The only authorized registry mutation in this wave is exactly one slot's credential_hash; no-op, sibling, skipped-generation, service-identity, and failure-domain migrations fail closed.",
            "Remote retained histories must keep registry identity unchanged or move to the exact direct successor; a lower/sibling/stale registry cannot be appended after a newer one without authority HOLD.",
            "No fresh AXM/monolith workload is read because the newest independent verifier found an authority-boundary defect that must be closed before stronger deployment claims.",
            "No merge, CANON promotion, energy, network, retained, incremental, or dormant-compute win is claimed."
        ],
        "next_gate": (
            "Wave 101: run the monotonic registry/record/quorum contract across at least three real OS processes "
            "with separate durable stores and separately held credentials. Test process kill/restart, partition/reconnect, "
            "stale file-store restoration, credential rotation/recovery, two-process compromise, and whether a durable "
            "maximum survives provider-local rollback. Do not call OS-process separation physical/provider independence."
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
