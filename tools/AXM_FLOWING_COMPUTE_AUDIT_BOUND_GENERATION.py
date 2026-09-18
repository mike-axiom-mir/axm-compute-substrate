from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from AXM_FLOWING_COMPUTE_AUDIT_WORK_RECEIPT import validate as validate_audit_receipt
from AXM_FLOWING_COMPUTE_FRESHNESS_BOUND_GENERATION import (
    SCHEMA as PRIOR_POINTER_SCHEMA,
    validate_pointer as validate_prior_pointer,
)
from AXM_FLOWING_COMPUTE_VERIFICATION_FRESHNESS import (
    advance as advance_freshness,
    validate as validate_freshness,
)

SCHEMA = 'axm.flowing-compute-audit-bound-generation/v0.1'
AUDITED = 'audited_reuse'
CARRIED = 'carried_immutable_proof'


def canon(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(',', ':'), ensure_ascii=False
    ).encode('utf-8')


def digest(value: Any) -> str:
    return hashlib.sha256(canon(value)).hexdigest()


def _is_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _validate_previous_pointer(pointer: dict[str, Any]) -> None:
    schema = pointer.get('schema')
    if schema == PRIOR_POINTER_SCHEMA:
        validate_prior_pointer(pointer)
    elif schema == SCHEMA:
        validate_pointer(pointer)
    else:
        raise ValueError('unsupported predecessor pointer schema')


def _replay_transition(
    *,
    previous_freshness: dict[str, dict[str, Any]],
    current_freshness: dict[str, dict[str, Any]],
    sequence: int,
    modes: dict[str, str],
) -> None:
    if set(previous_freshness) != set(current_freshness) or set(modes) != set(current_freshness):
        raise ValueError('freshness/mode contract coverage mismatch')
    for contract_id in sorted(current_freshness):
        prior = previous_freshness[contract_id]
        current = current_freshness[contract_id]
        replayed = advance_freshness(
            state=prior,
            sequence=sequence,
            mode=modes[contract_id],
            artifact_sha256=prior['artifact_sha256'],
            proof_sha256=prior['proof_sha256'],
        )
        if replayed.get('status') != 'ADVANCED':
            raise ValueError('freshness replay did not advance')
        if replayed['state'] != current:
            raise ValueError(f'freshness transition mismatch for {contract_id}')


def _receipt_ref(receipt: dict[str, Any]) -> dict[str, Any]:
    return {
        'receipt_sha256': receipt['receipt_sha256'],
        'sequence': int(receipt['sequence']),
        'predecessor_state_sha256': receipt['predecessor_state_sha256'],
    }


def make_pointer(
    *,
    previous_pointer: dict[str, Any],
    generation_sha256: str,
    transition_result: dict[str, Any],
    audit_receipts: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Commit one generation, its freshness set, and exact audit receipt IDs together.

    The Wave 79 transition must already have validated the receipts. This constructor
    revalidates those receipt bodies against predecessor freshness before allowing
    compact receipt references into the atomic pointer.
    """
    _validate_previous_pointer(previous_pointer)
    if transition_result.get('status') != 'ADVANCED':
        raise ValueError('transition result did not advance')
    sequence = int(transition_result['sequence'])
    if sequence != int(previous_pointer['sequence']) + 1:
        raise ValueError('generation sequence does not follow predecessor')

    freshness = transition_result['freshness']
    modes = transition_result['modes']
    receipt_ids = transition_result.get('validated_audit_receipts', {})
    receipts = audit_receipts or {}

    _replay_transition(
        previous_freshness=previous_pointer['freshness'],
        current_freshness=freshness,
        sequence=sequence,
        modes=modes,
    )

    audited_contracts = {cid for cid, mode in modes.items() if mode == AUDITED}
    carried_contracts = {cid for cid, mode in modes.items() if mode == CARRIED}
    unknown = {cid: mode for cid, mode in modes.items() if mode not in (AUDITED, CARRIED)}
    if unknown:
        raise ValueError('unsupported verification mode in transition')
    if set(receipt_ids) != audited_contracts:
        raise ValueError('validated audit receipt coverage mismatch')
    if set(receipts) != audited_contracts:
        raise ValueError('audit receipt evidence coverage mismatch')
    if carried_contracts & set(receipt_ids):
        raise ValueError('carried contract cannot commit an audit receipt')

    receipt_refs: dict[str, dict[str, Any]] = {}
    for cid in sorted(audited_contracts):
        receipt = receipts[cid]
        validate_audit_receipt(
            receipt=receipt,
            state=previous_pointer['freshness'][cid],
            sequence=sequence,
        )
        if receipt['receipt_sha256'] != receipt_ids[cid]:
            raise ValueError('transition audit receipt identity mismatch')
        receipt_refs[cid] = _receipt_ref(receipt)

    if not _is_sha256(generation_sha256):
        raise ValueError('generation SHA-256 must be 64 hex characters')

    body = {
        'schema': SCHEMA,
        'sequence': sequence,
        'generation_sha256': generation_sha256,
        'previous_pointer_sha256': previous_pointer['pointer_sha256'],
        'freshness': freshness,
        'modes': dict(modes),
        'audit_receipts': receipt_refs,
        'truth': {
            'generation_freshness_and_audit_receipt_ids_share_one_commit_boundary': True,
            'audited_receipt_ids_are_revalidated_against_predecessor_freshness': True,
            'carried_reuse_commits_no_fresh_audit_receipt': True,
            'receipt_digest_is_integrity_not_actor_authentication': True,
        },
    }
    body['pointer_sha256'] = digest(body)
    validate_pointer(body)
    return body


def validate_pointer(pointer: dict[str, Any]) -> None:
    if pointer.get('schema') != SCHEMA:
        raise ValueError('unsupported audit-bound generation pointer schema')
    stored = pointer.get('pointer_sha256')
    body = dict(pointer)
    body.pop('pointer_sha256', None)
    if stored != digest(body):
        raise ValueError('audit-bound pointer integrity mismatch')
    if not _is_sha256(pointer.get('generation_sha256')):
        raise ValueError('invalid generation SHA-256')
    if not _is_sha256(pointer.get('previous_pointer_sha256')):
        raise ValueError('invalid predecessor pointer SHA-256')

    sequence = int(pointer['sequence'])
    if sequence <= 0:
        raise ValueError('audit-bound pointer requires a predecessor generation')

    freshness = pointer.get('freshness', {})
    modes = pointer.get('modes', {})
    receipt_refs = pointer.get('audit_receipts', {})
    if not freshness or set(freshness) != set(modes):
        raise ValueError('freshness/mode contract coverage mismatch')

    audited_contracts: set[str] = set()
    for cid, state in freshness.items():
        validate_freshness(state)
        if int(state['current_sequence']) != sequence:
            raise ValueError('freshness sequence does not match generation')
        mode = modes[cid]
        if mode == AUDITED:
            audited_contracts.add(cid)
            if int(state['last_strong_audit_sequence']) != sequence:
                raise ValueError('audited freshness state did not reset at this generation')
        elif mode == CARRIED:
            if int(state['last_strong_audit_sequence']) >= sequence:
                raise ValueError('carried freshness state claims a fresh audit')
        else:
            raise ValueError('unsupported verification mode')

    if set(receipt_refs) != audited_contracts:
        raise ValueError('audit receipt map does not exactly match audited contracts')
    for cid, ref in receipt_refs.items():
        if not _is_sha256(ref.get('receipt_sha256')):
            raise ValueError('invalid audit receipt SHA-256')
        if int(ref.get('sequence', -1)) != sequence:
            raise ValueError('audit receipt reference is stale for this generation')
        predecessor_state_sha = ref.get('predecessor_state_sha256')
        if not _is_sha256(predecessor_state_sha):
            raise ValueError('invalid audit receipt predecessor state SHA-256')


def validate_chain(
    *,
    previous_pointer: dict[str, Any],
    pointer: dict[str, Any],
    audit_receipt_store: dict[str, dict[str, Any]] | None = None,
) -> None:
    """Validate pointer semantics plus its exact predecessor and receipt evidence."""
    _validate_previous_pointer(previous_pointer)
    validate_pointer(pointer)
    if int(pointer['sequence']) != int(previous_pointer['sequence']) + 1:
        raise ValueError('pointer sequence does not follow predecessor')
    if pointer['previous_pointer_sha256'] != previous_pointer['pointer_sha256']:
        raise ValueError('predecessor pointer identity mismatch')

    _replay_transition(
        previous_freshness=previous_pointer['freshness'],
        current_freshness=pointer['freshness'],
        sequence=int(pointer['sequence']),
        modes=pointer['modes'],
    )

    store = audit_receipt_store or {}
    for cid, ref in pointer['audit_receipts'].items():
        prior_state = previous_pointer['freshness'][cid]
        if ref['predecessor_state_sha256'] != prior_state['state_sha256']:
            raise ValueError('audit receipt reference names the wrong predecessor state')
        receipt_sha = ref['receipt_sha256']
        receipt = store.get(receipt_sha)
        if receipt is None:
            raise ValueError(f'audit receipt body unavailable for {cid}')
        if receipt.get('receipt_sha256') != receipt_sha:
            raise ValueError('audit receipt store key/body mismatch')
        validate_audit_receipt(
            receipt=receipt,
            state=prior_state,
            sequence=int(pointer['sequence']),
        )


def atomic_write(path: str | Path, pointer: dict[str, Any]) -> None:
    validate_pointer(pointer)
    path = Path(path)
    tmp = path.with_name(path.name + '.tmp')
    with tmp.open('wb') as handle:
        handle.write(canon(pointer) + b'\n')
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    directory_fd = os.open(str(path.parent), os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def read(path: str | Path) -> dict[str, Any]:
    pointer = json.loads(Path(path).read_text())
    validate_pointer(pointer)
    return pointer
