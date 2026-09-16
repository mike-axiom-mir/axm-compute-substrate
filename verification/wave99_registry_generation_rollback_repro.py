#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
TARGET = TOOLS / "AXM_FLOWING_COMPUTE_REMOTE_WITNESS_REGISTRY_QUORUM.py"
SELFTEST = TOOLS / "AXM_FLOWING_COMPUTE_REMOTE_WITNESS_REGISTRY_QUORUM_SELFTEST.py"
EXPECTED_BUILDER_HEAD = "0c3ea28b4d731cde942d337c87a046f363d496c2"
EXPECTED_TOOL_BLOB = "c4c0a6bcabeafcf19502303857d1fc4da6fe8ea5"
EXPECTED_SELFTEST_BLOB = "6efa792265c4fd3b54e7cfb192f5e1440402010a"


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
    eq(git_blob_sha(TARGET), EXPECTED_TOOL_BLOB, "wrong Wave 99 tool blob")
    eq(git_blob_sha(SELFTEST), EXPECTED_SELFTEST_BLOB, "wrong Wave 99 self-test blob")
    sys.path.insert(0, str(TOOLS))
    spec = importlib.util.spec_from_file_location("wave99_target", TARGET)
    req(spec is not None and spec.loader is not None, "cannot load Wave 99 target")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def publish_all(m, rt, st, boot, services, tokens, registry_store, label: str) -> None:
    for slot in m.REMOTE_IDS:
        eq(m.publish(rt, st, boot, services, tokens, registry_store, slot), "APPENDED", f"{label} {slot} publish")
    req(m.authority(rt, st, boot, services, registry_store).startswith("AUTHORITATIVE_QUORUM_3"), f"{label} not 3/3 authoritative")


def main() -> None:
    m = load_target()
    st, priv, boot, rt, services, tokens, rs = m.fixture()
    reg0 = m.get_registry(rs, rt["remote_registry_sha"])
    eq(reg0["generation"], 0, "registry genesis generation")

    # Advance to a signed generation-1 registry with the exact same witness identities.
    reg1 = m.make_registry(deepcopy(reg0["slots"]), 1, reg0["registry_sha"])
    m.put_registry(rs, reg1)
    cp1, use1, link1, meta1 = m.prepare(
        rt, st, priv, boot, services, rs,
        hashlib.sha256(b"wave99-verifier-reg1").hexdigest(),
        reg1["registry_sha"],
    )
    eq(m.commit(rt, st, boot, link1["authority_sha"], meta1), "COMMITTED", "registry generation 1 commit")
    publish_all(m, rt, st, boot, services, tokens, rs, "registry generation 1")

    # Advance normally again to generation 2, preserving the same remote credentials/domains.
    reg2 = m.make_registry(deepcopy(reg1["slots"]), 2, reg1["registry_sha"])
    m.put_registry(rs, reg2)
    cp2, use2, link2, meta2 = m.prepare(
        rt, st, priv, boot, services, rs,
        hashlib.sha256(b"wave99-verifier-reg2").hexdigest(),
        reg2["registry_sha"],
    )
    eq(m.commit(rt, st, boot, link2["authority_sha"], meta2), "COMMITTED", "registry generation 2 commit")
    publish_all(m, rt, st, boot, services, tokens, rs, "registry generation 2")
    eq(m.get_registry(rs, rt["remote_registry_sha"])["generation"], 2, "current registry before rollback")

    retained_reg2_heads = {slot: services[slot]["head"] for slot in m.REMOTE_IDS}
    retained_counts = {slot: len(services[slot]["records"]) for slot in m.REMOTE_IDS}
    for slot in m.REMOTE_IDS:
        eq(m.verify_remote_full(services[slot], slot, reg2["slots"][slot])["registry_sha"], reg2["registry_sha"], f"{slot} generation-2 head")

    # Adversarial gate: target the old generation-0 registry directly. prepare()/commit() do not
    # require target_registry_sha to be the current registry or its direct successor.
    cp3, use3, link3, meta3 = m.prepare(
        rt, st, priv, boot, services, rs,
        hashlib.sha256(b"wave99-verifier-after-registry-rewind").hexdigest(),
        reg0["registry_sha"],
    )
    eq(m.commit(rt, st, boot, link3["authority_sha"], meta3), "COMMITTED", "stale generation-0 registry commit")
    eq(m.get_registry(rs, rt["remote_registry_sha"])["generation"], 0, "runtime registry rewound to generation 0")

    # Two unchanged witnesses can append the new authority under the stale registry. Their stores retain
    # the generation-2 records; the new generation-0 records are merely appended after them.
    for slot in ("remote-a", "remote-b"):
        eq(m.publish(rt, st, boot, services, tokens, rs, slot), "APPENDED", f"rollback {slot} publish")
        req(retained_reg2_heads[slot] in services[slot]["records"], f"{slot} generation-2 record was deleted")
        req(len(services[slot]["records"]) == retained_counts[slot] + 1, f"{slot} did not append exactly one rollback record")
        head = m.verify_remote_full(services[slot], slot, reg0["slots"][slot])
        eq(head["registry_sha"], reg0["registry_sha"], f"{slot} latest registry after rollback")
        eq(head["seq"], retained_counts[slot] + 1, f"{slot} rollback record sequence")

    # The third witness is left untouched at the newer generation-2 head. Two stale-registry heads are
    # nevertheless enough for current authority.
    eq(services["remote-c"]["head"], retained_reg2_heads["remote-c"], "remote-c newer head retained")
    verdict = m.authority(rt, st, boot, services, rs)
    req(verdict.startswith("AUTHORITATIVE_QUORUM_2"), f"stale registry rollback unexpectedly held: {verdict}")

    print("WAVE99_EXPECTED_BUILDER_HEAD", EXPECTED_BUILDER_HEAD)
    print("WAVE99_EXACT_TOOL_BLOB", EXPECTED_TOOL_BLOB)
    print("WAVE99_EXACT_SELFTEST_BLOB", EXPECTED_SELFTEST_BLOB)
    print("REGISTRY_GENERATIONS", {"before": 2, "after": 0})
    print("NEWER_REMOTE_RECORDS_RETAINED", True)
    print("REMOTE_C_LEFT_AT_NEWER_REGISTRY", True)
    print("ROLLBACK_AUTHORITY", verdict)
    print("VERDICT FAIL_WAVE99_REGISTRY_GENERATION_CAN_REWIND_THROUGH_NORMAL_SIGNED_QUORUM_PATH")


if __name__ == "__main__":
    main()
