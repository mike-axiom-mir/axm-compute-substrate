from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

import AXM_FLOWING_COMPUTE_RETENTION_EPOCH_CAS as w84
import AXM_FLOWING_COMPUTE_EPOCH_ANCHOR as w85


def main() -> int:
    report: dict[str, object] = {
        'schema': 'axm.flowing-compute-wave85-adversarial-verifier/v0.1',
        'builder_head': '1a88cdafff7fee0134fdec903a9ee0b74b2562d8',
        'claim': 'Wave85 latest-anchor consistency does not by itself prove pointer-history continuity across anchor epochs',
    }

    # Primary counterexample: keep the exact same Wave85 anchor ledger, switch the
    # primary to a different epoch-0 branch using the published Wave84 API, then
    # append the alternate branch's epoch-1 pointer through the public Wave85
    # AnchorLedger.append() API.  No anchor file is deleted or rewritten.
    with tempfile.TemporaryDirectory(prefix='axm-wave85-verifier-') as tmp:
        root = Path(tmp)
        pointer = root / 'primary/current.json'
        pointer.parent.mkdir(parents=True)
        store = root / 'primary/objects'
        anchor = root / 'separate-anchor'

        original_a0 = w85.initialize(pointer, store, anchor)
        original_a0_id = w84.pointer_id(original_a0)

        # Establish a different but syntactically valid epoch-0 primary branch
        # using an exact retention identity already present in the builder.
        alternate_b0 = w84.initialize(pointer, store, w84.W83_DROP_RETENTION_SHA)
        before_append = w85.recovery_status(pointer, store, anchor)

        step = w84.epoch_cas(
            pointer_path=pointer,
            pointer_store_path=store,
            expected_pointer=alternate_b0,
            candidate_retention_sha256=w84.W83_KEEP_RETENTION_SHA,
            selection_kind='FORWARD',
            note='verifier alternate primary branch',
        )
        if step['status'] != 'COMMITTED':
            raise AssertionError(step)
        alternate_c1 = w84.read_current(pointer, store)

        appended = w85.AnchorLedger(anchor).append(
            alternate_c1,
            'verifier: append alternate branch without proving prior anchor pointer continuity',
        )
        after_append = w85.recovery_status(pointer, store, anchor)
        records = w85.AnchorLedger(anchor).records()

        predecessor_mismatch = (
            alternate_c1['predecessor_pointer_sha256'] != records[0]['pointer_sha256']
        )

        # The important boundary: the anchor correctly reports divergence before
        # the append, but the public append can launder the disconnected branch
        # into a latest state that recovery_status labels CONSISTENT.
        assert before_append['status'] == 'DIVERGENCE', before_append
        assert predecessor_mismatch
        assert records[0]['pointer_sha256'] == original_a0_id
        assert records[1]['pointer_sha256'] == w84.pointer_id(alternate_c1)
        assert records[1]['predecessor_anchor_sha256'] == records[0]['anchor_sha256']
        assert after_append['status'] == 'CONSISTENT', after_append

        report['history_discontinuity'] = {
            'status_before_append': before_append['status'],
            'status_after_append': after_append['status'],
            'anchor0_pointer_sha256': records[0]['pointer_sha256'],
            'alternate_epoch0_pointer_sha256': w84.pointer_id(alternate_b0),
            'anchor1_pointer_predecessor_sha256': records[1]['pointer_predecessor_sha256'],
            'anchor0_pointer_equals_anchor1_pointer_predecessor': not predecessor_mismatch,
            'same_anchor_directory_used': True,
            'anchor_files_rewritten_or_deleted': False,
            'latest_anchor_sha256': appended['anchor_sha256'],
        }

    # Secondary boundary: Wave85 initialize() calls Wave84 initialize() before
    # checking whether the anchor ledger is empty.  A rejected second initialize
    # therefore mutates the primary pointer first.  The surviving anchor catches
    # it, so this is recoverable fail-after-mutation, not silent history loss.
    with tempfile.TemporaryDirectory(prefix='axm-wave85-init-order-') as tmp:
        root = Path(tmp)
        pointer = root / 'primary/current.json'
        pointer.parent.mkdir(parents=True)
        store = root / 'primary/objects'
        anchor = root / 'separate-anchor'

        p0 = w85.initialize(pointer, store, anchor)
        committed = w85.anchored_cas(
            pointer_path=pointer,
            pointer_store_path=store,
            anchor_path=anchor,
            expected_pointer=p0,
            candidate_retention_sha256=w84.W83_DROP_RETENTION_SHA,
            note='verifier initialize-order base',
        )
        if committed['status'] != 'COMMITTED':
            raise AssertionError(committed)
        epoch_before = w84.read_current(pointer, store)['commit_epoch']

        rejected = False
        error = None
        try:
            w85.initialize(pointer, store, anchor)
        except Exception as exc:
            rejected = True
            error = str(exc)

        epoch_after = w84.read_current(pointer, store)['commit_epoch']
        recovery = w85.recovery_status(pointer, store, anchor)
        assert rejected
        assert epoch_before == 1 and epoch_after == 0
        assert recovery['status'] == 'ANCHORED_COMMIT_PENDING_POINTER_MOVE', recovery

        report['initialize_fail_after_mutation'] = {
            'initialize_rejected': rejected,
            'error': error,
            'primary_epoch_before': epoch_before,
            'primary_epoch_after_rejection': epoch_after,
            'recovery_status_after_rejection': recovery['status'],
            'interpretation': 'surviving anchor catches the rewind, but rejected initialize is not side-effect-free',
        }

    report['verdict'] = {
        'narrow_whole_store_rewind_detection_survives': True,
        'full_anchor_pointer_history_continuity_proven': False,
        'suggested_gate': 'bind each new anchor pointer predecessor to the prior anchor pointer identity and revalidate that cross-chain invariant on load; make initialize creation-only and preflight anchor state before touching primary storage',
    }

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
