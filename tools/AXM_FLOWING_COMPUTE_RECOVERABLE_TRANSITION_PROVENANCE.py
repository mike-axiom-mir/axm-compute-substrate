#!/usr/bin/env python3
"""AXM Flowing Compute Wave 112: exact crash-recoverable transition provenance.

Additive experiment over exact Wave 111. Independent verifier PR #36 found a bounded liveness hole:
a lower Wave-110 commit can be durable while the Wave-111 provenance append is lost to a crash. Wave
111 correctly HOLDs that state, but retrying its public commit API re-enters lower transaction
semantics and cannot finish the already-committed exact decision. The verifier also exposed a
quadratic retained-history validation component because Wave 111 re-linearizes the full Wave-108
marker chains once per committed epoch.

Wave 112 adds two bounded repairs without rewriting Wave 111:

1. Public commit retry is idempotent for one very specific crash state. If lower Wave-110 evidence is
   VALID, proves the requested authority is already committed, proves exactly one retained transition
   targets it, and Wave-111 provenance is missing only that trailing row, Wave 112 appends only that
   exact missing provenance fact. A different transition SHA cannot recover the commit.
2. Wave-112 status validation linearizes the Wave-108 commit/high-water marker chains once per
   validation pass and indexes them by sequence, instead of rescanning both chains for every epoch.

Truth boundary: recovery is evidence-driven inside the same modeled Python failure domain. It does not
create an independent durable commit-decision witness and it does not make an abandoned PREPARE safe
to delete. Whole-domain rollback still erases every newer fact. The structural scaling test is
synthetic correctness/algorithmic evidence only; this wave makes no wall-clock, energy,
retained/incremental/dormant-compute, OS-process, device, physical, network, or provider-independence
claim. No merge or CANON promotion is performed by this tool.
"""
from __future__ import annotations

import hashlib

import AXM_FLOWING_COMPUTE_TRANSITION_PROVENANCE_LEDGER as w111
import AXM_FLOWING_COMPUTE_TRANSITION_EVIDENCE_GUARD as w110
import AXM_FLOWING_COMPUTE_COMMITTED_HISTORY_MANIFEST as w108
import AXM_FLOWING_COMPUTE_REMOTE_REGISTRY_MONOTONICITY as w100
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w104

q = w111.q
g = w111.g

SRC = {
    "wave111_builder_head": "ea430afcade876dee771c972028a4c02761a737f",
    "wave111_tested_source_commit": "8b3c7e727fb1110259da15a9e9e62b720c520045",
    "wave111_tool_blob": "638294762fc84245e265bfad138869f83c621fd6",
    "wave111_selftest_blob": "d48f09c80900ad3a8ab1667f524832ca3a2892db",
    "verifier_pr": 36,
    "verifier_base": "ea430afcade876dee771c972028a4c02761a737f",
    "verifier_ci_tested_head": "5f71aee8ecacd1565b0dc74f0e525762deacd2be",
    "verifier_current_head_at_wave112_start": "07e920990787eec76d5dd0ef0483240f3cf6dc52",
    "verifier_ci_run": 35214808338,
    "verifier_verdict": "FAIL_COMMIT_TO_PROVENANCE_CRASH_HAS_NO_PUBLIC_RETRY_RECOVERY",
}

PROVENANCE_STORE = w111.PROVENANCE_STORE
HISTORY_NONE = w111.HISTORY_NONE
HISTORY_VALID = w111.HISTORY_VALID
HISTORY_INCOMPLETE = w111.HISTORY_INCOMPLETE
HISTORY_UNRESOLVED = w111.HISTORY_UNRESOLVED
HOLD_INCOMPLETE = w111.HOLD_INCOMPLETE
HOLD_UNRESOLVED = w111.HOLD_UNRESOLVED


def _indexed_marker_rows(st: dict) -> dict[int, tuple[tuple[str, dict], tuple[str, dict]]]:
    """Verify/linearize Wave-108 marker chains once, then index exact paired rows by sequence."""
    chains = w108._marker_chains(st)
    commits = chains["commits"]
    highs = chains["highs"]
    if len(commits) != len(highs):
        raise ValueError("wave108-marker-chain-length-mismatch")
    indexed: dict[int, tuple[tuple[str, dict], tuple[str, dict]]] = {}
    for seq, (commit_row, high_row) in enumerate(zip(commits, highs), start=1):
        commit_sha, commit_body = commit_row
        high_sha, high_body = high_row
        if commit_body.get("seq") != seq or high_body.get("seq") != seq:
            raise ValueError("wave108-marker-sequence-mismatch")
        if commit_body.get("authority_sha") != high_body.get("authority_sha"):
            raise ValueError("wave108-marker-pair-authority-mismatch")
        indexed[seq] = ((commit_sha, commit_body), (high_sha, high_body))
    return indexed


def _validated_provenance_state(
    st: dict,
    boot: dict,
    registry_store: dict,
    transition_store: dict,
    base: dict,
) -> dict:
    """Validate Wave-111 provenance against one indexed Wave-108 marker view."""
    try:
        provenance = w111._provenance_rows(st)
        assert provenance is not None
        committed = list(base.get("committed_authority_shas", []))
        if len(provenance) != len(committed):
            raise ValueError("committed-transition-provenance-count-mismatch")
        markers = _indexed_marker_rows(st)
        if len(markers) != len(committed):
            raise ValueError("wave108-marker-count-does-not-match-committed-authorities")

        previous_authority: str | None = None
        previous_target_registry: str | None = None
        expected_transition_shas: list[str] = []
        for seq, ((record_sha, record), authority_sha) in enumerate(zip(provenance, committed), start=1):
            if record.get("seq") != seq or record.get("epoch") != seq:
                raise ValueError("transition-provenance-sequence-or-epoch-mismatch")
            if record.get("authority_sha") != authority_sha:
                raise ValueError("transition-provenance-authority-mismatch")

            link, cp, _use = g.w98.resolve(st, authority_sha, boot)
            if record.get("checkpoint_sha") != link.get("checkpoint_sha") or record.get("checkpoint_sha") != cp.get("checkpoint_sha"):
                raise ValueError("transition-provenance-checkpoint-mismatch")
            if record.get("use_sha") != link.get("use_sha"):
                raise ValueError("transition-provenance-use-mismatch")

            transition_sha = record.get("transition_sha")
            if not isinstance(transition_sha, str) or len(transition_sha) != 64:
                raise ValueError("transition-provenance-transition-sha-shape-invalid")
            transition = w100.get_transition(transition_store, transition_sha)
            w111._validate_transition_semantics(
                transition, registry_store, link, cp, previous_authority
            )
            if previous_target_registry is not None and transition.get("current_registry_sha") != previous_target_registry:
                raise ValueError("transition-registry-lineage-not-contiguous")
            previous_target_registry = transition.get("target_registry_sha")

            if seq not in markers:
                raise ValueError("wave108-marker-sequence-missing")
            (commit_record_sha, commit_record), (high_water_sha, high_water) = markers[seq]
            if record.get("wave108_commit_record_sha") != commit_record_sha:
                raise ValueError("transition-provenance-wave108-commit-record-mismatch")
            if record.get("wave108_high_water_sha") != high_water_sha:
                raise ValueError("transition-provenance-wave108-high-water-mismatch")
            if commit_record.get("authority_sha") != authority_sha or high_water.get("authority_sha") != authority_sha:
                raise ValueError("transition-provenance-wave108-authority-mismatch")

            if record.get("target_state_sha") != transition.get("target_state_sha"):
                raise ValueError("transition-provenance-target-state-mismatch")
            if record.get("current_registry_sha") != transition.get("current_registry_sha"):
                raise ValueError("transition-provenance-current-registry-mismatch")
            if record.get("target_registry_sha") != transition.get("target_registry_sha"):
                raise ValueError("transition-provenance-target-registry-mismatch")
            if record.get("transition_kind") != transition.get("transition_kind"):
                raise ValueError("transition-provenance-kind-mismatch")

            expected_transition_shas.append(transition_sha)
            previous_authority = authority_sha
    except Exception as exc:
        return {
            "status": HISTORY_INCOMPLETE,
            "reason": f"committed-transition-provenance:{type(exc).__name__}:{exc}",
            "wave110": base,
        }

    return {
        "status": HISTORY_VALID,
        "reason": "indexed-markers-exact-transition-provenance-and-transition-semantics-agree",
        "wave110": base,
        "committed_count": len(committed),
        "committed_authority_shas": committed,
        "expected_transition_shas": expected_transition_shas,
        "provenance_head_sha": provenance[-1][0] if provenance else "",
    }


def commit_status_state(
    st: dict,
    boot: dict,
    rt: dict | None,
    registry_store: dict,
    binding_store: dict,
    transition_store: dict,
) -> dict:
    """Classify history while preserving Wave-111 exact provenance and avoiding per-epoch rescans."""
    base = w110.commit_status_state(st, boot, rt, registry_store, binding_store, transition_store)
    status = base.get("status")
    try:
        transitions = w110._validated_transitions(transition_store)
    except Exception as exc:
        return {
            "status": HISTORY_INCOMPLETE,
            "reason": f"transition-evidence-verification:{type(exc).__name__}:{exc}",
            "wave110": base,
        }

    if status == HISTORY_NONE:
        try:
            provenance = w111._provenance_rows(st, allow_missing=True)
        except Exception as exc:
            return {
                "status": HISTORY_INCOMPLETE,
                "reason": f"transition-provenance-verification:{type(exc).__name__}:{exc}",
                "wave110": base,
            }
        if transitions or provenance:
            return {
                "status": HISTORY_UNRESOLVED,
                "reason": "lower-history-none-but-transaction-or-provenance-evidence-survives",
                "wave110": base,
                "transition_shas": sorted(transitions),
                "provenance_count": len(provenance or []),
            }
        return {"status": HISTORY_NONE, "reason": str(base.get("reason")), "wave110": base}

    if status == HISTORY_INCOMPLETE:
        return {"status": HISTORY_INCOMPLETE, "reason": str(base.get("reason")), "wave110": base}
    if status == HISTORY_UNRESOLVED:
        return {
            "status": HISTORY_UNRESOLVED,
            "reason": str(base.get("reason")),
            "wave110": base,
            "transition_shas": sorted(transitions),
        }
    if status != HISTORY_VALID:
        return {
            "status": HISTORY_INCOMPLETE,
            "reason": "unexpected-wave110-history-status",
            "wave110": base,
        }

    checked = _validated_provenance_state(st, boot, registry_store, transition_store, base)
    if checked.get("status") != HISTORY_VALID:
        return checked

    expected = list(checked.get("expected_transition_shas", []))
    extras = sorted(set(transitions) - set(expected))
    if extras:
        return {
            "status": HISTORY_UNRESOLVED,
            "reason": "retained-unmanifested-transition-evidence-after-provenance-check",
            "wave110": base,
            "committed_count": checked.get("committed_count", 0),
            "expected_transition_shas": expected,
            "extra_transition_shas": extras,
        }
    return checked


def _recover_missing_trailing_provenance(
    st: dict,
    boot: dict,
    rt: dict | None,
    registry_store: dict,
    transition_store: dict,
    binding_store: dict,
    link_sha: str,
    transition_sha: str,
) -> str | None:
    """Append only one proven missing trailing provenance row; otherwise return None or fail closed."""
    base = w110.commit_status_state(st, boot, rt, registry_store, binding_store, transition_store)
    if base.get("status") != HISTORY_VALID:
        return None
    committed = list(base.get("committed_authority_shas", []))
    if link_sha not in committed:
        return None

    rows = w111._provenance_rows(st)
    assert rows is not None
    by_authority = {record.get("authority_sha"): record for _sha, record in rows}
    if link_sha in by_authority:
        if by_authority[link_sha].get("transition_sha") != transition_sha:
            raise ValueError("already-committed-authority-bound-to-different-transition")
        return "ALREADY_COMMITTED"

    # Recovery is deliberately only one trailing row. Any wider provenance loss is corruption, not a
    # license to infer/rebuild history.
    if len(committed) != len(rows) + 1 or committed[-1] != link_sha:
        raise ValueError("recovery-requires-exactly-one-missing-trailing-provenance-row")
    for seq, (_record_sha, record) in enumerate(rows, start=1):
        if record.get("authority_sha") != committed[seq - 1]:
            raise ValueError("recovery-existing-provenance-prefix-mismatch")

    transitions = w110._validated_transitions(transition_store)
    candidates = [
        (sha, body) for sha, body in transitions.items()
        if body.get("target_authority_sha") == link_sha
    ]
    if len(candidates) != 1:
        raise ValueError("recovery-committed-authority-transition-match-not-unique")
    proven_transition_sha, transition = candidates[0]
    if proven_transition_sha != transition_sha:
        raise ValueError("recovery-transition-sha-does-not-match-lower-committed-evidence")

    link, cp, _use = g.w98.resolve(st, link_sha, boot)
    previous_authority = rows[-1][1]["authority_sha"] if rows else None
    w111._validate_transition_semantics(
        transition, registry_store, link, cp, previous_authority
    )

    marker = w111._append_provenance(
        st, boot, registry_store, transition_store, link_sha, transition_sha
    )
    if marker not in ("RECORDED", "ALREADY_RECORDED"):
        raise RuntimeError(f"unexpected Wave 112 recovery provenance result: {marker}")
    state = commit_status_state(st, boot, rt, registry_store, binding_store, transition_store)
    if state.get("status") != HISTORY_VALID:
        raise RuntimeError(f"Wave 112 recovery did not settle exact committed history: {state}")
    return "COMMITTED_RECOVERED_PROVENANCE"


def adopt_genesis(
    rt: dict,
    st: dict,
    boot: dict,
    services: dict,
    registry_store: dict,
    transition_store: dict,
    certificate_store: dict,
    domain: w104.CertificateWitnessDomain,
    binding_store: dict,
) -> str:
    result = w111.adopt_genesis(
        rt, st, boot, services, registry_store, transition_store,
        certificate_store, domain, binding_store
    )
    state = commit_status_state(st, boot, rt, registry_store, binding_store, transition_store)
    if state.get("status") != HISTORY_VALID:
        raise ValueError(f"Wave 112 genesis evidence HOLD: {state}")
    return result


def authority(
    rt: dict,
    st: dict,
    boot: dict,
    services: dict,
    registry_store: dict,
    transition_store: dict,
    certificate_store: dict,
    domain: w104.CertificateWitnessDomain,
    binding_store: dict,
    resolved_endpoints: dict | None = None,
) -> str:
    state = commit_status_state(st, boot, rt, registry_store, binding_store, transition_store)
    if state.get("status") == HISTORY_INCOMPLETE:
        return HOLD_INCOMPLETE
    if state.get("status") == HISTORY_UNRESOLVED:
        return HOLD_UNRESOLVED
    return w110.authority(
        rt, st, boot, services, registry_store, transition_store,
        certificate_store, domain, binding_store, resolved_endpoints
    )


def prepare(
    rt: dict,
    st: dict,
    priv: dict,
    boot: dict,
    services: dict,
    registry_store: dict,
    transition_store: dict,
    certificate_store: dict,
    domain: w104.CertificateWitnessDomain,
    binding_store: dict,
    target_user_app_state_sha: str | None = None,
    target_remote_registry_sha: str | None = None,
) -> tuple:
    verdict = authority(
        rt, st, boot, services, registry_store, transition_store,
        certificate_store, domain, binding_store
    )
    if not verdict.startswith("AUTHORITATIVE"):
        raise ValueError("Wave 112 predecessor HOLD")
    return w110.prepare(
        rt, st, priv, boot, services, registry_store, transition_store,
        certificate_store, domain, binding_store,
        target_user_app_state_sha, target_remote_registry_sha
    )


def commit(
    rt: dict,
    st: dict,
    boot: dict,
    registry_store: dict,
    transition_store: dict,
    link_sha: str,
    transition_sha: str,
    binding_store: dict,
    n: int | None = None,
) -> str:
    recovered = _recover_missing_trailing_provenance(
        st, boot, rt, registry_store, transition_store, binding_store,
        link_sha, transition_sha
    )
    if recovered is not None:
        return recovered

    result = w110.commit(
        rt, st, boot, registry_store, transition_store,
        link_sha, transition_sha, binding_store, n
    )
    if result == "COMMITTED":
        marker = w111._append_provenance(
            st, boot, registry_store, transition_store, link_sha, transition_sha
        )
        if marker not in ("RECORDED", "ALREADY_RECORDED"):
            raise RuntimeError(f"unexpected Wave 112 provenance result: {marker}")
    return result


def publish(rt: dict, st: dict, boot: dict, services: dict, tokens: dict,
            registry_store: dict, slot: str) -> str:
    return w110.publish(rt, st, boot, services, tokens, registry_store, slot)


def certify_and_sync(rt: dict, st: dict, boot: dict, services: dict, registry_store: dict,
                     certificate_store: dict, domain: w104.CertificateWitnessDomain,
                     slots: tuple[str, ...] | list[str] | None = None) -> tuple[str, dict]:
    return w110.certify_and_sync(
        rt, st, boot, services, registry_store, certificate_store, domain, slots
    )


def advance_all(
    st: dict,
    priv: dict,
    boot: dict,
    rt: dict,
    services: dict,
    tokens: dict,
    registry_store: dict,
    transition_store: dict,
    certificate_store: dict,
    domain: w104.CertificateWitnessDomain,
    binding_store: dict,
    app_label: str,
) -> tuple:
    app = hashlib.sha256(app_label.encode("utf-8")).hexdigest()
    cp, use, link, transition_sha, body = prepare(
        rt, st, priv, boot, services, registry_store, transition_store,
        certificate_store, domain, binding_store, app
    )
    unresolved = commit_status_state(st, boot, rt, registry_store, binding_store, transition_store)
    if unresolved.get("status") != HISTORY_UNRESOLVED:
        raise RuntimeError(f"Wave 112 prepare did not enter unresolved state: {unresolved}")
    result = commit(
        rt, st, boot, registry_store, transition_store,
        link["authority_sha"], transition_sha, binding_store
    )
    if result not in ("COMMITTED", "COMMITTED_RECOVERED_PROVENANCE"):
        raise RuntimeError(f"Wave 112 local commit failed: {result}")
    resolved = commit_status_state(st, boot, rt, registry_store, binding_store, transition_store)
    if resolved.get("status") != HISTORY_VALID:
        raise RuntimeError(f"Wave 112 commit provenance did not settle: {resolved}")
    for slot in q.REMOTE_IDS:
        remote_result = publish(rt, st, boot, services, tokens, registry_store, slot)
        if remote_result not in ("APPENDED", "ALREADY_CURRENT"):
            raise RuntimeError(f"Wave 112 publish failed for {slot}: {remote_result}")
    certificate_sha, certificate = certify_and_sync(
        rt, st, boot, services, registry_store, certificate_store, domain
    )
    final = authority(
        rt, st, boot, services, registry_store, transition_store,
        certificate_store, domain, binding_store
    )
    if not final.startswith("AUTHORITATIVE"):
        raise RuntimeError(f"Wave 112 final authority failed: {final}")
    return cp, use, link, transition_sha, body, certificate_sha, certificate
