from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve()
MODULE_PATH = HERE.parents[1] / "tools" / "AXM_FLOWING_COMPUTE_RECEIPT_STORE.py"
spec = importlib.util.spec_from_file_location("wave81", MODULE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load Wave 81 module")
w81 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w81)


def result(name: str, passed: bool, detail: dict) -> dict:
    return {"name": name, "status": "BOUNDARY_REPRODUCED" if passed else "NOT_REPRODUCED", "detail": detail}


def main() -> dict:
    receipt = w81.wave79()
    w81.validate_receipt(receipt)

    with tempfile.TemporaryDirectory(prefix="axm-wave81-verifier-") as td:
        root = Path(td) / "store"
        receipt_id = w81.put_receipt(root, receipt)
        ref = {
            receipt["contract_id"]: {
                "receipt_sha256": receipt_id,
                "sequence": 1,
                "predecessor_state_sha256": receipt["predecessor_state_sha256"],
            }
        }

        good = w81.checkpoint(
            "1b93525216e04d20e4b5556f8ada44aeefcbb8168b33c9d01c723dfcc6117c58",
            1,
            ref,
            "verifier baseline",
        )
        good_id = w81.put_checkpoint(root, good)
        good_retention = w81.retention([good_id], "verifier baseline retention")
        baseline = w81.recover(root, good_retention)

        # Counterexample 1: constructor invariant is not re-enforced by validator/recovery.
        # The constructor requires every receipt ref sequence == checkpoint sequence.
        # Rehash a checkpoint whose outer sequence is changed while the receipt ref stays at 1.
        split = copy.deepcopy(good)
        split["sequence"] = 999
        split.pop("checkpoint_sha256", None)
        split["checkpoint_sha256"] = w81.digest(split)
        split_id = w81.put_checkpoint(root, split)
        split_retention = w81.retention([split_id], "verifier sequence-split retention")
        split_recovery = w81.recover(root, split_retention)
        observed = split_recovery["reachable_receipts"][receipt_id][0]
        sequence_split_passed = observed["sequence"] == 999 and receipt["sequence"] == 1

        # Counterexample 2: retention() rejects an empty root set, but validate_retention()
        # accepts the same shape after it is rehashed. GC then treats every receipt as unreachable.
        empty = copy.deepcopy(good_retention)
        empty["retained_checkpoints"] = []
        empty.pop("retention_sha256", None)
        empty["retention_sha256"] = w81.digest(empty)
        w81.validate_retention(empty)
        empty_recovery = w81.recover(root, empty)
        empty_candidates = sorted(w81.candidates(root, empty))

        deletion_root = Path(td) / "deletion-store"
        w81.put_receipt(deletion_root, receipt)
        w81.put_checkpoint(deletion_root, good)
        before_delete = receipt_id in w81.keys(deletion_root)
        w81.delete_if_unreachable(deletion_root, empty, receipt_id)
        after_delete = receipt_id in w81.keys(deletion_root)
        empty_retention_passed = (
            empty_recovery["retained_checkpoint_count"] == 0
            and receipt_id in empty_candidates
            and before_delete
            and not after_delete
        )

        return {
            "schema": "axm.flowing-compute-independent-verifier-wave81/v0.1",
            "status": "BOUNDARIES_REPRODUCED" if sequence_split_passed and empty_retention_passed else "INCOMPLETE",
            "builder_module": str(MODULE_PATH.relative_to(HERE.parents[1])),
            "baseline_recovery": baseline,
            "tests": [
                result(
                    "checkpoint_sequence_constructor_validator_split",
                    sequence_split_passed,
                    {
                        "checkpoint_sequence": 999,
                        "receipt_ref_sequence": 1,
                        "receipt_body_sequence": receipt["sequence"],
                        "recovery_reported_sequence": observed["sequence"],
                        "checkpoint_accepted_by_put_checkpoint": True,
                        "recovery_accepted": True,
                    },
                ),
                result(
                    "empty_retention_validator_gc_split",
                    empty_retention_passed,
                    {
                        "retention_constructor_would_reject_empty_roots": True,
                        "validate_retention_accepted_rehashed_empty_roots": True,
                        "recovered_checkpoint_count": empty_recovery["retained_checkpoint_count"],
                        "receipt_became_gc_candidate": receipt_id in empty_candidates,
                        "delete_if_unreachable_removed_receipt": before_delete and not after_delete,
                    },
                ),
            ],
            "benchmark_boundary": {
                "wave81_self_test_loop": "1000 recover(root, manifest) calls in one process",
                "interpretation": "useful warm filesystem/cache bookkeeping evidence; not a cold-process or cold-storage restart latency measurement",
            },
            "truth": {
                "not_a_sha256_break": True,
                "does_not_claim_actor_authentication": True,
                "does_not_invalidate_exact_receipt_body_recovery": True,
                "does_show_constructor_validator_semantic_drift": True,
                "does_show_gc_accepts_a_hash_valid_manifest_shape_constructor_itself_forbids": True,
            },
        }


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, sort_keys=True))
