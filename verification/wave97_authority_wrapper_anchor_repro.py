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


def git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def load_target():
    assert git_blob_sha(TARGET) == EXPECTED_TOOL_BLOB, "wrong Wave 97 tool blob"
    spec = importlib.util.spec_from_file_location("wave97_target", TARGET)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def commit_two_epochs(m):
    st, priv, boot, rt, ext = m.fixture()

    cp1, u1, l1 = m.prep_cp(rt, st, priv, boot, ext)
    assert m.commit(rt, st, boot, l1) == "COMMITTED"
    assert m.pubext(rt, st, boot, ext) == "APPENDED"
    assert m.auth(rt, st, boot, ext).startswith("AUTHORITATIVE")

    rt["state_sha"] = hashlib.sha256(b"verifier-wave97-state-2").hexdigest()
    cp2, u2, l2 = m.prep_cp(rt, st, priv, boot, ext)
    assert m.commit(rt, st, boot, l2) == "COMMITTED"
    assert m.pubext(rt, st, boot, ext) == "APPENDED"
    assert m.auth(rt, st, boot, ext).startswith("AUTHORITATIVE")
    return st, priv, boot, rt, ext, (cp1, u1, l1), (cp2, u2, l2)


def reproduce_unsealed_link_wrapper(m):
    st, priv, boot, rt, ext, first, second = commit_two_epochs(m)
    cp1, _u1, l1 = first
    cp2, _u2, l2 = second

    # Honest replay is blocked, matching the builder control.
    assert m.commit(rt, st, boot, l1) == "PREDECESSOR_HOLD"

    # Change only the caller-supplied wrapper. Its content address is now invalid,
    # while authority_sha still names the exact old stored link.
    spoof = deepcopy(l1)
    spoof["predecessor_authority_sha"] = rt["a"]
    assert m.fail(lambda: m.chk(spoof, "authority_sha"), "mismatch")

    # commit() checks predecessor_authority_sha on the unsealed caller object,
    # but resolves authority_sha from the store separately and never compares them.
    result = m.commit(rt, st, boot, spoof)
    assert result == "COMMITTED", result
    assert rt["a"] == l1["authority_sha"]
    assert all(rt["w"][w] == l1["authority_sha"] for w in m.W)

    stored_old = m.get(st["L"], l1["authority_sha"], "authority_sha")
    assert stored_old["predecessor_authority_sha"] is None
    assert spoof["predecessor_authority_sha"] == l2["authority_sha"]

    # The already-published external anchor catches the rollback afterwards,
    # so this is a local commit/state-boundary failure rather than a full finality break.
    assert m.auth(rt, st, boot, ext) == "HOLD_EXTERNAL_AHEAD"

    return {
        "honest_old_replay": "PREDECESSOR_HOLD",
        "spoofed_unsealed_wrapper": result,
        "post_attack_authority": m.auth(rt, st, boot, ext),
        "old_checkpoint_sha": cp1["checkpoint_sha"],
        "new_checkpoint_sha": cp2["checkpoint_sha"],
    }


def reproduce_unvalidated_external_anchor(m):
    st, _priv, boot, rt, ext, first, second = commit_two_epochs(m)
    cp1, _u1, l1 = first
    cp2, _u2, l2 = second

    assert m.auth(rt, st, boot, ext).startswith("AUTHORITATIVE")

    # Corrupt the newest external record's own integrity/lineage metadata while
    # leaving only the two fields auth() currently compares unchanged.
    corrupt = deepcopy(ext)
    corrupt[-1]["epoch"] = 999
    corrupt[-1]["previous_record_sha"] = "f" * 64
    corrupt[-1]["record_sha"] = "0" * 64
    assert m.fail(lambda: m.chk(corrupt[-1], "record_sha"), "mismatch")
    accepted_corrupt = m.auth(rt, st, boot, corrupt)
    assert accepted_corrupt.startswith("AUTHORITATIVE"), accepted_corrupt

    # Stronger stale-proof check: roll local state to epoch 1, keep the external
    # list length/history, and alter only the latest record's authority/checkpoint
    # fields without resealing it. auth() accepts the malformed record as if it
    # were a valid surviving anchor.
    rolled = deepcopy(rt)
    rolled["a"] = l1["authority_sha"]
    rolled["w"] = {w: l1["authority_sha"] for w in m.W}
    rolled["state_sha"] = cp1["state_sha"]
    assert m.auth(rolled, st, boot, ext) == "HOLD_EXTERNAL_AHEAD"

    stale_anchor = deepcopy(ext)
    stale_anchor[-1]["authority_sha"] = l1["authority_sha"]
    stale_anchor[-1]["checkpoint_sha"] = cp1["checkpoint_sha"]
    assert m.fail(lambda: m.chk(stale_anchor[-1], "record_sha"), "mismatch")
    accepted_stale = m.auth(rolled, st, boot, stale_anchor)
    assert accepted_stale.startswith("AUTHORITATIVE"), accepted_stale

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
        assert m.commit(rt, st, boot, link) == "COMMITTED"
        assert m.pubext(rt, st, boot, ext) == "APPENDED"
    counted = CountingDict(st["U"])
    st["U"] = counted
    assert m.auth(rt, st, boot, ext).startswith("AUTHORITATIVE")
    return counted.reads


def main():
    m = load_target()

    # Re-run the builder's own controls from the exact target module as a control.
    builder = m.run(1)
    assert builder["controls"]["passed"] == builder["controls"]["total"] == 25

    wrapper = reproduce_unsealed_link_wrapper(m)
    anchor = reproduce_unvalidated_external_anchor(m)

    reads_1 = use_store_reads_at_epoch(m, 1)
    reads_6 = use_store_reads_at_epoch(m, 6)
    assert reads_6 > reads_1

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
