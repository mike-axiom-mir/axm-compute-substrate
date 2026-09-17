#!/usr/bin/env python3
"""AXM Flowing Compute Wave 108: multi-epoch committed-history manifest.

Additive experiment over exact Wave 107. Independent verifier PR #32 showed that Wave 107 can
classify retained history as VALID after the newest committed authority-link body is deleted at
retained depth >= 2, because an older surviving link still resolves and newer C/U rows are tolerated.

Wave 108 adds two append-only content-addressed marker chains:
- a committed-authority ledger naming every accepted authority link and its checkpoint/use identity;
- a paired high-water ledger naming each committed-ledger record.

Authority requires the two marker chains to agree and every named committed authority link to fully
resolve. Prepared-but-uncommitted next-epoch links are tolerated only when the runtime still points to
the previous committed epoch. If the lower commit advances the runtime before the Wave-108 marker is
persisted, reads fail closed rather than guessing whether that link committed.

Truth boundary:
- both marker chains still live in the same modeled Python state; coordinated rollback/truncation of
  the complete authority + marker + external-support world to an older genuine prefix remains a
  preserved counterexample;
- this does not establish OS-process/device/provider independence or physically monotonic storage;
- existing Wave-107 histories cannot be silently migrated into this manifest: migration requires a
  separately verified explicit procedure;
- no fresh AXM/monolith workload, performance, energy, network, retained/incremental/dormant-compute
  result is claimed;
- no merge or CANON promotion is performed by this tool.
"""
from __future__ import annotations

import hashlib
import json

import AXM_FLOWING_COMPUTE_BOOTSTRAP_PARTIAL_EVIDENCE_GUARD as w107
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w104


g = w107.g
q = w107.q

SRC = {
    "wave107_builder_head": "22289521483fe8e171f6c9016f0bd0b10e54a235",
    "wave107_tested_source_commit": "9e4edc8c484d32f9210804dc25ca61fadf7aa835",
    "wave107_tool_blob": "7aeb0e6f6018d1708b5fe89a4fdbf8e024398deb",
    "wave107_selftest_blob": "66d676685b23fd5cbcc5ac8f06a0ec5e383fd295",
    "verifier_pr": 32,
    "verifier_head": "3573711a726b527d43dd056ca2bfdbdd5be81c0a",
    "verifier_evidence_blob": "154cdc9cbc197d75a814a2b29e945d02e9d9f454",
    "verifier_repro_blob": "010c59d1de7f8ce3dac8029bf620b789b134ecf2",
    "verifier_ci_run": 35193912823,
}

COMMIT_STORE = "W108_COMMITTED_AUTHORITY_LEDGER"
HIGH_WATER_STORE = "W108_COMMITTED_HIGH_WATER_LEDGER"
SCHEMA_COMMIT = "axm.flowing_compute.wave108.committed_authority/v1"
SCHEMA_HIGH = "axm.flowing_compute.wave108.committed_high_water/v1"

HISTORY_NONE = "NONE"
HISTORY_VALID = "VALID"
HISTORY_INCOMPLETE = "INCOMPLETE_OR_CORRUPT"
HOLD_INCOMPLETE = "HOLD_COMMITTED_HISTORY_INCOMPLETE"


def _canon(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(value: dict) -> str:
    return hashlib.sha256(_canon(value)).hexdigest()


def _marker_store(st: dict, key: str, *, allow_missing: bool = False):
    if key not in st:
        if allow_missing:
            return None
        raise ValueError(f"missing-marker-store:{key}")
    value = st[key]
    if not isinstance(value, dict):
        raise ValueError(f"marker-store-shape:{key}")
    return value


def _linearize(store: dict, schema: str, previous_field: str) -> list[tuple[str, dict]]:
    by_seq: dict[int, tuple[str, dict]] = {}
    for key, body in store.items():
        if not isinstance(key, str) or len(key) != 64 or not isinstance(body, dict):
            raise ValueError("marker-row-shape")
        if _sha(body) != key:
            raise ValueError("marker-key-body-mismatch")
        if body.get("schema") != schema:
            raise ValueError("marker-schema-mismatch")
        seq = body.get("seq")
        if not isinstance(seq, int) or isinstance(seq, bool) or seq < 1:
            raise ValueError("marker-sequence-invalid")
        if seq in by_seq:
            raise ValueError("marker-duplicate-sequence")
        by_seq[seq] = (key, body)

    if not by_seq:
        return []
    expected = list(range(1, max(by_seq) + 1))
    if sorted(by_seq) != expected:
        raise ValueError("marker-sequence-gap")

    rows = [by_seq[seq] for seq in expected]
    previous = ""
    for key, body in rows:
        if body.get(previous_field, "") != previous:
            raise ValueError("marker-predecessor-mismatch")
        previous = key
    return rows


def _marker_chains(st: dict, *, allow_missing: bool = False) -> dict:
    commits = _marker_store(st, COMMIT_STORE, allow_missing=allow_missing)
    highs = _marker_store(st, HIGH_WATER_STORE, allow_missing=allow_missing)
    if commits is None or highs is None:
        if commits is None and highs is None:
            return {"missing": True, "commits": [], "highs": []}
        raise ValueError("one-marker-store-missing")

    commit_rows = _linearize(commits, SCHEMA_COMMIT, "previous_commit_record_sha")
    high_rows = _linearize(highs, SCHEMA_HIGH, "previous_high_water_sha")
    if len(commit_rows) != len(high_rows):
        raise ValueError("marker-high-water-length-mismatch")

    for index, ((commit_sha, commit), (high_sha, high)) in enumerate(
        zip(commit_rows, high_rows), start=1
    ):
        if commit.get("seq") != index or high.get("seq") != index:
            raise ValueError("marker-index-mismatch")
        if commit.get("epoch") != index:
            raise ValueError("committed-epoch-not-contiguous")
        if high.get("commit_record_sha") != commit_sha:
            raise ValueError("high-water-commit-mismatch")
        if high.get("authority_sha") != commit.get("authority_sha"):
            raise ValueError("high-water-authority-mismatch")

    return {
        "missing": False,
        "commits": commit_rows,
        "highs": high_rows,
        "max_seq": len(commit_rows),
        "commit_head_sha": commit_rows[-1][0] if commit_rows else "",
        "high_water_head_sha": high_rows[-1][0] if high_rows else "",
    }


def _initialize_empty_markers(st: dict, boot: dict) -> None:
    base = w107.retained_authority_history_state(st, boot)
    if base["status"] == w107.HISTORY_INCOMPLETE:
        raise ValueError(w107.HOLD_INCOMPLETE)
    if COMMIT_STORE in st or HIGH_WATER_STORE in st:
        chains = _marker_chains(st)
        if chains["commits"] or chains["highs"]:
            return
        return
    if base["status"] != w107.HISTORY_NONE:
        raise ValueError("existing-wave107-history-requires-explicit-manifest-migration")
    st[COMMIT_STORE] = {}
    st[HIGH_WATER_STORE] = {}


def committed_history_state(st: dict, boot: dict, rt: dict | None = None) -> dict:
    """Verify committed-history completeness and distinguish an uncommitted prepared next link.

    Extra C/U rows are allowed. Extra L rows are allowed only when they resolve, are exactly the next
    epoch, and the runtime still points at the last manifested committed authority (or genesis for the
    first candidate). Once runtime points at an unmanifested link, the read fails closed: that is the
    lower-commit -> marker-persist crash boundary.
    """
    base = w107.retained_authority_history_state(st, boot)
    if base["status"] == w107.HISTORY_INCOMPLETE:
        return {
            "status": HISTORY_INCOMPLETE,
            "reason": "wave107-base-history-incomplete",
            "base": base,
        }

    try:
        chains = _marker_chains(st, allow_missing=True)
    except Exception as exc:
        return {
            "status": HISTORY_INCOMPLETE,
            "reason": f"marker-chain:{type(exc).__name__}:{exc}",
            "base": base,
        }

    if chains.get("missing"):
        if base["status"] == w107.HISTORY_NONE:
            return {
                "status": HISTORY_NONE,
                "reason": "pre-wave108-fresh-state-no-authority-history",
                "base": base,
                "committed_count": 0,
            }
        return {
            "status": HISTORY_INCOMPLETE,
            "reason": "authority-history-exists-without-wave108-marker-stores",
            "base": base,
        }

    commit_rows = chains["commits"]
    committed_shas = []
    for _, record in commit_rows:
        authority_sha = record.get("authority_sha")
        checkpoint_sha = record.get("checkpoint_sha")
        use_sha = record.get("use_sha")
        if not all(isinstance(v, str) and len(v) == 64 for v in (authority_sha, checkpoint_sha, use_sha)):
            return {
                "status": HISTORY_INCOMPLETE,
                "reason": "committed-marker-identity-shape-invalid",
                "base": base,
            }
        try:
            link, cp, use = g.w98.resolve(st, authority_sha, boot)
        except Exception as exc:
            return {
                "status": HISTORY_INCOMPLETE,
                "reason": f"manifested-authority-does-not-resolve:{type(exc).__name__}:{exc}",
                "base": base,
                "missing_authority_sha": authority_sha,
            }
        if (
            link.get("authority_sha") != authority_sha
            or link.get("checkpoint_sha") != checkpoint_sha
            or link.get("use_sha") != use_sha
            or link.get("epoch") != record.get("epoch")
            or cp.get("checkpoint_sha") != checkpoint_sha
        ):
            return {
                "status": HISTORY_INCOMPLETE,
                "reason": "manifested-authority-identity-mismatch",
                "base": base,
                "authority_sha": authority_sha,
            }
        committed_shas.append(authority_sha)

    links = st.get("L", {})
    if not isinstance(links, dict):
        return {"status": HISTORY_INCOMPLETE, "reason": "authority-link-store-shape-invalid", "base": base}
    extras = sorted(set(links) - set(committed_shas))
    prepared = []
    max_seq = len(commit_rows)

    current_authority_sha = None
    current_epoch = 0
    if rt is not None and base["status"] != w107.HISTORY_NONE:
        try:
            status, current_link, _ = q.current_local(rt, st, boot)
            if status == "LOCAL_OK":
                current_authority_sha = current_link.get("authority_sha")
                current_epoch = current_link.get("epoch", 0)
        except Exception:
            current_authority_sha = None

    for authority_sha in extras:
        try:
            link, cp, use = g.w98.resolve(st, authority_sha, boot)
        except Exception as exc:
            return {
                "status": HISTORY_INCOMPLETE,
                "reason": f"unmanifested-authority-does-not-resolve:{type(exc).__name__}:{exc}",
                "base": base,
                "authority_sha": authority_sha,
            }
        if link.get("epoch") != max_seq + 1:
            return {
                "status": HISTORY_INCOMPLETE,
                "reason": "unmanifested-authority-not-next-epoch",
                "base": base,
                "authority_sha": authority_sha,
            }
        if rt is None or current_authority_sha == authority_sha or current_epoch != max_seq:
            return {
                "status": HISTORY_INCOMPLETE,
                "reason": "runtime-points-to-or-cannot-disambiguate-unmanifested-authority",
                "base": base,
                "authority_sha": authority_sha,
            }
        prepared.append(authority_sha)

    if commit_rows and base["status"] == w107.HISTORY_NONE:
        return {
            "status": HISTORY_INCOMPLETE,
            "reason": "commit-markers-exist-without-authority-history",
            "base": base,
        }
    if not commit_rows and base["status"] == w107.HISTORY_VALID:
        if not prepared:
            return {
                "status": HISTORY_INCOMPLETE,
                "reason": "authority-history-exists-with-empty-commit-manifest",
                "base": base,
            }

    return {
        "status": HISTORY_VALID if (commit_rows or COMMIT_STORE in st) else HISTORY_NONE,
        "reason": "paired-commit-and-high-water-ledgers-verify",
        "base": base,
        "committed_count": len(commit_rows),
        "committed_authority_shas": committed_shas,
        "prepared_authority_shas": prepared,
        "commit_head_sha": chains.get("commit_head_sha", ""),
        "high_water_head_sha": chains.get("high_water_head_sha", ""),
    }


def _guard(st: dict, boot: dict, rt: dict | None = None) -> dict:
    state = committed_history_state(st, boot, rt)
    if state["status"] == HISTORY_INCOMPLETE:
        raise ValueError(HOLD_INCOMPLETE)
    return state


def _append_commit_marker(st: dict, boot: dict, link_sha: str) -> str:
    chains = _marker_chains(st)
    for record_sha, record in chains["commits"]:
        if record.get("authority_sha") == link_sha:
            return "ALREADY_RECORDED"

    link, cp, use = g.w98.resolve(st, link_sha, boot)
    seq = len(chains["commits"]) + 1
    if link.get("epoch") != seq:
        raise ValueError("committed authority epoch does not match manifest sequence")
    commit = {
        "schema": SCHEMA_COMMIT,
        "seq": seq,
        "epoch": link["epoch"],
        "authority_sha": link_sha,
        "checkpoint_sha": link["checkpoint_sha"],
        "use_sha": link["use_sha"],
        "previous_commit_record_sha": chains["commit_head_sha"],
    }
    commit_sha = _sha(commit)
    st[COMMIT_STORE][commit_sha] = commit

    high = {
        "schema": SCHEMA_HIGH,
        "seq": seq,
        "authority_sha": link_sha,
        "commit_record_sha": commit_sha,
        "previous_high_water_sha": chains["high_water_head_sha"],
    }
    high_sha = _sha(high)
    st[HIGH_WATER_STORE][high_sha] = high
    return "RECORDED"


def adopt_genesis(rt: dict, st: dict, boot: dict, services: dict, registry_store: dict,
                  certificate_store: dict, domain: w104.CertificateWitnessDomain,
                  binding_store: dict) -> str:
    _initialize_empty_markers(st, boot)
    _guard(st, boot, rt)
    return w107.adopt_genesis(
        rt, st, boot, services, registry_store, certificate_store, domain, binding_store
    )


def authority(rt: dict, st: dict, boot: dict, services: dict, registry_store: dict,
              certificate_store: dict, domain: w104.CertificateWitnessDomain,
              binding_store: dict, resolved_endpoints: dict | None = None) -> str:
    state = committed_history_state(st, boot, rt)
    if state["status"] == HISTORY_INCOMPLETE:
        return HOLD_INCOMPLETE
    return w107.authority(
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
        raise ValueError("Wave 108 predecessor HOLD")
    return w107.prepare(
        rt, st, priv, boot, services, registry_store, transition_store,
        certificate_store, domain, binding_store,
        target_user_app_state_sha, target_remote_registry_sha
    )


def commit(rt: dict, st: dict, boot: dict, registry_store: dict, transition_store: dict,
           link_sha: str, transition_sha: str, binding_store: dict,
           n: int | None = None) -> str:
    result = w107.commit(
        rt, st, boot, registry_store, transition_store,
        link_sha, transition_sha, binding_store, n
    )
    if result == "COMMITTED":
        marker = _append_commit_marker(st, boot, link_sha)
        if marker not in ("RECORDED", "ALREADY_RECORDED"):
            raise RuntimeError(f"unexpected Wave 108 marker result: {marker}")
    return result


def publish(rt: dict, st: dict, boot: dict, services: dict, tokens: dict,
            registry_store: dict, slot: str) -> str:
    return w107.publish(rt, st, boot, services, tokens, registry_store, slot)


def certify_and_sync(rt: dict, st: dict, boot: dict, services: dict, registry_store: dict,
                     certificate_store: dict, domain: w104.CertificateWitnessDomain,
                     slots: tuple[str, ...] | list[str] | None = None) -> tuple[str, dict]:
    return w107.certify_and_sync(
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
        raise RuntimeError(f"Wave 108 local commit failed: {result}")
    for slot in q.REMOTE_IDS:
        remote_result = publish(rt, st, boot, services, tokens, registry_store, slot)
        if remote_result not in ("APPENDED", "ALREADY_CURRENT"):
            raise RuntimeError(f"Wave 108 remote publish failed: {slot}: {remote_result}")
    cert_result, sync = certify_and_sync(
        rt, st, boot, services, registry_store, certificate_store, domain
    )
    if cert_result not in ("CERTIFIED", "ALREADY_CERTIFIED"):
        raise RuntimeError(f"Wave 108 quorum certification failed: {cert_result}")
    if any(value not in ("ALREADY_CURRENT", "WITNESS_SYNCED_1") for value in sync.values()):
        raise RuntimeError(f"Wave 108 certificate witness sync failed: {sync}")
    verdict = authority(
        rt, st, boot, services, registry_store, certificate_store, domain, binding_store
    )
    if not verdict.startswith("AUTHORITATIVE"):
        raise RuntimeError(f"Wave 108 authority failed: {verdict}")
    return cp, use, link, transition_sha, body
