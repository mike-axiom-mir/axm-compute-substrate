from __future__ import annotations

import json
import os
import shutil
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable

import AXM_FLOWING_COMPUTE_RETENTION_EPOCH_CAS as w84
import AXM_FLOWING_COMPUTE_EPOCH_ANCHOR as w85

SCHEMA = 'axm.flowing-compute-multi-anchor-witness/v0.1'
DEFAULT_WITNESS_IDS = ('witness-a', 'witness-b', 'witness-c')


def witness_paths(root: str | Path, ids: Iterable[str] = DEFAULT_WITNESS_IDS) -> dict[str, Path]:
    base = Path(root)
    return {wid: base / wid for wid in ids}


def _head_summary(anchor: dict[str, Any]) -> dict[str, Any]:
    return {
        'anchor_epoch': anchor['anchor_epoch'],
        'anchor_sha256': anchor['anchor_sha256'],
        'pointer_sha256': anchor['pointer_sha256'],
        'retention_sha256': anchor['retention_sha256'],
        'selection_kind': anchor['selection_kind'],
    }


def _read_heads(paths: dict[str, Path]) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    heads: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    for wid, path in sorted(paths.items()):
        if not path.is_dir():
            errors[wid] = 'witness path missing'
            continue
        try:
            heads[wid] = w85.AnchorLedger(path).latest()
        except Exception as exc:
            errors[wid] = f'{type(exc).__name__}: {exc}'
    return heads, errors


def _head_groups(heads: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for wid, anchor in heads.items():
        groups.setdefault(anchor['anchor_sha256'], []).append(wid)
    return {sha: sorted(ids) for sha, ids in sorted(groups.items())}


def _surviving_newer(heads: dict[str, dict[str, Any]], current_epoch: int | None) -> list[str]:
    if current_epoch is None:
        return []
    return sorted(wid for wid, head in heads.items() if head['anchor_epoch'] > current_epoch)


def initialize(pointer_path: str | Path, pointer_store_path: str | Path,
               paths: dict[str, Path]) -> dict[str, Any]:
    if len(paths) < 2 or len(set(paths)) != len(paths):
        raise ValueError('at least two distinct witness paths required')
    pointer = w84.initialize(pointer_path, pointer_store_path, w84.W81_RETENTION_SHA)
    anchors = []
    note = 'Wave86 genesis over exact Wave85/Wave84/Wave81 starting pointer'
    for wid, path in sorted(paths.items()):
        if path.exists() and any(path.iterdir()):
            raise ValueError(f'witness must start empty: {wid}')
        ledger = w85.AnchorLedger(path)
        anchor = ledger.append(pointer, note)
        w85.validate_binding(anchor, pointer)
        anchors.append(anchor['anchor_sha256'])
    if len(set(anchors)) != 1:
        raise AssertionError('identical genesis witnesses produced different content identities')
    return pointer


def witness_status(pointer_path: str | Path, pointer_store_path: str | Path,
                   paths: dict[str, Path], repair: bool = False) -> dict[str, Any]:
    try:
        current = w84.read_current(pointer_path, pointer_store_path)
        current_epoch: int | None = current['commit_epoch']
        current_sha: str | None = w84.pointer_id(current)
    except Exception as exc:
        current = None
        current_epoch = None
        current_sha = None
        primary_error = f'{type(exc).__name__}: {exc}'
    else:
        primary_error = None

    heads, errors = _read_heads(paths)
    summaries = {wid: _head_summary(a) for wid, a in sorted(heads.items())}

    if errors:
        return {
            'status': 'WITNESS_INCOMPLETE_HOLD',
            'primary_epoch': current_epoch,
            'primary_error': primary_error,
            'witness_errors': errors,
            'valid_witness_heads': summaries,
            'newer_surviving_witnesses': _surviving_newer(heads, current_epoch),
            'authority_selected': False,
        }
    if primary_error:
        return {
            'status': 'PRIMARY_INVALID_HOLD',
            'primary_error': primary_error,
            'valid_witness_heads': summaries,
            'authority_selected': False,
        }
    if not heads:
        return {'status': 'WITNESS_INCOMPLETE_HOLD', 'reason': 'no witness heads', 'authority_selected': False}

    groups = _head_groups(heads)
    if len(groups) != 1:
        return {
            'status': 'WITNESS_DIVERGENCE_HOLD',
            'primary_epoch': current_epoch,
            'primary_pointer_sha256': current_sha,
            'witness_groups': groups,
            'witness_heads': summaries,
            'newer_surviving_witnesses': _surviving_newer(heads, current_epoch),
            'authority_selected': False,
            'majority_vote_used': False,
            'newest_witness_wins': False,
        }

    common = next(iter(heads.values()))
    anchor_epoch = common['anchor_epoch']

    if current_epoch == anchor_epoch:
        try:
            w85.validate_binding(common, current)
        except Exception as exc:
            return {
                'status': 'PRIMARY_WITNESS_DIVERGENCE_HOLD',
                'primary_epoch': current_epoch,
                'witness_epoch': anchor_epoch,
                'error': str(exc),
                'authority_selected': False,
            }
        return {
            'status': 'CONSISTENT',
            'epoch': current_epoch,
            'witness_count': len(heads),
            'anchor_sha256': common['anchor_sha256'],
            'pointer_sha256': current_sha,
        }

    if current_epoch > anchor_epoch:
        return {
            'status': 'UNWITNESSED_POINTER_ADVANCE_HOLD',
            'primary_epoch': current_epoch,
            'witness_epoch': anchor_epoch,
            'authority_selected': False,
        }

    if anchor_epoch == current_epoch + 1:
        store = w84.PointerStore(pointer_store_path)
        try:
            target = store.get(common['pointer_sha256'])
            w85.validate_binding(common, target)
        except Exception as exc:
            return {
                'status': 'REWIND_DETECTED_MISSING_COMMITTED_POINTER',
                'primary_epoch': current_epoch,
                'witness_epoch': anchor_epoch,
                'error': str(exc),
                'authority_selected': False,
            }
        if target['predecessor_pointer_sha256'] != current_sha:
            return {
                'status': 'REWIND_DETECTED_PREDECESSOR_MISMATCH',
                'primary_epoch': current_epoch,
                'witness_epoch': anchor_epoch,
                'authority_selected': False,
            }
        if not repair:
            return {
                'status': 'UNANIMOUS_WITNESS_COMMIT_PENDING_POINTER_MOVE',
                'primary_epoch': current_epoch,
                'witness_epoch': anchor_epoch,
                'pointer_sha256': common['pointer_sha256'],
            }
        w84._durable_replace(Path(pointer_path), w84.canon(target))
        return {'status': 'RECOVERED_UNANIMOUS_WITNESS_COMMIT', 'epoch': target['commit_epoch']}

    return {
        'status': 'PRIMARY_REWIND_DETECTED_HOLD',
        'primary_epoch': current_epoch,
        'witness_epoch': anchor_epoch,
        'authority_selected': False,
    }


def multi_anchor_cas(*, pointer_path: str | Path, pointer_store_path: str | Path,
                     paths: dict[str, Path], expected_pointer: dict[str, Any],
                     candidate_retention_sha256: str, selection_kind: str = 'FORWARD',
                     note: str = '', crash_before_witnesses: bool = False,
                     crash_after_witness_count: int | None = None,
                     crash_after_all_witnesses: bool = False) -> dict[str, Any]:
    pointer_path = Path(pointer_path)
    lock = pointer_path.with_suffix(pointer_path.suffix + '.multi-anchor.lock')
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.touch(exist_ok=True)
    import fcntl
    with lock.open('rb') as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        state = witness_status(pointer_path, pointer_store_path, paths)
        if state['status'] != 'CONSISTENT':
            return {'status': 'HOLD_WITNESS_RECOVERY_REQUIRED', 'recovery': state}
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
        if crash_before_witnesses:
            return {'status': 'CRASH_BEFORE_WITNESSES', 'staged_pointer_sha256': w84.pointer_id(candidate)}

        anchor_ids: list[str] = []
        ordered = sorted(paths.items())
        if crash_after_witness_count is not None and not (1 <= crash_after_witness_count <= len(ordered)):
            raise ValueError('crash_after_witness_count out of range')
        for count, (wid, path) in enumerate(ordered, start=1):
            anchor = w85.AnchorLedger(path).append(candidate, f'Wave86 commit decision: {note}')
            anchor_ids.append(anchor['anchor_sha256'])
            if crash_after_witness_count == count:
                return {
                    'status': 'CRASH_DURING_WITNESS_FANOUT',
                    'witnesses_appended': count,
                    'witnesses_total': len(ordered),
                    'staged_pointer_sha256': w84.pointer_id(candidate),
                }
        if len(set(anchor_ids)) != 1:
            raise AssertionError('identical witness appends diverged unexpectedly')
        if crash_after_all_witnesses:
            return {
                'status': 'CRASH_AFTER_ALL_WITNESSES_BEFORE_POINTER',
                'witnesses_appended': len(ordered),
                'anchor_sha256': anchor_ids[0],
            }

        w84._durable_replace(pointer_path, w84.canon(candidate))
        return {
            'status': 'COMMITTED',
            'epoch': candidate['commit_epoch'],
            'pointer_sha256': w84.pointer_id(candidate),
            'anchor_sha256': anchor_ids[0],
            'witness_count': len(ordered),
        }


def _copy_dir(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def _restore_dir(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def _snapshot_all(pointer: Path, store: Path, paths: dict[str, Path], destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(pointer, destination / 'current.json')
    _copy_dir(store, destination / 'objects')
    for wid, path in paths.items():
        _copy_dir(path, destination / wid)


def _restore_primary(snapshot: Path, pointer: Path, store: Path) -> None:
    shutil.copy2(snapshot / 'current.json', pointer)
    _restore_dir(snapshot / 'objects', store)


def _restore_all(snapshot: Path, pointer: Path, store: Path, paths: dict[str, Path]) -> None:
    _restore_primary(snapshot, pointer, store)
    for wid, path in paths.items():
        _restore_dir(snapshot / wid, path)


def self_test(benchmark_rounds: int = 100) -> dict[str, Any]:
    checks: list[tuple[str, bool]] = []

    with tempfile.TemporaryDirectory(prefix='axm-wave86-core-') as tmp:
        root = Path(tmp); pointer = root/'primary/current.json'; pointer.parent.mkdir(parents=True)
        store = root/'primary/objects'; paths = witness_paths(root/'witnesses')
        a0 = initialize(pointer, store, paths)
        genesis = root/'snap-genesis'; _snapshot_all(pointer, store, paths, genesis)
        checks.append(('genesis_exact_wave81', a0['retention_sha256'] == w84.W81_RETENTION_SHA))
        checks.append(('three_witness_genesis_consistent', witness_status(pointer, store, paths)['status'] == 'CONSISTENT'))

        fwd = multi_anchor_cas(pointer_path=pointer, pointer_store_path=store, paths=paths,
                               expected_pointer=a0, candidate_retention_sha256=w84.W83_DROP_RETENTION_SHA,
                               note='Wave86 forward to exact Wave83 DROP retention')
        checks.append(('three_witness_forward_commits', fwd['status'] == 'COMMITTED'))
        b1 = w84.read_current(pointer, store)
        rb = multi_anchor_cas(pointer_path=pointer, pointer_store_path=store, paths=paths,
                              expected_pointer=b1, candidate_retention_sha256=w84.W81_RETENTION_SHA,
                              selection_kind='ROLLBACK', note='Wave86 intentional rollback to exact Wave81 retention')
        checks.append(('intentional_rollback_preserved', rb['status'] == 'COMMITTED' and w84.read_current(pointer, store)['commit_epoch'] == 2))
        snap2 = root/'snap-epoch2'; _snapshot_all(pointer, store, paths, snap2)
        checks.append(('epoch2_three_witness_consistent', witness_status(pointer, store, paths)['status'] == 'CONSISTENT'))

        _restore_primary(genesis, pointer, store)
        checks.append(('primary_only_rewind_detected', witness_status(pointer, store, paths)['status'] == 'PRIMARY_REWIND_DETECTED_HOLD'))
        _restore_all(snap2, pointer, store, paths)

        _restore_primary(genesis, pointer, store)
        _restore_dir(genesis/'witness-a', paths['witness-a'])
        s = witness_status(pointer, store, paths)
        checks.append(('primary_plus_one_witness_rewind_detected', s['status'] == 'WITNESS_DIVERGENCE_HOLD' and len(s['newer_surviving_witnesses']) == 2))
        _restore_all(snap2, pointer, store, paths)

        _restore_primary(genesis, pointer, store)
        _restore_dir(genesis/'witness-a', paths['witness-a'])
        _restore_dir(genesis/'witness-b', paths['witness-b'])
        s = witness_status(pointer, store, paths)
        checks.append(('single_newer_witness_exposes_rewind_without_authority',
                       s['status'] == 'WITNESS_DIVERGENCE_HOLD' and s['newer_surviving_witnesses'] == ['witness-c'] and not s['authority_selected']))

        _restore_all(genesis, pointer, store, paths)
        checks.append(('counterexample_all_domains_rollback_not_detected', witness_status(pointer, store, paths)['status'] == 'CONSISTENT'))

    with tempfile.TemporaryDirectory(prefix='axm-wave86-diverge-') as tmp:
        root = Path(tmp); pointer = root/'p/current.json'; pointer.parent.mkdir(parents=True)
        store = root/'p/objects'; paths = witness_paths(root/'w')
        a0 = initialize(pointer, store, paths)
        multi_anchor_cas(pointer_path=pointer, pointer_store_path=store, paths=paths,
                         expected_pointer=a0, candidate_retention_sha256=w84.W83_DROP_RETENTION_SHA, note='fork base B')
        b1 = w84.read_current(pointer, store)
        snap1 = root/'snap1'; _snapshot_all(pointer, store, paths, snap1)
        multi_anchor_cas(pointer_path=pointer, pointer_store_path=store, paths=paths,
                         expected_pointer=b1, candidate_retention_sha256=w84.W81_RETENTION_SHA,
                         selection_kind='ROLLBACK', note='clean A2')
        a2 = w84.read_current(pointer, store)
        clean2 = root/'clean2'; _snapshot_all(pointer, store, paths, clean2)

        _restore_dir(snap1/'witness-c', paths['witness-c'])
        alt2 = w84.make_pointer(commit_epoch=2, retention_sha256=w84.W83_KEEP_RETENTION_SHA,
                                predecessor_pointer_sha256=w84.pointer_id(b1), selection_kind='FORWARD',
                                expected_prior_retention_sha256=b1['retention_sha256'], note='valid minority fork')
        w85.AnchorLedger(paths['witness-c']).append(alt2, 'Wave86 valid minority fork')
        s = witness_status(pointer, store, paths)
        groups = sorted(len(v) for v in s.get('witness_groups', {}).values())
        checks.append(('valid_two_vs_one_fork_fails_closed_no_majority',
                       s['status'] == 'WITNESS_DIVERGENCE_HOLD' and groups == [1, 2] and not s['majority_vote_used']))
        _restore_all(clean2, pointer, store, paths)

        newer3 = w84.make_pointer(commit_epoch=3, retention_sha256=w84.W83_KEEP_RETENTION_SHA,
                                  predecessor_pointer_sha256=w84.pointer_id(a2), selection_kind='FORWARD',
                                  expected_prior_retention_sha256=a2['retention_sha256'], note='newer minority fork')
        w85.AnchorLedger(paths['witness-c']).append(newer3, 'Wave86 newer minority fork')
        s = witness_status(pointer, store, paths)
        checks.append(('newest_witness_does_not_win',
                       s['status'] == 'WITNESS_DIVERGENCE_HOLD' and s['newer_surviving_witnesses'] == ['witness-c'] and not s['newest_witness_wins']))
        _restore_all(clean2, pointer, store, paths)

        c_latest = w85.AnchorLedger(paths['witness-c']).latest()
        cfile = paths['witness-c']/f"{c_latest['anchor_epoch']:020d}-{c_latest['anchor_sha256']}.json"
        raw = cfile.read_bytes(); bad = json.loads(raw); bad['retention_sha256'] = w84.W83_KEEP_RETENTION_SHA; cfile.write_text(json.dumps(bad))
        checks.append(('corrupt_witness_holds', witness_status(pointer, store, paths)['status'] == 'WITNESS_INCOMPLETE_HOLD'))
        cfile.write_bytes(raw)

        cfile.unlink()
        checks.append(('truncated_witness_holds_without_silent_repair', witness_status(pointer, store, paths)['status'] == 'WITNESS_DIVERGENCE_HOLD'))
        cfile.write_bytes(raw)

        moved = root/'missing-witness-c'; paths['witness-c'].rename(moved)
        checks.append(('missing_witness_holds_no_two_of_three_quorum', witness_status(pointer, store, paths)['status'] == 'WITNESS_INCOMPLETE_HOLD'))
        moved.rename(paths['witness-c'])

    with tempfile.TemporaryDirectory(prefix='axm-wave86-crash-pre-') as tmp:
        root = Path(tmp); pointer = root/'p/current.json'; pointer.parent.mkdir(parents=True)
        store = root/'p/objects'; paths = witness_paths(root/'w'); a0 = initialize(pointer, store, paths)
        pre = multi_anchor_cas(pointer_path=pointer, pointer_store_path=store, paths=paths,
                               expected_pointer=a0, candidate_retention_sha256=w84.W83_DROP_RETENTION_SHA,
                               note='crash before any witness', crash_before_witnesses=True)
        checks.append(('pre_witness_crash_zero_authority', pre['status'] == 'CRASH_BEFORE_WITNESSES' and witness_status(pointer, store, paths)['status'] == 'CONSISTENT'))

    with tempfile.TemporaryDirectory(prefix='axm-wave86-crash-partial-') as tmp:
        root = Path(tmp); pointer = root/'p/current.json'; pointer.parent.mkdir(parents=True)
        store = root/'p/objects'; paths = witness_paths(root/'w'); a0 = initialize(pointer, store, paths)
        partial = multi_anchor_cas(pointer_path=pointer, pointer_store_path=store, paths=paths,
                                   expected_pointer=a0, candidate_retention_sha256=w84.W83_DROP_RETENTION_SHA,
                                   note='partial witness fanout crash', crash_after_witness_count=1)
        s = witness_status(pointer, store, paths)
        checks.append(('partial_witness_fanout_fails_closed', partial['status'] == 'CRASH_DURING_WITNESS_FANOUT' and s['status'] == 'WITNESS_DIVERGENCE_HOLD'))
        held = multi_anchor_cas(pointer_path=pointer, pointer_store_path=store, paths=paths,
                                expected_pointer=a0, candidate_retention_sha256=w84.W83_KEEP_RETENTION_SHA,
                                note='must not write through partial fanout')
        checks.append(('partial_fanout_blocks_new_commit', held['status'] == 'HOLD_WITNESS_RECOVERY_REQUIRED'))

    with tempfile.TemporaryDirectory(prefix='axm-wave86-crash-all-') as tmp:
        root = Path(tmp); pointer = root/'p/current.json'; pointer.parent.mkdir(parents=True)
        store = root/'p/objects'; paths = witness_paths(root/'w'); a0 = initialize(pointer, store, paths)
        allw = multi_anchor_cas(pointer_path=pointer, pointer_store_path=store, paths=paths,
                                expected_pointer=a0, candidate_retention_sha256=w84.W83_DROP_RETENTION_SHA,
                                note='all witness durable before pointer crash', crash_after_all_witnesses=True)
        pending = witness_status(pointer, store, paths)
        repaired = witness_status(pointer, store, paths, repair=True)
        checks.append(('unanimous_witness_pending_detected', allw['status'] == 'CRASH_AFTER_ALL_WITNESSES_BEFORE_POINTER' and pending['status'] == 'UNANIMOUS_WITNESS_COMMIT_PENDING_POINTER_MOVE'))
        checks.append(('unanimous_witness_pending_recoverable', repaired['status'] == 'RECOVERED_UNANIMOUS_WITNESS_COMMIT' and witness_status(pointer, store, paths)['status'] == 'CONSISTENT'))

    samples: list[float] = []
    for _ in range(benchmark_rounds):
        with tempfile.TemporaryDirectory(prefix='axm-wave86-bench-') as tmp:
            root = Path(tmp); pointer = root/'p/current.json'; pointer.parent.mkdir(parents=True)
            store = root/'p/objects'; paths = witness_paths(root/'w'); p0 = initialize(pointer, store, paths)
            start = time.process_time_ns()
            result = multi_anchor_cas(pointer_path=pointer, pointer_store_path=store, paths=paths,
                                      expected_pointer=p0, candidate_retention_sha256=w84.W83_KEEP_RETENTION_SHA,
                                      note='synthetic three-witness fanout benchmark')
            elapsed = (time.process_time_ns() - start) / 1000.0
            if result['status'] != 'COMMITTED':
                raise AssertionError(result)
            samples.append(elapsed)

    failed = [name for name, ok in checks if not ok]
    return {
        'schema': SCHEMA,
        'status': 'PASS' if not failed else 'FAIL',
        'checks_passed': sum(bool(ok) for _, ok in checks),
        'checks_total': len(checks),
        'failed_checks': failed,
        'checks': [{'name': name, 'passed': bool(ok)} for name, ok in checks],
        'benchmark': {
            'kind': 'synthetic single-host infrastructure fanout',
            'rounds': benchmark_rounds,
            'witnesses': len(DEFAULT_WITNESS_IDS),
            'median_process_cpu_us': statistics.median(samples),
            'min_process_cpu_us': min(samples),
            'max_process_cpu_us': max(samples),
            'truth': 'Process CPU for local JSON/hash/fsync orchestration; not wall-clock latency, joules, monolith workload timing, or a compute-efficiency result.',
        },
        'provenance': {
            'wave81_retention_sha256': w84.W81_RETENTION_SHA,
            'wave83_drop_retention_sha256': w84.W83_DROP_RETENTION_SHA,
            'wave83_keep_retention_sha256': w84.W83_KEEP_RETENTION_SHA,
            'fresh_monolith_audit': False,
        },
        'preserved_counterexample': 'If the primary and every configured software witness are rolled back together to one mutually consistent old snapshot, this software-only contract cannot prove the lost future.',
        'known_failure': 'A crash during witness fan-out leaves valid witnesses divergent and intentionally fails closed; Wave86 does not silently repair or vote through that partial fan-out.',
    }


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--benchmark-rounds', type=int, default=100)
    parser.add_argument('--out')
    args = parser.parse_args()
    report = self_test(args.benchmark_rounds)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(text + '\n')
    print(text)
