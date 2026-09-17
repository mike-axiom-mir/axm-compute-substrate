#!/usr/bin/env python3
"""Independent adversarial reproducer for Flowing Compute Wave 95.

Targets exact builder head:
42bf7230f2537fe7229983769b9130f9c58c2393

This imports the published Wave 95 module unchanged. It does not propose a fix.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO / "tools" / "AXM_FLOWING_COMPUTE_AUTHORITY_CHECKPOINT_COMPACTION.py"
SPEC = importlib.util.spec_from_file_location("wave95", MODULE_PATH)
assert SPEC and SPEC.loader
w = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(w)

EXPECTED_BUILDER_HEAD = "42bf7230f2537fe7229983769b9130f9c58c2393"
EXPECTED_TOOL_BLOB = "5e38d8ad23dc9c659d774127beb95a745b08a151"


def commit_transition(rt, st, registry: str, rotate=None):
    target = w.transition(rt, st, w.td(registry), rotate=rotate)
    verdict = w.apply_transition(rt, target)
    assert verdict == "COMMITTED", verdict
    assert w.authority(rt, st).startswith("AUTHORITATIVE"), w.authority(rt, st)
    return target


def checkpoint_replay_attack():
    st, rt = w.fixture()

    # Reach a first legitimate live state and publish checkpoint epoch 1.
    commit_transition(rt, st, "verifier-registry-1")
    cp1, _ = w.checkpoint(tuple(rt["cur"]), st, 1)
    assert w.apply_checkpoint(rt, cp1) == "COMMITTED"
    assert w.authority(rt, st) == "AUTHORITATIVE_CHECKPOINTED"
    tuple_after_cp1 = tuple(rt["cur"])

    # Advance normally, then publish a newer legitimate checkpoint epoch 2.
    commit_transition(rt, st, "verifier-registry-2")
    cp2, _ = w.checkpoint(tuple(rt["cur"]), st, 2)
    assert w.apply_checkpoint(rt, cp2) == "COMMITTED"
    assert w.authority(rt, st) == "AUTHORITATIVE_CHECKPOINTED"
    live_tuple_before_replay = tuple(rt["cur"])
    assert cp2["epoch"] > cp1["epoch"]
    assert tuple_after_cp1 != live_tuple_before_replay
    assert rt["checkpoint_sha"] == cp2["checkpoint_sha"]

    # Replay the already-valid older checkpoint through the normal publication API.
    replay_result = w.apply_checkpoint(rt, cp1)
    replay_authority = w.authority(rt, st)

    assert replay_result == "COMMITTED", replay_result
    assert rt["checkpoint_sha"] == cp1["checkpoint_sha"]
    assert cp1["epoch"] == 1 and cp2["epoch"] == 2
    assert tuple(rt["cur"]) == live_tuple_before_replay, "live state should not need to roll back"
    assert replay_authority == "AUTHORITATIVE_CHECKPOINTED", replay_authority

    # The stale checkpoint can now be the active cut while the live tuple stays newer.
    # A normal transition still succeeds from this state.
    commit_transition(rt, st, "verifier-registry-3")

    return {
        "newer_checkpoint_epoch": cp2["epoch"],
        "replayed_checkpoint_epoch": cp1["epoch"],
        "publication_result": replay_result,
        "authority_after_replay": replay_authority,
        "live_tuple_rolled_back": False,
        "post_replay_transition": "COMMITTED",
    }


def recheckpoint_after_compaction_negative_case():
    st, rt = w.fixture()
    commit_transition(rt, st, "compact-registry-1")
    commit_transition(rt, st, "compact-registry-2", rotate="truth")

    cp1, _ = w.checkpoint(tuple(rt["cur"]), st, 1)
    assert w.apply_checkpoint(rt, cp1) == "COMMITTED"
    removed = w.prune_precut(cp1, st)
    assert sum(removed.values()) > 0
    assert w.authority(rt, st) == "AUTHORITATIVE_CHECKPOINTED"

    # Wave 95 explicitly demonstrates that normal post-cut evolution remains possible.
    commit_transition(rt, st, "compact-registry-3")
    assert w.authority(rt, st) == "AUTHORITATIVE_CHECKPOINTED"

    # But the public checkpoint constructor always insists on closure to genesis.
    # The deliberately pruned pre-cut bodies are therefore required again when
    # attempting the next checkpoint, making repeated compaction impossible.
    error = None
    try:
        w.checkpoint(tuple(rt["cur"]), st, 2)
    except Exception as exc:  # exact public API negative case
        error = str(exc)

    assert error is not None, "unexpectedly created a second checkpoint after pruning"
    assert "body missing" in error, error
    assert w.authority(rt, st) == "AUTHORITATIVE_CHECKPOINTED"

    return {
        "first_checkpoint_committed": True,
        "precut_prune_performed": True,
        "postcut_transition_committed": True,
        "second_checkpoint_created": False,
        "second_checkpoint_error": error,
        "authority_remains": w.authority(rt, st),
    }


def main():
    replay = checkpoint_replay_attack()
    recheckpoint = recheckpoint_after_compaction_negative_case()

    print("EXACT_BUILDER_HEAD", EXPECTED_BUILDER_HEAD)
    print("EXACT_TOOL_BLOB", EXPECTED_TOOL_BLOB)
    print("CHECKPOINT_REPLAY", replay)
    print("RECHECKPOINT_AFTER_COMPACTION", recheckpoint)
    print("FAIL_OLDER_VALID_CHECKPOINT_CAN_BE_REPROMOTED_WITHOUT_LIVE_STATE_ROLLBACK")
    print("FAIL_COMPACTION_CUT_CANNOT_BE_ADVANCED_AFTER_PRECUT_PRUNE")


if __name__ == "__main__":
    main()
