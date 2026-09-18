from __future__ import annotations
from typing import Any
from AXM_FLOWING_COMPUTE_VERIFICATION_FRESHNESS import advance, validate

SCHEMA = 'axm.flowing-compute-partial-audit-transition/v0.1'


def advance_freshness_set(*, freshness: dict[str, dict[str, Any]], sequence: int,
                          modes: dict[str, str],
                          max_carried_generations: dict[str, int | None] | None = None) -> dict[str, Any]:
    """Advance every registered freshness state as one logical transition.

    No partially advanced set is returned if any contract cannot advance.
    Caller may bind the resulting complete set into the atomic generation pointer.
    """
    if set(freshness) != set(modes):
        missing = sorted(set(freshness) - set(modes))
        extra = sorted(set(modes) - set(freshness))
        raise ValueError(f'mode coverage mismatch missing={missing} extra={extra}')
    limits = max_carried_generations or {}
    for state in freshness.values():
        validate(state)

    staged: dict[str, dict[str, Any]] = {}
    for contract_id in sorted(freshness):
        state = freshness[contract_id]
        result = advance(
            state=state,
            sequence=int(sequence),
            mode=modes[contract_id],
            artifact_sha256=state['artifact_sha256'],
            proof_sha256=state['proof_sha256'],
            max_carried_generations=limits.get(contract_id),
        )
        if result.get('status') != 'ADVANCED':
            return {
                'schema': SCHEMA,
                'status': 'HOLD',
                'sequence': int(sequence),
                'held_contract_id': contract_id,
                'held_result': result,
                'truth': {
                    'partial_freshness_transition_not_exposed': True,
                    'hold_does_not_advance_other_contracts': True,
                },
            }
        staged[contract_id] = result['state']

    return {
        'schema': SCHEMA,
        'status': 'ADVANCED',
        'sequence': int(sequence),
        'freshness': staged,
        'modes': dict(modes),
        'truth': {
            'all_registered_contracts_advanced_as_one_logical_transition': True,
            'per_contract_audit_mode_preserved': True,
        },
    }
