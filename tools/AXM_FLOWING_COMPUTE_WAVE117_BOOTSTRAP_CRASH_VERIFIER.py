#!/usr/bin/env python3
"""Independent Wave 117 adversarial verifier: genesis bootstrap crash/retry atomicity.

This verifier does not rewrite builder evidence or promote CANON. It starts from the
exact Wave 117 builder head and simulates crashes at two durable-write boundaries
inside Wave 117 ``adopt_genesis``:

1. after the checkpoint-anchored outcome root is persisted;
2. after both the root and application envelope are persisted;

In both cases the lower Wave 116 genesis adoption has not happened. A restart restores
the pre-call runtime object and retries the exact public Wave 117 ``adopt_genesis``.
The expected safety property for a recoverable bootstrap is that an exact retry can
resume/reconcile the partial bootstrap (or expose a dedicated recovery path) without
mistaking Wave 117's own pre-genesis records for a completed genesis.
"""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

import AXM_FLOWING_COMPUTE_OUTCOME_AUTHORITY_ROOT_ANCHOR as w

VERDICT = "FAIL_WAVE117_BOOTSTRAP_CRASH_HAS_NO_PUBLIC_RETRY_RECOVERY"
BUILDER_HEAD = "1c033d96e792c9f8532bf2355c9f1ec958da969a"


def fresh_world() -> dict:
    st, priv, boot, rt, services, tokens, rs = w.q.fixture()
    ts = {}
    cs = w.g.new_certificate_store()
    certificate_domain = w.w104.new_certificate_witness_domain()
    bs = {}
    outcome_domain = w.new_outcome_authority_domain()
    return {
        "st": st,
        "priv": priv,
        "boot": boot,
        "rt": rt,
        "services": services,
        "tokens": tokens,
        "rs": rs,
        "ts": ts,
        "cs": cs,
        "certificate_domain": certificate_domain,
        "bs": bs,
        "outcome_domain": outcome_domain,
    }


def public_adopt(e: dict) -> str:
    return w.adopt_genesis(
        e["rt"],
        e["st"],
        e["boot"],
        e["services"],
        e["rs"],
        e["ts"],
        e["cs"],
        e["certificate_domain"],
        e["bs"],
        e["outcome_domain"],
    )


def control_clean_adoption() -> dict:
    e = fresh_world()
    result = public_adopt(e)
    state = w.commit_status_state(
        e["st"], e["boot"], e["rt"], e["rs"], e["bs"], e["ts"], e["outcome_domain"]
    )
    return {
        "result": result,
        "history_status": state.get("status"),
        "wave117_root_count": len(e["st"].get(w.OUTCOME_ROOT_STORE, {})),
        "wave117_envelope_count": len(e["st"].get(w.ENVELOPE_STORE, {})),
        "lower_binding_present": w.w116.OUTCOME_BINDING in e["st"],
        "wave105_binding_count": len(e["bs"]),
    }


def simulate_bootstrap_crash(cut: str) -> dict:
    if cut not in {"after_root", "after_root_and_envelope"}:
        raise ValueError(cut)
    e = fresh_world()
    pre_crash_rt = deepcopy(e["rt"])
    original_app_state_sha = pre_crash_rt.get("app_state_sha")

    # Reproduce only Wave 117's durable prefix. The lower Wave 116 genesis adoption
    # deliberately does not run: the simulated process dies at this boundary.
    root_sha = w._put_root(e["st"], w._seal_root(e["outcome_domain"].authority_id))
    envelope_sha = None
    if cut == "after_root_and_envelope":
        envelope_sha = w._put_envelope(
            e["st"], w._seal_envelope(original_app_state_sha, root_sha)
        )

    # Model restart: do not grant the verifier any benefit from volatile in-memory
    # mutation. Only the records already written into the modeled durable state survive.
    e["rt"].clear()
    e["rt"].update(deepcopy(pre_crash_rt))

    before_retry = {
        "root_count": len(e["st"].get(w.OUTCOME_ROOT_STORE, {})),
        "envelope_count": len(e["st"].get(w.ENVELOPE_STORE, {})),
        "lower_binding_present": w.w116.OUTCOME_BINDING in e["st"],
        "wave105_binding_count": len(e["bs"]),
        "transition_count": len(e["ts"]),
    }

    retry_errors = []
    for _ in range(2):
        try:
            public_adopt(e)
        except Exception as exc:  # exact public retry is the object under test
            retry_errors.append(f"{type(exc).__name__}:{exc}")
        else:
            retry_errors.append(None)

    after_retry = {
        "root_count": len(e["st"].get(w.OUTCOME_ROOT_STORE, {})),
        "envelope_count": len(e["st"].get(w.ENVELOPE_STORE, {})),
        "lower_binding_present": w.w116.OUTCOME_BINDING in e["st"],
        "wave105_binding_count": len(e["bs"]),
        "transition_count": len(e["ts"]),
    }
    status = w.commit_status_state(
        e["st"], e["boot"], e["rt"], e["rs"], e["bs"], e["ts"], e["outcome_domain"]
    )

    blocked_exactly = (
        len(retry_errors) == 2
        and all(
            isinstance(err, str) and "wave117-root-anchor-state-already-present" in err
            for err in retry_errors
        )
    )
    lower_genesis_still_absent = (
        not after_retry["lower_binding_present"]
        and after_retry["wave105_binding_count"] == 0
        and after_retry["transition_count"] == 0
    )
    return {
        "cut": cut,
        "root_sha": root_sha,
        "envelope_sha": envelope_sha,
        "before_retry": before_retry,
        "retry_errors": retry_errors,
        "after_retry": after_retry,
        "post_retry_history_status": status.get("status"),
        "post_retry_history_reason": status.get("reason"),
        "exact_public_retry_blocked": blocked_exactly,
        "lower_genesis_still_absent": lower_genesis_still_absent,
        "failure_reproduced": blocked_exactly and lower_genesis_still_absent,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out")
    args = parser.parse_args()

    control = control_clean_adoption()
    cuts = [
        simulate_bootstrap_crash("after_root"),
        simulate_bootstrap_crash("after_root_and_envelope"),
    ]
    control_ok = (
        control["history_status"] in (w.HISTORY_NONE, w.HISTORY_VALID)
        and control["wave117_root_count"] == 1
        and control["wave117_envelope_count"] == 1
        and control["lower_binding_present"]
        and control["wave105_binding_count"] >= 1
    )
    failure_reproduced = control_ok and all(item["failure_reproduced"] for item in cuts)

    report = {
        "schema": "axm.flowing-compute.wave117.adversarial-bootstrap-crash/v1",
        "builder_head": BUILDER_HEAD,
        "verdict": VERDICT if failure_reproduced else "NOT_REPRODUCED",
        "control": control,
        "crash_cuts": cuts,
        "truth_boundary": {
            "stale_authority_accepted": False,
            "forgery_or_hash_collision_required": False,
            "lower_genesis_completed_before_crash": False,
            "runtime_state_presumed_durable": False,
            "same_process_modeled_durability_only": True,
            "claim": "public bootstrap retry/recovery liveness and evidence atomicity only",
        },
    }
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.json_out:
        path = Path(args.json_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    return 0 if failure_reproduced else 1


if __name__ == "__main__":
    raise SystemExit(main())
