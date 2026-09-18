#!/usr/bin/env python3
"""Wave 138 adversarial self-test: stable-state validation-to-use object binding."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_AUTHENTICATED_ANCHOR as protocol
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_CUSTODY as w128
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_ROTATION as w132
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ROTATION_NAMESPACE as w137
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ROTATION_NAMESPACE_SELFTEST as t137
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_OBJECT_BOUND_CONSUMPTION as w138
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_ROTATION_SELFTEST as t132

SCRIPT = Path(__file__).resolve()
ENV_UID = t132.ENV_UID
PAYLOAD = b"AXM-W138-BOUND-CONSUMER-PAYLOAD\n"


def rid(name: str) -> str:
    return hashlib.sha256(("AXM-W138-" + name).encode()).hexdigest()


def parse(cp) -> dict:
    lines = cp.stdout.strip().splitlines()
    if not lines:
        return {"ok": False, "error": f"missing-json:{cp.returncode}:{cp.stderr[-1600:]}"}
    try:
        return json.loads(lines[-1])
    except Exception:
        return {"ok": False, "error": f"json-parse:{cp.stdout[-1600:]}:{cp.stderr[-1600:]}"}


def run_as(anchor_uid: int, worker_uid: int, args: list[str], check: bool = True):
    return t132.run_as(
        anchor_uid,
        t132.pycmd(str(SCRIPT), *args),
        extra_env={ENV_UID: str(worker_uid)},
        check=check,
        timeout=90.0,
    )


def authority_file(path: Path, data: bytes, uid: int, mode: int = 0o600) -> None:
    path.write_bytes(data)
    os.chown(path, uid, uid)
    os.chmod(path, mode)


def setup(base: Path, name: str, anchor_uid: int, worker_uid: int):
    return t137.setup(base, name, anchor_uid, worker_uid)


def rotate(anchor_uid: int, worker_uid: int, anchor: Path, witness: Path, name: str) -> dict:
    return parse(t137.rotate(anchor_uid, worker_uid, anchor, witness, rid(name)))


def make_alt_key(base: Path, name: str, anchor_uid: int) -> tuple[Path, Path]:
    private, public = w128._generate_response_keypair_memfd()
    priv = base / f"{name}-private.pem"
    pub = base / f"{name}-public.pem"
    authority_file(priv, private, anchor_uid)
    authority_file(pub, public, anchor_uid)
    return priv, pub


def make_lineage_rollback(base: Path, name: str, anchor: Path, anchor_uid: int) -> Path:
    lineage = anchor / w132.ROT_DIR / w132.LINEAGE
    lines = lineage.read_bytes().splitlines(keepends=True)
    if len(lines) < 1:
        raise RuntimeError("wave138-lineage-copy-needs-one-row")
    p = base / f"{name}-lineage-seq1.jsonl"
    authority_file(p, lines[0], anchor_uid)
    return p


def child_bind(anchor: Path, witness: Path) -> int:
    try:
        view = w138.bind_validated_rotation_view(anchor, witness)
    except BaseException as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 3
    print(json.dumps({
        "ok": True,
        "seq": view.validated["seq"],
        "head": view.validated["head_rotation_sha"],
        "private_inode": view.private_file.ino,
        "public_inode": view.public_file.ino,
        "lineage_sha256": view.authority_lineage_file.sha256,
    }, sort_keys=True))
    return 0


def child_predecessor_private_swap(anchor: Path, witness: Path,
                                   alt_private: Path, alt_public: Path) -> int:
    try:
        validated = w137.validate_rotation_state(anchor, witness)
        original_public = (anchor / protocol.PUBLIC_KEY).read_bytes()
        os.replace(alt_private, anchor / protocol.PRIVATE_KEY)
        signature = w128._sign_memfd(anchor / protocol.PRIVATE_KEY, PAYLOAD)
        result = {
            "ok": True,
            "validated_fp": validated["current_response_public_fingerprint"],
            "verified_by_validated_public":
                w138.verify_public_bytes(original_public, PAYLOAD, signature),
            "verified_by_substituted_public":
                w138.verify_public_bytes(alt_public.read_bytes(), PAYLOAD, signature),
        }
    except BaseException as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 3
    print(json.dumps(result, sort_keys=True))
    return 0


def child_bind_swap_private(anchor: Path, witness: Path, alt_private: Path) -> int:
    target = anchor / protocol.PRIVATE_KEY
    def swap() -> None:
        os.replace(alt_private, target)
    try:
        w138.bind_validated_rotation_view(anchor, witness, after_validation_hook=swap)
    except BaseException as exc:
        print(json.dumps({
            "ok": True,
            "failed_closed": True,
            "error": f"{type(exc).__name__}:{exc}",
            "replacement_retained": target.exists(),
        }, sort_keys=True))
        return 0
    print(json.dumps({"ok": False, "error": "wave138-private-substitution-was-accepted"}, sort_keys=True))
    return 4


def child_bound_sign_swap(anchor: Path, witness: Path,
                          alt_private: Path, alt_public: Path) -> int:
    try:
        view = w138.bind_validated_rotation_view(anchor, witness)
        def swap() -> None:
            os.replace(alt_private, anchor / protocol.PRIVATE_KEY)
        signature = w138.sign_from_bound_view(view, PAYLOAD, after_bind_hook=swap)
        result = {
            "ok": True,
            "verified_by_bound_public":
                w138.verify_public_bytes(view.public_file.data, PAYLOAD, signature),
            "verified_by_substituted_public":
                w138.verify_public_bytes(alt_public.read_bytes(), PAYLOAD, signature),
            "path_still_matches_bound_inode":
                w138.path_still_matches(view.private_file),
        }
    except BaseException as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 3
    print(json.dumps(result, sort_keys=True))
    return 0


def child_predecessor_lineage_swap(anchor: Path, witness: Path, rollback: Path) -> int:
    try:
        validated = w137.validate_rotation_state(anchor, witness)
        target = anchor / w132.ROT_DIR / w132.LINEAGE
        os.replace(rollback, target)
        consumed = w132._read_jsonl(target)
        result = {
            "ok": True,
            "validated_seq": validated["seq"],
            "consumed_seq_after_path_reopen": len(consumed),
        }
    except BaseException as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 3
    print(json.dumps(result, sort_keys=True))
    return 0


def child_bind_swap_lineage(anchor: Path, witness: Path, rollback: Path) -> int:
    target = anchor / w132.ROT_DIR / w132.LINEAGE
    def swap() -> None:
        os.replace(rollback, target)
    try:
        w138.bind_validated_rotation_view(anchor, witness, after_validation_hook=swap)
    except BaseException as exc:
        print(json.dumps({
            "ok": True,
            "failed_closed": True,
            "error": f"{type(exc).__name__}:{exc}",
            "rollback_retained": target.exists(),
        }, sort_keys=True))
        return 0
    print(json.dumps({"ok": False, "error": "wave138-lineage-substitution-was-accepted"}, sort_keys=True))
    return 4


def child_bound_lineage_swap(anchor: Path, witness: Path, rollback: Path) -> int:
    try:
        view = w138.bind_validated_rotation_view(anchor, witness)
        target = anchor / w132.ROT_DIR / w132.LINEAGE
        os.replace(rollback, target)
        result = {
            "ok": True,
            "bound_seq": len(view.authority_lineage),
            "validated_seq": view.validated["seq"],
            "path_still_matches_bound_inode":
                w138.path_still_matches(view.authority_lineage_file),
            "reopened_seq": len(w132._read_jsonl(target)),
        }
    except BaseException as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 3
    print(json.dumps(result, sort_keys=True))
    return 0


def child_symlink_public_swap(anchor: Path, witness: Path, alt_public: Path) -> int:
    target = anchor / protocol.PUBLIC_KEY
    def swap() -> None:
        target.unlink()
        target.symlink_to(alt_public)
    try:
        w138.bind_validated_rotation_view(anchor, witness, after_validation_hook=swap)
    except BaseException as exc:
        print(json.dumps({
            "ok": True,
            "failed_closed": True,
            "error": f"{type(exc).__name__}:{exc}",
            "symlink_retained": target.is_symlink(),
        }, sort_keys=True))
        return 0
    print(json.dumps({"ok": False, "error": "wave138-symlink-substitution-was-accepted"}, sort_keys=True))
    return 4


def run_suite(worker_uid: int, anchor_uid: int, report_path: Path | None) -> int:
    if os.geteuid() != 0:
        raise PermissionError("wave138-selftest-requires-root-orchestrator")
    if worker_uid == anchor_uid:
        raise ValueError("worker-and-anchor-uid-must-differ")

    base = Path(tempfile.mkdtemp(prefix="axm-w138-object-binding-"))
    os.chmod(base, 0o777)
    results: list[dict] = []

    witness, anchor, _, _ = setup(base, "clean", anchor_uid, worker_uid)
    r1 = rotate(anchor_uid, worker_uid, anchor, witness, "clean-one")
    r2 = rotate(anchor_uid, worker_uid, anchor, witness, "clean-two")
    bound = parse(run_as(anchor_uid, worker_uid, ["--child-bind", str(anchor), str(witness)]))
    results.append({
        "name": "clean_wave137_state_binds_exact_seq2_view",
        "ok": r1.get("ok") is True and r2.get("ok") is True and bound.get("ok") is True and bound.get("seq") == 2,
        "detail": {"seq": bound.get("seq"), "head": bound.get("head")},
    })

    witness, anchor, _, _ = setup(base, "pred-private", anchor_uid, worker_uid)
    first = rotate(anchor_uid, worker_uid, anchor, witness, "pred-private-one")
    alt_priv, alt_pub = make_alt_key(base, "pred-private-alt", anchor_uid)
    pred = parse(run_as(anchor_uid, worker_uid, [
        "--child-pred-private-swap", str(anchor), str(witness), str(alt_priv), str(alt_pub)
    ]))
    results.append({
        "name": "wave137_validate_then_reopen_private_path_can_consume_substitute",
        "ok": first.get("ok") is True and pred.get("ok") is True and pred.get("verified_by_validated_public") is False and pred.get("verified_by_substituted_public") is True,
        "detail": pred,
    })

    witness, anchor, _, _ = setup(base, "bind-private", anchor_uid, worker_uid)
    first = rotate(anchor_uid, worker_uid, anchor, witness, "bind-private-one")
    alt_priv, _ = make_alt_key(base, "bind-private-alt", anchor_uid)
    guarded = parse(run_as(anchor_uid, worker_uid, [
        "--child-bind-swap-private", str(anchor), str(witness), str(alt_priv)
    ]))
    results.append({
        "name": "private_substitution_after_validation_fails_closed_and_remains",
        "ok": first.get("ok") is True and guarded.get("ok") is True and guarded.get("failed_closed") is True and guarded.get("replacement_retained") is True,
        "detail": guarded,
    })

    witness, anchor, _, _ = setup(base, "bound-private", anchor_uid, worker_uid)
    first = rotate(anchor_uid, worker_uid, anchor, witness, "bound-private-one")
    alt_priv, alt_pub = make_alt_key(base, "bound-private-alt", anchor_uid)
    fixed = parse(run_as(anchor_uid, worker_uid, [
        "--child-bound-sign-swap", str(anchor), str(witness), str(alt_priv), str(alt_pub)
    ]))
    results.append({
        "name": "bound_private_bytes_sign_original_identity_after_path_swap",
        "ok": first.get("ok") is True and fixed.get("ok") is True and fixed.get("verified_by_bound_public") is True and fixed.get("verified_by_substituted_public") is False and fixed.get("path_still_matches_bound_inode") is False,
        "detail": fixed,
    })

    witness, anchor, _, _ = setup(base, "pred-lineage", anchor_uid, worker_uid)
    one = rotate(anchor_uid, worker_uid, anchor, witness, "pred-lineage-one")
    rollback = make_lineage_rollback(base, "pred-lineage", anchor, anchor_uid)
    two = rotate(anchor_uid, worker_uid, anchor, witness, "pred-lineage-two")
    pred_lineage = parse(run_as(anchor_uid, worker_uid, [
        "--child-pred-lineage-swap", str(anchor), str(witness), str(rollback)
    ]))
    results.append({
        "name": "wave137_validate_then_reopen_lineage_path_can_observe_rollback",
        "ok": one.get("ok") is True and two.get("ok") is True and pred_lineage.get("ok") is True and pred_lineage.get("validated_seq") == 2 and pred_lineage.get("consumed_seq_after_path_reopen") == 1,
        "detail": pred_lineage,
    })

    witness, anchor, _, _ = setup(base, "bind-lineage", anchor_uid, worker_uid)
    one = rotate(anchor_uid, worker_uid, anchor, witness, "bind-lineage-one")
    rollback = make_lineage_rollback(base, "bind-lineage", anchor, anchor_uid)
    two = rotate(anchor_uid, worker_uid, anchor, witness, "bind-lineage-two")
    guarded_lineage = parse(run_as(anchor_uid, worker_uid, [
        "--child-bind-swap-lineage", str(anchor), str(witness), str(rollback)
    ]))
    results.append({
        "name": "lineage_rollback_after_validation_fails_closed_and_remains",
        "ok": one.get("ok") is True and two.get("ok") is True and guarded_lineage.get("ok") is True and guarded_lineage.get("failed_closed") is True and guarded_lineage.get("rollback_retained") is True,
        "detail": guarded_lineage,
    })

    witness, anchor, _, _ = setup(base, "bound-lineage", anchor_uid, worker_uid)
    one = rotate(anchor_uid, worker_uid, anchor, witness, "bound-lineage-one")
    rollback = make_lineage_rollback(base, "bound-lineage", anchor, anchor_uid)
    two = rotate(anchor_uid, worker_uid, anchor, witness, "bound-lineage-two")
    fixed_lineage = parse(run_as(anchor_uid, worker_uid, [
        "--child-bound-lineage-swap", str(anchor), str(witness), str(rollback)
    ]))
    results.append({
        "name": "bound_lineage_rows_remain_seq2_after_path_rollback",
        "ok": one.get("ok") is True and two.get("ok") is True and fixed_lineage.get("ok") is True and fixed_lineage.get("bound_seq") == 2 and fixed_lineage.get("validated_seq") == 2 and fixed_lineage.get("reopened_seq") == 1 and fixed_lineage.get("path_still_matches_bound_inode") is False,
        "detail": fixed_lineage,
    })

    witness, anchor, _, _ = setup(base, "symlink-public", anchor_uid, worker_uid)
    first = rotate(anchor_uid, worker_uid, anchor, witness, "symlink-public-one")
    _, alt_pub = make_alt_key(base, "symlink-public-alt", anchor_uid)
    symlink = parse(run_as(anchor_uid, worker_uid, [
        "--child-symlink-public-swap", str(anchor), str(witness), str(alt_pub)
    ]))
    results.append({
        "name": "public_symlink_substitution_after_validation_fails_closed_and_remains",
        "ok": first.get("ok") is True and symlink.get("ok") is True and symlink.get("failed_closed") is True and symlink.get("symlink_retained") is True,
        "detail": symlink,
    })

    passed = sum(bool(r["ok"]) for r in results)
    report = {
        "schema": "axm.flowing-compute.wave138-object-binding-selftest.v1",
        "mode": "optimized" if sys.flags.optimize else "normal",
        "worker_uid": worker_uid,
        "anchor_uid": anchor_uid,
        "passed": passed,
        "total": len(results),
        "results": results,
        "truth_boundary": (
            "Same-host Linux filesystem TOCTOU evidence around stable Wave-137 rotation state. "
            "The suite preserves predecessor counterexamples where validation is followed by a "
            "pathname reopen that consumes a substituted private key or historical lineage. "
            "Wave 138 binds exact regular-file inode metadata and bytes after validation, compares "
            "them to the validated seq/head/current-key identity, uses bound private bytes for "
            "signing, and rejects symlink substitution. It does not protect against an attacker "
            "who controls the authority process/memory, authority UID generally, root/kernel, "
            "user namespaces, copied genuine keys on another host, whole-domain rollback, or "
            "pending-transaction TOCTOU not yet threaded through the rotation writer. No speed, "
            "energy, retained/incremental/dormant-compute, throughput, or scaling claim."
        ),
    }
    if report_path:
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if passed == len(results) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker-uid", type=int)
    ap.add_argument("--anchor-uid", type=int)
    ap.add_argument("--report")
    ap.add_argument("--child-bind", nargs=2, metavar=("ANCHOR", "WITNESS"))
    ap.add_argument("--child-pred-private-swap", nargs=4, metavar=("ANCHOR", "WITNESS", "ALT_PRIVATE", "ALT_PUBLIC"))
    ap.add_argument("--child-bind-swap-private", nargs=3, metavar=("ANCHOR", "WITNESS", "ALT_PRIVATE"))
    ap.add_argument("--child-bound-sign-swap", nargs=4, metavar=("ANCHOR", "WITNESS", "ALT_PRIVATE", "ALT_PUBLIC"))
    ap.add_argument("--child-pred-lineage-swap", nargs=3, metavar=("ANCHOR", "WITNESS", "ROLLBACK"))
    ap.add_argument("--child-bind-swap-lineage", nargs=3, metavar=("ANCHOR", "WITNESS", "ROLLBACK"))
    ap.add_argument("--child-bound-lineage-swap", nargs=3, metavar=("ANCHOR", "WITNESS", "ROLLBACK"))
    ap.add_argument("--child-symlink-public-swap", nargs=3, metavar=("ANCHOR", "WITNESS", "ALT_PUBLIC"))
    args = ap.parse_args()

    if args.child_bind:
        return child_bind(Path(args.child_bind[0]), Path(args.child_bind[1]))
    if args.child_pred_private_swap:
        a, w, priv, pub = args.child_pred_private_swap
        return child_predecessor_private_swap(Path(a), Path(w), Path(priv), Path(pub))
    if args.child_bind_swap_private:
        a, w, priv = args.child_bind_swap_private
        return child_bind_swap_private(Path(a), Path(w), Path(priv))
    if args.child_bound_sign_swap:
        a, w, priv, pub = args.child_bound_sign_swap
        return child_bound_sign_swap(Path(a), Path(w), Path(priv), Path(pub))
    if args.child_pred_lineage_swap:
        a, w, rollback = args.child_pred_lineage_swap
        return child_predecessor_lineage_swap(Path(a), Path(w), Path(rollback))
    if args.child_bind_swap_lineage:
        a, w, rollback = args.child_bind_swap_lineage
        return child_bind_swap_lineage(Path(a), Path(w), Path(rollback))
    if args.child_bound_lineage_swap:
        a, w, rollback = args.child_bound_lineage_swap
        return child_bound_lineage_swap(Path(a), Path(w), Path(rollback))
    if args.child_symlink_public_swap:
        a, w, pub = args.child_symlink_public_swap
        return child_symlink_public_swap(Path(a), Path(w), Path(pub))
    if args.worker_uid is None or args.anchor_uid is None:
        ap.error("--worker-uid and --anchor-uid are required for suite mode")
    return run_suite(args.worker_uid, args.anchor_uid, Path(args.report) if args.report else None)


if __name__ == "__main__":
    raise SystemExit(main())
