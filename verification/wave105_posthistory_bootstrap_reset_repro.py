#!/usr/bin/env python3
"""Independent verifier repro for Wave 105.

This does not modify builder state. It demonstrates that after a genuinely accepted
Wave-105 epoch, the public genesis-adoption path can be re-entered if the caller
supplies a stale genesis runtime view, stale genesis remote-service snapshots, and
a fresh empty certificate store/domain. The original newer remotes, certificate
witnesses, certificate store, signed checkpoint bodies, and bound root remain intact.
"""
from __future__ import annotations

import json
import os
import sys
from copy import deepcopy

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_ROOT_BINDING as w
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w104


g = w.g
q = w.q


def run() -> dict:
    st, priv, boot, rt, services, tokens, rs = q.fixture()
    rt_genesis = deepcopy(rt)
    services_genesis = deepcopy(services)

    cs = g.new_certificate_store()
    original_domain = w104.new_certificate_witness_domain()
    bs = {}

    original_root0 = w.adopt_genesis(
        rt, st, boot, services, rs, cs, original_domain, bs
    )
    w.advance_all(
        st, priv, boot, rt, services, tokens, rs, {}, cs,
        original_domain, bs, "verifier-wave105-accepted-epoch1"
    )
    original_authority = w.authority(
        rt, st, boot, services, rs, cs, original_domain, bs
    )
    if not original_authority.startswith("AUTHORITATIVE"):
        raise AssertionError(f"setup failed: {original_authority}")

    # Preserve proof that accepted history and the original bound domain still exist.
    original_domain_heads_before = {
        slot: sorted(rec["certificate_seq"] for rec in ep.records.values())
        for slot, ep in original_domain._endpoints.items()
    }
    original_certificate_head = cs.get("head")
    signed_checkpoint_count = len(st.get("C", {}))
    authority_body_count = len(st.get("L", {}))

    # Attack: do NOT roll back the original objects. Supply old caller-side snapshots
    # plus a fresh empty certificate store and a new legitimate witness domain.
    attacked_rt = deepcopy(rt_genesis)
    attacked_services = deepcopy(services_genesis)
    attacked_cs = g.new_certificate_store()
    attacked_bs = deepcopy(bs)
    replacement_domain = w104.new_certificate_witness_domain()

    replacement_root0 = w.adopt_genesis(
        attacked_rt, st, boot, attacked_services, rs, attacked_cs,
        replacement_domain, attacked_bs
    )
    attacked_authority = w.authority(
        attacked_rt, st, boot, attacked_services, rs, attacked_cs,
        replacement_domain, attacked_bs
    )

    # The original accepted world must remain intact and independently authoritative.
    original_after = w.authority(
        rt, st, boot, services, rs, cs, original_domain, bs
    )
    original_domain_heads_after = {
        slot: sorted(rec["certificate_seq"] for rec in ep.records.values())
        for slot, ep in original_domain._endpoints.items()
    }

    failure = (
        replacement_domain.registry_sha != original_domain.registry_sha
        and replacement_root0 != original_root0
        and attacked_authority == "AUTHORITATIVE_GENESIS_MODELED"
        and original_after.startswith("AUTHORITATIVE")
        and original_certificate_head is not None
        and cs.get("head") == original_certificate_head
        and original_domain_heads_after == original_domain_heads_before
        and signed_checkpoint_count > 0
        and authority_body_count > 0
    )

    report = {
        "schema": "axm.flowing_compute.verifier.wave105.posthistory_bootstrap_reset/v1",
        "builder_head": "5c683032e0834e8a57e1bb780f624eb1cb312d3c",
        "wave105_tool_blob": "1e0e543c57f880c3e631619fa1859c24ace5ff79",
        "wave105_selftest_blob": "c6d39f469e98590823af3a576c4efbb18957d00b",
        "original": {
            "authority_before": original_authority,
            "authority_after": original_after,
            "certificate_store_head": original_certificate_head,
            "certificate_witness_registry_sha": original_domain.registry_sha,
            "root_binding_sha": original_root0,
            "endpoint_certificate_sequences": original_domain_heads_after,
            "signed_checkpoint_count": signed_checkpoint_count,
            "authority_body_count": authority_body_count,
        },
        "attack": {
            "replacement_certificate_store_head": attacked_cs.get("head"),
            "replacement_certificate_witness_registry_sha": replacement_domain.registry_sha,
            "replacement_root_binding_sha": replacement_root0,
            "authority": attacked_authority,
            "uses_fresh_old_credentials": False,
            "modifies_original_newer_remotes": False,
            "modifies_original_certificate_witnesses": False,
            "deletes_original_certificate_store": False,
            "deletes_signed_checkpoint_bodies": False,
            "requires_hash_forge": False,
        },
        "verdict": (
            "FAIL_POSTHISTORY_BOOTSTRAP_REENTRY_CREATES_PARALLEL_AUTHORITATIVE_GENESIS"
            if failure else
            "NO_REPRO_POSTHISTORY_BOOTSTRAP_REENTRY"
        ),
    }
    return report


def main() -> None:
    report = run()
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["verdict"].startswith("FAIL_"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
