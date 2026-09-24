#!/usr/bin/env python3
"""AXM Flowing Compute Wave 100: monotonic registry-transition authority boundary.

Additive experiment over the exact Wave 99 registry/quorum tool. This wave directly repairs
independent verifier PR #24 before any stronger physical failure-domain claim.

Truth boundary:
- remote witnesses are still modeled Python objects in one process;
- this tool proves a stricter registry-transition contract, not physical independence;
- remote credentials remain symmetric test tokens;
- no CANON, moral/root-judgment, energy, or retained/incremental/dormant-compute claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from copy import deepcopy

import AXM_FLOWING_COMPUTE_REMOTE_WITNESS_REGISTRY_QUORUM as q

SRC = {
    "wave99_head": "0c3ea28b4d731cde942d337c87a046f363d496c2",
    "wave99_tool_blob": "c4c0a6bcabeafcf19502303857d1fc4da6fe8ea5",
    "wave99_selftest_blob": "6efa792265c4fd3b54e7cfb192f5e1440402010a",
    "verifier_pr": 24,
    "verifier_head": "0c13b87882df2a6a18bd3dff032b47b92a36a3a6",
    "verifier_evidence_blob": "367d8627679e76114a1dd767e95b4b92090447ad",
}

TRANSITION_SCHEMA = "remote-registry-transition/w100-v1"


def _seal(body: dict, field: str) -> dict:
    return q.w98.seal(body, field)


def _chk(body: dict, field: str) -> None:
    q.w98.chk(body, field)


def registry_delta(current: dict, target: dict) -> dict:
    """Return the only transition shapes Wave 100 is willing to authorize."""
    if current["registry_sha"] == target["registry_sha"]:
        return {
            "kind": "SAME",
            "changed_slots": [],
            "changed_fields": {},
        }

    if target["predecessor_registry_sha"] != current["registry_sha"]:
        raise ValueError("registry target is not exact direct successor")
    if target["generation"] != current["generation"] + 1:
        raise ValueError("registry target generation is not current+1")

    changed_fields = {}
    for slot in q.REMOTE_IDS:
        a = current["slots"][slot]
        b = target["slots"][slot]
        fields = sorted(k for k in a if a[k] != b[k])
        if fields:
            changed_fields[slot] = fields

    changed_slots = sorted(changed_fields)
    if len(changed_slots) != 1:
        raise ValueError("registry successor must change exactly one slot")
    slot = changed_slots[0]
    if changed_fields[slot] != ["credential_hash"]:
        raise ValueError("Wave 100 only authorizes credential-only registry rotation")

    return {
        "kind": "CREDENTIAL_ROTATION",
        "changed_slots": changed_slots,
        "changed_fields": changed_fields,
    }


def validate_live_registry_step(registry_store: dict, current_sha: str, target_sha: str) -> dict:
    current = q.get_registry(registry_store, current_sha)
    target = q.get_registry(registry_store, target_sha)
    delta = registry_delta(current, target)
    return {
        "current": current,
        "target": target,
        "delta": delta,
    }


def make_transition(registry_store: dict, current_sha: str, target_sha: str,
                    predecessor_authority_sha: str | None, target_authority_sha: str,
                    target_checkpoint_sha: str, target_app_state_sha: str) -> dict:
    step = validate_live_registry_step(registry_store, current_sha, target_sha)
    current, target, delta = step["current"], step["target"], step["delta"]
    return _seal({
        "schema": TRANSITION_SCHEMA,
        "predecessor_authority_sha": predecessor_authority_sha,
        "target_authority_sha": target_authority_sha,
        "target_checkpoint_sha": target_checkpoint_sha,
        "current_registry_sha": current_sha,
        "current_generation": current["generation"],
        "target_registry_sha": target_sha,
        "target_generation": target["generation"],
        "transition_kind": delta["kind"],
        "changed_slots": delta["changed_slots"],
        "changed_fields": delta["changed_fields"],
        "target_app_state_sha": target_app_state_sha,
        "target_state_sha": q.binding(target_app_state_sha, target_sha),
        "transition_sha": "",
    }, "transition_sha")


def put_transition(store: dict, transition: dict) -> str:
    _chk(transition, "transition_sha")
    if transition.get("schema") != TRANSITION_SCHEMA:
        raise ValueError("transition schema mismatch")
    sha = transition["transition_sha"]
    if sha in store and store[sha] != transition:
        raise ValueError("transition collision")
    store[sha] = deepcopy(transition)
    return sha


def get_transition(store: dict, sha: str) -> dict:
    if sha not in store:
        raise ValueError("transition body missing")
    tr = deepcopy(store[sha])
    _chk(tr, "transition_sha")
    if tr["transition_sha"] != sha:
        raise ValueError("transition key/body mismatch")
    if tr.get("schema") != TRANSITION_SCHEMA:
        raise ValueError("transition schema mismatch")
    return tr


def current_authority_sha(rt: dict, st: dict, boot: dict) -> str | None:
    status, link, _ = q.current_local(rt, st, boot)
    if status == "GENESIS":
        return None
    if status == "LOCAL_OK":
        return link["authority_sha"]
    return None


def prepare(rt: dict, st: dict, priv: dict, boot: dict, services: dict,
            registry_store: dict, transition_store: dict,
            target_app_state_sha: str | None = None,
            target_registry_sha: str | None = None) -> tuple:
    verdict = authority(rt, st, boot, services, registry_store)
    if not verdict.startswith("AUTHORITATIVE"):
        raise ValueError("predecessor HOLD")

    current_registry_sha = rt["remote_registry_sha"]
    target_registry_sha = target_registry_sha or current_registry_sha
    validate_live_registry_step(registry_store, current_registry_sha, target_registry_sha)

    status, predecessor_link, _ = q.current_local(rt, st, boot)
    if status == "GENESIS":
        predecessor_authority_sha = None
    elif status == "LOCAL_OK":
        predecessor_authority_sha = predecessor_link["authority_sha"]
    else:
        raise ValueError("predecessor local state is not settled")

    cp, use, link, _legacy_meta = q.prepare(
        rt, st, priv, boot, services, registry_store,
        target_app_state_sha=target_app_state_sha,
        target_registry_sha=target_registry_sha,
    )
    target_app_state_sha = target_app_state_sha or rt["app_state_sha"]
    tr = make_transition(
        registry_store,
        current_registry_sha,
        target_registry_sha,
        predecessor_authority_sha,
        link["authority_sha"],
        cp["checkpoint_sha"],
        target_app_state_sha,
    )
    put_transition(transition_store, tr)
    return cp, use, link, tr["transition_sha"]


def commit(rt: dict, st: dict, boot: dict, registry_store: dict, transition_store: dict,
           link_sha: str, transition_sha: str, n: int | None = None) -> str:
    try:
        tr = get_transition(transition_store, transition_sha)
        link, cp, _ = q.w98.resolve(st, link_sha, boot)
        if tr["target_authority_sha"] != link["authority_sha"]:
            return "TRANSITION_AUTHORITY_HOLD"
        if tr["target_checkpoint_sha"] != cp["checkpoint_sha"]:
            return "TRANSITION_CHECKPOINT_HOLD"
        if rt.get("remote_registry_sha") != tr["current_registry_sha"]:
            return "TRANSITION_CURRENT_REGISTRY_HOLD"

        step = validate_live_registry_step(
            registry_store, tr["current_registry_sha"], tr["target_registry_sha"]
        )
        current, target, delta = step["current"], step["target"], step["delta"]
        if current["generation"] != tr["current_generation"] or target["generation"] != tr["target_generation"]:
            return "TRANSITION_GENERATION_HOLD"
        if delta["kind"] != tr["transition_kind"] or delta["changed_slots"] != tr["changed_slots"] \
                or delta["changed_fields"] != tr["changed_fields"]:
            return "TRANSITION_DELTA_HOLD"

        expected_state = q.binding(tr["target_app_state_sha"], tr["target_registry_sha"])
        if expected_state != tr["target_state_sha"] or expected_state != cp.get("state_sha"):
            return "TRANSITION_STATE_BINDING_HOLD"

        status, pred_link, _ = q.current_local(rt, st, boot)
        if status == "GENESIS":
            actual_pred = None
        elif status == "LOCAL_OK":
            actual_pred = pred_link["authority_sha"]
        elif status == "HOLD_PARTIAL":
            actual_pred = tr["predecessor_authority_sha"]
        else:
            return "TRANSITION_PREDECESSOR_HOLD"
        if actual_pred != tr["predecessor_authority_sha"]:
            return "TRANSITION_PREDECESSOR_HOLD"
        if link.get("predecessor_authority_sha") != tr["predecessor_authority_sha"]:
            return "TRANSITION_LINK_PREDECESSOR_HOLD"

        safe_meta = {
            "target_app_state_sha": tr["target_app_state_sha"],
            "target_registry_sha": tr["target_registry_sha"],
            "target_state_sha": tr["target_state_sha"],
        }
        return q.commit(rt, st, boot, link["authority_sha"], safe_meta, n)
    except Exception:
        return "TRANSITION_VALIDATION_HOLD"


def _records_by_seq(service: dict) -> list[dict]:
    rows = []
    for body in service.get("records", {}).values():
        rec = deepcopy(body)
        _chk(rec, "record_sha")
        rows.append(rec)
    rows.sort(key=lambda r: r["seq"])
    return rows


def verify_remote_registry_history(service: dict, registry_store: dict) -> dict | None:
    """Require each retained remote record's registry identity to move monotonically."""
    rows = _records_by_seq(service)
    if not rows:
        return None
    for i, rec in enumerate(rows):
        reg = q.get_registry(registry_store, rec["registry_sha"])
        if i == 0:
            continue
        prev = rows[i - 1]
        prev_reg = q.get_registry(registry_store, prev["registry_sha"])
        if reg["registry_sha"] == prev_reg["registry_sha"]:
            continue
        registry_delta(prev_reg, reg)
    return deepcopy(rows[-1])


def _remote_target_step_ok(service: dict, registry_store: dict, target_registry_sha: str) -> bool:
    rows = _records_by_seq(service)
    if not rows:
        return True
    prev = q.get_registry(registry_store, rows[-1]["registry_sha"])
    target = q.get_registry(registry_store, target_registry_sha)
    if prev["registry_sha"] == target["registry_sha"]:
        return True
    registry_delta(prev, target)
    return True


def authority(rt: dict, st: dict, boot: dict, services: dict, registry_store: dict) -> str:
    base = q.authority(rt, st, boot, services, registry_store)
    if base in ("HOLD_REMOTE_ALIAS", "HOLD_REMOTE_SET", "HOLD_REMOTE_IDENTITY", "HOLD_REGISTRY",
                "HOLD_STATE_BINDING", "HOLD_PARTIAL", "HOLD_WITNESS_MISMATCH"):
        return base

    for slot in q.REMOTE_IDS:
        svc = services.get(slot)
        if svc is None or not svc.get("online"):
            continue
        try:
            verify_remote_registry_history(svc, registry_store)
        except Exception:
            return "HOLD_REMOTE_REGISTRY_LINEAGE"

    return base


def publish(rt: dict, st: dict, boot: dict, services: dict, tokens: dict,
            registry_store: dict, slot: str) -> str:
    if slot not in q.REMOTE_IDS or slot not in services:
        return "REMOTE_IDENTITY_HOLD"
    try:
        verify_remote_registry_history(services[slot], registry_store)
        _remote_target_step_ok(services[slot], registry_store, rt["remote_registry_sha"])
    except Exception:
        return "REMOTE_REGISTRY_TRANSITION_HOLD"
    result = q.publish(rt, st, boot, services, tokens, registry_store, slot)
    if result in ("APPENDED", "ALREADY_CURRENT"):
        try:
            verify_remote_registry_history(services[slot], registry_store)
        except Exception:
            return "REMOTE_REGISTRY_LINEAGE_HOLD"
    return result


def recover_poisoned(rt: dict, st: dict, boot: dict, services: dict, token: bytes,
                     registry_store: dict, slot: str) -> str:
    if slot not in q.REMOTE_IDS or slot not in services:
        return "REMOTE_IDENTITY_HOLD"
    try:
        verify_remote_registry_history(services[slot], registry_store)
        current = q.get_registry(registry_store, rt["remote_registry_sha"])
        pred_sha = current["predecessor_registry_sha"]
        if pred_sha is None:
            return "RECOVERY_REGISTRY_HOLD"
        pred = q.get_registry(registry_store, pred_sha)
        delta = registry_delta(pred, current)
        if delta["kind"] != "CREDENTIAL_ROTATION" or delta["changed_slots"] != [slot]:
            return "RECOVERY_REGISTRY_DELTA_HOLD"
        _remote_target_step_ok(services[slot], registry_store, current["registry_sha"])
    except Exception:
        return "RECOVERY_REGISTRY_HOLD"
    result = q.recover_poisoned(rt, st, boot, services, token, registry_store, slot)
    if result == "APPENDED":
        try:
            verify_remote_registry_history(services[slot], registry_store)
        except Exception:
            return "RECOVERY_LINEAGE_HOLD"
    return result


def advance_all(st, priv, boot, rt, services, tokens, registry_store, transition_store,
                app_label: str) -> tuple:
    app = hashlib.sha256(app_label.encode()).hexdigest()
    cp, use, link, tr_sha = prepare(
        rt, st, priv, boot, services, registry_store, transition_store, app
    )
    if commit(rt, st, boot, registry_store, transition_store, link["authority_sha"], tr_sha) != "COMMITTED":
        raise RuntimeError("local commit failed")
    for slot in q.REMOTE_IDS:
        if publish(rt, st, boot, services, tokens, registry_store, slot) not in ("APPENDED", "ALREADY_CURRENT"):
            raise RuntimeError("remote publish failed")
    if not authority(rt, st, boot, services, registry_store).startswith("AUTHORITATIVE"):
        raise RuntimeError("authority failed")
    return cp, use, link, tr_sha


def build_depth(depth: int):
    st, priv, boot, rt, services, tokens, registry_store = q.fixture()
    transition_store = {}
    for i in range(depth):
        advance_all(
            st, priv, boot, rt, services, tokens, registry_store, transition_store,
            f"wave100-state-{i}"
        )
    return st, priv, boot, rt, services, tokens, registry_store, transition_store


def bench(depths=(1, 4, 8), rounds=5):
    rows = []
    for depth in depths:
        st, priv, boot, rt, services, tokens, registry_store, transition_store = build_depth(depth)
        samples = []
        for _ in range(rounds):
            t0 = time.process_time_ns()
            verdict = authority(rt, st, boot, services, registry_store)
            samples.append(time.process_time_ns() - t0)
            if not verdict.startswith("AUTHORITATIVE"):
                raise RuntimeError("benchmark authority failed")
        rows.append({
            "depth": depth,
            "rounds": rounds,
            "authority_median_cpu_us": statistics.median(samples) / 1000.0,
        })
    return rows


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--benchmark-rounds", type=int, default=5)
    p.add_argument("--report")
    args = p.parse_args()
    report = {
        "schema": "axm.flowing_compute.wave100.protocol-smoke/v1",
        "source": SRC,
        "synthetic_scaling": bench(rounds=args.benchmark_rounds),
    }
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")


if __name__ == "__main__":
    main()
