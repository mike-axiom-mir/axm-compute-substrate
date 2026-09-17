#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "AXM_FLOWING_COMPUTE_EVIDENCE_CLOSURE_SIGNER_KEYS.py"
SPEC = importlib.util.spec_from_file_location("wave94", TOOL)
assert SPEC and SPEC.loader
wave94 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = wave94
SPEC.loader.exec_module(wave94)


def main() -> None:
    stores, rt = wave94.fixture()
    H, A, K, S, KS, secrets = stores

    assert wave94.authority(rt, stores) == "AUTHORITATIVE"

    # Establish one ordinary committed successor so both current state objects have
    # real predecessor-object references back to the genesis tuple.
    b1 = wave94.bundle(rt, stores, wave94.td("verifier-registry-1"))
    assert wave94.validate(rt, b1, stores) == b1["target"]
    assert wave94.apply(rt, b1, stores) == "COMMITTED"
    assert wave94.authority(rt, stores) == "AUTHORITATIVE"

    current_state_sha = rt["cur"][1]
    current_key_state_sha = rt["cur"][2]
    current_state = wave94.get(S, current_state_sha, "state_sha")
    current_key_state = wave94.get(KS, current_key_state_sha, "key_state_sha")

    missing_state_sha = current_state["predecessor"]
    missing_key_state_sha = current_key_state["predecessor"]
    assert missing_state_sha in S
    assert missing_key_state_sha in KS

    # Control: Wave 94 really does fail closed when a history ancestor is missing.
    current_history = wave94.get(H, rt["cur"][0], "history_sha")
    missing_history_sha = current_history["predecessor"]
    saved_history = H.pop(missing_history_sha)
    assert wave94.authority(rt, stores) == "HOLD"
    H[missing_history_sha] = saved_history
    assert wave94.authority(rt, stores) == "AUTHORITATIVE"

    # Attack the two other explicit predecessor chains in the authority tuple.
    # Delete the predecessor attestation-state and predecessor signer-key-state
    # bodies while leaving the current bodies and all attestation/key evidence intact.
    saved_state = S.pop(missing_state_sha)
    saved_key_state = KS.pop(missing_key_state_sha)
    assert current_state["predecessor"] == missing_state_sha
    assert current_key_state["predecessor"] == missing_key_state_sha
    assert missing_state_sha not in S
    assert missing_key_state_sha not in KS

    # tuple_closure() resolves only the current S/KS bodies. It walks H, A and K,
    # but never follows S.predecessor or KS.predecessor, so both dangling references
    # remain accepted as authoritative.
    authority_after_loss = wave94.authority(rt, stores)
    assert authority_after_loss == "AUTHORITATIVE", authority_after_loss

    # The live system can then extend normally over those missing predecessor-state
    # bodies. The next state/key-state objects point to the current generation-1
    # bodies, while the older genesis S/KS bodies remain absent forever underneath.
    b2 = wave94.bundle(rt, stores, wave94.td("verifier-registry-2"))
    target = wave94.validate(rt, b2, stores)
    assert target == b2["target"]
    result2 = wave94.apply(rt, b2, stores)
    assert result2 == "COMMITTED", result2
    final_authority = wave94.authority(rt, stores)
    assert final_authority == "AUTHORITATIVE", final_authority
    assert missing_state_sha not in S
    assert missing_key_state_sha not in KS

    s2 = wave94.get(S, rt["cur"][1], "state_sha")
    ks2 = wave94.get(KS, rt["cur"][2], "key_state_sha")
    assert s2["predecessor"] == current_state_sha
    assert ks2["predecessor"] == current_key_state_sha

    # Secondary hidden-cost check: Wave 94's HMAC model requires historical private
    # secrets to remain present for authority closure. After a real rotation, erasing
    # the retired secret (while keeping its public-ish key record) freezes authority.
    stores2, rt2 = wave94.fixture()
    H2, A2, K2, S2, KS2, secrets2 = stores2
    pre = wave94.bundle(rt2, stores2, wave94.td("secret-retention-pre"))
    assert wave94.apply(rt2, pre, stores2) == "COMMITTED"
    old_truth_key = wave94.get(KS2, rt2["cur"][2], "key_state_sha")["heads"]["truth"]
    rot = wave94.bundle(rt2, stores2, wave94.td("secret-retention-rotation"), rotate="truth")
    assert wave94.apply(rt2, rot, stores2) == "COMMITTED"
    assert wave94.authority(rt2, stores2) == "AUTHORITATIVE"
    retired_secret = secrets2.pop(old_truth_key)
    authority_after_retired_secret_erasure = wave94.authority(rt2, stores2)
    assert authority_after_retired_secret_erasure == "HOLD"
    secrets2[old_truth_key] = retired_secret
    assert wave94.authority(rt2, stores2) == "AUTHORITATIVE"

    print(json.dumps({
        "verdict": "FAIL_ATTESTATION_AND_KEY_STATE_PREDECESSOR_BODIES_CAN_DANGLE_AND_HISTORY_CAN_EXTEND",
        "builder_wave94_head": "340fd44141b40493b0ddd7a51fd653ada9ddf9b8",
        "control_missing_history_ancestor_holds": True,
        "missing_predecessor_attestation_state_sha256": missing_state_sha,
        "missing_predecessor_key_state_sha256": missing_key_state_sha,
        "current_state_still_names_missing_predecessor": current_state["predecessor"] == missing_state_sha,
        "current_key_state_still_names_missing_predecessor": current_key_state["predecessor"] == missing_key_state_sha,
        "authority_after_state_chain_body_loss": authority_after_loss,
        "generation2_commit_over_dangling_state_chains": result2,
        "final_authority": final_authority,
        "missing_state_bodies_remain_absent_after_extension": missing_state_sha not in S and missing_key_state_sha not in KS,
        "secondary_retired_hmac_secret_erasure_status": authority_after_retired_secret_erasure,
        "hash_collision_required": False,
        "attestation_or_key_body_loss_required": False,
        "whole_runtime_rollback_required": False
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
