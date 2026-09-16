from __future__ import annotations
from typing import Any

from AXM_FLOWING_COMPUTE_AUDIT_WORK_RECEIPT import validate as validate_audit_receipt
from AXM_FLOWING_COMPUTE_PARTIAL_AUDIT import advance_freshness_set

SCHEMA = 'axm.flowing-compute-receipt-bound-partial-audit/v0.1'
AUDITED = 'audited_reuse'
CARRIED = 'carried_immutable_proof'


def advance_with_receipts(*, freshness: dict[str, dict[str, Any]], sequence: int,
                          modes: dict[str, str], audit_receipts: dict[str, dict[str, Any]] | None = None,
                          max_carried_generations: dict[str, int | None] | None = None) -> dict[str, Any]:
    """Require real audit-work evidence before an audited freshness reset.

    No next freshness set is exposed if receipt validation or the underlying transition holds.
    """
    receipts = audit_receipts or {}
    if set(freshness) != set(modes):
        return {
            'schema': SCHEMA, 'status': 'HOLD', 'reason': 'MODE_COVERAGE_MISMATCH',
            'truth': {'partial_freshness_transition_not_exposed': True},
        }

    audited_contracts = {cid for cid, mode in modes.items() if mode == AUDITED}
    carried_contracts = {cid for cid, mode in modes.items() if mode == CARRIED}
    unknown = {cid: mode for cid, mode in modes.items() if mode not in (AUDITED, CARRIED)}
    if unknown:
        return {
            'schema': SCHEMA, 'status': 'HOLD', 'reason': 'UNKNOWN_VERIFICATION_MODE',
            'unknown_modes': unknown,
            'truth': {'partial_freshness_transition_not_exposed': True},
        }
    extra_receipts = sorted(set(receipts) - audited_contracts)
    if extra_receipts:
        return {
            'schema': SCHEMA, 'status': 'HOLD', 'reason': 'UNEXPECTED_AUDIT_RECEIPT',
            'contracts': extra_receipts,
            'truth': {'partial_freshness_transition_not_exposed': True},
        }
    missing_receipts = sorted(audited_contracts - set(receipts))
    if missing_receipts:
        return {
            'schema': SCHEMA, 'status': 'HOLD', 'reason': 'AUDIT_RECEIPT_REQUIRED',
            'contracts': missing_receipts,
            'truth': {'partial_freshness_transition_not_exposed': True},
        }

    validated_receipt_ids: dict[str, str] = {}
    try:
        for cid in sorted(audited_contracts):
            validate_audit_receipt(receipt=receipts[cid], state=freshness[cid], sequence=sequence)
            validated_receipt_ids[cid] = receipts[cid]['receipt_sha256']
    except (KeyError, TypeError, ValueError) as exc:
        return {
            'schema': SCHEMA, 'status': 'HOLD', 'reason': 'AUDIT_RECEIPT_INVALID',
            'detail': str(exc),
            'truth': {'partial_freshness_transition_not_exposed': True},
        }

    result = advance_freshness_set(
        freshness=freshness,
        sequence=sequence,
        modes=modes,
        max_carried_generations=max_carried_generations,
    )
    if result.get('status') != 'ADVANCED':
        return {
            'schema': SCHEMA,
            'status': 'HOLD',
            'reason': 'UNDERLYING_FRESHNESS_TRANSITION_HELD',
            'held_result': result,
            'validated_audit_receipts': validated_receipt_ids,
            'truth': {'partial_freshness_transition_not_exposed': True},
        }
    return {
        'schema': SCHEMA,
        'status': 'ADVANCED',
        'sequence': int(sequence),
        'freshness': result['freshness'],
        'modes': dict(modes),
        'validated_audit_receipts': validated_receipt_ids,
        'truth': {
            'audited_freshness_reset_requires_validated_audit_work_receipt': True,
            'carried_mode_does_not_claim_fresh_byte_verification': True,
            'all_registered_contracts_advance_or_none_are_exposed': True,
        },
    }
