#!/usr/bin/env python3
"""Independent adversarial verifier for AXM Flowing Compute Wave 113.

Target: the one-row crash-recovery path claims to recover the exact transition after the lower
Wave-110 commit is already durable but the Wave-111 provenance row is missing.

Adversarial question: is the exact transition identity actually rooted by the lower durable commit,
or is recovery merely choosing whichever single semantically compatible transition survives?

The reproducer keeps the committed authority/checkpoint/markers intact, removes only the genuine
unprovenanced trailing transition body, inserts a newly content-addressed semantically equivalent
transition with an extra ignored field, and asks Wave 113 to recover using that replacement SHA.
No hash collision, credential forgery, authority/checkpoint replacement, or marker rewrite is used.
"""
from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

import AXM_FLOWING_COMPUTE_RECOVERY_ATOMICITY as w
import AXM_FLOWING_COMPUTE_TRANSITION_PROVENANCE_LEDGER as w111
import AXM_FLOWING_COMPUTE_TRANSITION_EVIDENCE_GUARD as w110
import AXM_FLOWING_COMPUTE_REMOTE_REGISTRY_MONOTONICITY as w100
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w104

q = w.q
g = w.g

BUILDER_HEAD = "3a2a19a9317291da82bda34d7dbe5fbc5d2a4ac7"
BUILDER_TESTED_SOURCE = "dfedcab483ba6f798e0cd8e18a8a0c893397efd5"


def new_world():
    st, priv, boot, rt, services, tokens, rs = q.fixture()
    ts = {}
    cs = g.new_certificate_store()
    domain = w104.new_certificate_witness_domain()
    bs = {}
    w.adopt_genesis(rt, st, boot, services, rs, ts, cs, domain, bs)
    return st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs


def lower_commit_after_one_epoch():
    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = new_world()
    first = w.advance_all(
        st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs,
        "verifier-wave113-e1",
    )
    cp2, use2, link2, tr2, body2 = w.prepare(
        rt, st, priv, boot, services, rs, ts, cs, domain, bs,
        target_user_app_state_sha="73" * 32,
    )
    original_transition = deepcopy(ts[tr2])
    lower = w110.commit(rt, st, boot, rs, ts, link2["authority_sha"], tr2, bs)
    before = w.commit_status_state(st, boot, rt, rs, bs, ts)
    return {
        "st": st, "priv": priv, "boot": boot, "rt": rt,
        "services": services, "tokens": tokens, "rs": rs, "ts": ts,
        "cs": cs, "domain": domain, "bs": bs,
        "first": first, "cp2": cp2, "use2": use2, "link2": link2,
        "tr2": tr2, "body2": body2, "original_transition": original_transition,
        "lower": lower, "before": before,
    }


def replacement_transition(original: dict, label: str) -> dict:
    replacement = deepcopy(original)
    # Wave-100 transition sealing permits additional fields. The later semantic validators inspect
    # the known transition semantics but do not reject this unknown field or require an exact schema
    # field set. Therefore this changes the content-addressed identity while preserving all checked
    # authority/checkpoint/state/registry semantics.
    replacement["verifier_replacement_nonce"] = label
    replacement["transition_sha"] = ""
    return w100._seal(replacement, "transition_sha")


def baseline_genuine_recovery() -> dict:
    x = lower_commit_after_one_epoch()
    result = w.commit(
        x["rt"], x["st"], x["boot"], x["rs"], x["ts"],
        x["link2"]["authority_sha"], x["tr2"], x["bs"],
    )
    after = w.commit_status_state(x["st"], x["boot"], x["rt"], x["rs"], x["bs"], x["ts"])
    return {
        "lower_commit": x["lower"],
        "status_before": x["before"].get("status"),
        "recovery_result": result,
        "status_after": after.get("status"),
        "ok": (
            x["lower"] == "COMMITTED"
            and x["before"].get("status") == w.HISTORY_INCOMPLETE
            and result == "COMMITTED_RECOVERED_PROVENANCE_ATOMIC"
            and after.get("status") == w.HISTORY_VALID
        ),
    }


def duplicate_survivor_control() -> dict:
    x = lower_commit_after_one_epoch()
    replacement = replacement_transition(x["original_transition"], "duplicate-control")
    replacement_sha = w100.put_transition(x["ts"], replacement)
    state = w.commit_status_state(x["st"], x["boot"], x["rt"], x["rs"], x["bs"], x["ts"])
    rows = w111._provenance_rows(x["st"])
    return {
        "original_transition_sha": x["tr2"],
        "replacement_transition_sha": replacement_sha,
        "different_identity": replacement_sha != x["tr2"],
        "status_with_both_retained": state.get("status"),
        "provenance_rows": len(rows or []),
        "ok": replacement_sha != x["tr2"] and state.get("status") != w.HISTORY_VALID,
    }


def substitution_attack() -> dict:
    x = lower_commit_after_one_epoch()
    original_sha = x["tr2"]
    original = deepcopy(x["original_transition"])

    # Narrow adversarial mutation: remove only the genuine *unprovenanced trailing transition body*.
    # The lower durable commit, authority/checkpoint/use bodies and Wave-108 commit/high-water markers
    # remain untouched.
    del x["ts"][original_sha]
    replacement = replacement_transition(original, "substitute-after-lower-commit")
    replacement_sha = w100.put_transition(x["ts"], replacement)

    pre_retry = w.commit_status_state(
        x["st"], x["boot"], x["rt"], x["rs"], x["bs"], x["ts"]
    )
    result = None
    error = None
    try:
        result = w.commit(
            x["rt"], x["st"], x["boot"], x["rs"], x["ts"],
            x["link2"]["authority_sha"], replacement_sha, x["bs"],
        )
    except Exception as exc:
        error = f"{type(exc).__name__}:{exc}"

    post_retry = w.commit_status_state(
        x["st"], x["boot"], x["rt"], x["rs"], x["bs"], x["ts"]
    )
    rows = w111._provenance_rows(x["st"])
    target_rows = [
        row for _sha, row in (rows or [])
        if row.get("authority_sha") == x["link2"]["authority_sha"]
    ]
    bound_transition = target_rows[0].get("transition_sha") if len(target_rows) == 1 else None

    final_authority = None
    publish_results = []
    certify_result = None
    if post_retry.get("status") == w.HISTORY_VALID:
        for slot in q.REMOTE_IDS:
            publish_results.append(w.publish(
                x["rt"], x["st"], x["boot"], x["services"], x["tokens"], x["rs"], slot
            ))
        certify_result = w.certify_and_sync(
            x["rt"], x["st"], x["boot"], x["services"], x["rs"],
            x["cs"], x["domain"],
        )[0]
        final_authority = w.authority(
            x["rt"], x["st"], x["boot"], x["services"], x["rs"], x["ts"],
            x["cs"], x["domain"], x["bs"],
        )

    reproduced = (
        x["lower"] == "COMMITTED"
        and replacement_sha != original_sha
        and original_sha not in x["ts"]
        and pre_retry.get("status") == w.HISTORY_INCOMPLETE
        and result == "COMMITTED_RECOVERED_PROVENANCE_ATOMIC"
        and error is None
        and post_retry.get("status") == w.HISTORY_VALID
        and bound_transition == replacement_sha
        and isinstance(final_authority, str)
        and final_authority.startswith("AUTHORITATIVE")
    )

    return {
        "lower_commit": x["lower"],
        "original_transition_sha": original_sha,
        "replacement_transition_sha": replacement_sha,
        "replacement_differs_only_by_unchecked_extra_field": all(
            replacement.get(k) == original.get(k)
            for k in original if k != "transition_sha"
        ) and replacement.get("verifier_replacement_nonce") == "substitute-after-lower-commit",
        "original_transition_removed": original_sha not in x["ts"],
        "committed_authority_sha": x["link2"]["authority_sha"],
        "status_before_retry": pre_retry.get("status"),
        "recovery_result": result,
        "recovery_error": error,
        "status_after_retry": post_retry.get("status"),
        "provenance_bound_transition_sha": bound_transition,
        "publish_results": publish_results,
        "certify_result": certify_result,
        "final_authority": final_authority,
        "reproduced": reproduced,
    }


def run() -> dict:
    baseline = baseline_genuine_recovery()
    duplicate = duplicate_survivor_control()
    attack = substitution_attack()
    verdict = (
        "FAIL_RECOVERY_BINDS_SUBSTITUTED_TRANSITION_IDENTITY"
        if baseline["ok"] and duplicate["ok"] and attack["reproduced"]
        else "NOT_REPRODUCED"
    )
    return {
        "schema": "axm.flowing-compute.verifier.wave113.recovery-transition-identity/v1",
        "builder_head": BUILDER_HEAD,
        "builder_tested_source": BUILDER_TESTED_SOURCE,
        "baseline_genuine_recovery": baseline,
        "duplicate_survivor_control": duplicate,
        "substitution_attack": attack,
        "truth_boundary": {
            "stale_authority_takeover_claim": False,
            "hash_collision_used": False,
            "credential_forgery_used": False,
            "authority_or_checkpoint_rewrite_used": False,
            "wave108_marker_rewrite_used": False,
            "performance_or_energy_claim": False,
            "retained_incremental_dormant_compute_claim": False,
            "os_process_or_provider_independence_claim": False,
            "scope": "recovery provenance identity / exact-transition claim in the documented one-row crash window",
        },
        "verdict": verdict,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out")
    args = parser.parse_args()
    report = run()
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    # A green verifier job means the adversarial failure reproduced exactly and the positive control
    # still passed; the verdict string itself remains prominently FAIL_... .
    return 0 if report["verdict"] == "FAIL_RECOVERY_BINDS_SUBSTITUTED_TRANSITION_IDENTITY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
