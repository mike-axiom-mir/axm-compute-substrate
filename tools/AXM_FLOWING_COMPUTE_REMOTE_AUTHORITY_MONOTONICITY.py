#!/usr/bin/env python3
"""AXM Flowing Compute Wave 101: remote authority-epoch monotonicity boundary.

Additive experiment over exact Wave 100 registry-monotonicity code. This wave directly repairs
independent verifier PR #25 before process-level failure-domain work.

Truth boundary:
- remote witnesses are still modeled Python objects in one process;
- this closes a retained-history authority rewind on the modeled contract, not physical rollback;
- remote credentials remain symmetric test tokens;
- one invalid remote history is quarantined rather than counted; two valid exact witnesses are still required;
- no CANON, moral/root-judgment, energy, network, retained/incremental/dormant-compute claim.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from copy import deepcopy

import AXM_FLOWING_COMPUTE_REMOTE_REGISTRY_MONOTONICITY as m
import AXM_FLOWING_COMPUTE_REMOTE_WITNESS_REGISTRY_QUORUM as q

SRC = {
    "wave100_head": "0fb2caa805cebf29185d0b40c9f1bbd46199263b",
    "wave100_source_commit": "c235f8f0682a98f9d5777df12ef97dce8ca0560d",
    "wave100_tool_blob": "9fc2dc55c2d3973010b1804ad766cc632b89fa1f",
    "wave100_selftest_blob": "12491f9996bd7bada33ea742dacbb186dfd037c8",
    "verifier_pr": 25,
    "verifier_head": "100e45fb18f7cfc52663af3ad53753eeab4c8365",
    "verifier_evidence_blob": "246138d4a3a1e8757ef1044e4e7a0928536870f5",
}


def _rows(service: dict) -> list[dict]:
    return m._records_by_seq(service)


def verify_remote_authority_history(service: dict, registry_store: dict) -> dict | None:
    """Require retained remote authority chronology to advance exactly one epoch per record.

    Wave 99 already validates content seals, record sequence continuity, and record-hash predecessor
    linkage when a service participates in quorum. Wave 100 adds monotonic registry lineage. This
    layer adds the missing semantic maximum: a later remote record cannot endorse an equal, older,
    or skipped authority epoch through the ordinary record chain.
    """
    m.verify_remote_registry_history(service, registry_store)
    rows = _rows(service)
    if not rows:
        return None

    for i, rec in enumerate(rows):
        epoch = rec.get("authority_epoch")
        if not isinstance(epoch, int) or epoch < 1:
            raise ValueError("remote authority epoch invalid")
        if i == 0:
            if epoch != 1:
                raise ValueError("remote authority history must start at epoch 1")
            continue
        prev = rows[i - 1]
        if epoch != prev["authority_epoch"] + 1:
            raise ValueError("remote authority epoch discontinuity")
    return deepcopy(rows[-1])


def _head_and_previous(service: dict) -> tuple[dict | None, dict | None]:
    rows = _rows(service)
    if not rows:
        return None, None
    return deepcopy(rows[-1]), (None if len(rows) == 1 else deepcopy(rows[-2]))


def _current_local_parts(rt: dict, st: dict, boot: dict):
    status, link, cp = q.current_local(rt, st, boot)
    return status, link, cp


def _direct_current_crossbind(rt: dict, st: dict, boot: dict, service: dict) -> bool:
    """Cross-bind a current remote head to the exact local predecessor authority/checkpoint."""
    status, link, cp = _current_local_parts(rt, st, boot)
    if status == "GENESIS":
        head, _ = _head_and_previous(service)
        return head is None
    if status != "LOCAL_OK":
        return False

    head, prev = _head_and_previous(service)
    if head is None:
        return False
    if (
        head.get("authority_epoch") != link.get("epoch")
        or head.get("authority_sha") != link.get("authority_sha")
        or head.get("checkpoint_sha") != cp.get("checkpoint_sha")
        or head.get("registry_sha") != rt.get("remote_registry_sha")
    ):
        return True

    if prev is None:
        return (
            link.get("epoch") == 1
            and link.get("predecessor_authority_sha") is None
            and cp.get("predecessor_checkpoint_sha") is None
        )
    return (
        link.get("predecessor_authority_sha") == prev.get("authority_sha")
        and cp.get("predecessor_checkpoint_sha") == prev.get("checkpoint_sha")
        and link.get("epoch") == prev.get("authority_epoch") + 1
    )


def _invalid_history_slots(rt: dict, st: dict, boot: dict, services: dict,
                           registry_store: dict) -> list[str]:
    bad = []
    for slot in q.REMOTE_IDS:
        svc = services.get(slot)
        if svc is None or not svc.get("online"):
            continue
        try:
            verify_remote_authority_history(svc, registry_store)
            if not _direct_current_crossbind(rt, st, boot, svc):
                raise ValueError("remote/local predecessor cross-bind mismatch")
        except Exception:
            bad.append(slot)
    return bad


def authority(rt: dict, st: dict, boot: dict, services: dict, registry_store: dict) -> str:
    """Quarantine invalid retained histories, then require Wave 100's exact 2-of-3 quorum."""
    bad = _invalid_history_slots(rt, st, boot, services, registry_store)
    if not bad:
        return m.authority(rt, st, boot, services, registry_store)

    sanitized = dict(services)
    for slot in bad:
        svc = services.get(slot)
        if svc is not None:
            replacement = dict(svc)
            replacement["online"] = False
            sanitized[slot] = replacement

    verdict = m.authority(rt, st, boot, sanitized, registry_store)
    if verdict.startswith("AUTHORITATIVE"):
        return verdict + "|QUARANTINED=" + ",".join(sorted(bad))
    return "HOLD_REMOTE_AUTHORITY_LINEAGE_QUORUM"


def _publish_precheck(rt: dict, st: dict, boot: dict, service: dict,
                      registry_store: dict) -> str | None:
    try:
        verify_remote_authority_history(service, registry_store)
    except Exception:
        return "REMOTE_AUTHORITY_HISTORY_HOLD"

    status, link, cp = _current_local_parts(rt, st, boot)
    if status != "LOCAL_OK":
        return "LOCAL_HOLD"
    head, prev = _head_and_previous(service)
    if head is None:
        if link.get("epoch") != 1 or link.get("predecessor_authority_sha") is not None \
                or cp.get("predecessor_checkpoint_sha") is not None:
            return "REMOTE_AUTHORITY_PREDECESSOR_HOLD"
        return None

    if link.get("epoch") != head.get("authority_epoch") + 1:
        return "REMOTE_AUTHORITY_EPOCH_HOLD"
    if link.get("predecessor_authority_sha") != head.get("authority_sha"):
        return "REMOTE_AUTHORITY_PREDECESSOR_HOLD"
    if cp.get("predecessor_checkpoint_sha") != head.get("checkpoint_sha"):
        return "REMOTE_CHECKPOINT_PREDECESSOR_HOLD"
    return None


def publish(rt: dict, st: dict, boot: dict, services: dict, tokens: dict,
            registry_store: dict, slot: str) -> str:
    if slot not in q.REMOTE_IDS or slot not in services:
        return "REMOTE_IDENTITY_HOLD"
    hold = _publish_precheck(rt, st, boot, services[slot], registry_store)
    if hold is not None:
        return hold
    result = m.publish(rt, st, boot, services, tokens, registry_store, slot)
    if result in ("APPENDED", "ALREADY_CURRENT"):
        try:
            verify_remote_authority_history(services[slot], registry_store)
            if not _direct_current_crossbind(rt, st, boot, services[slot]):
                return "REMOTE_LOCAL_CROSSBIND_HOLD"
        except Exception:
            return "REMOTE_AUTHORITY_LINEAGE_HOLD"
    return result


def prepare(rt: dict, st: dict, priv: dict, boot: dict, services: dict,
            registry_store: dict, transition_store: dict,
            target_app_state_sha: str | None = None,
            target_registry_sha: str | None = None) -> tuple:
    if not authority(rt, st, boot, services, registry_store).startswith("AUTHORITATIVE"):
        raise ValueError("predecessor HOLD")
    return m.prepare(
        rt, st, priv, boot, services, registry_store, transition_store,
        target_app_state_sha=target_app_state_sha,
        target_registry_sha=target_registry_sha,
    )


def commit(rt: dict, st: dict, boot: dict, registry_store: dict, transition_store: dict,
           link_sha: str, transition_sha: str, n: int | None = None) -> str:
    return m.commit(rt, st, boot, registry_store, transition_store, link_sha, transition_sha, n)


def advance_all(st, priv, boot, rt, services, tokens, registry_store, transition_store,
                app_label: str) -> tuple:
    import hashlib
    app = hashlib.sha256(app_label.encode()).hexdigest()
    cp, use, link, tr_sha = prepare(
        rt, st, priv, boot, services, registry_store, transition_store, app
    )
    if commit(rt, st, boot, registry_store, transition_store, link["authority_sha"], tr_sha) != "COMMITTED":
        raise RuntimeError("local commit failed")
    for slot in q.REMOTE_IDS:
        if publish(rt, st, boot, services, tokens, registry_store, slot) not in ("APPENDED", "ALREADY_CURRENT"):
            raise RuntimeError(f"remote publish failed: {slot}")
    if not authority(rt, st, boot, services, registry_store).startswith("AUTHORITATIVE"):
        raise RuntimeError("authority failed")
    return cp, use, link, tr_sha


def build_depth(depth: int):
    st, priv, boot, rt, services, tokens, registry_store = q.fixture()
    transition_store = {}
    for i in range(depth):
        advance_all(
            st, priv, boot, rt, services, tokens, registry_store, transition_store,
            f"wave101-state-{i}",
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
        "schema": "axm.flowing_compute.wave101.protocol-smoke/v1",
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
