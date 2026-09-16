#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "AXM_FLOWING_COMPUTE_TRANSITION_ATTESTATION_HISTORY.py"
SPEC = importlib.util.spec_from_file_location("wave93", TOOL)
assert SPEC and SPEC.loader
wave93 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = wave93
SPEC.loader.exec_module(wave93)


def replacement(stores, old, old_truth_sha, label):
    E, R, T, H, AT, S, AU = stores
    old_truth = E[old_truth_sha]
    nxt = wave93.W.ev(
        "eval-truth",
        ["truth"],
        old_truth["evaluation_tool_sha256"],
        wave93.td(label + "-source"),
        label,
        old_truth_sha,
    )
    wave93.put(E, nxt, "evaluator_sha256")
    entries = dict(old["evaluator_entries"])
    entries["eval-truth"] = nxt["evaluator_sha256"]
    assignments = dict(old["root_assignments"])
    new, transition = wave93.successor(
        stores, old, entries, assignments, "REPLACE", label
    )
    return nxt, new, transition


def main() -> None:
    stores, x = wave93.fixture()
    E, R, T, H, AT, S, AU = stores
    r0, h0, s0 = x["r0"], x["h0"], x["s0"]
    runtime = deepcopy(x["rt"])

    assert wave93.authority(runtime, R, E, H, S) == "AUTHORITATIVE"

    truth1, r1, t1 = replacement(stores, r0, x["truth0"], "truth-v2")
    au1, h1, s1, m1 = wave93.auth_with_history(stores, t1, r0, h0, s0)
    result1 = wave93.apply(
        runtime,
        t1["transition_sha256"],
        h0["history_sha256"],
        au1["authorization_sha256"],
        stores,
    )
    assert result1 == "COMMITTED", result1
    assert wave93.authority(runtime, R, E, H, S) == "AUTHORITATIVE"

    # Remove evidence that is part of the already-committed lineage, not evidence
    # for the next transition. The continuity evaluator remains active, and its
    # committed state head still points at this exact attestation hash.
    missing_attestation_sha = m1["continuity"]
    assert s1["heads"]["eval-continuity"]["last_attestation_sha256"] == missing_attestation_sha
    del AT[missing_attestation_sha]

    # Also remove the predecessor evaluator-history body. h1 still names it via
    # predecessor_history_sha256, but val_hist()/authority() do not resolve it.
    missing_history_sha = h0["history_sha256"]
    assert h1["predecessor_history_sha256"] == missing_history_sha
    del H[missing_history_sha]

    # Current authority remains accepted despite both dangling predecessor hashes.
    authority_after_loss = wave93.authority(runtime, R, E, H, S)
    assert authority_after_loss == "AUTHORITATIVE", authority_after_loss

    # Extend the live history normally. The next continuity attestation uses the
    # missing committed attestation as its predecessor, but derive_state() checks
    # only the predecessor hash stored in the state head; it never resolves the
    # predecessor attestation body. hist_step() similarly extends h1 without
    # resolving h1.predecessor_history_sha256.
    truth2, r2, t2 = replacement(stores, r1, truth1["evaluator_sha256"], "truth-v3")
    au2, h2, s2, m2 = wave93.auth_with_history(stores, t2, r1, h1, s1)

    continuity2 = AT[m2["continuity"]]
    assert continuity2["previous_attestation_sha256"] == missing_attestation_sha
    assert missing_attestation_sha not in AT
    assert h2["predecessor_history_sha256"] == h1["history_sha256"]
    assert missing_history_sha not in H

    result2 = wave93.apply(
        runtime,
        t2["transition_sha256"],
        h1["history_sha256"],
        au2["authorization_sha256"],
        stores,
    )
    assert result2 == "COMMITTED", result2
    final_authority = wave93.authority(runtime, R, E, H, S)
    assert final_authority == "AUTHORITATIVE", final_authority

    print(
        json.dumps(
            {
                "verdict": "FAIL_COMMITTED_HISTORY_CAN_EXTEND_OVER_MISSING_PREDECESSOR_BODIES",
                "builder_wave93_head": "24c3597089097d67b5f2972beb11d51a764bee12",
                "control_generation1_commit": result1,
                "missing_active_evaluator_prior_attestation_body": missing_attestation_sha not in AT,
                "committed_state_head_still_names_missing_attestation": s1["heads"]["eval-continuity"]["last_attestation_sha256"] == missing_attestation_sha,
                "missing_predecessor_history_body": missing_history_sha not in H,
                "current_history_still_names_missing_predecessor": h1["predecessor_history_sha256"] == missing_history_sha,
                "authority_after_committed_evidence_loss": authority_after_loss,
                "next_attestation_chains_to_missing_body": continuity2["previous_attestation_sha256"] == missing_attestation_sha,
                "generation2_commit": result2,
                "final_authority": final_authority,
                "hash_collision_required": False,
                "store_key_body_substitution_required": False,
                "whole_current_tuple_rollback_required": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
