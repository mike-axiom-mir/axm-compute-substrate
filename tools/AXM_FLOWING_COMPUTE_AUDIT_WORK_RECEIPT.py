from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

SCHEMA = 'axm.flowing-compute-audit-work-receipt/v0.1'
MODE = 'audited_reuse'


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def challenge(*, state: dict[str, Any], sequence: int) -> str:
    """Bind an audit to one exact predecessor freshness state and next sequence."""
    return digest({
        'schema': 'axm.flowing-compute-audit-challenge/v0.1',
        'contract_id': state['contract_id'],
        'sequence': int(sequence),
        'mode': MODE,
        'predecessor_state_sha256': state['state_sha256'],
        'artifact_sha256': state['artifact_sha256'],
        'artifact_bytes': int(state['artifact_bytes']),
        'proof_sha256': state['proof_sha256'],
    })


def perform(*, state: dict[str, Any], sequence: int, artifact_path: str | Path,
            chunk_bytes: int = 1024 * 1024) -> dict[str, Any]:
    """Read the complete artifact and emit PASS/FAIL audit-work evidence.

    This is local deterministic evidence. receipt_sha256 protects receipt integrity,
    not actor authenticity; it is not a TPM/signature/remote attestation.
    """
    path = Path(artifact_path)
    expected_bytes = int(state['artifact_bytes'])
    expected_sha = state['artifact_sha256']
    h = hashlib.sha256()
    bytes_read = 0
    chunks_read = 0
    t0 = time.process_time_ns()
    w0 = time.perf_counter_ns()
    with path.open('rb') as f:
        while True:
            block = f.read(chunk_bytes)
            if not block:
                break
            h.update(block)
            bytes_read += len(block)
            chunks_read += 1
    cpu_ns = time.process_time_ns() - t0
    wall_ns = time.perf_counter_ns() - w0
    observed_sha = h.hexdigest()
    status = 'AUDIT_PASS' if bytes_read == expected_bytes and observed_sha == expected_sha else 'AUDIT_FAIL'
    body = {
        'schema': SCHEMA,
        'status': status,
        'contract_id': state['contract_id'],
        'sequence': int(sequence),
        'mode': MODE,
        'challenge_sha256': challenge(state=state, sequence=sequence),
        'predecessor_state_sha256': state['state_sha256'],
        'proof_sha256': state['proof_sha256'],
        'expected_artifact_sha256': expected_sha,
        'observed_artifact_sha256': observed_sha,
        'expected_artifact_bytes': expected_bytes,
        'bytes_read': bytes_read,
        'chunks_read': chunks_read,
        'chunk_bytes': int(chunk_bytes),
        'audit_cpu_ns': cpu_ns,
        'audit_wall_ns': wall_ns,
        'truth': {
            'receipt_created_after_full_local_byte_read': True,
            'receipt_digest_is_integrity_not_actor_authentication': True,
            'cpu_time_is_not_joules': True,
        },
    }
    body['receipt_sha256'] = digest(body)
    return body


def validate(*, receipt: dict[str, Any], state: dict[str, Any], sequence: int) -> None:
    if receipt.get('schema') != SCHEMA:
        raise ValueError('audit receipt schema mismatch')
    supplied = receipt.get('receipt_sha256')
    body = dict(receipt)
    body.pop('receipt_sha256', None)
    if supplied != digest(body):
        raise ValueError('audit receipt integrity mismatch')
    if receipt.get('status') != 'AUDIT_PASS':
        raise ValueError('audit receipt did not pass')
    if receipt.get('contract_id') != state['contract_id']:
        raise ValueError('audit receipt contract mismatch')
    if int(receipt.get('sequence', -1)) != int(sequence):
        raise ValueError('audit receipt sequence mismatch')
    if receipt.get('mode') != MODE:
        raise ValueError('audit receipt mode mismatch')
    if receipt.get('challenge_sha256') != challenge(state=state, sequence=sequence):
        raise ValueError('audit receipt challenge mismatch')
    if receipt.get('predecessor_state_sha256') != state['state_sha256']:
        raise ValueError('audit receipt predecessor mismatch')
    if receipt.get('proof_sha256') != state['proof_sha256']:
        raise ValueError('audit receipt proof mismatch')
    if receipt.get('expected_artifact_sha256') != state['artifact_sha256']:
        raise ValueError('audit receipt expected artifact mismatch')
    if receipt.get('observed_artifact_sha256') != state['artifact_sha256']:
        raise ValueError('audit receipt observed artifact mismatch')
    if int(receipt.get('expected_artifact_bytes', -1)) != int(state['artifact_bytes']):
        raise ValueError('audit receipt expected byte count mismatch')
    if int(receipt.get('bytes_read', -1)) != int(state['artifact_bytes']):
        raise ValueError('audit receipt incomplete byte read')
    if int(receipt.get('chunks_read', 0)) <= 0:
        raise ValueError('audit receipt missing read chunks')
