#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "tools" / "AXM_FLOWING_COMPUTE_SECRET_SIGNER_LINEAGE.py"
EXPECTED_TOOL_BLOB = "f5ca09a21e64ec390c15e5825751d0d6977d023d"
EXPECTED_BUILDER_HEAD = "20e82977205040168c5fa79b967ee6868aa3f7db"


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
    eq(git_blob_sha(TARGET), EXPECTED_TOOL_BLOB, "wrong Wave 97 tool blob")
    spec = importlib.util.spec_from_file_location("wave97_target", TARGET)
    req(spec is not None and spec.loader is not None, "cannot load Wave 97 target")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def commit_two_epochs(m):
    st, priv, boot, rt, ext = m.fixture()

    cp1, u1, l1 = m.prep_cp(rt, st, priv, boot, ext)
    eq(m.commit(rt, st, boot, l1), "COMMITTED", "epoch1 commit")
    eq(m.pubext(rt, st, boot, ext), "APPENDED", "epoch1 external publish")
    req(m.auth(rt, st, boot, ext).startswith("AUTHORITATIVE"), "epoch1 not authoritative")

    rt["state_sha"] = hashlib.sha256(b"verifier-wave97-state-2").hexdigest()
    cp2, u2, l2 = m.prep_cp(rt, st, priv, boot, ext)
    eq(m.commit(rt, st, boot, l2), "COMMITTED", "epoch2 commit")
    eq(m.pubext(rt, st, boot, ext), "APPENDED", "epoch2 external publish")
    req(m.auth(rt, st, boot, ext).startswith("AUTHORITATIVE"), "epoch2 not authoritative")
    return st, priv, boot, rt, ext, (cp1, u1, l1), (cp2, u2, l2)


def reproduce_unsealed_link_wrapper(m):
    st, _priv, boot, rt, ext, first, second = commit_two_epochs(m)
    cp1, _u1, l1 = first
    cp2, _u2, l2 = second

    honest = m.commit(rt, st, boot, l1)
    eq(honest, "PREDECESSOR_HOLD", "honest old replay control")

    spoof = deepcopy(l1)
    spoof["predecessor_authority_sha"] = rt["a"]
    req(m.fail(lambda: m.chk(spoof, "authority_sha"), "mismatch"), "spoof wrapper unexpectedly sealed")

    result = m.commit(rt, st, boot, spoof)
    eq(result, "COMMITTED", "spoofed wrapper replay")
    eq(rt["a"], l1["authority_sha"], "runtime authority did not roll back")
    req(all(rt["w"][w] == l1["authority_sha"] for w in m.W), "witnesses did not roll back")

    stored_old = m.get(st["L"], l1["authority_sha"], "authority_sha")
    req(stored_old["predecessor_authority_sha"] is None, "stored old link unexpectedly changed")
    eq(spoof["predecessor_authority_sha"], l2["authority_sha"], "spoof predecessor")

    post = m.auth(rt, st, boot, ext)
    eq(post, "HOLD_EXTERNAL_AHEAD", "published external anchor should catch local rollback")

    return {
        "honest_old_replay": honest,
        "spoofed_unsealed_wrapper": result,
        "post_attack_authority": post,
        "old_checkpoint_sha": cp1["checkpoint_sha"],
        "new_checkpoint_sha": cp2["checkpoint_sha"],
    }


def reproduce_unvalidated_external_anchor(m):
    st, _priv, boot, rt, ext, first, second = commit_two_epochs(m)
    cp1, _u1, l1 = first
    cp2, _u2, l2 = second

    req(m.auth(rt, st, boot, ext).startswith("AUTHORITATIVE"), "valid epoch2 control failed")

    corrupt = deepcopy(ext)
    corrupt[-1]["epoch"] = 999
    corrupt[-1]["previous_record_sha"] = "f" * 64
    corrupt[-1]["record_sha"] = "0" * 64
    req(m.fail(lambda: m.chk(corrupt[-1], "record_sha"), "mismatch"), "corrupt anchor unexpectedly sealed")
    accepted_corrupt = m.auth(rt, st, boot, corrupt)
    req(accepted_corrupt.startswith("AUTHORITATIVE"), f"corrupt anchor was unexpectedly rejected: {accepted_corrupt}")

    rolled = deepcopy(rt)
    rolled["a"] = l1["authority_sha"]
    rolled["w"] = {w: l1["authority_sha"] for w in m.W}
    rolled["state_sha"] = cp1["state_sha"]
    eq(m.auth(rolled, st, boot, ext), "HOLD_EXTERNAL_AHEAD", "untouched anchor rollback control")

    stale_anchor = deepcopy(ext)
    stale_anchor[-1]["authority_sha"] = l1["authority_sha"]
    stale_anchor[-1]["checkpoint_sha"] = cp1["checkpoint_sha"]
    req(m.fail(lambda: m.chk(stale_anchor[-1], "record_sha"), "mismatch"), "stale anchor unexpectedly sealed")
    accepted_stale = m.auth(rolled, st, boot, stale_anchor)
    req(accepted_stale.startswith("AUTHORITATIVE"), f"malformed stale anchor was unexpectedly rejected: {accepted_stale}")

    return {
        "valid_epoch2_authority": "AUTHORITATIVE",
        "corrupt_anchor_record_accepted": accepted_corrupt,
        "untouched_anchor_detects_local_rollback": "HOLD_EXTERNAL_AHEAD",
        "malformed_latest_anchor_masks_rollback": accepted_stale,
        "external_records_retained": len(stale_anchor),
        "target_old_authority": l1["authority_sha"],
        "latest_real_authority": l2["authority_sha"],
        "latest_real_checkpoint": cp2["checkpoint_sha"],
    }


class CountingDict(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reads = 0

    def __getitem__(self, key):
        self.reads += 1
        return super().__getitem__(key)


def use_store_reads_at_epoch(m, epochs: int) -> int:
    st, priv, boot, rt, ext = m.fixture()
    for i in range(epochs):
        rt["state_sha"] = hashlib.sha256(f"history-{i}".encode()).hexdigest()
        _cp, _u, link = m.prep_cp(rt, st, priv, boot, ext)
        eq(m.commit(rt, st, boot, link), "COMMITTED", f"history epoch {i+1} commit")
        eq(m.pubext(rt, st, boot, ext), "APPENDED", f"history epoch {i+1} external publish")
    counted = CountingDict(st["U"])
    st["U"] = counted
    req(m.auth(rt, st, boot, ext).startswith("AUTHORITATIVE"), "history authority control failed")
    return counted.reads


def main():
    m = load_target()

    builder = m.run(1)
    eq(builder["controls"]["passed"], 25, "builder controls passed")
    eq(builder["controls"]["total"], 25, "builder controls total")

    wrapper = reproduce_unsealed_link_wrapper(m)
    anchor = reproduce_unvalidated_external_anchor(m)

    reads_1 = use_store_reads_at_epoch(m, 1)
    reads_6 = use_store_reads_at_epoch(m, 6)
    req(reads_6 > reads_1, f"expected retained-use reads to grow: epoch1={reads_1}, epoch6={reads_6}")

    print("WAVE97_EXACT_TOOL_BLOB", EXPECTED_TOOL_BLOB)
    print("WAVE97_EXPECTED_BUILDER_HEAD", EXPECTED_BUILDER_HEAD)
    print("BUILDER_CONTROLS", "25/25")
    print("UNSEALED_LINK_WRAPPER", wrapper)
    print("UNVALIDATED_EXTERNAL_ANCHOR", anchor)
    print("USE_STORE_READS_EPOCH_1", reads_1)
    print("USE_STORE_READS_EPOCH_6", reads_6)
    print("VERDICT FAIL_WAVE97_AUTHORITY_BOUNDARIES_NOT_FULLY_CONTENT_ADDRESSED")


if __name__ == "__main__":
    main()
