#!/usr/bin/env python3
"""AXM Flowing Compute Wave 106: durable bootstrap-lineage closure.

Additive experiment over exact Wave 105. Independent verifier PR #30 showed that Wave 105 can
re-enter genesis after an accepted authority epoch when a caller supplies a saved genesis runtime
view, saved genesis remote-service snapshots, a fresh empty certificate store, and a fresh legitimate
certificate-witness domain while the original accepted world remains intact.

Wave 106 adds one small append-only lineage store inside the retained authority state ``st``:
- the first genesis root adoption writes one sealed adoption record;
- a successful first authority commit appends one sealed closure record linked to that adoption;
- genesis authority is denied once retained authority evidence or a closure exists;
- a fresh/substitute certificate store, runtime pointer, or witness domain cannot reopen bootstrap
  while the same retained authority state is supplied;
- if the Wave-106 lineage store is lost while retained authority bodies remain, bootstrap fails closed
  instead of silently selecting a new root.

Truth boundary:
- the adoption record is a local content-addressed root lock, not an independently signed or physically
  monotonic fact; initial root selection remains a configuration/bootstrap trust boundary;
- a whole rollback/substitution of ``st`` to a pre-adoption image still erases the Wave-106 memory and
  remains a preserved counterexample;
- crash after the lower local commit but before the Wave-106 closure append can cause a safe HOLD;
  Wave 106 does not claim an atomic durable transaction across those writes;
- all stores/endpoints/credentials still live inside one Python process;
- symmetric HMAC witness credentials remain test-only;
- no CANON, merge, network, energy, performance, retained/incremental/dormant-compute win is claimed.
"""
from __future__ import annotations

import hashlib
from copy import deepcopy

import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_ROOT_BINDING as w105
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w104

g = w105.g
q = w105.q

SRC = {
    "wave105_builder_head": "5c683032e0834e8a57e1bb780f624eb1cb312d3c",
    "wave105_tool_blob": "1e0e543c57f880c3e631619fa1859c24ace5ff79",
    "wave105_selftest_blob": "c6d39f469e98590823af3a576c4efbb18957d00b",
    "verifier_pr": 30,
    "verifier_head": "ddefa0f3bc1aff5de804efaac1192433a6595ee1",
    "verifier_evidence_blob": "847fb896cb5d4d3c5ac7d7ab264c94833c49225b",
    "verifier_repro_blob": "975258a690ae9d8756797666be56ee29b5118051",
}

STORE_KEY = "W106_BOOTSTRAP_LINEAGE"
ADOPTION_SCHEMA = "axm-bootstrap-lineage-adoption/w106-v1"
CLOSURE_SCHEMA = "axm-bootstrap-lineage-closure/w106-v1"


def _is_sha(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _D(body: object) -> str:
    return g.w98.D(body)


def _seal(body: dict, field: str) -> dict:
    return g.w98.seal(body, field)


def _chk(body: dict, field: str) -> None:
    g.w98.chk(body, field)


def _lineage_store(st: dict, create: bool = False) -> dict | None:
    store = st.get(STORE_KEY)
    if store is None and create:
        store = {}
        st[STORE_KEY] = store
    if store is not None and not isinstance(store, dict):
        raise ValueError("Wave 106 lineage store shape invalid")
    return store


def _boot_sha(boot: dict) -> str:
    return _D({"schema": "axm-bootstrap-boot-fingerprint/w106-v1", "boot": boot})


def _bootstrap_id(boot: dict, user_app_state_sha: str, remote_registry_sha: str) -> str:
    return _D({
        "schema": "axm-bootstrap-substrate-identity/w106-v1",
        "boot_sha": _boot_sha(boot),
        "genesis_user_app_state_sha": user_app_state_sha,
        "genesis_remote_registry_sha": remote_registry_sha,
    })


def make_adoption(boot: dict, user_app_state_sha: str, remote_registry_sha: str,
                  certificate_witness_registry_sha: str, genesis_binding_sha: str) -> dict:
    return _seal({
        "schema": ADOPTION_SCHEMA,
        "bootstrap_id": _bootstrap_id(boot, user_app_state_sha, remote_registry_sha),
        "boot_sha": _boot_sha(boot),
        "genesis_user_app_state_sha": user_app_state_sha,
        "genesis_remote_registry_sha": remote_registry_sha,
        "certificate_witness_registry_sha": certificate_witness_registry_sha,
        "genesis_binding_sha": genesis_binding_sha,
        "adoption_sha": "",
    }, "adoption_sha")


def verify_adoption(record: dict, boot: dict, registry_store: dict,
                    binding_store: dict | None = None) -> dict:
    body = deepcopy(record)
    _chk(body, "adoption_sha")
    if body.get("schema") != ADOPTION_SCHEMA:
        raise ValueError("Wave 106 adoption schema mismatch")
    for field in (
        "bootstrap_id",
        "boot_sha",
        "genesis_user_app_state_sha",
        "genesis_remote_registry_sha",
        "certificate_witness_registry_sha",
        "genesis_binding_sha",
        "adoption_sha",
    ):
        if not _is_sha(body.get(field)):
            raise ValueError(f"Wave 106 adoption {field} invalid")
    if body["boot_sha"] != _boot_sha(boot):
        raise ValueError("Wave 106 adoption boot identity mismatch")
    expected_id = _bootstrap_id(
        boot, body["genesis_user_app_state_sha"], body["genesis_remote_registry_sha"]
    )
    if body["bootstrap_id"] != expected_id:
        raise ValueError("Wave 106 bootstrap identity mismatch")
    q.get_registry(registry_store, body["genesis_remote_registry_sha"])
    expected_binding = w105.make_binding(
        0,
        body["genesis_user_app_state_sha"],
        body["genesis_remote_registry_sha"],
        body["certificate_witness_registry_sha"],
        None,
    )
    if expected_binding["binding_sha"] != body["genesis_binding_sha"]:
        raise ValueError("Wave 106 adoption/genesis binding mismatch")
    if binding_store is not None and body["genesis_binding_sha"] in binding_store:
        actual = w105.get_binding(
            binding_store, registry_store, body["genesis_binding_sha"]
        )
        if actual != expected_binding:
            raise ValueError("Wave 106 retained genesis binding mismatch")
    return body


def make_closure(adoption: dict, first_authority_sha: str, first_checkpoint_sha: str,
                 first_binding_sha: str) -> dict:
    return _seal({
        "schema": CLOSURE_SCHEMA,
        "bootstrap_id": adoption["bootstrap_id"],
        "adoption_sha": adoption["adoption_sha"],
        "certificate_witness_registry_sha": adoption["certificate_witness_registry_sha"],
        "first_authority_sha": first_authority_sha,
        "first_checkpoint_sha": first_checkpoint_sha,
        "first_binding_sha": first_binding_sha,
        "closure_sha": "",
    }, "closure_sha")


def verify_closure(record: dict, adoption: dict, st: dict, boot: dict,
                   registry_store: dict, binding_store: dict) -> dict:
    body = deepcopy(record)
    _chk(body, "closure_sha")
    if body.get("schema") != CLOSURE_SCHEMA:
        raise ValueError("Wave 106 closure schema mismatch")
    for field in (
        "bootstrap_id",
        "adoption_sha",
        "certificate_witness_registry_sha",
        "first_authority_sha",
        "first_checkpoint_sha",
        "first_binding_sha",
        "closure_sha",
    ):
        if not _is_sha(body.get(field)):
            raise ValueError(f"Wave 106 closure {field} invalid")
    if (
        body["bootstrap_id"] != adoption["bootstrap_id"]
        or body["adoption_sha"] != adoption["adoption_sha"]
        or body["certificate_witness_registry_sha"]
        != adoption["certificate_witness_registry_sha"]
    ):
        raise ValueError("Wave 106 closure/adoption mismatch")
    link, cp, _use = g.w98.resolve(st, body["first_authority_sha"], boot)
    if link.get("epoch") != 1:
        raise ValueError("Wave 106 closure must bind authority epoch 1")
    if cp.get("checkpoint_sha") != body["first_checkpoint_sha"]:
        raise ValueError("Wave 106 closure checkpoint mismatch")
    binding = w105.get_binding(binding_store, registry_store, body["first_binding_sha"])
    if (
        binding.get("seq") != 1
        or binding.get("predecessor_binding_sha") != adoption["genesis_binding_sha"]
        or binding.get("certificate_witness_registry_sha")
        != adoption["certificate_witness_registry_sha"]
    ):
        raise ValueError("Wave 106 closure binding lineage mismatch")
    expected_state = q.binding(binding["binding_sha"], binding["remote_registry_sha"])
    if cp.get("state_sha") != expected_state:
        raise ValueError("Wave 106 closure checkpoint/root binding mismatch")
    return body


def _records(st: dict, boot: dict, registry_store: dict,
             binding_store: dict | None = None) -> tuple[dict | None, dict | None]:
    store = _lineage_store(st, False)
    if store is None:
        return None, None
    adoptions = []
    closures_raw = []
    for key, record in store.items():
        if not isinstance(record, dict):
            raise ValueError("Wave 106 lineage record shape invalid")
        if record.get("schema") == ADOPTION_SCHEMA:
            if record.get("adoption_sha") != key:
                raise ValueError("Wave 106 adoption key/body mismatch")
            adoptions.append(verify_adoption(record, boot, registry_store, binding_store))
        elif record.get("schema") == CLOSURE_SCHEMA:
            if record.get("closure_sha") != key:
                raise ValueError("Wave 106 closure key/body mismatch")
            closures_raw.append(record)
        else:
            raise ValueError("Wave 106 unknown lineage record schema")
    if len(adoptions) > 1:
        raise ValueError("Wave 106 multiple bootstrap adoptions retained")
    adoption = adoptions[0] if adoptions else None
    if closures_raw and adoption is None:
        raise ValueError("Wave 106 closure exists without adoption")
    closures = []
    if adoption is not None:
        for record in closures_raw:
            if binding_store is None:
                _chk(record, "closure_sha")
                if (
                    record.get("schema") != CLOSURE_SCHEMA
                    or record.get("adoption_sha") != adoption["adoption_sha"]
                ):
                    raise ValueError("Wave 106 closure/adoption mismatch")
                closures.append(deepcopy(record))
            else:
                closures.append(
                    verify_closure(
                        record, adoption, st, boot, registry_store, binding_store
                    )
                )
    if len(closures) > 1:
        raise ValueError("Wave 106 multiple bootstrap closures retained")
    return adoption, closures[0] if closures else None


def _put_record(st: dict, record: dict, field: str) -> str:
    store = _lineage_store(st, True)
    sha = record[field]
    existing = store.get(sha)
    if existing is not None and existing != record:
        raise ValueError("Wave 106 lineage record collision")
    store[sha] = deepcopy(record)
    return sha


def _retained_authority_evidence(st: dict, boot: dict) -> list[str]:
    """Return structurally valid retained authority bodies.

    This intentionally treats a prepared-but-not-committed authority body as bootstrap-closing
    evidence when the Wave-106 lineage store is missing. That is a fail-closed availability tradeoff:
    ``st`` alone cannot prove which prepared body had its runtime pointer committed.
    """
    rows = []
    links = st.get("L", {})
    if not isinstance(links, dict):
        raise ValueError("authority link store shape invalid")
    for sha in links:
        try:
            link, _cp, _use = g.w98.resolve(st, sha, boot)
        except Exception:
            continue
        if link.get("authority_sha") == sha:
            rows.append(sha)
    return sorted(rows)


def adopt_genesis(rt: dict, st: dict, boot: dict, services: dict, registry_store: dict,
                  certificate_store: dict, domain: w104.CertificateWitnessDomain,
                  binding_store: dict) -> str:
    """Adopt or recover exactly one genesis root while bootstrap is still open."""
    domain.verify_bindings()
    status, link, cp = q.current_local(rt, st, boot)
    if status != "GENESIS" or link is not None or cp is not None:
        raise ValueError("Wave 106 root adoption is genesis-only")

    try:
        adoption, closure = _records(st, boot, registry_store, binding_store)
    except Exception as exc:
        raise ValueError(f"Wave 106 lineage invalid: {exc}") from exc

    retained = _retained_authority_evidence(st, boot)
    if closure is not None or retained:
        raise ValueError("Wave 106 bootstrap is closed by retained authority evidence")

    if adoption is None:
        if g.verify_certificate_store(certificate_store, registry_store) is not None:
            raise ValueError("cannot adopt Wave 106 root after certificate history exists")
        initial_user_app = rt.get("app_state_sha")
        initial_remote_registry = rt.get("remote_registry_sha")
        if not _is_sha(initial_user_app) or not _is_sha(initial_remote_registry):
            raise ValueError("Wave 106 genesis runtime identity invalid")
        root = w105.adopt_genesis(
            rt, st, boot, services, registry_store, certificate_store, domain, binding_store
        )
        record = make_adoption(
            boot,
            initial_user_app,
            initial_remote_registry,
            domain.registry_sha,
            root,
        )
        verify_adoption(record, boot, registry_store, binding_store)
        _put_record(st, record, "adoption_sha")
        return root

    if adoption["certificate_witness_registry_sha"] != domain.registry_sha:
        raise ValueError("Wave 106 genesis root already adopted to another witness registry")
    if adoption["genesis_remote_registry_sha"] != rt.get("remote_registry_sha"):
        raise ValueError("Wave 106 genesis remote registry mismatch")

    current_app = rt.get("app_state_sha")
    if current_app not in (
        adoption["genesis_user_app_state_sha"],
        adoption["genesis_binding_sha"],
    ):
        raise ValueError("Wave 106 genesis app identity mismatch")

    # Recreate the exact original genesis binding if its CAS body was lost, but never select a new root.
    expected = w105.make_binding(
        0,
        adoption["genesis_user_app_state_sha"],
        adoption["genesis_remote_registry_sha"],
        adoption["certificate_witness_registry_sha"],
        None,
    )
    w105.put_binding(binding_store, expected, registry_store)
    rt["app_state_sha"] = adoption["genesis_user_app_state_sha"]
    rt["state_sha"] = q.binding(
        adoption["genesis_user_app_state_sha"], adoption["genesis_remote_registry_sha"]
    )
    root = w105.adopt_genesis(
        rt, st, boot, services, registry_store, certificate_store, domain, binding_store
    )
    if root != adoption["genesis_binding_sha"]:
        raise ValueError("Wave 106 recovered genesis root mismatch")
    return root


def authority(rt: dict, st: dict, boot: dict, services: dict, registry_store: dict,
              certificate_store: dict, domain: w104.CertificateWitnessDomain,
              binding_store: dict, resolved_endpoints: dict | None = None) -> str:
    try:
        adoption, closure = _records(st, boot, registry_store, binding_store)
    except Exception:
        return "HOLD_BOOTSTRAP_LINEAGE_INVALID"

    retained = _retained_authority_evidence(st, boot)
    if adoption is None:
        if retained:
            return "HOLD_BOOTSTRAP_LINEAGE_MISSING_WITH_AUTHORITY_HISTORY"
        return "HOLD_BOOTSTRAP_LINEAGE_UNADOPTED"

    if adoption["certificate_witness_registry_sha"] != domain.registry_sha:
        return "HOLD_CERTIFICATE_WITNESS_REGISTRY_ROOT_MISMATCH"

    status, _link, _cp = q.current_local(rt, st, boot)
    if status == "GENESIS":
        if closure is not None or retained:
            return "HOLD_BOOTSTRAP_CLOSED"
        if rt.get("app_state_sha") != adoption["genesis_binding_sha"]:
            return "HOLD_BOOTSTRAP_GENESIS_POINTER_MISMATCH"
    elif status == "LOCAL_OK":
        if closure is None:
            return "HOLD_BOOTSTRAP_CLOSURE_MISSING"
    else:
        return status

    return w105.authority(
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
        raise ValueError("Wave 106 predecessor HOLD")
    return w105.prepare(
        rt, st, priv, boot, services, registry_store, transition_store,
        certificate_store, domain, binding_store,
        target_user_app_state_sha, target_remote_registry_sha
    )


def _append_first_closure_from_runtime(rt: dict, st: dict, boot: dict,
                                       registry_store: dict, binding_store: dict) -> str:
    adoption, closure = _records(st, boot, registry_store, binding_store)
    if adoption is None:
        raise ValueError("Wave 106 adoption missing at closure")
    status, link, cp = q.current_local(rt, st, boot)
    if status != "LOCAL_OK" or link.get("epoch") != 1:
        raise ValueError("Wave 106 first closure requires committed epoch 1")
    if closure is not None:
        verified = verify_closure(
            closure, adoption, st, boot, registry_store, binding_store
        )
        if (
            verified["first_authority_sha"] == link["authority_sha"]
            and verified["first_checkpoint_sha"] == cp["checkpoint_sha"]
            and verified["first_binding_sha"] == rt.get("app_state_sha")
        ):
            return verified["closure_sha"]
        raise ValueError("Wave 106 conflicting first closure")
    record = make_closure(
        adoption,
        link["authority_sha"],
        cp["checkpoint_sha"],
        rt["app_state_sha"],
    )
    verify_closure(record, adoption, st, boot, registry_store, binding_store)
    return _put_record(st, record, "closure_sha")


def commit(rt: dict, st: dict, boot: dict, registry_store: dict, transition_store: dict,
           link_sha: str, transition_sha: str, binding_store: dict,
           n: int | None = None) -> str:
    result = w105.commit(
        rt, st, boot, registry_store, transition_store,
        link_sha, transition_sha, binding_store, n
    )
    if result != "COMMITTED":
        return result
    status, link, _cp = q.current_local(rt, st, boot)
    if status != "LOCAL_OK":
        return "COMMITTED_BOOTSTRAP_CLOSURE_HOLD"
    try:
        if link.get("epoch") == 1:
            _append_first_closure_from_runtime(
                rt, st, boot, registry_store, binding_store
            )
        else:
            _adoption, closure = _records(
                st, boot, registry_store, binding_store
            )
            if closure is None:
                raise ValueError("Wave 106 closure missing after later commit")
    except Exception:
        return "COMMITTED_BOOTSTRAP_CLOSURE_HOLD"
    return "COMMITTED"


def publish(rt: dict, st: dict, boot: dict, services: dict, tokens: dict,
            registry_store: dict, slot: str) -> str:
    return w105.publish(rt, st, boot, services, tokens, registry_store, slot)


def certify_and_sync(rt: dict, st: dict, boot: dict, services: dict, registry_store: dict,
                     certificate_store: dict, domain: w104.CertificateWitnessDomain,
                     slots: tuple[str, ...] | list[str] | None = None) -> tuple[str, dict]:
    return w105.certify_and_sync(
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
        raise RuntimeError(f"Wave 106 local commit failed: {result}")
    for slot in q.REMOTE_IDS:
        remote_result = publish(
            rt, st, boot, services, tokens, registry_store, slot
        )
        if remote_result not in ("APPENDED", "ALREADY_CURRENT"):
            raise RuntimeError(f"Wave 106 remote publish failed: {slot}: {remote_result}")
    cert_result, sync = certify_and_sync(
        rt, st, boot, services, registry_store, certificate_store, domain
    )
    if cert_result not in ("CERTIFIED", "ALREADY_CERTIFIED"):
        raise RuntimeError(f"Wave 106 quorum certification failed: {cert_result}")
    if any(value not in ("ALREADY_CURRENT", "WITNESS_SYNCED_1") for value in sync.values()):
        raise RuntimeError(f"Wave 106 certificate witness sync failed: {sync}")
    verdict = authority(
        rt, st, boot, services, registry_store, certificate_store, domain, binding_store
    )
    if not verdict.startswith("AUTHORITATIVE"):
        raise RuntimeError(f"Wave 106 authority failed: {verdict}")
    return cp, use, link, transition_sha, body
