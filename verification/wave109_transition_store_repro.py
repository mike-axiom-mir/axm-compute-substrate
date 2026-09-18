#!/usr/bin/env python3
"""Independent adversarial reproducer for Wave 109.

Finding: Wave 109 calls its preserved stale-prefix case "complete newer local transaction erasure",
but the normal transition store still retains a sealed Wave-100 transition for the accepted newer
epoch. commit_status_state()/authority() do not receive or inspect transition_store, so the newer
transaction artifact is mechanically invisible to the ambiguity guard.

This reproducer leaves the exact epoch-2 transition body intact, verifies it through the unchanged
Wave-100 get_transition() path, removes the newer L/C/U/root-binding + Wave-108 marker tails as in the
builder's own preserved counterexample, and then recreates the same partial stale quorum. If Wave 109
returns authoritative for epoch 1 while the sealed transition still names epoch 2's authority,
checkpoint, and root-binding SHA, the stated "complete transaction evidence erasure" boundary is too
strong.
"""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import AXM_FLOWING_COMPUTE_COMMIT_STATUS_AMBIGUITY_GUARD as w
import AXM_FLOWING_COMPUTE_COMMITTED_HISTORY_MANIFEST as w108
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w104
import AXM_FLOWING_COMPUTE_REMOTE_REGISTRY_MONOTONICITY as w100

q = w.q
g = w.g

BUILDER_HEAD = "84c5f53f4a6e9ffafc013db634adba485cd44479"
TESTED_SOURCE_COMMIT = "1747e087d3ab07312484980da987b88f8e8f56cd"
TOOL_BLOB = "6dbb03509100fdd724c3576a4938a9406e0eaf3e"
SELFTEST_BLOB = "f2142dc67475eba86d4c20975d53551cfb1170b0"
EXPECTED_FAIL = "FAIL_SURVIVING_TRANSITION_RECORD_IGNORED_BY_COMMIT_STATUS_GUARD"


def row_at_seq(store: dict, seq: int):
    for sha, body in store.items():
        if isinstance(body, dict) and body.get("seq") == seq:
            return sha, body
    raise KeyError(seq)


def new_world():
    st, priv, boot, rt, services, tokens, rs = q.fixture()
    ts = {}
    cs = g.new_certificate_store()
    domain = w104.new_certificate_witness_domain()
    bs = {}
    w.adopt_genesis(rt, st, boot, services, rs, cs, domain, bs)
    return st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs


def run() -> dict:
    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world()

    # Establish a real accepted epoch 1 and preserve its legitimate stale snapshots.
    _cp1, _use1, _link1, _tr1, _binding1 = w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs,
        "verifier-wave109-epoch1",
    )
    rt1 = deepcopy(rt)
    services1 = deepcopy(services)
    cs1 = deepcopy(cs)
    witness_disks1 = domain.disk_snapshots()
    cert1_sha = cs1["head"]

    # Establish a real accepted epoch 2. Critically, keep transition_store intact.
    cp2, _use2, link2, transition2_sha, _binding2 = w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs,
        "verifier-wave109-epoch2",
    )
    cert2_sha = cs["head"]
    binding2_sha = rt["app_state_sha"]
    witness_disks2 = domain.disk_snapshots()

    transition2 = w100.get_transition(ts, transition2_sha)
    transition_survives_and_names_epoch2 = (
        transition2.get("target_authority_sha") == link2["authority_sha"]
        and transition2.get("target_checkpoint_sha") == cp2["checkpoint_sha"]
        and transition2.get("target_app_state_sha") == binding2_sha
        and transition2.get("transition_sha") == transition2_sha
    )
    if not transition_survives_and_names_epoch2:
        raise AssertionError("epoch-2 transition record did not verify/name exact epoch-2 identities")

    # Remove only Wave-108 marker seq2 and roll the mutable runtime pointer back to epoch 1.
    attacked_st = deepcopy(st)
    commit2_sha, _ = row_at_seq(attacked_st[w108.COMMIT_STORE], 2)
    high2_sha, _ = row_at_seq(attacked_st[w108.HIGH_WATER_STORE], 2)
    attacked_st[w108.COMMIT_STORE].pop(commit2_sha)
    attacked_st[w108.HIGH_WATER_STORE].pop(high2_sha)
    attacked_rt = deepcopy(rt1)

    # Same partial stale quorum used by the builder's preserved Wave-109 counterexample.
    attacked_services = deepcopy(services)
    attacked_services["remote-b"] = deepcopy(services1["remote-b"])
    attacked_services["remote-c"] = deepcopy(services1["remote-c"])

    attacked_cs = deepcopy(cs)
    attacked_cs["records"].pop(cert2_sha)
    attacked_cs["head"] = cert1_sha

    mixed_disks = deepcopy(witness_disks2)
    mixed_disks["cert-b"] = deepcopy(witness_disks1["cert-b"])
    mixed_disks["cert-c"] = deepcopy(witness_disks1["cert-c"])
    domain.restore_disks(mixed_disks)
    domain._endpoints["cert-a"].online = False

    # Erase the same newer local L/C/U/root-binding rows used by Wave 109's preserved case.
    link2_sha = link2["authority_sha"]
    cp2_sha = link2["checkpoint_sha"]
    use2_sha = link2["use_sha"]
    damaged_st = deepcopy(attacked_st)
    damaged_st["L"].pop(link2_sha)
    damaged_st["C"].pop(cp2_sha)
    damaged_st["U"].pop(use2_sha)
    damaged_bs = deepcopy(bs)
    damaged_bs.pop(binding2_sha)

    # Transition evidence is intentionally NOT erased. Verify it again after all damage.
    retained_transition = w100.get_transition(ts, transition2_sha)
    retained_transition_exact = (
        retained_transition.get("target_authority_sha") == link2_sha
        and retained_transition.get("target_checkpoint_sha") == cp2_sha
        and retained_transition.get("target_app_state_sha") == binding2_sha
    )

    state = w.commit_status_state(damaged_st, boot, attacked_rt, rs, damaged_bs)
    authority = w.authority(
        attacked_rt, damaged_st, boot, attacked_services, rs, attacked_cs, domain, damaged_bs
    )

    stale_authority_with_surviving_transition = (
        retained_transition_exact
        and state.get("status") == w.HISTORY_VALID
        and state.get("committed_count") == 1
        and authority.startswith("AUTHORITATIVE")
    )

    report = {
        "schema": "axm.verification.wave109.transition_store_gap/v1",
        "builder_head": BUILDER_HEAD,
        "tested_source_commit": TESTED_SOURCE_COMMIT,
        "tool_blob": TOOL_BLOB,
        "selftest_blob": SELFTEST_BLOB,
        "verdict": EXPECTED_FAIL if stale_authority_with_surviving_transition else "NOT_REPRODUCED",
        "transition_store": {
            "retained": transition2_sha in ts,
            "transition_sha": transition2_sha,
            "target_authority_sha": retained_transition.get("target_authority_sha"),
            "target_checkpoint_sha": retained_transition.get("target_checkpoint_sha"),
            "target_app_state_sha": retained_transition.get("target_app_state_sha"),
            "exact_epoch2_identity_match": retained_transition_exact,
        },
        "erased_newer_rows": {
            "wave108_commit_marker_seq2": True,
            "wave108_high_water_seq2": True,
            "authority_link": link2_sha not in damaged_st["L"],
            "checkpoint": cp2_sha not in damaged_st["C"],
            "signer_use": use2_sha not in damaged_st["U"],
            "root_binding": binding2_sha not in damaged_bs,
            "transition_record": False,
        },
        "wave109_commit_status_state": state,
        "wave109_authority": authority,
        "severity_boundary": {
            "hash_forge_used": False,
            "credential_forge_used": False,
            "transition_body_modified": False,
            "newer_remote_a_retained": True,
            "newer_cert_a_disk_retained_but_endpoint_unavailable": True,
            "claim": (
                "The surviving transition does not by itself prove commit. But Wave 109 explicitly "
                "chooses HOLD when retained transaction evidence cannot distinguish prepared from "
                "committed-then-damaged. Because transition_store is another sealed retained prepare "
                "artifact naming the exact newer authority/checkpoint/binding, omitting it makes the "
                "published 'complete newer local transaction evidence erasure' boundary too strong."
            ),
        },
    }
    return report


def main() -> int:
    report = run()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["verdict"] == EXPECTED_FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
