from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import AXM_FLOWING_COMPUTE_MULTI_ANCHOR_WITNESS as w86


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="axm-wave86-verifier-") as tmp:
        root = Path(tmp)
        pointer = root / "primary" / "current.json"
        pointer.parent.mkdir(parents=True)
        store = root / "primary" / "objects"
        paths = w86.witness_paths(root / "witnesses")

        # Establish the exact three-witness Wave86 genesis and preserve it.
        a0 = w86.initialize(pointer, store, paths)
        genesis = root / "genesis"
        w86._snapshot_all(pointer, store, paths, genesis)

        # Move all three witnesses forward twice, matching the Wave86 self-test shape.
        first = w86.multi_anchor_cas(
            pointer_path=pointer,
            pointer_store_path=store,
            paths=paths,
            expected_pointer=a0,
            candidate_retention_sha256=w86.w84.W83_DROP_RETENTION_SHA,
            note="verifier forward",
        )
        assert first["status"] == "COMMITTED", first
        b1 = w86.w84.read_current(pointer, store)
        second = w86.multi_anchor_cas(
            pointer_path=pointer,
            pointer_store_path=store,
            paths=paths,
            expected_pointer=b1,
            candidate_retention_sha256=w86.w84.W81_RETENTION_SHA,
            selection_kind="ROLLBACK",
            note="verifier intentional rollback",
        )
        assert second["status"] == "COMMITTED", second
        assert w86.w84.read_current(pointer, store)["commit_epoch"] == 2

        # Rewind the primary plus A/B to genesis while leaving C at the newer epoch.
        # With the original configured set, Wave86 correctly detects disagreement.
        w86._restore_primary(genesis, pointer, store)
        w86._restore_dir(genesis / "witness-a", paths["witness-a"])
        w86._restore_dir(genesis / "witness-b", paths["witness-b"])
        full_status = w86.witness_status(pointer, store, paths)
        assert full_status["status"] == "WITNESS_DIVERGENCE_HOLD", full_status

        # Counterexample: the witness set is caller-supplied and is not bound to the
        # primary pointer, anchor history, or a persisted configuration identity.
        # Drop the surviving newer witness from the argument entirely.
        one_witness = {"witness-a": paths["witness-a"]}
        reduced_status = w86.witness_status(pointer, store, one_witness)
        assert reduced_status["status"] == "CONSISTENT", reduced_status
        assert reduced_status["witness_count"] == 1, reduced_status

        # The same reduced set is accepted by the actual commit API. multi_anchor_cas
        # does not re-enforce initialize()'s >=2 check, so a single rewound witness can
        # authorize a new commit while the omitted witness-c still preserves newer
        # conflicting history.
        rewound = w86.w84.read_current(pointer, store)
        bypass = w86.multi_anchor_cas(
            pointer_path=pointer,
            pointer_store_path=store,
            paths=one_witness,
            expected_pointer=rewound,
            candidate_retention_sha256=w86.w84.W83_DROP_RETENTION_SHA,
            note="verifier witness-set shrink bypass",
        )
        assert bypass["status"] == "COMMITTED", bypass
        assert bypass["witness_count"] == 1, bypass

        # Restoring the original configured set still exposes disagreement; the point
        # is that the commit already happened because configuration membership itself
        # was outside the hashed/retained contract.
        full_after = w86.witness_status(pointer, store, paths)
        assert full_after["status"] == "WITNESS_DIVERGENCE_HOLD", full_after

        print(json.dumps({
            "full_set_before": full_status["status"],
            "reduced_set_before": reduced_status["status"],
            "reduced_witness_count": reduced_status["witness_count"],
            "commit_with_one_witness": bypass["status"],
            "commit_witness_count": bypass["witness_count"],
            "full_set_after": full_after["status"],
            "finding": "witness membership is trusted caller input; set shrink can bypass a surviving newer witness",
        }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
