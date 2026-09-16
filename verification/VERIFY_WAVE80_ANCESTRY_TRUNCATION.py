from __future__ import annotations

from tools.AXM_FLOWING_COMPUTE_AUDIT_BOUND_GENERATION import (
    SCHEMA,
    AUDITED,
    CARRIED,
    digest,
    validate_pointer,
    validate_chain,
)
from tools.AXM_FLOWING_COMPUTE_VERIFICATION_FRESHNESS import start, advance

CID = 'verifier.demo.contract/v0.1'


def finish_pointer(body: dict) -> dict:
    pointer = dict(body)
    pointer['pointer_sha256'] = digest(body)
    return pointer


def main() -> None:
    # G0 is a normal freshness state.
    g0_state = start(
        contract_id=CID,
        artifact_sha256='a' * 64,
        artifact_bytes=4096,
        proof_sha256='b' * 64,
        audited_sequence=0,
    )

    # Build a *locally valid* G1 Wave80 pointer that claims an audit at G1,
    # but whose receipt SHA has no body in any receipt store.
    g1_state = advance(
        state=g0_state,
        sequence=1,
        mode=AUDITED,
        artifact_sha256=g0_state['artifact_sha256'],
        proof_sha256=g0_state['proof_sha256'],
    )['state']

    poisoned_g1 = finish_pointer({
        'schema': SCHEMA,
        'sequence': 1,
        'generation_sha256': 'e' * 64,
        'previous_pointer_sha256': 'd' * 64,
        'freshness': {CID: g1_state},
        'modes': {CID: AUDITED},
        'audit_receipts': {
            CID: {
                'receipt_sha256': 'c' * 64,
                'sequence': 1,
                'predecessor_state_sha256': g0_state['state_sha256'],
            }
        },
        'truth': {
            'generation_freshness_and_audit_receipt_ids_share_one_commit_boundary': True,
            'audited_receipt_ids_are_revalidated_against_predecessor_freshness': True,
            'carried_reuse_commits_no_fresh_audit_receipt': True,
            'receipt_digest_is_integrity_not_actor_authentication': True,
        },
    })

    # Current standalone Wave80 validation accepts this pointer because it checks
    # receipt-reference shape, not receipt-body resolvability.
    validate_pointer(poisoned_g1)

    # G2 only carries the prior proof. It legitimately contains no new receipt.
    g2_state = advance(
        state=g1_state,
        sequence=2,
        mode=CARRIED,
        artifact_sha256=g1_state['artifact_sha256'],
        proof_sha256=g1_state['proof_sha256'],
    )['state']
    carried_g2 = finish_pointer({
        'schema': SCHEMA,
        'sequence': 2,
        'generation_sha256': 'f' * 64,
        'previous_pointer_sha256': poisoned_g1['pointer_sha256'],
        'freshness': {CID: g2_state},
        'modes': {CID: CARRIED},
        'audit_receipts': {},
        'truth': poisoned_g1['truth'],
    })

    # Counterexample: validate_chain only resolves receipt bodies on the *current*
    # pointer. It validates the predecessor only with validate_pointer(). Because
    # G2 has no current receipt, an empty store is sufficient and the poisoned G1
    # becomes a trusted predecessor anchor for this call.
    validate_chain(
        previous_pointer=poisoned_g1,
        pointer=carried_g2,
        audit_receipt_store={},
    )

    print('COUNTEREXAMPLE: PASS')
    print('Wave80 one-hop validate_chain accepted a carried child whose audited')
    print('predecessor receipt body was never resolved in this validation call.')


if __name__ == '__main__':
    main()
