from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / 'tools' / 'AXM_FLOWING_COMPUTE_RETENTION_EPOCH_CAS.py'

spec = importlib.util.spec_from_file_location('wave84_builder', MODULE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f'cannot load {MODULE_PATH}')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

report = {
    'schema': 'axm.flowing-compute-wave84-adversarial-verifier/v0.1',
    'builder_module': str(MODULE_PATH.relative_to(ROOT)),
    'primary': {},
    'secondary': {},
}

# Primary: initialize() can be called on an already-live pointer/store and rewinds
# the current pointer all the way back to the exact epoch-0 object.
with tempfile.TemporaryDirectory(prefix='axm-wave84-verifier-reinit-') as td:
    base = Path(td)
    ptr = base / 'current.json'
    store = base / 'pointer_objects'

    a0 = m.initialize(ptr, store, m.W81_RETENTION_SHA)
    forward = m.epoch_cas(
        pointer_path=ptr,
        pointer_store_path=store,
        expected_pointer=a0,
        candidate_retention_sha256=m.W83_DROP_RETENTION_SHA,
        selection_kind='FORWARD',
        note='verifier: advance before reinitialize attack',
    )
    b1 = m.read_current(ptr, store)
    assert forward['status'] == 'COMMITTED'
    assert b1['commit_epoch'] == 1
    assert m.pointer_id(b1) != m.pointer_id(a0)

    rewound = m.initialize(ptr, store, m.W81_RETENTION_SHA)
    after_reinit = m.read_current(ptr, store)
    assert after_reinit['commit_epoch'] == 0
    assert m.pointer_id(after_reinit) == m.pointer_id(a0)
    assert m.pointer_id(rewound) == m.pointer_id(a0)

    stale_writer = m.epoch_cas(
        pointer_path=ptr,
        pointer_store_path=store,
        expected_pointer=a0,  # captured before the epoch-1 commit
        candidate_retention_sha256=m.W83_KEEP_RETENTION_SHA,
        selection_kind='FORWARD',
        note='verifier: stale A0 writer after reinitialize rewind',
    )
    assert stale_writer['status'] == 'COMMITTED'
    assert stale_writer['commit_epoch'] == 1

    report['primary'] = {
        'status': 'REPRODUCED',
        'sequence': ['A@0', 'B@1', 'initialize(A@0)', 'stale-A0-writer COMMITTED'],
        'a0_pointer_sha256': m.pointer_id(a0),
        'b1_pointer_sha256': m.pointer_id(b1),
        'reinitialized_pointer_sha256': m.pointer_id(after_reinit),
        'stale_writer_status': stale_writer['status'],
        'stale_writer_epoch': stale_writer['commit_epoch'],
    }

# Secondary: the official epoch_cas() path accepts any 64-character retention
# identity. A ROLLBACK does not prove that the target retention exists or is an
# ancestor/previously selected retention object.
with tempfile.TemporaryDirectory(prefix='axm-wave84-verifier-fake-retention-') as td:
    base = Path(td)
    ptr = base / 'current.json'
    store = base / 'pointer_objects'
    a0 = m.initialize(ptr, store, m.W81_RETENTION_SHA)
    nonexistent_retention = 'f' * 64
    fake_rollback = m.epoch_cas(
        pointer_path=ptr,
        pointer_store_path=store,
        expected_pointer=a0,
        candidate_retention_sha256=nonexistent_retention,
        selection_kind='ROLLBACK',
        note='verifier: nonexistent retention accepted as rollback target',
    )
    current = m.read_current(ptr, store)
    assert fake_rollback['status'] == 'COMMITTED'
    assert current['retention_sha256'] == nonexistent_retention
    assert current['selection_kind'] == 'ROLLBACK'

    report['secondary'] = {
        'status': 'REPRODUCED',
        'rollback_status': fake_rollback['status'],
        'selected_retention_sha256': current['retention_sha256'],
        'selection_kind': current['selection_kind'],
        'retention_existence_checked_by_epoch_cas': False,
    }

report['overall'] = 'FAIL_BOUNDED_WAVE84_RECOVERY_SEMANTICS'
print(json.dumps(report, indent=2, sort_keys=True))
