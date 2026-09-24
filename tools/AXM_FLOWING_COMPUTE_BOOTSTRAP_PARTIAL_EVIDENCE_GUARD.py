#!/usr/bin/env python3
"""AXM Flowing Compute Wave 107: fail-closed partial authority-evidence guard.

Additive experiment over exact Wave 106. Independent verifier PR #31 showed that Wave 106's
retained-history fallback silently skipped an authority link when any dependency of that link failed
to resolve. Deleting the Wave-106 lineage store plus one signer-use body could therefore turn
"history exists but is incomplete" into "no history" and reopen bootstrap from a saved genesis view.

Wave 107 makes the bootstrap decision tri-state instead of boolean:
- NONE: no retained authority-facing evidence is present;
- VALID: at least one retained authority link fully resolves;
- INCOMPLETE_OR_CORRUPT: authority-facing evidence exists but cannot be proven complete.

Bootstrap adoption is allowed only from NONE (or the already-adopted open-bootstrap state handled by
Wave 106). Any incomplete/corrupt retained authority evidence fails closed. This deliberately keeps
the existing safety-over-availability tradeoff for abandoned prepared state.

Truth boundary:
- this is still one-process modeled state, not durable OS/process/device/provider independence;
- whole rollback/substitution of the entire retained authority state to a pre-adoption image remains a
  preserved counterexample;
- no fresh AXM/monolith workload, performance, energy, network, retained/incremental/dormant-compute
  result is claimed;
- no merge or CANON promotion is performed by this tool.
"""
from __future__ import annotations

import hashlib
from copy import deepcopy

import AXM_FLOWING_COMPUTE_BOOTSTRAP_LINEAGE_CLOSURE as w106
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w104


g = w106.g
q = w106.q

SRC = {
    "wave106_builder_head": "eb8ac4d23a3399af82885afc435dae6de0aa28b6",
    "wave106_tested_source_commit": "652f3da1acd88e02f085cf1ace92c6bfb412e065",
    "wave106_tool_blob": "daaa9e33b3418138972701bac1cecca928378a17",
    "wave106_selftest_blob": "3da3ebd06bed5b756ca58d5b77ac9eb5de12bbc6",
    "verifier_pr": 31,
    "verifier_head": "06beba92c188879d65ebd970bbaaa529ca095660",
    "verifier_evidence_blob": "d0e6c230bc11f04811748d36b3400ca597c9ffc6",
    "verifier_repro_blob": "c3342d4561ba10ea8deaeb878ffead870edde252",
}

HISTORY_NONE = "NONE"
HISTORY_VALID = "VALID"
HISTORY_INCOMPLETE = "INCOMPLETE_OR_CORRUPT"
HOLD_INCOMPLETE = "HOLD_BOOTSTRAP_AUTHORITY_EVIDENCE_INCOMPLETE"


def _store(st: dict, key: str) -> dict:
    value = st.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"authority store {key} shape invalid")
    return value


def retained_authority_history_state(st: dict, boot: dict) -> dict:
    """Classify retained authority evidence without treating corruption as absence.

    The Wave-98+ retained authority closure is rooted in three authority-facing CAS stores used by
    resolve(): L (authority links), C (signed checkpoints), and U (signer-use evidence). A retained L
    row must resolve completely. If L is empty while C or U still contains rows, history is incomplete
    rather than absent. Extra C/U rows are tolerated when at least one link resolves because older
    retained rows may legitimately coexist with the current chain.
    """
    try:
        links = _store(st, "L")
        checkpoints = _store(st, "C")
        uses = _store(st, "U")
    except Exception as exc:
        return {
            "status": HISTORY_INCOMPLETE,
            "reason": f"store-shape:{type(exc).__name__}:{exc}",
            "link_keys": [],
            "resolved_links": [],
            "unresolved_links": [],
            "checkpoint_count": None,
            "use_count": None,
        }

    evidence_present = bool(links or checkpoints or uses)
    if not evidence_present:
        return {
            "status": HISTORY_NONE,
            "reason": "no-authority-facing-retained-rows",
            "link_keys": [],
            "resolved_links": [],
            "unresolved_links": [],
            "checkpoint_count": 0,
            "use_count": 0,
        }

    if not links:
        return {
            "status": HISTORY_INCOMPLETE,
            "reason": "checkpoint-or-use-evidence-without-authority-link",
            "link_keys": [],
            "resolved_links": [],
            "unresolved_links": [],
            "checkpoint_count": len(checkpoints),
            "use_count": len(uses),
        }

    resolved = []
    unresolved = []
    for sha in sorted(links):
        body = links.get(sha)
        if not isinstance(body, dict):
            unresolved.append({"sha": sha, "error": "link-body-shape-invalid"})
            continue
        if body.get("authority_sha") != sha:
            unresolved.append({"sha": sha, "error": "link-key-body-mismatch"})
            continue
        try:
            link, cp, use = g.w98.resolve(st, sha, boot)
            if link.get("authority_sha") != sha:
                raise ValueError("resolved authority identity mismatch")
            cp_sha = link.get("checkpoint_sha")
            use_sha = link.get("use_sha")
            if cp.get("checkpoint_sha") != cp_sha:
                raise ValueError("resolved checkpoint identity mismatch")
            # Wave-97+ signer-use rows carry their own content identity; if the lower layer changes
            # field naming later, resolve() remains the primary completeness gate.
            if use_sha not in uses:
                raise ValueError("resolved signer-use row absent from U store")
            resolved.append(sha)
        except Exception as exc:
            unresolved.append({
                "sha": sha,
                "error": f"{type(exc).__name__}:{exc}",
            })

    if unresolved:
        return {
            "status": HISTORY_INCOMPLETE,
            "reason": "one-or-more-retained-authority-links-do-not-resolve",
            "link_keys": sorted(links),
            "resolved_links": resolved,
            "unresolved_links": unresolved,
            "checkpoint_count": len(checkpoints),
            "use_count": len(uses),
        }

    return {
        "status": HISTORY_VALID,
        "reason": "all-retained-authority-links-resolve",
        "link_keys": sorted(links),
        "resolved_links": resolved,
        "unresolved_links": [],
        "checkpoint_count": len(checkpoints),
        "use_count": len(uses),
    }


def _guard(st: dict, boot: dict) -> dict:
    state = retained_authority_history_state(st, boot)
    if state["status"] == HISTORY_INCOMPLETE:
        raise ValueError(HOLD_INCOMPLETE)
    return state


def adopt_genesis(rt: dict, st: dict, boot: dict, services: dict, registry_store: dict,
                  certificate_store: dict, domain: w104.CertificateWitnessDomain,
                  binding_store: dict) -> str:
    _guard(st, boot)
    return w106.adopt_genesis(
        rt, st, boot, services, registry_store, certificate_store, domain, binding_store
    )


def authority(rt: dict, st: dict, boot: dict, services: dict, registry_store: dict,
              certificate_store: dict, domain: w104.CertificateWitnessDomain,
              binding_store: dict, resolved_endpoints: dict | None = None) -> str:
    state = retained_authority_history_state(st, boot)
    if state["status"] == HISTORY_INCOMPLETE:
        return HOLD_INCOMPLETE
    return w106.authority(
        rt, st, boot, services, registry_store, certificate_store,
        domain, binding_store, resolved_endpoints
    )


def prepare(rt: dict, st: dict, priv: dict, boot: dict, services: dict,
            registry_store: dict, transition_store: dict, certificate_store: dict,
            domain: w104.CertificateWitnessDomain, binding_store: dict,
            target_user_app_state_sha: str | None = None,
            target_remote_registry_sha: str | None = None) -> tuple:
    verdict = authority(
        rt, st, boot, services, registry_store, certificate_store, domain, binding_store
    )
    if not verdict.startswith("AUTHORITATIVE"):
        raise ValueError("Wave 107 predecessor HOLD")
    return w106.prepare(
        rt, st, priv, boot, services, registry_store, transition_store,
        certificate_store, domain, binding_store,
        target_user_app_state_sha, target_remote_registry_sha
    )


def commit(rt: dict, st: dict, boot: dict, registry_store: dict, transition_store: dict,
           link_sha: str, transition_sha: str, binding_store: dict,
           n: int | None = None) -> str:
    return w106.commit(
        rt, st, boot, registry_store, transition_store,
        link_sha, transition_sha, binding_store, n
    )


def publish(rt: dict, st: dict, boot: dict, services: dict, tokens: dict,
            registry_store: dict, slot: str) -> str:
    return w106.publish(rt, st, boot, services, tokens, registry_store, slot)


def certify_and_sync(rt: dict, st: dict, boot: dict, services: dict, registry_store: dict,
                     certificate_store: dict, domain: w104.CertificateWitnessDomain,
                     slots: tuple[str, ...] | list[str] | None = None) -> tuple[str, dict]:
    return w106.certify_and_sync(
        rt, st, boot, services, registry_store, certificate_store, domain, slots
    )


def advance_all(st: dict, priv: dict, boot: dict, rt: dict, services: dict, tokens: dict,
                registry_store: dict, transition_store: dict, certificate_store: dict,
                domain: w104.CertificateWitnessDomain, binding_store: dict,
                app_label: str) -> tuple:
    app = hashlib.sha256(app_label.encode("utf-8")).hexdigest()
    cp, use, link, transition_sha, body = prepare(
        rt, st, priv, boot, services, registry_store, transition_store,
        certificate_store, domain, binding_store, app
    )
    result = commit(
        rt, st, boot, registry_store, transition_store,
        link["authority_sha"], transition_sha, binding_store
    )
    if result != "COMMITTED":
        raise RuntimeError(f"Wave 107 local commit failed: {result}")
    for slot in q.REMOTE_IDS:
        remote_result = publish(rt, st, boot, services, tokens, registry_store, slot)
        if remote_result not in ("APPENDED", "ALREADY_CURRENT"):
            raise RuntimeError(f"Wave 107 remote publish failed: {slot}: {remote_result}")
    cert_result, sync = certify_and_sync(
        rt, st, boot, services, registry_store, certificate_store, domain
    )
    if cert_result not in ("CERTIFIED", "ALREADY_CERTIFIED"):
        raise RuntimeError(f"Wave 107 quorum certification failed: {cert_result}")
    if any(value not in ("ALREADY_CURRENT", "WITNESS_SYNCED_1") for value in sync.values()):
        raise RuntimeError(f"Wave 107 certificate witness sync failed: {sync}")
    verdict = authority(
        rt, st, boot, services, registry_store, certificate_store, domain, binding_store
    )
    if not verdict.startswith("AUTHORITATIVE"):
        raise RuntimeError(f"Wave 107 authority failed: {verdict}")
    return cp, use, link, transition_sha, body
