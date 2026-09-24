#!/usr/bin/env python3
"""AXM Flowing Compute Wave 109: fail-closed commit-status ambiguity guard.

Additive experiment over exact Wave 108. Independent verifier PR #33 showed that deleting the
newest rows from both Wave-108 marker ledgers can relabel a genuinely accepted epoch as a harmless
prepared-only epoch while its L/C/U authority bodies and Wave-105 root-binding body remain retained.
With a partial stale quorum and the only newer certificate witness unavailable, stale authority can
then return.

Wave 109 does not pretend the same local failure domain can reconstruct a lost durable fact. Instead
it removes the unsafe guess: any retained transaction evidence that is not named by the committed
marker ledger is classified as UNRESOLVED_COMMIT_STATUS and authority fails closed. This includes a
legitimate in-flight prepare. Commit may still complete because the commit path already carries the
prepared identities; once Wave 108 appends its paired markers the ambiguity clears.

The guard cross-checks four retained evidence families:
- manifested authority links L;
- their exact checkpoint C and signer-use U bodies;
- the Wave-105 certificate-witness-root binding chain;
- the Wave-108 paired commit/high-water marker chains.

Truth boundary:
- UNRESOLVED means exactly that: the current single-domain evidence cannot prove whether the extra
  transaction was merely prepared or had once committed and lost its marker tail;
- deleting the marker tail AND every newer L/C/U/binding body can still reduce the local world to an
  older genuine prefix; this remains a preserved coordinated-rollback counterexample;
- stores/credentials are still modeled Python state in one process, not process/device/provider
  independent durable storage;
- no fresh AXM/monolith, performance, energy, network, retained/incremental/dormant-compute result is
  claimed here;
- no merge or CANON promotion is performed by this tool.
"""
from __future__ import annotations

import hashlib

import AXM_FLOWING_COMPUTE_COMMITTED_HISTORY_MANIFEST as w108
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_ROOT_BINDING as w105
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w104


g = w108.g
q = w108.q

SRC = {
    "wave108_builder_head": "7573e1e97d026ed07065fcca46cc0d88a26e64b5",
    "wave108_tested_source_commit": "7b9ec8548bde69df1d8971567aaf04abd0fa2e5c",
    "wave108_tool_blob": "629318c9645649a29d7a4d4c97f106a0ba958f6d",
    "wave108_selftest_blob": "aeac803084fc05e82c626bb830cee48146c710e2",
    "verifier_pr": 33,
    "verifier_head": "49a8bfe61d7e062c52e419d9670cb95e41730e98",
    "verifier_ci_head": "d2d5851a1bf3088d1d2c96af909777bc6ea2ed6f",
    "verifier_evidence_blob": "b69e34546378a0e7a38f550e89afb926a8909e21",
    "verifier_repro_blob": "196482bc43391d151508f70fa176f20ea7e8e72a",
    "verifier_ci_run": 35198901311,
    "verifier_ci_normal_job": 105128625588,
    "verifier_ci_optimized_job": 105128625455,
}

HISTORY_NONE = w108.HISTORY_NONE
HISTORY_VALID = w108.HISTORY_VALID
HISTORY_INCOMPLETE = w108.HISTORY_INCOMPLETE
HISTORY_UNRESOLVED = "UNRESOLVED_COMMIT_STATUS"
HOLD_INCOMPLETE = w108.HOLD_INCOMPLETE
HOLD_UNRESOLVED = "HOLD_COMMIT_STATUS_UNRESOLVED"


def _dict_store(value, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label}-store-shape-invalid")
    return value


def _validated_bindings(binding_store: dict, registry_store: dict) -> dict[str, dict]:
    store = _dict_store(binding_store, "binding")
    rows: dict[str, dict] = {}
    for sha, body in store.items():
        if not isinstance(sha, str) or len(sha) != 64 or not isinstance(body, dict):
            raise ValueError("binding-row-shape-invalid")
        if body.get("schema") != w105.BINDING_SCHEMA:
            raise ValueError("unexpected-binding-store-schema")
        rows[sha] = w105.verify_binding(body, store, registry_store, sha)
    return rows


def _manifested_identities(st: dict, boot: dict, committed_shas: list[str]) -> dict:
    checkpoints: set[str] = set()
    uses: set[str] = set()
    rows = []
    for authority_sha in committed_shas:
        link, cp, use = g.w98.resolve(st, authority_sha, boot)
        checkpoints.add(link["checkpoint_sha"])
        uses.add(link["use_sha"])
        rows.append((link, cp, use))
    return {"checkpoints": checkpoints, "uses": uses, "rows": rows}


def _binding_chain_for_manifest(
    rows: dict[str, dict], manifested_rows: list[tuple[dict, dict, dict]], rt: dict | None
) -> tuple[set[str], list[dict]]:
    """Resolve the exact binding chain named by manifested checkpoint state identities.

    Wave 105 checkpoint state is q.binding(binding_sha, remote_registry_sha), so each manifested
    checkpoint mechanically identifies its root-binding row without trusting the mutable runtime.
    """
    matched: list[tuple[str, dict]] = []
    for link, cp, _use in manifested_rows:
        candidates = []
        for sha, body in rows.items():
            if body.get("seq") != link.get("epoch"):
                continue
            expected_state = q.binding(body["binding_sha"], body["remote_registry_sha"])
            if cp.get("state_sha") == expected_state:
                candidates.append((sha, body))
        if len(candidates) != 1:
            raise ValueError("manifested-checkpoint-binding-match-not-unique")
        matched.append(candidates[0])

    expected: set[str] = set()
    chain: list[dict] = []
    if matched:
        for index, (sha, body) in enumerate(matched, start=1):
            if body.get("seq") != index:
                raise ValueError("manifested-binding-sequence-mismatch")
            if index > 1 and body.get("predecessor_binding_sha") != matched[index - 2][0]:
                raise ValueError("manifested-binding-predecessor-mismatch")
            expected.add(sha)
            chain.append(body)
        genesis_sha = matched[0][1].get("predecessor_binding_sha")
        if not isinstance(genesis_sha, str) or genesis_sha not in rows:
            raise ValueError("manifested-binding-genesis-missing")
        genesis = rows[genesis_sha]
        if genesis.get("seq") != 0 or genesis.get("predecessor_binding_sha") is not None:
            raise ValueError("manifested-binding-genesis-invalid")
        if genesis.get("certificate_witness_registry_sha") != matched[-1][1].get(
            "certificate_witness_registry_sha"
        ):
            raise ValueError("manifested-binding-root-changed")
        expected.add(genesis_sha)
        chain.insert(0, genesis)
        return expected, chain

    # Empty committed history after Wave-108 adoption should have one exact genesis binding. Prefer
    # the runtime pointer when available, but do not use it to excuse multiple retained genesis roots.
    genesis_candidates = [(sha, body) for sha, body in rows.items() if body.get("seq") == 0]
    if len(genesis_candidates) != 1:
        raise ValueError("genesis-binding-match-not-unique")
    genesis_sha, genesis = genesis_candidates[0]
    if rt is not None and rt.get("app_state_sha") != genesis_sha:
        raise ValueError("runtime-genesis-binding-mismatch")
    expected.add(genesis_sha)
    chain.append(genesis)
    return expected, chain


def commit_status_state(
    st: dict,
    boot: dict,
    rt: dict | None,
    registry_store: dict,
    binding_store: dict,
) -> dict:
    """Classify committed history without silently downgrading retained extra evidence."""
    base = w108.committed_history_state(st, boot, rt)
    if base.get("status") in (HISTORY_NONE, HISTORY_INCOMPLETE):
        return {
            "status": base.get("status"),
            "reason": "wave108-base-" + str(base.get("reason")),
            "wave108": base,
        }
    if base.get("status") != HISTORY_VALID:
        return {
            "status": HISTORY_INCOMPLETE,
            "reason": "unexpected-wave108-history-status",
            "wave108": base,
        }

    try:
        links = _dict_store(st.get("L", {}), "authority-link")
        checkpoints = _dict_store(st.get("C", {}), "checkpoint")
        uses = _dict_store(st.get("U", {}), "signer-use")
        committed_shas = list(base.get("committed_authority_shas", []))
        manifested = _manifested_identities(st, boot, committed_shas)
        binding_rows = _validated_bindings(binding_store, registry_store)
        expected_binding_shas, binding_chain = _binding_chain_for_manifest(
            binding_rows, manifested["rows"], rt
        )
    except Exception as exc:
        return {
            "status": HISTORY_INCOMPLETE,
            "reason": f"cross-evidence-verification:{type(exc).__name__}:{exc}",
            "wave108": base,
        }

    expected_links = set(committed_shas)
    extra_links = sorted(set(links) - expected_links)
    extra_checkpoints = sorted(set(checkpoints) - manifested["checkpoints"])
    extra_uses = sorted(set(uses) - manifested["uses"])
    extra_bindings = sorted(set(binding_rows) - expected_binding_shas)

    if extra_links or extra_checkpoints or extra_uses or extra_bindings:
        return {
            "status": HISTORY_UNRESOLVED,
            "reason": "retained-unmanifested-transaction-evidence",
            "wave108": base,
            "committed_count": len(committed_shas),
            "extra_authority_shas": extra_links,
            "extra_checkpoint_shas": extra_checkpoints,
            "extra_use_shas": extra_uses,
            "extra_binding_shas": extra_bindings,
            "expected_binding_shas": sorted(expected_binding_shas),
            "binding_chain_seqs": [row.get("seq") for row in binding_chain],
        }

    return {
        "status": HISTORY_VALID,
        "reason": "markers-and-retained-transaction-evidence-agree",
        "wave108": base,
        "committed_count": len(committed_shas),
        "committed_authority_shas": committed_shas,
        "expected_binding_shas": sorted(expected_binding_shas),
        "binding_chain_seqs": [row.get("seq") for row in binding_chain],
    }


def adopt_genesis(
    rt: dict,
    st: dict,
    boot: dict,
    services: dict,
    registry_store: dict,
    certificate_store: dict,
    domain: w104.CertificateWitnessDomain,
    binding_store: dict,
) -> str:
    result = w108.adopt_genesis(
        rt, st, boot, services, registry_store, certificate_store, domain, binding_store
    )
    state = commit_status_state(st, boot, rt, registry_store, binding_store)
    if state["status"] != HISTORY_VALID:
        raise ValueError(f"Wave 109 genesis evidence HOLD: {state['status']}")
    return result


def authority(
    rt: dict,
    st: dict,
    boot: dict,
    services: dict,
    registry_store: dict,
    certificate_store: dict,
    domain: w104.CertificateWitnessDomain,
    binding_store: dict,
    resolved_endpoints: dict | None = None,
) -> str:
    state = commit_status_state(st, boot, rt, registry_store, binding_store)
    if state["status"] == HISTORY_INCOMPLETE:
        return HOLD_INCOMPLETE
    if state["status"] == HISTORY_UNRESOLVED:
        return HOLD_UNRESOLVED
    return w108.authority(
        rt,
        st,
        boot,
        services,
        registry_store,
        certificate_store,
        domain,
        binding_store,
        resolved_endpoints,
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
        rt, st, boot, services, registry_store, certificate_store, domain, binding_store
    )
    if not verdict.startswith("AUTHORITATIVE"):
        raise ValueError("Wave 109 predecessor HOLD")
    return w108.prepare(
        rt,
        st,
        priv,
        boot,
        services,
        registry_store,
        transition_store,
        certificate_store,
        domain,
        binding_store,
        target_user_app_state_sha,
        target_remote_registry_sha,
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
    return w108.commit(
        rt,
        st,
        boot,
        registry_store,
        transition_store,
        link_sha,
        transition_sha,
        binding_store,
        n,
    )


def publish(
    rt: dict,
    st: dict,
    boot: dict,
    services: dict,
    tokens: dict,
    registry_store: dict,
    slot: str,
) -> str:
    return w108.publish(rt, st, boot, services, tokens, registry_store, slot)


def certify_and_sync(
    rt: dict,
    st: dict,
    boot: dict,
    services: dict,
    registry_store: dict,
    certificate_store: dict,
    domain: w104.CertificateWitnessDomain,
    slots: tuple[str, ...] | list[str] | None = None,
) -> tuple[str, dict]:
    return w108.certify_and_sync(
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
        rt,
        st,
        priv,
        boot,
        services,
        registry_store,
        transition_store,
        certificate_store,
        domain,
        binding_store,
        app,
    )
    unresolved = commit_status_state(st, boot, rt, registry_store, binding_store)
    if unresolved["status"] != HISTORY_UNRESOLVED:
        raise RuntimeError(f"Wave 109 prepare did not enter unresolved state: {unresolved}")
    result = commit(
        rt,
        st,
        boot,
        registry_store,
        transition_store,
        link["authority_sha"],
        transition_sha,
        binding_store,
    )
    if result != "COMMITTED":
        raise RuntimeError(f"Wave 109 local commit failed: {result}")
    resolved = commit_status_state(st, boot, rt, registry_store, binding_store)
    if resolved["status"] != HISTORY_VALID:
        raise RuntimeError(f"Wave 109 commit ambiguity did not clear: {resolved}")
    for slot in q.REMOTE_IDS:
        remote_result = publish(rt, st, boot, services, tokens, registry_store, slot)
        if remote_result not in ("APPENDED", "ALREADY_CURRENT"):
            raise RuntimeError(f"Wave 109 remote publish failed: {slot}: {remote_result}")
    cert_result, sync = certify_and_sync(
        rt, st, boot, services, registry_store, certificate_store, domain
    )
    if cert_result not in ("CERTIFIED", "ALREADY_CERTIFIED"):
        raise RuntimeError(f"Wave 109 quorum certification failed: {cert_result}")
    if any(value not in ("ALREADY_CURRENT", "WITNESS_SYNCED_1") for value in sync.values()):
        raise RuntimeError(f"Wave 109 certificate witness sync failed: {sync}")
    verdict = authority(
        rt, st, boot, services, registry_store, certificate_store, domain, binding_store
    )
    if not verdict.startswith("AUTHORITATIVE"):
        raise RuntimeError(f"Wave 109 authority failed: {verdict}")
    return cp, use, link, transition_sha, body
