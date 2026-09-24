#!/usr/bin/env python3
"""Wave 101 adversarial/self-test for remote authority chronology."""
from __future__ import annotations

import argparse
import hashlib
import json
import secrets
from copy import deepcopy

import AXM_FLOWING_COMPUTE_REMOTE_AUTHORITY_MONOTONICITY as a
import AXM_FLOWING_COMPUTE_REMOTE_REGISTRY_MONOTONICITY as m
import AXM_FLOWING_COMPUTE_REMOTE_WITNESS_REGISTRY_QUORUM as q


def expect_fail(fn, contains: str | None = None) -> bool:
    try:
        fn()
    except Exception as exc:
        return contains is None or contains in str(exc)
    return False


def run(rounds: int) -> dict:
    controls = []
    add = lambda name, value: controls.append({"name": name, "pass": bool(value)})

    add(
        "exact_sources",
        a.SRC["wave100_head"] == "0fb2caa805cebf29185d0b40c9f1bbd46199263b"
        and a.SRC["wave100_tool_blob"] == "9fc2dc55c2d3973010b1804ad766cc632b89fa1f"
        and a.SRC["wave100_selftest_blob"] == "12491f9996bd7bada33ea742dacbb186dfd037c8"
        and a.SRC["verifier_head"] == "100e45fb18f7cfc52663af3ad53753eeab4c8365"
        and a.SRC["verifier_evidence_blob"] == "246138d4a3a1e8757ef1044e4e7a0928536870f5",
    )

    st, priv, boot, rt, services, tokens, rs = q.fixture()
    ts = {}
    add("genesis_authority", a.authority(rt, st, boot, services, rs) == "AUTHORITATIVE_GENESIS_MODELED")

    cp1, u1, l1, t1 = a.advance_all(st, priv, boot, rt, services, tokens, rs, ts, "wave101-base-1")
    snap1 = {"st": deepcopy(st), "rt": deepcopy(rt)}
    add("epoch1_three_of_three", a.authority(rt, st, boot, services, rs).startswith("AUTHORITATIVE_QUORUM_3"))

    cp2, u2, l2, t2 = a.advance_all(st, priv, boot, rt, services, tokens, rs, ts, "wave101-base-2")
    remote_epoch2 = deepcopy(services)
    add("epoch2_three_of_three", a.authority(rt, st, boot, services, rs).startswith("AUTHORITATIVE_QUORUM_3"))
    add(
        "normal_history_exact_epochs",
        all([r["authority_epoch"] for r in sorted(services[s]["records"].values(), key=lambda x: x["seq"])] == [1, 2]
            for s in q.REMOTE_IDS),
    )

    rolled_st, rolled_rt = deepcopy(snap1["st"]), deepcopy(snap1["rt"])
    add("untouched_remotes_expose_local_rollback",
        not a.authority(rolled_rt, rolled_st, boot, remote_epoch2, rs).startswith("AUTHORITATIVE"))
    guarded = deepcopy(remote_epoch2)
    add(
        "guarded_publish_rejects_old_local",
        a.publish(rolled_rt, rolled_st, boot, guarded, tokens, rs, "remote-a")
        in ("REMOTE_AUTHORITY_EPOCH_HOLD", "REMOTE_PREDECESSOR_HOLD"),
    )

    attacked = deepcopy(remote_epoch2)
    reg = q.get_registry(rs, rolled_rt["remote_registry_sha"])
    raw_results = {}
    for slot in ("remote-a", "remote-b"):
        raw_results[slot] = q.append_raw(
            attacked[slot], slot, reg["slots"][slot], tokens[slot],
            l1["epoch"], l1["authority_sha"], cp1["checkpoint_sha"], rolled_rt["remote_registry_sha"],
        )
    add("pr25_old_raw_primitive_still_reproduces", all(v == "APPENDED" for v in raw_results.values()))
    add("pr25_wave100_false_authority_still_reproduces",
        m.authority(rolled_rt, rolled_st, boot, attacked, rs).startswith("AUTHORITATIVE_QUORUM_2"))
    add(
        "pr25_attacked_history_rejected",
        all(expect_fail(lambda s=s: a.verify_remote_authority_history(attacked[s], rs), "epoch discontinuity")
            for s in ("remote-a", "remote-b")),
    )
    add("pr25_wave101_false_authority_blocked",
        not a.authority(rolled_rt, rolled_st, boot, attacked, rs).startswith("AUTHORITATIVE"))

    equal = deepcopy(remote_epoch2)
    equal_raw = q.append_raw(
        equal["remote-a"], "remote-a", reg["slots"]["remote-a"], tokens["remote-a"],
        l2["epoch"], "a" * 64, "b" * 64, rt["remote_registry_sha"],
    )
    add("equal_epoch_sibling_raw_append_reproduced", equal_raw == "APPENDED")
    add("equal_epoch_sibling_rejected",
        expect_fail(lambda: a.verify_remote_authority_history(equal["remote-a"], rs), "epoch discontinuity"))

    skipped = deepcopy(remote_epoch2)
    skipped_raw = q.append_raw(
        skipped["remote-a"], "remote-a", reg["slots"]["remote-a"], tokens["remote-a"],
        l2["epoch"] + 2, "c" * 64, "d" * 64, rt["remote_registry_sha"],
    )
    add("skipped_epoch_raw_append_reproduced", skipped_raw == "APPENDED")
    add("skipped_epoch_rejected",
        expect_fail(lambda: a.verify_remote_authority_history(skipped["remote-a"], rs), "epoch discontinuity"))

    one_bad = deepcopy(remote_epoch2)
    poison_one = q.append_raw(
        one_bad["remote-a"], "remote-a", reg["slots"]["remote-a"], tokens["remote-a"],
        1, l1["authority_sha"], cp1["checkpoint_sha"], rt["remote_registry_sha"],
    )
    add("one_poison_record_created", poison_one == "APPENDED")
    one_bad_verdict = a.authority(rt, st, boot, one_bad, rs)
    add("one_poison_quarantined_two_healthy_survive",
        one_bad_verdict.startswith("AUTHORITATIVE_QUORUM_2") and "QUARANTINED=remote-a" in one_bad_verdict)

    two_bad = deepcopy(one_bad)
    poison_two = q.append_raw(
        two_bad["remote-b"], "remote-b", reg["slots"]["remote-b"], tokens["remote-b"],
        1, l1["authority_sha"], cp1["checkpoint_sha"], rt["remote_registry_sha"],
    )
    add("second_poison_record_created", poison_two == "APPENDED")
    add("two_poisoned_witnesses_lose_quorum",
        a.authority(rt, st, boot, two_bad, rs) == "HOLD_REMOTE_AUTHORITY_LINEAGE_QUORUM")

    new_token = secrets.token_bytes(32)
    reg0 = q.get_registry(rs, rt["remote_registry_sha"])
    reg1 = q.rotate_registry_credential(rs, reg0["registry_sha"], "remote-a", q.H(new_token))
    cp3, u3, l3, t3 = a.prepare(
        rt, st, priv, boot, services, rs, ts,
        hashlib.sha256(b"wave101-credential-rotation").hexdigest(), reg1["registry_sha"],
    )
    add("rotation_local_commit", a.commit(rt, st, boot, rs, ts, l3["authority_sha"], t3) == "COMMITTED")
    services["remote-a"]["credential_hash"] = q.H(new_token)
    tokens["remote-a"] = new_token
    add("rotation_publish_a", a.publish(rt, st, boot, services, tokens, rs, "remote-a") == "APPENDED")
    add("rotation_publish_b", a.publish(rt, st, boot, services, tokens, rs, "remote-b") == "APPENDED")
    add("rotation_two_of_three_authority", a.authority(rt, st, boot, services, rs).startswith("AUTHORITATIVE_QUORUM_2"))
    add("rotation_publish_c", a.publish(rt, st, boot, services, tokens, rs, "remote-c") == "APPENDED")
    add("rotation_three_of_three_authority", a.authority(rt, st, boot, services, rs).startswith("AUTHORITATIVE_QUORUM_3"))
    add("rotation_epoch_is_direct_successor", l3["epoch"] == l2["epoch"] + 1)

    rolled_services = {}
    for slot in q.REMOTE_IDS:
        rows = [deepcopy(v) for v in remote_epoch2[slot]["records"].values() if v["authority_epoch"] <= 1]
        row = rows[0]
        rolled_services[slot] = deepcopy(remote_epoch2[slot])
        rolled_services[slot]["records"] = {row["record_sha"]: row}
        rolled_services[slot]["head"] = row["record_sha"]
    whole_rollback_counterexample = a.authority(
        snap1["rt"], snap1["st"], boot, rolled_services, rs,
    ).startswith("AUTHORITATIVE")
    add("whole_modeled_domain_rollback_counterexample_preserved", whole_rollback_counterexample)

    passed = sum(row["pass"] for row in controls)
    return {
        "schema": "axm.flowing_compute.wave101.report/v1",
        "wave": 101,
        "source": a.SRC,
        "controls": {"passed": passed, "total": len(controls), "rows": controls},
        "synthetic_scaling": {
            "label": (
                "SYNTHETIC single-process remote-history/quorum bookkeeping only; not OS-process, provider, "
                "network, energy, monolith-compute, retained, incremental, or dormant-compute evidence"
            ),
            "rows": a.bench((1, 4, 8), rounds),
        },
        "counterexamples_preserved": [
            "All three remote witnesses are still modeled Python objects in one process.",
            "Rolling local runtime plus all modeled remote stores and supporting stores back together remains internally self-consistent.",
            "Two current symmetric append credentials can still poison two remote histories and intentionally force authority HOLD, even though the rewind no longer regains authority.",
            "A poisoned witness whose retained authority chronology is invalid is quarantined; this wave does not invent a history rewrite to rehabilitate it.",
            "Remote credentials remain symmetric test tokens rather than independent service public-key attestations.",
            "Enough current local signer compromise plus a valid remote quorum can still create a competing structurally valid forward world.",
            "Mechanical chronology/quorum evidence does not prove moral/root judgment correctness, consent, evaluator legitimacy, or canonical AXM authority.",
        ],
        "truth_boundary": [
            "Wave 101 directly addresses verifier PR #25 before process-level separation.",
            "Remote record sequence is no longer treated as an authority maximum by itself; retained authority epochs must start at 1 and advance exactly +1.",
            "A current remote head is cross-bound to the exact local predecessor authority and predecessor checkpoint before it counts as current authority.",
            "One invalid remote authority history is quarantined and cannot be counted; two healthy exact witnesses can still satisfy the existing 2-of-3 contract.",
            "No fresh AXM/monolith workload is read because the newest independent verifier found a protocol rollback defect that must be closed before stronger deployment claims.",
            "No merge, CANON promotion, physical failure-domain, network, energy, retained, incremental, or dormant-compute win is claimed.",
        ],
        "next_gate": (
            "Wave 102: move the repaired registry + authority chronology + quorum contract across at least three real OS processes with separate durable stores and separately held credentials. "
            "Test kill/restart, partition/reconnect, stale file-store restoration, credential rotation, one poisoned process quarantine, two-process compromise, and whether an independently durable maximum survives process-local rollback. "
            "Do not call OS-process separation physical/provider independence."
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
