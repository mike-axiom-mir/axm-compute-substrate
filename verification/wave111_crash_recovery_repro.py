#!/usr/bin/env python3
"""Independent adversarial verifier for AXM Flowing Compute Wave 111.

This verifier does not alter builder source. It probes two boundaries that are not covered by the
Wave-111 self-test:

1. Recovery after the documented lower-commit -> provenance-persist crash boundary. Wave 111 proves
   this boundary fails closed, but a durable protocol also needs a bounded recovery path. We simulate
   the exact crash by committing through unchanged Wave 110 (so Wave-111 provenance is absent), then
   retry the public Wave-111 commit API with the exact same link/transition.

2. Retained-history verification cost. Wave 111 intentionally leaves depth-6 untimed. Its per-epoch
   provenance loop calls _marker_rows_for_seq(), which re-runs Wave-108 _marker_chains(). We instrument
   exact marker-row linearization work at depths 1/4/8 to expose scaling without claiming wall-clock
   performance or energy results.

A third liveness probe records the public state after an intentionally abandoned prepare. This is an
availability/agency boundary, not a stale-authority claim.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import AXM_FLOWING_COMPUTE_TRANSITION_PROVENANCE_LEDGER as w
import AXM_FLOWING_COMPUTE_TRANSITION_EVIDENCE_GUARD as w110
import AXM_FLOWING_COMPUTE_COMMITTED_HISTORY_MANIFEST as w108
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w104

q = w.q
g = w.g

BUILDER_HEAD = "ea430afcade876dee771c972028a4c02761a737f"
TESTED_SOURCE_COMMIT = "8b3c7e727fb1110259da15a9e9e62b720c520045"
TOOL_BLOB = "638294762fc84245e265bfad138869f83c621fd6"
SELFTEST_BLOB = "d48f09c80900ad3a8ab1667f524832ca3a2892db"


def new_world():
    st, priv, boot, rt, services, tokens, rs = q.fixture()
    ts = {}
    cs = g.new_certificate_store()
    domain = w104.new_certificate_witness_domain()
    bs = {}
    w.adopt_genesis(rt, st, boot, services, rs, ts, cs, domain, bs)
    return st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs


def crash_retry_case() -> dict:
    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world()
    cp, use, link, transition_sha, body = w.prepare(
        rt, st, priv, boot, services, rs, ts, cs, domain, bs,
        target_user_app_state_sha="41" * 32,
    )

    # Simulate a process crash after the unchanged lower layer has committed and persisted its normal
    # marker state but before Wave 111 appends the exact-transition provenance row.
    lower_result = w110.commit(
        rt, st, boot, rs, ts, link["authority_sha"], transition_sha, bs
    )
    state_after_crash = w.commit_status_state(st, boot, rt, rs, bs, ts)
    authority_after_crash = w.authority(
        rt, st, boot, services, rs, ts, cs, domain, bs
    )

    retry_result = None
    retry_exception = None
    try:
        retry_result = w.commit(
            rt, st, boot, rs, ts, link["authority_sha"], transition_sha, bs
        )
    except Exception as exc:  # evidence, not harness failure
        retry_exception = f"{type(exc).__name__}:{exc}"

    state_after_retry = w.commit_status_state(st, boot, rt, rs, bs, ts)

    # If local provenance repaired, finish ordinary publication/certification to distinguish a local
    # recovery problem from merely not having published the already-repaired epoch yet.
    publish_results = {}
    cert_result = None
    cert_sync = None
    authority_after_finish = None
    if state_after_retry.get("status") == w.HISTORY_VALID:
        for slot in q.REMOTE_IDS:
            try:
                publish_results[slot] = w.publish(rt, st, boot, services, tokens, rs, slot)
            except Exception as exc:
                publish_results[slot] = f"EXC:{type(exc).__name__}:{exc}"
        try:
            cert_result, cert_sync = w.certify_and_sync(
                rt, st, boot, services, rs, cs, domain
            )
        except Exception as exc:
            cert_result = f"EXC:{type(exc).__name__}:{exc}"
        authority_after_finish = w.authority(
            rt, st, boot, services, rs, ts, cs, domain, bs
        )

    recovered = state_after_retry.get("status") == w.HISTORY_VALID
    return {
        "lower_commit_result": lower_result,
        "state_after_crash": state_after_crash,
        "authority_after_crash": authority_after_crash,
        "retry_result": retry_result,
        "retry_exception": retry_exception,
        "state_after_retry": state_after_retry,
        "recovered_by_public_commit_retry": recovered,
        "publish_results_if_recovered": publish_results,
        "certificate_result_if_recovered": cert_result,
        "certificate_sync_if_recovered": cert_sync,
        "authority_after_finish_if_recovered": authority_after_finish,
        "verdict": (
            "SURVIVES_PUBLIC_RETRY_RECOVERY"
            if recovered
            else "FAIL_COMMIT_TO_PROVENANCE_CRASH_HAS_NO_PUBLIC_RETRY_RECOVERY"
        ),
    }


def abandoned_prepare_case() -> dict:
    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world()
    _cp, _use, link, transition_sha, _body = w.prepare(
        rt, st, priv, boot, services, rs, ts, cs, domain, bs,
        target_user_app_state_sha="52" * 32,
    )
    unresolved = w.commit_status_state(st, boot, rt, rs, bs, ts)
    blocked = w.authority(rt, st, boot, services, rs, ts, cs, domain, bs)

    second_prepare = None
    try:
        w.prepare(
            rt, st, priv, boot, services, rs, ts, cs, domain, bs,
            target_user_app_state_sha="53" * 32,
        )
        second_prepare = "UNEXPECTEDLY_ALLOWED"
    except Exception as exc:
        second_prepare = f"BLOCKED:{type(exc).__name__}:{exc}"

    genesis_retry = None
    try:
        w.adopt_genesis(rt, st, boot, services, rs, ts, cs, domain, bs)
        genesis_retry = "UNEXPECTEDLY_ALLOWED"
    except Exception as exc:
        genesis_retry = f"BLOCKED:{type(exc).__name__}:{exc}"

    # Deleting only the speculative transition is not a supported public abort. Record whether even
    # that manual partial cleanup clears the lower prepared evidence; do not promote it as a fix.
    ts.pop(transition_sha, None)
    after_transition_only_cleanup = w.commit_status_state(st, boot, rt, rs, bs, ts)
    authority_after_transition_only_cleanup = w.authority(
        rt, st, boot, services, rs, ts, cs, domain, bs
    )

    return {
        "prepared_authority_sha": link["authority_sha"],
        "state_after_prepare": unresolved,
        "authority_after_prepare": blocked,
        "public_abort_api_present": hasattr(w, "abort"),
        "second_prepare": second_prepare,
        "genesis_retry": genesis_retry,
        "state_after_transition_only_cleanup": after_transition_only_cleanup,
        "authority_after_transition_only_cleanup": authority_after_transition_only_cleanup,
        "classification": "LIVENESS_BOUNDARY_NOT_STALE_AUTHORITY_CLAIM",
    }


def build_depth(depth: int):
    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world()
    for i in range(1, depth + 1):
        w.advance_all(
            st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs,
            f"verifier-wave111-depth-{depth}-epoch-{i}",
        )
    return st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs


def marker_scan_case(depth: int) -> dict:
    st, _priv, boot, rt, _services, _tokens, rs, ts, _cs, _domain, bs = build_depth(depth)

    counts = {
        "marker_rows_for_seq_calls": 0,
        "marker_chains_calls": 0,
        "linearize_calls": 0,
        "marker_store_rows_scanned": 0,
    }
    original_rows = w._marker_rows_for_seq
    original_chains = w108._marker_chains
    original_linearize = w108._linearize

    def wrapped_rows(st_arg, seq_arg):
        counts["marker_rows_for_seq_calls"] += 1
        return original_rows(st_arg, seq_arg)

    def wrapped_chains(*args, **kwargs):
        counts["marker_chains_calls"] += 1
        return original_chains(*args, **kwargs)

    def wrapped_linearize(store, *args, **kwargs):
        counts["linearize_calls"] += 1
        counts["marker_store_rows_scanned"] += len(store)
        return original_linearize(store, *args, **kwargs)

    w._marker_rows_for_seq = wrapped_rows
    w108._marker_chains = wrapped_chains
    w108._linearize = wrapped_linearize
    try:
        state = w.commit_status_state(st, boot, rt, rs, bs, ts)
    finally:
        w._marker_rows_for_seq = original_rows
        w108._marker_chains = original_chains
        w108._linearize = original_linearize

    counts["history_status"] = state.get("status")
    counts["depth"] = depth
    return counts


def main() -> int:
    crash = crash_retry_case()
    abandoned = abandoned_prepare_case()
    scans = [marker_scan_case(depth) for depth in (1, 4, 8)]

    report = {
        "schema": "axm.flowing-compute.wave111.independent-adversarial-verifier/v1",
        "builder": {
            "head": BUILDER_HEAD,
            "tested_source_commit": TESTED_SOURCE_COMMIT,
            "tool_blob": TOOL_BLOB,
            "selftest_blob": SELFTEST_BLOB,
        },
        "crash_retry": crash,
        "abandoned_prepare": abandoned,
        "marker_scan_scaling": scans,
        "truth_boundary": {
            "no_builder_files_modified": True,
            "no_wall_clock_performance_claim": True,
            "no_energy_claim": True,
            "no_os_process_independence_claim": True,
            "scan_counts_are_structural_not_timing": True,
        },
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
