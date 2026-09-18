#!/usr/bin/env python3
"""Independent Wave 136 verifier: clone one genuinely current authority, then fork rotation.

DRAFT / NON-CANON verifier lane only. This script does not modify builder files.
It first establishes one genuine Wave-136 rotation, clones the complete current
anchor+witness stores byte-for-byte, then lets the original and clone authorize
different next rotations sequentially. The expected adversarial verdict is that
both local histories validate even though they share the same predecessor/current
private identity at the clone point and diverge at the same next sequence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

import AXM_FLOWING_COMPUTE_PROCESS_WITNESS as w
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_AUTHENTICATED_ANCHOR as protocol
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_ROTATION as w132
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_ROTATION_SELFTEST as t132
import AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ROTATION_TRANSACTION_RECOVERY as w136

TOOLS = Path(__file__).resolve().parents[1] / "tools"
W136 = TOOLS / "AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ROTATION_TRANSACTION_RECOVERY.py"
ENV_UID = t132.ENV_UID


def rid(name: str) -> str:
    return hashlib.sha256(("AXM-W136-CLONE-FORK-" + name).encode()).hexdigest()


def parse(cp) -> dict:
    lines = cp.stdout.strip().splitlines()
    if not lines:
        return {"ok": False, "error": f"missing-json:{cp.returncode}:{cp.stderr[-1600:]}"}
    try:
        return {"ok": True, "result": json.loads(lines[-1]), "returncode": cp.returncode}
    except Exception:
        return {"ok": False, "error": f"json-parse:{cp.stdout[-1600:]}:{cp.stderr[-1600:]}", "returncode": cp.returncode}


def run_w136(anchor_uid: int, worker_uid: int, args: list[str], check: bool = True):
    return t132.run_as(
        anchor_uid,
        t132.pycmd(str(W136), *args),
        extra_env={ENV_UID: str(worker_uid)},
        check=check,
        timeout=120.0,
    )


def rotate(anchor_uid: int, worker_uid: int, anchor: Path, witness: Path, rotation_id: str) -> dict:
    cp = run_w136(anchor_uid, worker_uid, ["rotate", str(anchor), str(witness), rotation_id])
    out = parse(cp)
    if not out.get("ok"):
        raise RuntimeError(out)
    return out["result"]


def validate(anchor_uid: int, worker_uid: int, anchor: Path, witness: Path) -> dict:
    cp = run_w136(anchor_uid, worker_uid, ["validate", str(anchor), str(witness)])
    out = parse(cp)
    if not out.get("ok"):
        raise RuntimeError(out)
    return out["result"]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_map(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.is_symlink():
            out[str(p.relative_to(root))] = sha(p.read_bytes())
    return out


def copy_store(src: Path, dst: Path, anchor_uid: int) -> None:
    shutil.copytree(src, dst, symlinks=True)
    t132.chown_tree(dst, anchor_uid)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker-uid", type=int, required=True)
    ap.add_argument("--anchor-uid", type=int, default=23001)
    ap.add_argument("--report")
    args = ap.parse_args()

    if os.geteuid() != 0:
        raise PermissionError("wave136-clone-fork-verifier-requires-root-orchestrator")
    if args.worker_uid == args.anchor_uid:
        raise ValueError("worker-and-anchor-uid-must-differ")

    base = Path(tempfile.mkdtemp(prefix="axm-w136-clone-fork-"))
    os.chmod(base, 0o777)

    witness_a, anchor_a, _, init = t132.setup_case(
        base, "source", args.anchor_uid, args.worker_uid
    )

    common_id = rid("common")
    common = rotate(args.anchor_uid, args.worker_uid, anchor_a, witness_a, common_id)
    common_valid = validate(args.anchor_uid, args.worker_uid, anchor_a, witness_a)
    if common.get("seq") != 1 or common_valid.get("seq") != 1:
        raise RuntimeError("common-sequence-1-establishment-failed")

    anchor_b = base / "clone-anchor"
    witness_b = base / "clone-witness"
    copy_store(anchor_a, anchor_b, args.anchor_uid)
    copy_store(witness_a, witness_b, args.anchor_uid)

    before_anchor_equal = file_map(anchor_a) == file_map(anchor_b)
    before_witness_equal = file_map(witness_a) == file_map(witness_b)

    private_a_before = (anchor_a / protocol.PRIVATE_KEY).read_bytes()
    private_b_before = (anchor_b / protocol.PRIVATE_KEY).read_bytes()
    public_a_before = (anchor_a / protocol.PUBLIC_KEY).read_bytes()
    public_b_before = (anchor_b / protocol.PUBLIC_KEY).read_bytes()

    line_a_before = (anchor_a / w132.ROT_DIR / w132.LINEAGE).read_bytes()
    line_b_before = (anchor_b / w132.ROT_DIR / w132.LINEAGE).read_bytes()
    witness_line_a_before = (witness_a / w132.WITNESS_LINEAGE).read_bytes()
    witness_line_b_before = (witness_b / w132.WITNESS_LINEAGE).read_bytes()

    fork_a_id = rid("fork-a")
    fork_b_id = rid("fork-b")
    fork_a = rotate(args.anchor_uid, args.worker_uid, anchor_a, witness_a, fork_a_id)
    fork_b = rotate(args.anchor_uid, args.worker_uid, anchor_b, witness_b, fork_b_id)

    valid_a = validate(args.anchor_uid, args.worker_uid, anchor_a, witness_a)
    valid_b = validate(args.anchor_uid, args.worker_uid, anchor_b, witness_b)

    rows_a = w132._read_jsonl(anchor_a / w132.ROT_DIR / w132.LINEAGE)
    rows_b = w132._read_jsonl(anchor_b / w132.ROT_DIR / w132.LINEAGE)
    witness_rows_a = w132._read_jsonl(witness_a / w132.WITNESS_LINEAGE)
    witness_rows_b = w132._read_jsonl(witness_b / w132.WITNESS_LINEAGE)

    common_row_same = len(rows_a) == 2 and len(rows_b) == 2 and rows_a[0] == rows_b[0]
    same_predecessor = (
        common_row_same
        and rows_a[1].get("seq") == 2
        and rows_b[1].get("seq") == 2
        and rows_a[1].get("prev_rotation_sha") == rows_b[1].get("prev_rotation_sha")
        and rows_a[1].get("prev_rotation_sha") == w132._cert_sha(rows_a[0])
        and rows_a[1].get("old_response_public_fingerprint") == rows_b[1].get("old_response_public_fingerprint")
    )
    divergent_successors = (
        common_row_same
        and rows_a[1].get("rotation_id") == fork_a_id
        and rows_b[1].get("rotation_id") == fork_b_id
        and rows_a[1].get("new_response_public_fingerprint") != rows_b[1].get("new_response_public_fingerprint")
        and w132._cert_sha(rows_a[1]) != w132._cert_sha(rows_b[1])
    )
    both_valid = (
        fork_a.get("seq") == 2 and fork_b.get("seq") == 2
        and valid_a.get("seq") == 2 and valid_b.get("seq") == 2
        and valid_a.get("last_rotation_id") == fork_a_id
        and valid_b.get("last_rotation_id") == fork_b_id
        and rows_a == witness_rows_a
        and rows_b == witness_rows_b
    )
    genuine_clone_point = (
        before_anchor_equal and before_witness_equal
        and private_a_before == private_b_before
        and public_a_before == public_b_before
        and line_a_before == line_b_before
        and witness_line_a_before == witness_line_b_before
        and sha(private_a_before) == sha(private_b_before)
        and common.get("current_response_public_fingerprint") == w132._public_fp(public_a_before)
    )

    reproduced = genuine_clone_point and same_predecessor and divergent_successors and both_valid
    verdict = (
        "FAIL_GENUINE_CLONED_CURRENT_AUTHORITY_FORKS_INDIVIDUALLY_VALID_ROTATION_LINEAGES"
        if reproduced
        else "NO_CLONED_AUTHORITY_FORK_REPRODUCED"
    )

    report = {
        "verdict": verdict,
        "reproduced": reproduced,
        "scope": "same-host byte-for-byte cloned authority+witness domain; sequential rotations; no key/signature forgery",
        "builder": {
            "wave": 136,
            "evidence_head": "411bd123b193eca34f44bec1ff3d9d9af32247c5",
            "exact_tested_source_from_receipt": "49d0bd8aa24a91036a85e1cd265985dfd97585b7",
            "tool_blob_from_receipt": "47fe034330c808b48ee39f64f70b07778b533372",
        },
        "clone_point": {
            "common_seq": common.get("seq"),
            "common_rotation_id": common_id,
            "anchor_trees_byte_identical": before_anchor_equal,
            "witness_trees_byte_identical": before_witness_equal,
            "current_private_bytes_identical": private_a_before == private_b_before,
            "current_private_sha256": sha(private_a_before),
            "current_public_fingerprint": w132._public_fp(public_a_before),
            "authority_lineage_identical": line_a_before == line_b_before,
            "witness_lineage_identical": witness_line_a_before == witness_line_b_before,
        },
        "fork_a": {
            "rotation_id": fork_a_id,
            "seq": fork_a.get("seq"),
            "validated_seq": valid_a.get("seq"),
            "head_rotation_sha": valid_a.get("head_rotation_sha"),
            "current_response_public_fingerprint": valid_a.get("current_response_public_fingerprint"),
        },
        "fork_b": {
            "rotation_id": fork_b_id,
            "seq": fork_b.get("seq"),
            "validated_seq": valid_b.get("seq"),
            "head_rotation_sha": valid_b.get("head_rotation_sha"),
            "current_response_public_fingerprint": valid_b.get("current_response_public_fingerprint"),
        },
        "checks": {
            "genuine_clone_point": genuine_clone_point,
            "same_exact_predecessor": same_predecessor,
            "different_authorized_successors": divergent_successors,
            "both_local_domains_validate": both_valid,
            "common_row_same": common_row_same,
            "fork_head_shas_differ": valid_a.get("head_rotation_sha") != valid_b.get("head_rotation_sha"),
        },
        "truth_boundary": {
            "not_builder_bounded_claim_falsification": True,
            "no_cross_host_execution": True,
            "no_user_namespace_execution": True,
            "no_root_or_kernel_compromise_of_live_authority": True,
            "orchestrator_root_used_only_to_construct_exact_clone_and_drop_to_authority_uid": True,
            "no_signature_or_private_key_forgery": True,
            "no_speed_energy_or_retained_compute_claim": True,
        },
        "initial_response_public_fingerprint": init.get("response_public_fingerprint"),
    }

    text = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.report:
        Path(args.report).write_text(text)
    print(text, end="")
    return 0 if reproduced else 1


if __name__ == "__main__":
    raise SystemExit(main())
