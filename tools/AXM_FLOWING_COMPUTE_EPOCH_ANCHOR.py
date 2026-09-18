from __future__ import annotations

import fcntl
import json
import os
import shutil
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any

import AXM_FLOWING_COMPUTE_RETENTION_EPOCH_CAS as w84

SCHEMA = 'axm.flowing-compute-epoch-anchor/v0.1'


def _body(obj: dict[str, Any], hash_key: str) -> dict[str, Any]:
    out = dict(obj)
    out.pop(hash_key, None)
    return out


def make_anchor(pointer: dict[str, Any], predecessor_anchor_sha256: str | None, note: str) -> dict[str, Any]:
    w84.validate_pointer(pointer)
    epoch = pointer['commit_epoch']
    if epoch == 0 and predecessor_anchor_sha256 is not None:
        raise ValueError('genesis anchor cannot have predecessor')
    if epoch > 0 and (not isinstance(predecessor_anchor_sha256, str) or len(predecessor_anchor_sha256) != 64):
        raise ValueError('nonzero anchor requires predecessor')
    anchor = {
        'schema': SCHEMA,
        'anchor_epoch': epoch,
        'pointer_sha256': w84.pointer_id(pointer),
        'retention_sha256': pointer['retention_sha256'],
        'pointer_predecessor_sha256': pointer['predecessor_pointer_sha256'],
        'selection_kind': pointer['selection_kind'],
        'predecessor_anchor_sha256': predecessor_anchor_sha256,
        'note': note,
        'truth': {
            'separate_failure_domain_required_for_rewind_detection': True,
            'anchor_is_commit_decision_not_actor_identity': True,
            'retention_rollback_may_select_old_content_without_rewinding_anchor_epoch': True,
            'combined_primary_and_anchor_rollback_is_not_detectable_by_this_software_only_contract': True,
        },
    }
    anchor['anchor_sha256'] = w84.dig(anchor)
    return anchor


def validate_anchor(anchor: dict[str, Any]) -> None:
    if anchor.get('schema') != SCHEMA:
        raise ValueError('anchor schema mismatch')
    key = anchor.get('anchor_sha256')
    if not isinstance(key, str) or key != w84.dig(_body(anchor, 'anchor_sha256')):
        raise ValueError('anchor integrity mismatch')
    epoch = anchor.get('anchor_epoch')
    if not isinstance(epoch, int) or epoch < 0:
        raise ValueError('anchor epoch invalid')
    for name in ('pointer_sha256', 'retention_sha256'):
        if not isinstance(anchor.get(name), str) or len(anchor[name]) != 64:
            raise ValueError(f'{name} shape')
    pred = anchor.get('predecessor_anchor_sha256')
    if epoch == 0 and pred is not None:
        raise ValueError('genesis predecessor mismatch')
    if epoch > 0 and (not isinstance(pred, str) or len(pred) != 64):
        raise ValueError('anchor predecessor missing')


class AnchorLedger:
    """Append-only-by-file ledger kept outside the primary pointer/object store."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.lock = self.path / '.lock'
        self.lock.touch(exist_ok=True)

    def records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for path in sorted(self.path.glob('*.json')):
            anchor = json.loads(path.read_text())
            validate_anchor(anchor)
            expected = f"{anchor['anchor_epoch']:020d}-{anchor['anchor_sha256']}.json"
            if path.name != expected:
                raise ValueError('anchor filename/body mismatch')
            records.append(anchor)
        records.sort(key=lambda a: a['anchor_epoch'])
        for index, anchor in enumerate(records):
            if anchor['anchor_epoch'] != index:
                raise ValueError('anchor epoch gap/duplicate')
            expected_pred = None if index == 0 else records[index - 1]['anchor_sha256']
            if anchor['predecessor_anchor_sha256'] != expected_pred:
                raise ValueError('anchor chain mismatch')
        return records

    def latest(self) -> dict[str, Any]:
        records = self.records()
        if not records:
            raise ValueError('anchor ledger empty')
        return records[-1]

    def append(self, pointer: dict[str, Any], note: str) -> dict[str, Any]:
        with self.lock.open('rb') as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            records = self.records()
            predecessor = records[-1]['anchor_sha256'] if records else None
            expected_epoch = len(records)
            if pointer['commit_epoch'] != expected_epoch:
                raise ValueError('anchor append must advance exactly one epoch')
            anchor = make_anchor(pointer, predecessor, note)
            target = self.path / f"{expected_epoch:020d}-{anchor['anchor_sha256']}.json"
            with target.open('xb') as out:
                out.write(w84.canon(anchor))
                out.flush()
                os.fsync(out.fileno())
            dfd = os.open(str(self.path), os.O_DIRECTORY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
            return anchor


def validate_binding(anchor: dict[str, Any], pointer: dict[str, Any]) -> None:
    validate_anchor(anchor)
    w84.validate_pointer(pointer)
    expected = (
        anchor['anchor_epoch'], anchor['pointer_sha256'], anchor['retention_sha256'],
        anchor['pointer_predecessor_sha256'], anchor['selection_kind'],
    )
    actual = (
        pointer['commit_epoch'], w84.pointer_id(pointer), pointer['retention_sha256'],
        pointer['predecessor_pointer_sha256'], pointer['selection_kind'],
    )
    if expected != actual:
        raise ValueError('anchor/pointer binding mismatch')


def initialize(pointer_path: str | Path, pointer_store_path: str | Path, anchor_path: str | Path) -> dict[str, Any]:
    pointer = w84.initialize(pointer_path, pointer_store_path, w84.W81_RETENTION_SHA)
    ledger = AnchorLedger(anchor_path)
    if ledger.records():
        raise ValueError('anchor ledger must be empty')
    anchor = ledger.append(pointer, 'Wave85 genesis over exact Wave84/Wave81 starting pointer')
    validate_binding(anchor, pointer)
    return pointer


def recovery_status(pointer_path: str | Path, pointer_store_path: str | Path,
                    anchor_path: str | Path, repair: bool = False) -> dict[str, Any]:
    current = w84.read_current(pointer_path, pointer_store_path)
    latest = AnchorLedger(anchor_path).latest()
    current_epoch = current['commit_epoch']
    anchor_epoch = latest['anchor_epoch']

    if current_epoch == anchor_epoch:
        try:
            validate_binding(latest, current)
        except Exception as exc:
            return {'status': 'DIVERGENCE', 'error': str(exc)}
        return {'status': 'CONSISTENT', 'epoch': current_epoch}

    if current_epoch > anchor_epoch:
        return {'status': 'UNANCHORED_POINTER_ADVANCE', 'current_epoch': current_epoch, 'anchor_epoch': anchor_epoch}

    if anchor_epoch == current_epoch + 1:
        store = w84.PointerStore(pointer_store_path)
        try:
            target = store.get(latest['pointer_sha256'])
            validate_binding(latest, target)
        except Exception as exc:
            return {'status': 'REWIND_DETECTED_MISSING_COMMITTED_POINTER',
                    'current_epoch': current_epoch, 'anchor_epoch': anchor_epoch, 'error': str(exc)}
        if target['predecessor_pointer_sha256'] != w84.pointer_id(current):
            return {'status': 'REWIND_DETECTED_PREDECESSOR_MISMATCH',
                    'current_epoch': current_epoch, 'anchor_epoch': anchor_epoch}
        if not repair:
            return {'status': 'ANCHORED_COMMIT_PENDING_POINTER_MOVE',
                    'current_epoch': current_epoch, 'anchor_epoch': anchor_epoch}
        w84._durable_replace(Path(pointer_path), w84.canon(target))
        return {'status': 'RECOVERED_ANCHORED_COMMIT', 'epoch': target['commit_epoch']}

    return {'status': 'REWIND_DETECTED_MULTI_EPOCH',
            'current_epoch': current_epoch, 'anchor_epoch': anchor_epoch}


def anchored_cas(*, pointer_path: str | Path, pointer_store_path: str | Path,
                 anchor_path: str | Path, expected_pointer: dict[str, Any],
                 candidate_retention_sha256: str, selection_kind: str = 'FORWARD',
                 note: str = '', crash_before_anchor: bool = False,
                 crash_after_anchor: bool = False, crash_after_replace: bool = False) -> dict[str, Any]:
    pointer_path = Path(pointer_path)
    lock = pointer_path.with_suffix(pointer_path.suffix + '.anchor-cas.lock')
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.touch(exist_ok=True)
    with lock.open('rb') as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        state = recovery_status(pointer_path, pointer_store_path, anchor_path)
        if state['status'] != 'CONSISTENT':
            return {'status': 'HOLD_RECOVERY_REQUIRED', 'recovery': state}
        current = w84.read_current(pointer_path, pointer_store_path)
        if w84.pointer_id(current) != w84.pointer_id(expected_pointer):
            return {'status': 'CONFLICT', 'current_epoch': current['commit_epoch']}
        if selection_kind not in ('FORWARD', 'ROLLBACK'):
            raise ValueError('selection kind')

        candidate = w84.make_pointer(
            commit_epoch=current['commit_epoch'] + 1,
            retention_sha256=candidate_retention_sha256,
            predecessor_pointer_sha256=w84.pointer_id(current),
            selection_kind=selection_kind,
            expected_prior_retention_sha256=current['retention_sha256'],
            note=note,
        )
        w84.PointerStore(pointer_store_path).put(candidate)
        if crash_before_anchor:
            return {'status': 'CRASH_BEFORE_ANCHOR', 'staged_pointer_sha256': w84.pointer_id(candidate)}

        anchor = AnchorLedger(anchor_path).append(candidate, f'commit decision: {note}')
        if crash_after_anchor:
            return {'status': 'CRASH_AFTER_ANCHOR_BEFORE_POINTER', 'anchor_sha256': anchor['anchor_sha256']}

        w84._durable_replace(pointer_path, w84.canon(candidate))
        if crash_after_replace:
            return {'status': 'CRASH_AFTER_POINTER', 'epoch': candidate['commit_epoch']}
        return {'status': 'COMMITTED', 'epoch': candidate['commit_epoch'],
                'pointer_sha256': w84.pointer_id(candidate), 'anchor_sha256': anchor['anchor_sha256']}


def _copy_primary(pointer: Path, store: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(pointer, destination / 'current.json')
    shutil.copytree(store, destination / 'objects', dirs_exist_ok=True)


def _restore_primary(source: Path, pointer: Path, store: Path) -> None:
    shutil.copy2(source / 'current.json', pointer)
    if store.exists():
        shutil.rmtree(store)
    shutil.copytree(source / 'objects', store)


def self_test(benchmark_rounds: int = 100) -> dict[str, Any]:
    checks: list[tuple[str, bool]] = []
    with tempfile.TemporaryDirectory(prefix='axm-wave85-') as tmp:
        root = Path(tmp)
        pointer = root / 'primary/current.json'; pointer.parent.mkdir(parents=True)
        store = root / 'primary/objects'; anchor = root / 'separate-anchor'
        a0 = initialize(pointer, store, anchor)
        backup_a0 = root / 'backup-a0'; _copy_primary(pointer, store, backup_a0)
        checks.append(('genesis_exact_wave81', a0['retention_sha256'] == w84.W81_RETENTION_SHA))
        checks.append(('genesis_consistent', recovery_status(pointer, store, anchor)['status'] == 'CONSISTENT'))

        pre = anchored_cas(pointer_path=pointer, pointer_store_path=store, anchor_path=anchor,
                           expected_pointer=a0, candidate_retention_sha256=w84.W83_DROP_RETENTION_SHA,
                           note='pre-anchor crash', crash_before_anchor=True)
        checks.append(('pre_anchor_crash_zero_authority', pre['status'] == 'CRASH_BEFORE_ANCHOR' and w84.read_current(pointer, store)['commit_epoch'] == 0))

        mid = anchored_cas(pointer_path=pointer, pointer_store_path=store, anchor_path=anchor,
                           expected_pointer=a0, candidate_retention_sha256=w84.W83_DROP_RETENTION_SHA,
                           note='write-ahead anchor crash', crash_after_anchor=True)
        checks.append(('anchored_pending_detected', mid['status'] == 'CRASH_AFTER_ANCHOR_BEFORE_POINTER' and recovery_status(pointer, store, anchor)['status'] == 'ANCHORED_COMMIT_PENDING_POINTER_MOVE'))
        checks.append(('anchored_pending_recovered', recovery_status(pointer, store, anchor, repair=True)['status'] == 'RECOVERED_ANCHORED_COMMIT'))
        b1 = w84.read_current(pointer, store)
        backup_b1 = root / 'backup-b1'; _copy_primary(pointer, store, backup_b1)

        rb = anchored_cas(pointer_path=pointer, pointer_store_path=store, anchor_path=anchor,
                          expected_pointer=b1, candidate_retention_sha256=w84.W81_RETENTION_SHA,
                          selection_kind='ROLLBACK', note='intentional retention rollback')
        checks.append(('ordinary_rollback_allowed', rb['status'] == 'COMMITTED' and w84.read_current(pointer, store)['commit_epoch'] == 2))
        checks.append(('rollback_still_anchor_consistent', recovery_status(pointer, store, anchor)['status'] == 'CONSISTENT'))

        _restore_primary(backup_a0, pointer, store)
        checks.append(('multi_epoch_primary_rewind_detected', recovery_status(pointer, store, anchor)['status'] == 'REWIND_DETECTED_MULTI_EPOCH'))
        _restore_primary(backup_b1, pointer, store)
        checks.append(('one_epoch_rewind_missing_committed_object_detected', recovery_status(pointer, store, anchor)['status'] == 'REWIND_DETECTED_MISSING_COMMITTED_POINTER'))

    with tempfile.TemporaryDirectory(prefix='axm-wave85-tamper-') as tmp:
        root = Path(tmp); pointer = root/'p/current.json'; pointer.parent.mkdir(parents=True)
        store = root/'p/objects'; anchor = root/'anchor'
        p0 = initialize(pointer, store, anchor)
        anchored_cas(pointer_path=pointer, pointer_store_path=store, anchor_path=anchor,
                     expected_pointer=p0, candidate_retention_sha256=w84.W83_KEEP_RETENTION_SHA, note='tamper base')
        latest = AnchorLedger(anchor).latest()
        path = anchor / f"{latest['anchor_epoch']:020d}-{latest['anchor_sha256']}.json"
        raw = path.read_bytes(); bad = json.loads(raw); bad['retention_sha256'] = w84.W81_RETENTION_SHA; path.write_text(json.dumps(bad))
        try:
            AnchorLedger(anchor).records(); rejected = False
        except Exception:
            rejected = True
        checks.append(('direct_anchor_tamper_rejected', rejected)); path.write_bytes(raw)

        path.unlink()
        checks.append(('anchor_truncation_detected', recovery_status(pointer, store, anchor)['status'] == 'UNANCHORED_POINTER_ADVANCE'))
        path.write_bytes(raw)

        # Limitation: restoring both failure domains together leaves no newer surviving fact.
        gptr = root/'g/current.json'; gptr.parent.mkdir(parents=True)
        gstore = root/'g/objects'; ganchor = root/'g-anchor'; initialize(gptr, gstore, ganchor)
        shutil.copy2(gptr, pointer); shutil.rmtree(store); shutil.copytree(gstore, store); shutil.rmtree(anchor); shutil.copytree(ganchor, anchor)
        checks.append(('counterexample_combined_rollback_not_detected', recovery_status(pointer, store, anchor)['status'] == 'CONSISTENT'))

    samples: list[float] = []
    for _ in range(benchmark_rounds):
        with tempfile.TemporaryDirectory(prefix='axm-wave85-bench-') as tmp:
            root = Path(tmp); pointer = root/'p/current.json'; pointer.parent.mkdir(parents=True)
            store = root/'p/objects'; anchor = root/'a'; p0 = initialize(pointer, store, anchor)
            start = time.process_time_ns()
            result = anchored_cas(pointer_path=pointer, pointer_store_path=store, anchor_path=anchor,
                                  expected_pointer=p0, candidate_retention_sha256=w84.W83_KEEP_RETENTION_SHA,
                                  note='synthetic anchor overhead benchmark')
            samples.append((time.process_time_ns() - start) / 1000.0)
            if result['status'] != 'COMMITTED':
                raise AssertionError(result)

    passed = sum(ok for _, ok in checks)
    return {
        'schema': 'axm.flowing-compute-wave85-selftest/v0.1',
        'status': 'PASS' if passed == len(checks) else 'FAIL',
        'passed': passed,
        'total': len(checks),
        'checks': [{'name': name, 'pass': ok} for name, ok in checks],
        'benchmark': {'rounds': benchmark_rounds, 'median_process_cpu_us': statistics.median(samples)},
        'truth_boundary': {
            'fresh_monolith_audit': False,
            'compute_efficiency_claim': False,
            'trusted_hardware_claim': False,
            'combined_primary_and_anchor_rollback_detectable': False,
        },
    }


if __name__ == '__main__':
    print(json.dumps(self_test(), indent=2, sort_keys=True))
