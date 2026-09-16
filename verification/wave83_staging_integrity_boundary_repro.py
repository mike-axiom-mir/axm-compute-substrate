from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from AXM_FLOWING_COMPUTE_RETENTION_AUTH_CAS import (  # noqa: E402
    C1,
    C3,
    ObjectStore,
    build_fixture,
    cas_commit,
    initialize_pointer,
    make_authorized_retention,
    read_pointer,
    rid,
    validate_authorized_retention,
)


def fail(fn):
    try:
        fn()
    except Exception as exc:  # deterministic verifier output
        return str(exc)
    raise AssertionError("unexpected success")


def main() -> dict:
    out = {}
    with tempfile.TemporaryDirectory(prefix="axm-wave83-verifier-") as td:
        base = Path(td)
        g0, store, _drop, _auth, _drop_candidate, keep_candidate = build_fixture(base)

        # Counterexample 1: staged candidate object is corrupted after staging.
        # cas_commit validates the in-memory candidate, then only checks store.has(hash).
        # It never reloads the staged candidate body by hash before pointer movement.
        staged_path = store.path / f"{keep_candidate['retention_sha256']}.json"
        staged_path.write_text('{"corrupted":true}')
        ptr = base / "current-corrupt-stage.json"
        initialize_pointer(ptr, g0)
        commit = cas_commit(
            pointer_path=ptr,
            expected_predecessor=g0,
            candidate=keep_candidate,
            store_path=store.path,
        )
        assert commit["status"] == "COMMITTED"
        assert read_pointer(ptr)["retention_sha256"] == keep_candidate["retention_sha256"]
        loaded = store.get(keep_candidate["retention_sha256"])
        reload_error = fail(lambda: validate_authorized_retention(loaded, g0, store))
        assert "integrity" in reload_error
        out["corrupted_staged_candidate"] = {
            "commit_status": commit["status"],
            "pointer_now_references": keep_candidate["retention_sha256"],
            "stored_body": loaded,
            "restart_validation": reload_error,
        }

        # Rebuild a clean store for the second counterexample.
        base2 = base / "extra-root"
        g0b, store2, *_ = build_fixture(base2)
        fake_checkpoint = "f" * 64
        injected = make_authorized_retention(
            g0b,
            {C1, C3, fake_checkpoint},
            {},
            {},
            "verifier: add unproven rollback root without checkpoint/existence evidence",
        )
        store2.put(injected, "retention_sha256")
        validate_authorized_retention(injected, g0b, store2)
        ptr2 = base2 / "current-extra-root.json"
        initialize_pointer(ptr2, g0b)
        commit2 = cas_commit(
            pointer_path=ptr2,
            expected_predecessor=g0b,
            candidate=injected,
            store_path=store2.path,
        )
        assert commit2["status"] == "COMMITTED"
        assert fake_checkpoint in injected["retained_checkpoints"]
        assert read_pointer(ptr2)["retention_sha256"] == rid(injected)
        out["unproven_root_injection"] = {
            "commit_status": commit2["status"],
            "fake_checkpoint": fake_checkpoint,
            "drop_receipts": injected["drop_receipts"],
            "drop_root_evaluations": injected["drop_root_evaluations"],
            "current_retention_sha256": rid(injected),
        }

    out["status"] = "COUNTEREXAMPLES_REPRODUCED"
    return out


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, sort_keys=True))
