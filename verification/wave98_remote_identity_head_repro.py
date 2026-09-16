#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "tools" / "AXM_FLOWING_COMPUTE_DUAL_REMOTE_WITNESS.py"
EXPECTED_TOOL_BLOB = "bc4347a75f04f6d9ff97e58128d2f5f0a16c85a1"
EXPECTED_BUILDER_HEAD = "56bb92218f9af62aceacee1ee625755b8ef54789"
EXPECTED_REPORT_BLOB = "397e1023f1ec1e233e3b0a6943d4b6e62854512b"


def req(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def eq(got, expected, label: str) -> None:
    if got != expected:
        raise RuntimeError(f"{label}: expected {expected!r}, got {got!r}")


def git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def load_target():
    eq(git_blob_sha(TARGET), EXPECTED_TOOL_BLOB, "wrong Wave 98 tool blob")
    spec = importlib.util.spec_from_file_location("wave98_target", TARGET)
    req(spec is not None and spec.loader is not None, "cannot load Wave 98 target")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def commit_two_epochs(m):
    st, priv, boot, rt, remotes, tokens = m.fixture()
    snapshots = []
    for epoch in (1, 2):
        rt["state_sha"] = hashlib.sha256(f"wave98-verifier-state-{epoch}".encode()).hexdigest()
        cp, use, link = m.prep_cp(rt, st, priv, boot, remotes)
        eq(m.commit_sha(rt, st, boot, link["authority_sha"]), "COMMITTED", f"epoch{epoch} local commit")
        for rid in m.REMOTE_IDS:
            eq(m.publish_remote(rt, st, boot, remotes[rid], tokens[rid]), "APPENDED", f"epoch{epoch} {rid} publish")
        req(m.authority(rt, st, boot, remotes).startswith("AUTHORITATIVE"), f"epoch{epoch} not authoritative")
        snapshots.append({
            "rt": deepcopy(rt),
            "remotes": deepcopy(remotes),
            "cp": deepcopy(cp),
            "use": deepcopy(use),
            "link": deepcopy(link),
        })
    return st, priv, boot, rt, remotes, tokens, snapshots


def reproduce_remote_slot_alias(m):
    st, _priv, boot, rt, remotes, _tokens, snapshots = commit_two_epochs(m)

    outage = deepcopy(remotes)
    outage["remote-b"]["online"] = False
    eq(m.authority(rt, st, boot, outage), "HOLD_REMOTE_UNAVAILABLE", "honest remote-b outage control")

    only_remote_a = deepcopy(remotes["remote-a"])
    aliased = {
        "remote-a": only_remote_a,
        "remote-b": only_remote_a,
    }
    req(aliased["remote-a"] is aliased["remote-b"], "test did not alias one service into both slots")
    eq(only_remote_a["service_id"], "remote-a", "single surviving service identity")

    verdict = m.authority(rt, st, boot, aliased)
    req(verdict.startswith("AUTHORITATIVE"), f"duplicate remote-a service unexpectedly rejected: {verdict}")

    return {
        "honest_remote_b_outage": "HOLD_REMOTE_UNAVAILABLE",
        "single_service_id_used_for_both_slots": only_remote_a["service_id"],
        "same_object_in_both_slots": aliased["remote-a"] is aliased["remote-b"],
        "single_credential_hash_used_twice": only_remote_a["credential_hash"],
        "authority_with_one_real_remote_counted_twice": verdict,
        "latest_authority_sha": snapshots[-1]["link"]["authority_sha"],
    }


def reproduce_head_rewind_with_newer_records_retained(m):
    st, _priv, boot, rt, remotes, _tokens, snapshots = commit_two_epochs(m)
    old = snapshots[0]
    current = snapshots[1]

    rolled_local = deepcopy(old["rt"])
    eq(m.authority(rolled_local, st, boot, remotes), "HOLD_REMOTE_DIVERGED", "untouched remote heads rollback control")

    head_rewound = deepcopy(remotes)
    retained_new_heads = {}
    for rid in m.REMOTE_IDS:
        retained_new_heads[rid] = head_rewound[rid]["head"]
        old_head = old["remotes"][rid]["head"]
        req(old_head in head_rewound[rid]["records"], f"{rid} old head missing from retained store")
        req(retained_new_heads[rid] in head_rewound[rid]["records"], f"{rid} new head missing before rewind")
        req(retained_new_heads[rid] != old_head, f"{rid} heads unexpectedly identical")
        head_rewound[rid]["head"] = old_head
        req(retained_new_heads[rid] in head_rewound[rid]["records"], f"{rid} newer record was deleted")
        eq(len(head_rewound[rid]["records"]), len(remotes[rid]["records"]), f"{rid} record count changed")

    verdict = m.authority(rolled_local, st, boot, head_rewound)
    req(verdict.startswith("AUTHORITATIVE"), f"rewound mutable heads unexpectedly rejected: {verdict}")

    return {
        "untouched_remote_heads_detect_local_rollback": "HOLD_REMOTE_DIVERGED",
        "newer_remote_records_still_present": True,
        "remote_record_counts": {rid: len(head_rewound[rid]["records"]) for rid in m.REMOTE_IDS},
        "rewound_head_authority": verdict,
        "old_authority_sha": old["link"]["authority_sha"],
        "new_authority_sha_still_retained": current["link"]["authority_sha"],
        "new_remote_heads_still_retained_as_records": retained_new_heads,
    }


def main():
    m = load_target()

    builder = m.run(1)
    eq(builder["controls"]["passed"], 29, "builder controls passed")
    eq(builder["controls"]["total"], 29, "builder controls total")

    alias = reproduce_remote_slot_alias(m)
    rewind = reproduce_head_rewind_with_newer_records_retained(m)

    print("WAVE98_EXACT_TOOL_BLOB", EXPECTED_TOOL_BLOB)
    print("WAVE98_EXPECTED_BUILDER_HEAD", EXPECTED_BUILDER_HEAD)
    print("WAVE98_EXPECTED_REPORT_BLOB", EXPECTED_REPORT_BLOB)
    print("BUILDER_CONTROLS", "29/29")
    print("REMOTE_SLOT_ALIAS", alias)
    print("REMOTE_HEAD_REWIND", rewind)
    print("VERDICT FAIL_WAVE98_REMOTE_WITNESS_IDENTITY_AND_HEAD_MONOTONICITY_NOT_BOUND")


if __name__ == "__main__":
    main()
