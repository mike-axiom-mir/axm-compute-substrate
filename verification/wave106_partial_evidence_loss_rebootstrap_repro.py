#!/usr/bin/env python3
"""Independent adversarial reproducer for Wave 106.

This does not patch builder code. It shows that Wave 106's retained-authority detector
silently ignores an authority link when one referenced signer-use body is missing.
Deleting the Wave-106 lineage store plus only that one auxiliary body can therefore
reopen bootstrap under a saved genesis runtime/remotes and a fresh certificate domain,
while the signed authority-link and checkpoint bodies remain retained.
"""
from __future__ import annotations

import json
from copy import deepcopy

import AXM_FLOWING_COMPUTE_BOOTSTRAP_LINEAGE_CLOSURE as w
import AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY as w104


g = w.g
q = w.q


def run() -> dict:
    st, priv, boot, rt, services, tokens, registry_store = q.fixture()
    genesis_rt = deepcopy(rt)
    genesis_services = deepcopy(services)
    transition_store = {}
    certificate_store = g.new_certificate_store()
    domain = w104.new_certificate_witness_domain()
    binding_store = {}

    original_root = w.adopt_genesis(
        rt,
        st,
        boot,
        services,
        registry_store,
        certificate_store,
        domain,
        binding_store,
    )
    w.advance_all(
        st,
        priv,
        boot,
        rt,
        services,
        tokens,
        registry_store,
        transition_store,
        certificate_store,
        domain,
        binding_store,
        "wave106-verifier-accepted-epoch1",
    )

    original_verdict = w.authority(
        rt,
        st,
        boot,
        services,
        registry_store,
        certificate_store,
        domain,
        binding_store,
    )
    if not original_verdict.startswith("AUTHORITATIVE"):
        raise AssertionError(f"control accepted world not authoritative: {original_verdict}")

    adoption, closure = w._records(st, boot, registry_store, binding_store)
    status, link, checkpoint = q.current_local(rt, st, boot)
    if status != "LOCAL_OK" or adoption is None or closure is None:
        raise AssertionError("control epoch-1 accepted state incomplete")

    authority_sha = link["authority_sha"]
    checkpoint_sha = checkpoint["checkpoint_sha"]
    use_sha = link["use_sha"]

    # Control: lineage-store loss alone is correctly detected while all authority dependencies exist.
    missing_lineage_only = deepcopy(st)
    del missing_lineage_only[w.STORE_KEY]
    control_retained = w._retained_authority_evidence(missing_lineage_only, boot)
    control_verdict = w.authority(
        deepcopy(genesis_rt),
        missing_lineage_only,
        boot,
        deepcopy(genesis_services),
        registry_store,
        g.new_certificate_store(),
        w104.new_certificate_witness_domain(),
        {},
    )
    if authority_sha not in control_retained:
        raise AssertionError("control should still detect retained authority")
    if control_verdict != "HOLD_BOOTSTRAP_LINEAGE_MISSING_WITH_AUTHORITY_HISTORY":
        raise AssertionError(f"lineage-loss control unexpectedly changed: {control_verdict}")

    # Adversarial step: preserve the sealed authority link and signed checkpoint, but remove
    # the Wave-106 lineage records and one referenced signer-use body. The retained-history
    # scanner catches resolve() failure and silently continues, turning corruption into 'no history'.
    attacked_st = deepcopy(st)
    del attacked_st[w.STORE_KEY]
    del attacked_st["U"][use_sha]

    if authority_sha not in attacked_st.get("L", {}):
        raise AssertionError("attack accidentally removed authority link body")
    if checkpoint_sha not in attacked_st.get("C", {}):
        raise AssertionError("attack accidentally removed signed checkpoint body")
    if w._retained_authority_evidence(attacked_st, boot):
        raise AssertionError("expected retained-history scanner to drop unresolved authority link")

    attacked_rt = deepcopy(genesis_rt)
    attacked_services = deepcopy(genesis_services)
    attacked_certificate_store = g.new_certificate_store()
    attacked_domain = w104.new_certificate_witness_domain()
    attacked_binding_store = {}

    replacement_root = w.adopt_genesis(
        attacked_rt,
        attacked_st,
        boot,
        attacked_services,
        registry_store,
        attacked_certificate_store,
        attacked_domain,
        attacked_binding_store,
    )
    attacked_verdict = w.authority(
        attacked_rt,
        attacked_st,
        boot,
        attacked_services,
        registry_store,
        attacked_certificate_store,
        attacked_domain,
        attacked_binding_store,
    )

    result = {
        "schema": "axm.verifier.wave106.partial-evidence-loss-rebootstrap/v1",
        "builder_head": "eb8ac4d23a3399af82885afc435dae6de0aa28b6",
        "wave106_tested_source_commit": "652f3da1acd88e02f085cf1ace92c6bfb412e065",
        "wave106_tool_blob": "daaa9e33b3418138972701bac1cecca928378a17",
        "wave106_selftest_blob": "3da3ebd06bed5b756ca58d5b77ac9eb5de12bbc6",
        "control": {
            "accepted_world": original_verdict,
            "lineage_loss_only": control_verdict,
            "retained_authority_detected": control_retained,
        },
        "attack": {
            "deleted_lineage_store": True,
            "deleted_signer_use_sha": use_sha,
            "preserved_authority_link_sha": authority_sha,
            "preserved_checkpoint_sha": checkpoint_sha,
            "preserved_authority_link_count": len(attacked_st.get("L", {})),
            "preserved_checkpoint_count": len(attacked_st.get("C", {})),
            "retained_authority_detector_after_partial_loss": w._retained_authority_evidence(attacked_st, boot),
            "replacement_root_differs": replacement_root != original_root,
            "replacement_root": replacement_root,
            "verdict": attacked_verdict,
        },
        "verifier_verdict": "FAIL_PARTIAL_EVIDENCE_LOSS_REOPENS_BOOTSTRAP"
        if replacement_root != original_root and attacked_verdict == "AUTHORITATIVE_GENESIS_MODELED"
        else "NOT_REPRODUCED",
    }

    if result["verifier_verdict"] != "FAIL_PARTIAL_EVIDENCE_LOSS_REOPENS_BOOTSTRAP":
        raise AssertionError(json.dumps(result, indent=2, sort_keys=True))
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
