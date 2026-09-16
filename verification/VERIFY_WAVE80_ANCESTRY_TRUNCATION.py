from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))

from AXM_FLOWING_COMPUTE_AUDIT_BOUND_GENERATION import (  # noqa: E402
    SCHEMA,
    AUDITED,
    CARRIED,
    digest,
    validate_pointer,
    validate_chain,
)
from AXM_FLOWING_COMPUTE_VERIFICATION_FRESHNESS import start, advance  # noqa: E402

CID = 'verifier.demo.contract/v0.1'


def finish_pointer(body: dict) -> dict:
    pointer = dict(body)
    pointer['pointer_sha256'] = digest(body)
    return pointer


def main() -> None:
    g0_state = start(
        contract_id=CID,
        artifact_sha256='a' * 64,
        artifact_bytes=4096,
        proof_sha256='b' * 64,
        audited_sequence=0,
    )

    # Poisoned audited predecessor: its receipt reference has valid shape but no
    # receipt body exists in any store used below.
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

    # Current standalone Wave80 validation accepts it: receipt body resolution is
    # performed only by validate_chain(), not validate_pointer().
    validate_pointer(poisoned_g1)

    # The next generation carries prior proof and therefore has no current receipt.
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

    # Counterexample: validate_chain() checks the predecessor with standalone
    # validate_pointer(), then resolves receipt bodies only for carried_g2. Because
    # G2 has no fresh receipt, the empty store is never asked for G1's missing body.
    validate_chain(
        previous_pointer=poisoned_g1,
        pointer=carried_g2,
        audit_receipt_store={},
    )

    print('COUNTEREXAMPLE: PASS')
    print('one-hop validate_chain accepted a carried child whose audited predecessor')
    print('receipt body was never resolved in this validation call')


if __name__ == '__main__':
    main()
