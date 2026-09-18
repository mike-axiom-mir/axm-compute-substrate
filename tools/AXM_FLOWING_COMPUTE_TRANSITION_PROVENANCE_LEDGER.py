#!/usr/bin/env python3
"""AXM Flowing Compute Wave 111: committed transition-provenance ledger.

Additive experiment over exact Wave 110. Independent verifier PR #35 showed two provenance gaps:
(1) the exact transition used by a committed authority was not retained by any committed decision,
so deleting it and inserting a different content-addressed transition could still classify VALID;
(2) Wave 110 returned early on lower HISTORY_NONE before inspecting surviving transition evidence.

Wave 111 adds a same-domain, append-only content-addressed provenance ledger that binds each committed
authority marker to the exact transition SHA that completed that commit. Read validation also replays
the transition's registry step and requires its target-state binding to equal the committed checkpoint.
Transition evidence is inspected even when lower history reports NONE.

Truth boundary: this ledger is still in the same modeled Python failure domain as the authority state.
Whole-domain rollback can erase it together with every newer fact. Therefore this wave is a semantic
provenance/fail-closed repair only. It is not the independently durable commit-decision witness yet,
and makes no performance, energy, retained/incremental/dormant-compute, process, device, physical, or
provider-independence claim. No merge or CANON promotion is performed by this tool.
"""
from __future__ import annotations

import hashlib
import json

import AXM_FLOWING_COMPUTE_TRANSITION_EVIDENCE_GUARD as w110
import AXM_FLOWING_COMPUTE_COMMITTED_HISTORY_MANIFEST as w108
import AXM_FLOWING_COMPUTE_REMOTE_REGISTRY_MONOTONICITY as w100
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w104

q = w110.q
g = w110.g

SRC = {
    "wave110_builder_head": "0d97d0dde7f3b72ff1da6ae68315c0e163330f75",
    "wave110_tested_source_commit": "dfe22164f853cf1f04f0ae93103e33478ed074fd",
    "wave110_tool_blob": "abc96489922bcf7af64412a8e85cf447796321b1",
    "wave110_selftest_blob": "00b0eccac36cf479c81004ceac811a6af1293b85",
    "verifier_pr": 35,
    "verifier_head": "eb8b2d21b63d280cd84f53f98769bc70c4939cf2",
    "verifier_evidence_blob": "3a035e1cb20a5e0159ca6dc9e5501f3cb669841e",
    "verifier_reproducer_blob": "62beb82f18517ee887bbc508b161db214bea477f",
    "verifier_ci_run": 35209627758,
    "verifier_ci_normal_job": 105163740894,
    "verifier_ci_optimized_job": 105163741071,
    "verifier_primary_verdict": "FAIL_COMMITTED_TRANSITION_IDENTITY_IS_SUBSTITUTABLE",
    "verifier_secondary_verdict": "FAIL_TRANSITION_ONLY_EVIDENCE_IS_IGNORED_WHEN_WAVE109_REPORTS_NONE",
}

PROVENANCE_STORE = "W111_COMMITTED_TRANSITION_PROVENANCE"
PROVENANCE_SCHEMA = "axm.flowing_compute.wave111.committed_transition_provenance/v1"

HISTORY_NONE = w110.HISTORY_NONE
HISTORY_VALID = w110.HISTORY_VALID
HISTORY_INCOMPLETE = w110.HISTORY_INCOMPLETE
HISTORY_UNRESOLVED = w110.HISTORY_UNRESOLVED
HOLD_INCOMPLETE = w110.HOLD_INCOMPLETE
HOLD_UNRESOLVED = w110.HOLD_UNRESOLVED


def _canon(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(value: dict) -> str:
    return hashlib.sha256(_canon(value)).hexdigest()


def _provenance_store(st: dict, *, allow_missing: bool = False) -> dict | None:
    if PROVENANCE_STORE not in st:
        if allow_missing:
            return None
        raise ValueError("transition-provenance-store-missing")
    value = st[PROVENANCE_STORE]
    if not isinstance(value, dict):
        raise ValueError("transition-provenance-store-shape-invalid")
    return value


def _provenance_rows(st: dict, *, allow_missing: bool = False) -> list[tuple[str, dict]] | None:
    store = _provenance_store(st, allow_missing=allow_missing)
    if store is None:
        return None
    by_seq: dict[int, tuple[str, dict]] = {}
    for key, body in store.items():
        if not isinstance(key, str) or len(key) != 64 or not isinstance(body, dict):
            raise ValueError("transition-provenance-row-shape-invalid")
        if _sha(body) != key:
            raise ValueError("transition-provenance-key-body-mismatch")
        if body.get("schema") != PROVENANCE_SCHEMA:
            raise ValueError("transition-provenance-schema-mismatch")
        seq = body.get("seq")
        if not isinstance(seq, int) or isinstance(seq, bool) or seq < 1:
            raise ValueError("transition-provenance-sequence-invalid")
        if seq in by_seq:
            raise ValueError("transition-provenance-duplicate-sequence")
        by_seq[seq] = (key, body)
    if not by_seq:
        return []
    if sorted(by_seq) != list(range(1, max(by_seq) + 1)):
        raise ValueError("transition-provenance-sequence-gap")
    rows = [by_seq[i] for i in range(1, max(by_seq) + 1)]
    previous = ""
    for key, body in rows:
        if body.get("previous_provenance_sha", "") != previous:
            raise ValueError("transition-provenance-predecessor-mismatch")
        previous = key
    return rows


def _validate_transition_semantics(
    transition: dict,
    registry_store: dict,
    link: dict,
    checkpoint: dict,
    previous_authority_sha: str | None,
) -> None:
    if transition.get("target_authority_sha") != link.get("authority_sha"):
        raise ValueError("transition-authority-mismatch")
    if transition.get("target_checkpoint_sha") != checkpoint.get("checkpoint_sha"):
        raise ValueError("transition-checkpoint-mismatch")
    if transition.get("predecessor_authority_sha") != previous_authority_sha:
        raise ValueError("transition-predecessor-authority-mismatch")
    if link.get("predecessor_authority_sha") != previous_authority_sha:
        raise ValueError("authority-link-predecessor-mismatch")

    app_sha = transition.get("target_app_state_sha")
    current_registry_sha = transition.get("current_registry_sha")
    target_registry_sha = transition.get("target_registry_sha")
    if not all(isinstance(v, str) and len(v) == 64 for v in (app_sha, current_registry_sha, target_registry_sha)):
        raise ValueError("transition-state-or-registry-identity-shape-invalid")

    expected_state = q.binding(app_sha, target_registry_sha)
    if transition.get("target_state_sha") != expected_state:
        raise ValueError("transition-target-state-binding-invalid")
    if checkpoint.get("state_sha") != expected_state:
        raise ValueError("transition-target-state-does-not-match-committed-checkpoint")

    step = w100.validate_live_registry_step(registry_store, current_registry_sha, target_registry_sha)
    current = step["current"]
    target = step["target"]
    delta = step["delta"]
    if transition.get("current_generation") != current.get("generation"):
        raise ValueError("transition-current-generation-mismatch")
    if transition.get("target_generation") != target.get("generation"):
        raise ValueError("transition-target-generation-mismatch")
    if transition.get("transition_kind") != delta.get("kind"):
        raise ValueError("transition-kind-mismatch")
    if transition.get("changed_slots") != delta.get("changed_slots"):
        raise ValueError("transition-changed-slots-mismatch")
    if transition.get("changed_fields") != delta.get("changed_fields"):
        raise ValueError("transition-changed-fields-mismatch")


def _marker_rows_for_seq(st: dict, seq: int) -> tuple[tuple[str, dict], tuple[str, dict]]:
    chains = w108._marker_chains(st)
    if seq < 1 or seq > len(chains["commits"]):
        raise ValueError("wave108-marker-sequence-missing")
    return chains["commits"][seq - 1], chains["highs"][seq - 1]


def _append_provenance(
    st: dict,
    boot: dict,
    registry_store: dict,
    transition_store: dict,
    link_sha: str,
    transition_sha: str,
) -> str:
    rows = _provenance_rows(st)
    assert rows is not None
    for _record_sha, record in rows:
        if record.get("authority_sha") == link_sha:
            if record.get("transition_sha") != transition_sha:
                raise ValueError("committed-authority-already-bound-to-different-transition")
            return "ALREADY_RECORDED"

    link, cp, use = g.w98.resolve(st, link_sha, boot)
    transition = w100.get_transition(transition_store, transition_sha)
    seq = len(rows) + 1
    if link.get("epoch") != seq:
        raise ValueError("provenance-epoch-does-not-match-sequence")
    previous_authority = rows[-1][1]["authority_sha"] if rows else None
    _validate_transition_semantics(transition, registry_store, link, cp, previous_authority)

    (commit_record_sha, commit_record), (high_water_sha, high_water) = _marker_rows_for_seq(st, seq)
    if commit_record.get("authority_sha") != link_sha or high_water.get("authority_sha") != link_sha:
        raise ValueError("provenance-wave108-marker-authority-mismatch")

    record = {
        "schema": PROVENANCE_SCHEMA,
        "seq": seq,
        "epoch": link["epoch"],
        "authority_sha": link_sha,
        "checkpoint_sha": link["checkpoint_sha"],
        "use_sha": link["use_sha"],
        "transition_sha": transition_sha,
        "target_state_sha": transition["target_state_sha"],
        "current_registry_sha": transition["current_registry_sha"],
        "target_registry_sha": transition["target_registry_sha"],
        "transition_kind": transition["transition_kind"],
        "wave108_commit_record_sha": commit_record_sha,
        "wave108_high_water_sha": high_water_sha,
        "previous_provenance_sha": rows[-1][0] if rows else "",
    }
    record_sha = _sha(record)
    store = _provenance_store(st)
    assert store is not None
    if record_sha in store and store[record_sha] != record:
        raise ValueError("transition-provenance-collision")
    store[record_sha] = record
    return "RECORDED"


def commit_status_state(
    st: dict,
    boot: dict,
    rt: dict | None,
    registry_store: dict,
    binding_store: dict,
    transition_store: dict,
) -> dict:
    """Verify lower commit status plus exact transition provenance for every committed epoch."""
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
            provenance = _provenance_rows(st, allow_missing=True)
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

    try:
        provenance = _provenance_rows(st)
        assert provenance is not None
        committed = list(base.get("committed_authority_shas", []))
        if len(provenance) != len(committed):
            raise ValueError("committed-transition-provenance-count-mismatch")

        previous_authority: str | None = None
        previous_target_registry: str | None = None
        expected_transition_shas: list[str] = []
        for seq, ((record_sha, record), authority_sha) in enumerate(zip(provenance, committed), start=1):
            if record.get("seq") != seq or record.get("epoch") != seq:
                raise ValueError("transition-provenance-sequence-or-epoch-mismatch")
            if record.get("authority_sha") != authority_sha:
                raise ValueError("transition-provenance-authority-mismatch")

            link, cp, use = g.w98.resolve(st, authority_sha, boot)
            if record.get("checkpoint_sha") != link.get("checkpoint_sha") or record.get("checkpoint_sha") != cp.get("checkpoint_sha"):
                raise ValueError("transition-provenance-checkpoint-mismatch")
            if record.get("use_sha") != link.get("use_sha"):
                raise ValueError("transition-provenance-use-mismatch")

            transition_sha = record.get("transition_sha")
            if not isinstance(transition_sha, str) or len(transition_sha) != 64:
                raise ValueError("transition-provenance-transition-sha-shape-invalid")
            transition = w100.get_transition(transition_store, transition_sha)
            _validate_transition_semantics(transition, registry_store, link, cp, previous_authority)

            if previous_target_registry is not None and transition.get("current_registry_sha") != previous_target_registry:
                raise ValueError("transition-registry-lineage-not-contiguous")
            previous_target_registry = transition.get("target_registry_sha")

            (commit_record_sha, commit_record), (high_water_sha, high_water) = _marker_rows_for_seq(st, seq)
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

    extras = sorted(set(transitions) - set(expected_transition_shas))
    if extras:
        return {
            "status": HISTORY_UNRESOLVED,
            "reason": "retained-unmanifested-transition-evidence-after-provenance-check",
            "wave110": base,
            "committed_count": len(committed),
            "expected_transition_shas": expected_transition_shas,
            "extra_transition_shas": extras,
        }

    return {
        "status": HISTORY_VALID,
        "reason": "commit-markers-exact-transition-provenance-and-transition-semantics-agree",
        "wave110": base,
        "committed_count": len(committed),
        "committed_authority_shas": committed,
        "expected_transition_shas": expected_transition_shas,
        "provenance_head_sha": provenance[-1][0] if provenance else "",
    }


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
    result = w110.adopt_genesis(
        rt, st, boot, services, registry_store, transition_store,
        certificate_store, domain, binding_store
    )
    base = w110.commit_status_state(st, boot, rt, registry_store, binding_store, transition_store)
    if base.get("status") != HISTORY_VALID or base.get("committed_count", 0) != 0 or transition_store:
        raise ValueError("Wave 111 genesis requires fresh zero-commit Wave 110 state")
    if PROVENANCE_STORE in st and st[PROVENANCE_STORE]:
        raise ValueError("existing Wave 111 provenance requires explicit migration/recovery")
    st.setdefault(PROVENANCE_STORE, {})
    state = commit_status_state(st, boot, rt, registry_store, binding_store, transition_store)
    if state.get("status") != HISTORY_VALID:
        raise ValueError(f"Wave 111 genesis evidence HOLD: {state}")
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
        raise ValueError("Wave 111 predecessor HOLD")
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
    result = w110.commit(
        rt, st, boot, registry_store, transition_store,
        link_sha, transition_sha, binding_store, n
    )
    if result == "COMMITTED":
        marker = _append_provenance(
            st, boot, registry_store, transition_store, link_sha, transition_sha
        )
        if marker not in ("RECORDED", "ALREADY_RECORDED"):
            raise RuntimeError(f"unexpected Wave 111 provenance result: {marker}")
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
        raise RuntimeError(f"Wave 111 prepare did not enter unresolved state: {unresolved}")
    result = commit(
        rt, st, boot, registry_store, transition_store,
        link["authority_sha"], transition_sha, binding_store
    )
    if result != "COMMITTED":
        raise RuntimeError(f"Wave 111 local commit failed: {result}")
    resolved = commit_status_state(st, boot, rt, registry_store, binding_store, transition_store)
    if resolved.get("status") != HISTORY_VALID:
        raise RuntimeError(f"Wave 111 commit provenance did not settle: {resolved}")
    for slot in q.REMOTE_IDS:
        remote_result = publish(rt, st, boot, services, tokens, registry_store, slot)
        if remote_result not in ("APPENDED", "ALREADY_CURRENT"):
            raise RuntimeError(f"Wave 111 publish failed for {slot}: {remote_result}")
    certificate_sha, certificate = certify_and_sync(
        rt, st, boot, services, registry_store, certificate_store, domain
    )
    final = authority(
        rt, st, boot, services, registry_store, transition_store,
        certificate_store, domain, binding_store
    )
    if not final.startswith("AUTHORITATIVE"):
        raise RuntimeError(f"Wave 111 final authority failed: {final}")
    return cp, use, link, transition_sha, body, certificate_sha, certificate
