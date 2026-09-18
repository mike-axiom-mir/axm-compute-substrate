#!/usr/bin/env python3
"""Independent Wave 108 adversarial reproducer.

This imports the unchanged Wave 108 implementation.  It tests whether truncating only the
newest entries from BOTH Wave-108 commit-marker ledgers can cause a genuinely accepted epoch-2
link that still exists in L/C/U to be reclassified as merely "prepared", and whether that lost
commit-status memory can combine with a partial stale quorum to make epoch 1 authoritative again.

No builder source is modified.  The strongest attack deliberately preserves:
- all epoch-2 local L/C/U bodies;
- the complete current Wave-105 binding store (including the epoch-2 binding);
- remote-a's full [1,2] history;
- cert-a's full [1,2] witness disk (but makes that one newer certificate witness unavailable).
Only the two Wave-108 marker tails, the local runtime pointer, the local certificate tail, two
remote stores, and two certificate-witness disks are restored to epoch 1.
"""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import AXM_FLOWING_COMPUTE_COMMITTED_HISTORY_MANIFEST as w  # noqa: E402
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w104  # noqa: E402


g = w.g
q = w.q

BUILDER_HEAD = "7573e1e97d026ed07065fcca46cc0d88a26e64b5"
TESTED_SOURCE_COMMIT = "7b9ec8548bde69df1d8971567aaf04abd0fa2e5c"
TOOL_BLOB = "629318c9645649a29d7a4d4c97f106a0ba958f6d"
SELFTEST_BLOB = "aeac803084fc05e82c626bb830cee48146c710e2"


def need(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def row_at_seq(store: dict, seq: int) -> tuple[str, dict]:
    matches = [(sha, body) for sha, body in store.items() if body.get("seq") == seq]
    if len(matches) != 1:
        raise RuntimeError(f"expected one row at seq {seq}, got {len(matches)}")
    return matches[0]


def remote_epochs(service: dict) -> list[int]:
    rows = sorted(service["records"].values(), key=lambda row: row["seq"])
    return [row["authority_epoch"] for row in rows]


def witness_sequences(endpoint) -> list[int]:
    rows = sorted(endpoint.records.values(), key=lambda row: row["seq"])
    return [row["certificate_seq"] for row in rows]


def new_world():
    st, priv, boot, rt, services, tokens, registry_store = q.fixture()
    transition_store = {}
    certificate_store = g.new_certificate_store()
    domain = w104.new_certificate_witness_domain()
    binding_store = {}
    w.adopt_genesis(
        rt, st, boot, services, registry_store, certificate_store, domain, binding_store
    )
    return (
        st, priv, boot, rt, services, tokens, registry_store, transition_store,
        certificate_store, domain, binding_store,
    )


def run() -> dict:
    (
        st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs,
    ) = new_world()

    # Build a genuinely accepted epoch 1 and preserve only the old pieces later used.
    w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs,
        "verifier-wave108-marker-tail-epoch1",
    )
    status1, link1, cp1 = q.current_local(rt, st, boot)
    need(status1 == "LOCAL_OK" and link1.get("epoch") == 1, f"bad epoch1 setup: {status1}")
    rt1 = deepcopy(rt)
    services1 = deepcopy(services)
    cs1 = deepcopy(cs)
    witness_disks1 = domain.disk_snapshots()
    cert1_sha = cs1.get("head")
    need(isinstance(cert1_sha, str), "epoch1 certificate head missing")

    # Advance normally again.  Epoch 2 is fully accepted and witnessed before any mutation.
    w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs,
        "verifier-wave108-marker-tail-epoch2",
    )
    status2, link2, cp2 = q.current_local(rt, st, boot)
    need(status2 == "LOCAL_OK" and link2.get("epoch") == 2, f"bad epoch2 setup: {status2}")
    accepted_epoch2 = w.authority(rt, st, boot, services, rs, cs, domain, bs)
    need(accepted_epoch2.startswith("AUTHORITATIVE"), f"epoch2 not authoritative: {accepted_epoch2}")

    clean_state = w.committed_history_state(st, boot, rt)
    need(clean_state.get("status") == w.HISTORY_VALID, f"clean Wave108 history invalid: {clean_state}")
    need(clean_state.get("committed_count") == 2, "clean Wave108 manifest did not retain two commits")

    cert2_sha = cs.get("head")
    need(isinstance(cert2_sha, str) and cert2_sha != cert1_sha, "epoch2 certificate head missing")
    witness_disks2 = domain.disk_snapshots()

    # Truncate only the newest Wave-108 marker row from each paired ledger.  Do NOT delete the
    # epoch-2 authority/checkpoint/use bodies.  Roll only the mutable runtime pointer to epoch 1.
    attacked_st = deepcopy(st)
    commit2_sha, _commit2 = row_at_seq(attacked_st[w.COMMIT_STORE], 2)
    high2_sha, _high2 = row_at_seq(attacked_st[w.HIGH_WATER_STORE], 2)
    attacked_st[w.COMMIT_STORE].pop(commit2_sha)
    attacked_st[w.HIGH_WATER_STORE].pop(high2_sha)
    attacked_rt = deepcopy(rt1)

    # First isolate the Wave-108 semantic effect.  With every newer external witness untouched,
    # stale authority must still be blocked.  But Wave 108 should not be allowed to forget that
    # link2 was previously COMMITTED and relabel it as a harmless prepared-only link.
    reclassified_state = w.committed_history_state(attacked_st, boot, attacked_rt)
    control_external_intact = w.authority(
        attacked_rt, attacked_st, boot, services, rs, cs, domain, bs
    )

    link2_sha = link2["authority_sha"]
    cp2_sha = link2["checkpoint_sha"]
    use2_sha = link2["use_sha"]
    local_epoch2_bodies_retained = (
        link2_sha in attacked_st.get("L", {})
        and cp2_sha in attacked_st.get("C", {})
        and use2_sha in attacked_st.get("U", {})
    )
    need(local_epoch2_bodies_retained, "attack accidentally removed epoch2 L/C/U bodies")

    # Narrow stale-quorum attack.  Keep remote-a fully newer.  Restore only B+C to their legitimate
    # epoch-1 snapshots.  Truncate only the local quorum-certificate tail back to certificate 1.
    attacked_services = deepcopy(services)
    attacked_services["remote-b"] = deepcopy(services1["remote-b"])
    attacked_services["remote-c"] = deepcopy(services1["remote-c"])

    attacked_cs = deepcopy(cs)
    attacked_cs["records"].pop(cert2_sha)
    attacked_cs["head"] = cert1_sha

    # Keep the genuine registered cert-a endpoint and its epoch-2 disk intact but make that one
    # newer certificate witness unavailable.  Restore only cert-b + cert-c disks to epoch 1.
    mixed_disks = deepcopy(witness_disks2)
    mixed_disks["cert-b"] = deepcopy(witness_disks1["cert-b"])
    mixed_disks["cert-c"] = deepcopy(witness_disks1["cert-c"])
    domain.restore_disks(mixed_disks)
    domain._endpoints["cert-a"].online = False

    # Deliberately keep the CURRENT binding store, including its epoch-2 binding body.  The stale
    # runtime merely points at the still-retained epoch-1 binding; no binding row is deleted.
    attacked_state = w.committed_history_state(attacked_st, boot, attacked_rt)
    attacked_authority = w.authority(
        attacked_rt, attacked_st, boot, attacked_services, rs, attacked_cs, domain, bs
    )

    remote_histories = {slot: remote_epochs(attacked_services[slot]) for slot in q.REMOTE_IDS}
    witness_histories = {
        slot: witness_sequences(domain._endpoints[slot]) for slot in w104.WITNESS_IDS
    }

    marker_reclassified = (
        attacked_state.get("status") == w.HISTORY_VALID
        and link2_sha in attacked_state.get("prepared_authority_shas", [])
        and attacked_state.get("committed_count") == 1
    )
    stale_authority = attacked_authority.startswith("AUTHORITATIVE")

    if stale_authority and marker_reclassified:
        verdict = (
            "FAIL_COMMITTED_MARKER_TAIL_TRUNCATION_RECLASSIFIES_ACCEPTED_EPOCH_AS_PREPARED_"
            "AND_PERMITS_STALE_QUORUM"
        )
    elif marker_reclassified:
        verdict = "FAIL_COMMITTED_MARKER_TAIL_TRUNCATION_FORGETS_COMMIT_STATUS_BOUNDED"
    else:
        verdict = "NOT_REPRODUCED"

    report = {
        "schema": "axm.flowing_compute.verifier.wave108.marker_tail_reclassification/v1",
        "verdict": verdict,
        "builder_head_tested": BUILDER_HEAD,
        "wave108_tested_source_commit": TESTED_SOURCE_COMMIT,
        "wave108_tool_blob": TOOL_BLOB,
        "wave108_selftest_blob": SELFTEST_BLOB,
        "control": {
            "epoch2_was_authoritative": accepted_epoch2,
            "clean_committed_count": clean_state.get("committed_count"),
            "marker_tail_and_runtime_rollback_with_newer_external_state_intact": control_external_intact,
            "marker_tail_only_history_state": reclassified_state,
        },
        "attack": {
            "deleted_only_from_wave108_markers": {
                "commit_seq2_record_sha": commit2_sha,
                "high_water_seq2_record_sha": high2_sha,
            },
            "epoch2_local_authority_body_retained": link2_sha in attacked_st.get("L", {}),
            "epoch2_local_checkpoint_body_retained": cp2_sha in attacked_st.get("C", {}),
            "epoch2_local_signer_use_body_retained": use2_sha in attacked_st.get("U", {}),
            "current_binding_store_preserved": True,
            "runtime_restored_to_epoch": link1.get("epoch"),
            "local_certificate_tail_restored_to_seq": 1,
            "remote_histories": remote_histories,
            "certificate_witness_histories": witness_histories,
            "cert_a_newer_disk_preserved_but_offline": (
                witness_histories.get("cert-a") == [1, 2]
                and not domain._endpoints["cert-a"].online
            ),
            "committed_history_state": attacked_state,
            "authority": attacked_authority,
        },
        "bounded_interpretation": [
            "The exact PR #32 newest-link deletion repair is not attacked here; all epoch-2 L/C/U bodies remain present.",
            "The attack targets commit-status memory: removing both Wave-108 seq-2 marker tails makes the still-retained epoch-2 link look like a legal prepared-only next epoch when runtime is rolled back to epoch 1.",
            "Remote-a remains fully at epochs [1,2]. Cert-a retains certificate sequences [1,2] but is unavailable; only B+C remote/witness stores are restored to epoch 1.",
            "The complete current Wave-105 binding store is preserved, including its newer binding body.",
            "No performance, energy, retained/incremental/dormant-compute, network, OS-process, device, provider, merge, or CANON claim is made by this verifier.",
        ],
    }

    need(verdict.startswith("FAIL_"), json.dumps(report, indent=2, sort_keys=True))
    return report


def main() -> None:
    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
