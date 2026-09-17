#!/usr/bin/env python3
"""Wave 112 CI self-test wrapper.

The first Wave-112 CI run correctly preserved a failed harness attempt: its synthetic marker-chain
instrumentation replaced Wave-108 ``_marker_chains`` with a one-positional-argument wrapper, while
Wave-108 legitimately also calls that function with the keyword-only ``allow_missing`` argument.
That made the scaling probe itself create ``INCOMPLETE_OR_CORRUPT`` before the implementation under
test reached the indexed-marker validator.

Keep that failed run and original self-test unchanged as evidence. This wrapper repairs only the
instrumentation signature, then executes the exact same Wave-112 control set. No implementation
behavior is patched here.
"""
from __future__ import annotations

import argparse
import json

import AXM_FLOWING_COMPUTE_RECOVERABLE_TRANSITION_PROVENANCE_SELFTEST as base

w = base.w
w108 = base.w108


def marker_scaling_case(depth: int) -> dict:
    st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs = base.new_world()
    for i in range(1, depth + 1):
        w.advance_all(
            st, priv, boot, rt, services, tokens, rs, ts, cs, domain, bs,
            f"wave112-synthetic-depth-{depth}-epoch-{i}",
        )

    calls = {"marker_chains": 0}
    original = w108._marker_chains

    def counted(state, *args, **kwargs):
        calls["marker_chains"] += 1
        return original(state, *args, **kwargs)

    w108._marker_chains = counted
    try:
        state = w.commit_status_state(st, boot, rt, rs, bs, ts)
    finally:
        w108._marker_chains = original
    return {
        "depth": depth,
        "status": state.get("status"),
        "reason": state.get("reason"),
        "marker_chains_calls": calls["marker_chains"],
        "structural_only": True,
    }


base.marker_scaling_case = marker_scaling_case


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out")
    args = parser.parse_args()
    report = base.run()
    report["ci_harness_note"] = (
        "original Wave-112 scaling monkeypatch omitted Wave-108 allow_missing keyword; "
        "this wrapper repairs only that instrumentation signature"
    )
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
