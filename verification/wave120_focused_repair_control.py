#!/usr/bin/env python3
"""Focused independent control for Wave 120's direct PR #44 repair."""
from __future__ import annotations

import argparse
import json

import AXM_FLOWING_COMPUTE_ROTATION_PREPARE_TRANSACTION as w
import AXM_FLOWING_COMPUTE_ROTATION_PREPARE_TRANSACTION_SELFTEST as t


def run() -> dict:
    result = t.failure_growth(w, 16, "verifier-wave120-focused-repair")
    survived = (
        result["scaling_mode"] == "full-public-authority-path"
        and result["errors_exact"]
        and result["root_growth"] == 0
        and result["envelope_growth"] == 0
        and result["orphan_compact_json_bytes"] == 0
        and result["transition_growth"] == 0
        and result["binding_growth"] == 0
        and result["authority_after"].startswith("AUTHORITATIVE")
    )
    report = {
        "schema": "axm.flowing-compute.verifier-wave120-focused-pr44-repair/v1",
        "builder_head": "f0d171e65fcc3d0618915bd7d9d79a4deabda7cb",
        "wave120_tool_blob": "cdf87ee52abb1c9381af38807cea73509ce9cd40",
        "attempts": 16,
        "result": result,
        "verdict": "BOUNDED_REPAIR_SURVIVES" if survived else "REPAIR_CONTROL_FAILED",
        "truth_boundary": "full public authority path; structural retained object/byte accounting only, not timing or energy",
    }
    if not survived:
        raise AssertionError(json.dumps(report, sort_keys=True))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out")
    args = parser.parse_args()
    report = run()
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")


if __name__ == "__main__":
    main()
