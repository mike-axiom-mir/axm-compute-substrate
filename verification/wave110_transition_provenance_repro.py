#!/usr/bin/env python3
"""Independent adversarial verifier for AXM Flowing Compute Wave 110.

Primary finding under test:
Wave 110 says each committed authority must have its *exact* retained transition. The commit-status
checker, however, does not retain or compare an expected transition SHA. It only asks for one sealed
transition that names the committed authority/checkpoint/predecessor and whose target-state hash is
self-consistent with caller-supplied app/registry strings. This reproducer deletes the real committed
transition and replaces it with a newly content-addressed transition that keeps the authority and
checkpoint names but changes the app-state, registry, generations, and delta semantics. If Wave 110
still classifies the history VALID and authoritative, "exact transition" provenance is not proven.

Secondary check:
Wave 110 returns immediately when Wave 109 reports HISTORY_NONE, before inspecting transition_store.
The reproducer therefore also tests whether a surviving accepted transition can be ignored after the
lower retained state is restored to genesis and the Wave-108 marker-store keys are removed.

No builder files are modified by this script; it is verifier-only evidence.
"""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import AXM_FLOWING_COMPUTE_TRANSITION_EVIDENCE_GUARD as w
import AXM_FLOWING_COMPUTE_COMMITTED_HISTORY_MANIFEST as w108
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w104
import AXM_FLOWING_COMPUTE_REMOTE_REGISTRY_MONOTONICITY as w100

q = w.q
g = w.g

BUILDER_HEAD = "0d97d0dde7f3b72ff1da6ae68315c0e163330f75"
TESTED_SOURCE_COMMIT = "dfe22164f853cf1f04f0ae93103e33478ed074fd"
TOOL_BLOB = "abc96489922bcf7af64412a8e85cf447796321b1"
SELFTEST_BLOB = "00b0eccac36cf479c81004ceac811a6af1293b85"
PRIMARY_FAIL = "FAIL_COMMITTED_TRANSITION_IDENTITY_IS_SUBSTITUTABLE"
SECONDARY_FAIL = "FAIL_TRANSITION_ONLY_EVIDENCE_IS_IGNORED_WHEN_WAVE109_REPORTS_NONE"


def new_world():
    st, priv, boot, rt, services, tokens, rs = q.fixture()
    ts = {}
    cs = g.new_certificate_store()
    domain = w104.new_certificate_witness_domain()
    bs = {}
    w.adopt_genesis(rt, st, boot, services, rs, ts, cs, domain, bs)
    return st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs


def substitution_case() -> dict:
    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world()
    cp1, _use1, link1, transition1_sha, _binding1, _cert1_sha, _cert1 = w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs,
        "verifier-wave110-transition-provenance-epoch1",
    )

    legitimate = w100.get_transition(ts, transition1_sha)
    legitimate_target_state = legitimate["target_state_sha"]
    legitimate_target_registry = legitimate["target_registry_sha"]
    legitimate_target_app = legitimate["target_app_state_sha"]

    # Delete the transition Wave 100 actually produced for the committed epoch.
    ts.pop(transition1_sha)

    # Replace it with a different, newly content-addressed transition. Keep only the identities that
    # Wave 110 currently compares against committed history; alter the semantics it does not compare.
    fake = deepcopy(legitimate)
    fake["target_app_state_sha"] = "11" * 32
    fake["target_registry_sha"] = "22" * 32
    fake["target_state_sha"] = q.binding(
        fake["target_app_state_sha"], fake["target_registry_sha"]
    )
    fake["current_registry_sha"] = "33" * 32
    fake["current_generation"] = 700
    fake["target_generation"] = 999
    fake["transition_kind"] = "VERIFIER_SYNTHETIC_SUBSTITUTION"
    fake["changed_slots"] = ["not-a-real-remote-slot"]
    fake["changed_fields"] = {"not-a-real-remote-slot": ["imaginary_field"]}
    fake["transition_sha"] = ""
    fake = w100._seal(fake, "transition_sha")
    fake_sha = w100.put_transition(ts, fake)

    state = w.commit_status_state(st, boot, rt, rs, bs, ts)
    authority = w.authority(rt, st, boot, services, rs, ts, cs, domain, bs)

    target_registry_absent = fake["target_registry_sha"] not in rs
    checkpoint_state_mismatch = fake["target_state_sha"] != cp1.get("state_sha")
    semantic_identity_changed = (
        fake["target_app_state_sha"] != legitimate_target_app
        and fake["target_registry_sha"] != legitimate_target_registry
        and fake["target_state_sha"] != legitimate_target_state
    )
    reproduced = (
        transition1_sha not in ts
        and fake_sha in ts
        and target_registry_absent
        and checkpoint_state_mismatch
        and semantic_identity_changed
        and state.get("status") == w.HISTORY_VALID
        and authority.startswith("AUTHORITATIVE")
    )

    return {
        "verdict": PRIMARY_FAIL if reproduced else "NOT_REPRODUCED",
        "committed_authority_sha": link1["authority_sha"],
        "committed_checkpoint_sha": cp1["checkpoint_sha"],
        "legitimate_transition_sha_removed": transition1_sha,
        "substitute_transition_sha": fake_sha,
        "substitute_target_registry_absent_from_registry_store": target_registry_absent,
        "substitute_target_state_mismatches_committed_checkpoint_state": checkpoint_state_mismatch,
        "substitute_changed_app_registry_state_identity": semantic_identity_changed,
        "substitute_semantics": {
            "target_app_state_sha": fake["target_app_state_sha"],
            "target_registry_sha": fake["target_registry_sha"],
            "target_state_sha": fake["target_state_sha"],
            "current_registry_sha": fake["current_registry_sha"],
            "current_generation": fake["current_generation"],
            "target_generation": fake["target_generation"],
            "transition_kind": fake["transition_kind"],
            "changed_slots": fake["changed_slots"],
            "changed_fields": fake["changed_fields"],
        },
        "wave110_commit_status_state": state,
        "wave110_authority": authority,
        "boundary": {
            "credential_forge_used": False,
            "existing_hash_collision_used": False,
            "real_transition_body_modified_in_place": False,
            "replacement_is_new_content_addressed_body": True,
            "claim": (
                "The Wave-110 guard proves that one self-consistent sealed body points at the same "
                "authority/checkpoint/predecessor. It does not prove that this is the transition "
                "actually created/committed for that authority, because no committed object names "
                "the expected transition SHA and checkpoint state/registry semantics are not "
                "revalidated here."
            ),
        },
    }


def none_short_circuit_case() -> dict:
    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world()

    # Preserve the already-adopted genesis world. This contains the Wave-106 adoption and genesis
    # binding, before any accepted authority epoch exists.
    genesis_st = deepcopy(st)
    genesis_rt = deepcopy(rt)
    genesis_services = deepcopy(services)
    genesis_cs = deepcopy(cs)
    genesis_disks = domain.disk_snapshots()
    genesis_bs = deepcopy(bs)

    cp1, _use1, link1, transition1_sha, _binding1, _cert1_sha, _cert1 = w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs,
        "verifier-wave110-none-short-circuit-epoch1",
    )
    retained = w100.get_transition(ts, transition1_sha)

    # Restore the lower authority world to its legitimate genesis image, but deliberately leave the
    # newer transition_store untouched. Removing the two Wave-108 marker-store keys makes Wave 108,
    # then Wave 109, classify this as HISTORY_NONE. Wave 110 currently returns before inspecting ts.
    attacked_st = deepcopy(genesis_st)
    attacked_st.pop(w108.COMMIT_STORE, None)
    attacked_st.pop(w108.HIGH_WATER_STORE, None)
    attacked_rt = deepcopy(genesis_rt)
    attacked_services = deepcopy(genesis_services)
    attacked_cs = deepcopy(genesis_cs)
    attacked_bs = deepcopy(genesis_bs)
    domain.restore_disks(genesis_disks)

    state = w.commit_status_state(attacked_st, boot, attacked_rt, rs, attacked_bs, ts)
    authority = w.authority(
        attacked_rt, attacked_st, boot, attacked_services, rs, ts,
        attacked_cs, domain, attacked_bs,
    )

    transition_still_names_accepted_epoch = (
        retained.get("target_authority_sha") == link1["authority_sha"]
        and retained.get("target_checkpoint_sha") == cp1["checkpoint_sha"]
        and transition1_sha in ts
    )
    reproduced = (
        transition_still_names_accepted_epoch
        and state.get("status") == w.HISTORY_NONE
        and authority.startswith("AUTHORITATIVE")
    )

    return {
        "verdict": SECONDARY_FAIL if reproduced else "NOT_REPRODUCED",
        "retained_transition_sha": transition1_sha,
        "retained_transition_names_accepted_epoch1": transition_still_names_accepted_epoch,
        "wave108_marker_store_keys_removed": True,
        "wave110_commit_status_state": state,
        "wave110_authority": authority,
        "boundary": {
            "transition_record_erased": False,
            "lower_authority_state_restored_to_saved_genesis": True,
            "marker_store_keys_removed": True,
            "claim": (
                "Wave 110 documents that a valid retained transition not accounted for by the "
                "committed marker lineage is unresolved. If HISTORY_NONE bypasses transition "
                "inspection and genesis becomes authoritative while the accepted-epoch transition "
                "survives, that boundary is too strong."
            ),
        },
    }


def run() -> dict:
    primary = substitution_case()
    secondary = none_short_circuit_case()
    return {
        "schema": "axm.verification.wave110.transition_provenance/v1",
        "builder_head": BUILDER_HEAD,
        "tested_source_commit": TESTED_SOURCE_COMMIT,
        "tool_blob": TOOL_BLOB,
        "selftest_blob": SELFTEST_BLOB,
        "primary": primary,
        "secondary": secondary,
        "overall_verdict": primary["verdict"],
    }


def main() -> int:
    report = run()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["primary"]["verdict"] == PRIMARY_FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
