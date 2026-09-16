#!/usr/bin/env python3
"""Independent exact-API adversarial reproducer for Flowing Compute Wave 96.

Imports the unchanged Wave 96 builder module and shows that its Lamport
"private" material is publicly reproducible from root/generation labels in the
published source. The verifier deliberately avoids Python assert for required
side effects so the same reproduction survives `python -O`.
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


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def regen_private(st, pub_sha: str):
    """Recreate supposed Lamport private material using only published metadata."""
    pub = w.get(st["PUB"], pub_sha, "pub_sha")
    rebuilt_pub, private_rows = w.lpair(
        pub["root"], pub["generation"], pub["predecessor_pub_sha"]
    )
    require(rebuilt_pub["pub_sha"] == pub_sha, "reconstructed public key mismatch")
    return private_rows


def forge_sibling_checkpoint(st, legit_checkpoint):
    """Reuse the exact already-used signers without the builder's private store."""
    signers = deepcopy(legit_checkpoint["signer_keys"])
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

    cp1, _ = w.prep(rt, st, ext, bootstrap, private_store, used, [0])
    w.verifycp(cp1, st, bootstrap)
    require(w.applycp(rt, cp1) == "COMMITTED", "checkpoint 1 local commit failed")
    require(w.extpub(ext, cp1) == "APPENDED", "checkpoint 1 external append failed")
    require(
        w.auth(rt, st, ext, bootstrap) == "AUTHORITATIVE_PUBLIC_CHECKPOINTED",
        "checkpoint 1 authority control failed",
    )

    target = w.trans(rt, st, ext, bootstrap, w.T("verifier-registry-1"), "truth")
    require(w.applyt(rt, target) == "COMMITTED", "normal transition failed")
    legit2, _ = w.prep(rt, st, ext, bootstrap, private_store, used, [0])
    w.verifycp(legit2, st, bootstrap, cp1)
    reused_signers = set(legit2["signer_keys"].values())
    require(reused_signers <= used, "normal prep did not mark Lamport signers used")

    for sha in reused_signers:
        private_store.pop(sha, None)
    require(
        all(sha not in private_store for sha in reused_signers),
        "retained private material was not deleted",
    )

    forged2, poisoned_next = forge_sibling_checkpoint(st, legit2)
    require(
        forged2["checkpoint_sha"] != legit2["checkpoint_sha"],
        "forged sibling was not distinct",
    )
    require(
        forged2["signer_keys"] == legit2["signer_keys"],
        "forged sibling did not reuse the exact OTS signer set",
    )
    require(
        all(sha not in st["PUB"] for sha in poisoned_next.values()),
        "poisoned successor key unexpectedly exists",
    )

    w.verifycp(forged2, st, bootstrap, cp1)
    require(w.applycp(rt, forged2) == "COMMITTED", "forged checkpoint was not committed")
    require(w.extpub(ext, forged2) == "APPENDED", "forged checkpoint was not externally appended")
    authority = w.auth(rt, st, ext, bootstrap)
    require(
        authority == "AUTHORITATIVE_PUBLIC_CHECKPOINTED",
        f"forged checkpoint did not become authoritative: {authority}",
    )

    failed_next = None
    try:
        w.prep(rt, st, ext, bootstrap, private_store, used, [0])
    except Exception as exc:
        failed_next = str(exc)
    require(
        failed_next is not None and "pub_sha body missing" in failed_next,
        f"expected poisoned successor failure, got: {failed_next}",
    )

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
