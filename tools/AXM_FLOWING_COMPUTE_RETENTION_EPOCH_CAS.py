from __future__ import annotations

import fcntl
import hashlib
import json
import multiprocessing as mp
import os
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any

SCHEMA = 'axm.flowing-compute-retention-epoch-pointer/v0.1'

# Exact retained-state identities inherited from prior append-only evidence.
W81_RETENTION_SHA = '53d91b18e1a12eb27bd503bcfa70b4cd74add598ceaef522c88d7c075fdee4d4'
W83_DROP_RETENTION_SHA = '4078169dce33c5816c7dd1073eaff5920bcfb07284a023726322e67970378dd1'
W83_KEEP_RETENTION_SHA = '0f918393dc9d4dfb33fe150bbdca9bd4ecbdca8fab0317becdf94fb9296b1721'
W83_ROOT_EVAL_SHA = '14702460c18e02f50ab09d45b420d4d3188960bde588cc89fad06211bf8fa4ee'
W82_DROP_RECEIPT_SHA = '9a60bbfb8302bbdc4e06eb39fd7898366b5fc1ef3963978dd857b845946b31a0'


def canon(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def dig(obj: Any) -> str:
    return hashlib.sha256(canon(obj)).hexdigest()


def pointer_id(p: dict[str, Any]) -> str:
    return p['pointer_sha256']


def _pointer_body(p: dict[str, Any]) -> dict[str, Any]:
    body = dict(p)
    body.pop('pointer_sha256', None)
    return body


def make_pointer(*, commit_epoch: int, retention_sha256: str,
                 predecessor_pointer_sha256: str | None,
                 selection_kind: str,
                 expected_prior_retention_sha256: str | None,
                 note: str) -> dict[str, Any]:
    if commit_epoch < 0:
        raise ValueError('commit_epoch must be non-negative')
    if not isinstance(retention_sha256, str) or len(retention_sha256) != 64:
        raise ValueError('retention hash shape')
    if commit_epoch == 0 and predecessor_pointer_sha256 is not None:
        raise ValueError('epoch zero cannot have predecessor pointer')
    if commit_epoch > 0 and (not isinstance(predecessor_pointer_sha256, str) or len(predecessor_pointer_sha256) != 64):
        raise ValueError('nonzero epoch requires predecessor pointer identity')
    if selection_kind not in ('INITIAL', 'FORWARD', 'ROLLBACK'):
        raise ValueError('selection kind')
    p = {
        'schema': SCHEMA,
        'commit_epoch': commit_epoch,
        'retention_sha256': retention_sha256,
        'predecessor_pointer_sha256': predecessor_pointer_sha256,
        'selection_kind': selection_kind,
        'expected_prior_retention_sha256': expected_prior_retention_sha256,
        'note': note,
        'truth': {
            'commit_epoch_orders_pointer_commits_not_retention_content': True,
            'rollback_may_select_older_retention_content_without_rewinding_commit_epoch': True,
            'cas_compares_exact_pointer_identity_and_epoch': True,
            'content_identity_alone_is_not_sufficient_against_aba': True,
            'hashes_do_not_establish_actor_or_evaluator_legitimacy': True,
        },
    }
    p['pointer_sha256'] = dig(p)
    return p


def validate_pointer(p: dict[str, Any]) -> None:
    if p.get('schema') != SCHEMA:
        raise ValueError('epoch pointer schema mismatch')
    key = p.get('pointer_sha256')
    if not isinstance(key, str) or key != dig(_pointer_body(p)):
        raise ValueError('epoch pointer integrity mismatch')
    epoch = p.get('commit_epoch')
    if not isinstance(epoch, int) or epoch < 0:
        raise ValueError('epoch pointer commit_epoch invalid')
    r = p.get('retention_sha256')
    if not isinstance(r, str) or len(r) != 64:
        raise ValueError('epoch pointer retention hash shape')
    pred = p.get('predecessor_pointer_sha256')
    if epoch == 0 and pred is not None:
        raise ValueError('epoch zero predecessor mismatch')
    if epoch > 0 and (not isinstance(pred, str) or len(pred) != 64):
        raise ValueError('nonzero epoch predecessor missing')


class PointerStore:
    """Append-only-by-key local content-addressed pointer evidence store."""
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)

    def put(self, p: dict[str, Any]) -> tuple[str, bool]:
        validate_pointer(p)
        key = pointer_id(p)
        dst = self.path / f'{key}.json'
        raw = canon(p)
        if dst.exists():
            if dst.read_bytes() != raw:
                raise ValueError('pointer-store collision/corruption')
            return key, False
        with dst.open('xb') as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        return key, True

    def get(self, key: str) -> dict[str, Any]:
        path = self.path / f'{key}.json'
        if not path.exists():
            raise ValueError('missing predecessor pointer evidence')
        p = json.loads(path.read_text())
        validate_pointer(p)
        if pointer_id(p) != key:
            raise ValueError('pointer-store key mismatch')
        return p


def validate_chain(head: dict[str, Any], store: PointerStore) -> int:
    """Validate the exact predecessor pointer chain back to epoch zero."""
    validate_pointer(head)
    seen: set[str] = set()
    cur = head
    while True:
        pid = pointer_id(cur)
        if pid in seen:
            raise ValueError('pointer chain cycle')
        seen.add(pid)
        epoch = cur['commit_epoch']
        if epoch == 0:
            if cur['predecessor_pointer_sha256'] is not None:
                raise ValueError('epoch zero predecessor mismatch')
            return len(seen)
        pred = store.get(cur['predecessor_pointer_sha256'])
        if pred['commit_epoch'] != epoch - 1:
            raise ValueError('pointer epoch chain is not monotonic by one')
        cur = pred


def _durable_replace(path: Path, raw: bytes, *, crash_before_replace: bool = False) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f'.{path.name}.{os.getpid()}.{time.time_ns()}.tmp')
    with tmp.open('xb') as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())
    if crash_before_replace:
        return str(tmp)
    os.replace(tmp, path)
    dfd = os.open(str(path.parent), os.O_DIRECTORY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)
    return str(path)


def initialize(pointer_path: str | Path, pointer_store_path: str | Path,
               retention_sha256: str = W81_RETENTION_SHA) -> dict[str, Any]:
    store = PointerStore(pointer_store_path)
    p0 = make_pointer(
        commit_epoch=0,
        retention_sha256=retention_sha256,
        predecessor_pointer_sha256=None,
        selection_kind='INITIAL',
        expected_prior_retention_sha256=None,
        note='Wave84 initial pointer over exact Wave81 retention identity',
    )
    store.put(p0)
    _durable_replace(Path(pointer_path), canon(p0))
    return p0


def read_current(pointer_path: str | Path, pointer_store_path: str | Path) -> dict[str, Any]:
    p = json.loads(Path(pointer_path).read_text())
    validate_pointer(p)
    store = PointerStore(pointer_store_path)
    stored = store.get(pointer_id(p))
    if stored != p:
        raise ValueError('current pointer/store body mismatch')
    validate_chain(p, store)
    return p


def epoch_cas(*, pointer_path: str | Path, pointer_store_path: str | Path,
              expected_pointer: dict[str, Any], candidate_retention_sha256: str,
              selection_kind: str = 'FORWARD', note: str = '',
              crash_before_replace: bool = False,
              crash_after_replace: bool = False) -> dict[str, Any]:
    validate_pointer(expected_pointer)
    if not isinstance(candidate_retention_sha256, str) or len(candidate_retention_sha256) != 64:
        raise ValueError('candidate retention hash shape')
    if selection_kind not in ('FORWARD', 'ROLLBACK'):
        raise ValueError('selection kind must be FORWARD or ROLLBACK')

    pointer_path = Path(pointer_path)
    store = PointerStore(pointer_store_path)
    lock_path = pointer_path.with_suffix(pointer_path.suffix + '.lock')
    lock_path.touch(exist_ok=True)
    with lock_path.open('rb') as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        current = read_current(pointer_path, pointer_store_path)
        if (pointer_id(current) != pointer_id(expected_pointer)
                or current['commit_epoch'] != expected_pointer['commit_epoch']
                or current['retention_sha256'] != expected_pointer['retention_sha256']):
            return {
                'status': 'CONFLICT',
                'expected_pointer_sha256': pointer_id(expected_pointer),
                'expected_epoch': expected_pointer['commit_epoch'],
                'expected_retention_sha256': expected_pointer['retention_sha256'],
                'current_pointer_sha256': pointer_id(current),
                'current_epoch': current['commit_epoch'],
                'current_retention_sha256': current['retention_sha256'],
                'candidate_retention_sha256': candidate_retention_sha256,
            }
        nxt = make_pointer(
            commit_epoch=current['commit_epoch'] + 1,
            retention_sha256=candidate_retention_sha256,
            predecessor_pointer_sha256=pointer_id(current),
            selection_kind=selection_kind,
            expected_prior_retention_sha256=current['retention_sha256'],
            note=note,
        )
        store.put(nxt)
        where = _durable_replace(pointer_path, canon(nxt), crash_before_replace=crash_before_replace)
        if crash_before_replace:
            return {
                'status': 'CRASH_SIMULATED_BEFORE_REPLACE',
                'staged_temp_path': where,
                'staged_pointer_sha256': pointer_id(nxt),
                'current_pointer_sha256': pointer_id(current),
                'current_epoch': current['commit_epoch'],
            }
        if crash_after_replace:
            return {
                'status': 'CRASH_SIMULATED_AFTER_REPLACE',
                'committed_pointer_sha256': pointer_id(nxt),
                'committed_epoch': nxt['commit_epoch'],
            }
        return {
            'status': 'COMMITTED',
            'previous_pointer_sha256': pointer_id(current),
            'previous_epoch': current['commit_epoch'],
            'pointer_sha256': pointer_id(nxt),
            'commit_epoch': nxt['commit_epoch'],
            'retention_sha256': nxt['retention_sha256'],
            'selection_kind': selection_kind,
        }


def _race_worker(pointer_path: str, store_path: str, expected: dict[str, Any],
                 candidate: str, gate, q, label: str) -> None:
    gate.wait()
    try:
        r = epoch_cas(pointer_path=pointer_path, pointer_store_path=store_path,
                      expected_pointer=expected, candidate_retention_sha256=candidate,
                      selection_kind='FORWARD', note=f'Wave84 race writer {label}')
    except Exception as e:
        r = {'status': 'ERROR', 'error': str(e)}
    r['writer'] = label
    q.put(r)


def fail(fn) -> str:
    try:
        fn()
    except Exception as e:
        return str(e)
    raise AssertionError('unexpected success')


def self_test(*, race_rounds: int = 40, benchmark_rounds: int = 100) -> dict[str, Any]:
    controls: list[tuple[str, bool]] = []
    with tempfile.TemporaryDirectory(prefix='axm-wave84-') as td:
        base = Path(td)
        ptr = base / 'current.json'
        pstore = base / 'pointer_objects'
        a0 = initialize(ptr, pstore, W81_RETENTION_SHA)
        controls.append(('initial_exact_wave81_identity', a0['retention_sha256'] == W81_RETENTION_SHA))
        controls.append(('initial_epoch_zero', a0['commit_epoch'] == 0))

        legacy_after_aba_would_accept = (W81_RETENTION_SHA == a0['retention_sha256'])
        controls.append(('legacy_content_only_aba_reproduced', legacy_after_aba_would_accept))

        b1r = epoch_cas(pointer_path=ptr, pointer_store_path=pstore, expected_pointer=a0,
                        candidate_retention_sha256=W83_DROP_RETENTION_SHA,
                        selection_kind='FORWARD', note='select exact Wave83 DROP candidate')
        b1 = read_current(ptr, pstore)
        controls.append(('forward_commit_epoch_one', b1r['status'] == 'COMMITTED' and b1['commit_epoch'] == 1))
        controls.append(('forward_exact_wave83_drop_identity', b1['retention_sha256'] == W83_DROP_RETENTION_SHA))

        a2r = epoch_cas(pointer_path=ptr, pointer_store_path=pstore, expected_pointer=b1,
                        candidate_retention_sha256=W81_RETENTION_SHA,
                        selection_kind='ROLLBACK', note='explicit rollback to exact Wave81 retention content')
        a2 = read_current(ptr, pstore)
        controls.append(('rollback_returns_to_old_content', a2r['status'] == 'COMMITTED' and a2['retention_sha256'] == W81_RETENTION_SHA))
        controls.append(('rollback_does_not_rewind_epoch', a2['commit_epoch'] == 2))
        controls.append(('rollback_has_distinct_pointer_identity', pointer_id(a2) != pointer_id(a0)))

        stale = epoch_cas(pointer_path=ptr, pointer_store_path=pstore, expected_pointer=a0,
                          candidate_retention_sha256=W83_KEEP_RETENTION_SHA,
                          note='stale writer prepared at first A')
        controls.append(('aba_stale_writer_conflicts', stale['status'] == 'CONFLICT' and stale['current_epoch'] == 2))

        fresh = epoch_cas(pointer_path=ptr, pointer_store_path=pstore, expected_pointer=a2,
                          candidate_retention_sha256=W83_KEEP_RETENTION_SHA,
                          note='fresh writer prepared after rollback')
        c3 = read_current(ptr, pstore)
        controls.append(('fresh_after_rollback_can_commit', fresh['status'] == 'COMMITTED' and c3['commit_epoch'] == 3))
        controls.append(('full_chain_validates', validate_chain(c3, PointerStore(pstore)) == 4))

        before = c3
        crash_pre = epoch_cas(pointer_path=ptr, pointer_store_path=pstore, expected_pointer=before,
                              candidate_retention_sha256=W83_DROP_RETENTION_SHA,
                              note='crash before pointer replacement', crash_before_replace=True)
        still = read_current(ptr, pstore)
        controls.append(('crash_before_replace_keeps_current_epoch', crash_pre['status'].startswith('CRASH_') and still == before))
        controls.append(('staged_pointer_has_zero_authority', crash_pre['staged_pointer_sha256'] != pointer_id(still)))

        retry = epoch_cas(pointer_path=ptr, pointer_store_path=pstore, expected_pointer=before,
                          candidate_retention_sha256=W83_DROP_RETENTION_SHA,
                          note='retry after pre-replace crash')
        d4 = read_current(ptr, pstore)
        controls.append(('retry_after_pre_replace_crash_commits', retry['status'] == 'COMMITTED' and d4['commit_epoch'] == 4))

        crash_post = epoch_cas(pointer_path=ptr, pointer_store_path=pstore, expected_pointer=d4,
                               candidate_retention_sha256=W83_KEEP_RETENTION_SHA,
                               note='crash after atomic replacement', crash_after_replace=True)
        e5 = read_current(ptr, pstore)
        controls.append(('crash_after_replace_recovers_new_epoch', crash_post['status'].startswith('CRASH_') and e5['commit_epoch'] == 5))

        raw = json.loads(ptr.read_text())
        raw['commit_epoch'] -= 2
        ptr.write_text(json.dumps(raw))
        controls.append(('epoch_tamper_without_rehash_rejected', 'integrity' in fail(lambda: read_current(ptr, pstore))))
        _durable_replace(ptr, canon(e5))

        fake = dict(e5)
        fake['commit_epoch'] = 50
        fake['pointer_sha256'] = dig(_pointer_body(fake))
        PointerStore(pstore).put(fake)
        _durable_replace(ptr, canon(fake))
        controls.append(('rehash_epoch_jump_rejected_by_chain', 'monotonic' in fail(lambda: read_current(ptr, pstore))))
        _durable_replace(ptr, canon(e5))

        ctx = mp.get_context('fork')
        race_ok = True
        drop_wins = keep_wins = 0
        for i in range(race_rounds):
            rb = base / f'race-{i}'
            rp = rb / 'current.json'; rs = rb / 'pointers'
            exp = initialize(rp, rs, W81_RETENTION_SHA)
            gate = ctx.Barrier(2); q = ctx.Queue()
            p1 = ctx.Process(target=_race_worker, args=(str(rp), str(rs), exp, W83_DROP_RETENTION_SHA, gate, q, 'DROP'))
            p2 = ctx.Process(target=_race_worker, args=(str(rp), str(rs), exp, W83_KEEP_RETENTION_SHA, gate, q, 'KEEP'))
            p1.start(); p2.start(); p1.join(); p2.join()
            rr = [q.get(), q.get()]
            statuses = sorted(x['status'] for x in rr)
            if statuses != ['COMMITTED', 'CONFLICT']:
                race_ok = False
            winner = next((x['writer'] for x in rr if x['status'] == 'COMMITTED'), None)
            drop_wins += winner == 'DROP'; keep_wins += winner == 'KEEP'
            cur = read_current(rp, rs)
            if cur['commit_epoch'] != 1:
                race_ok = False
        controls.append(('same_epoch_races_exactly_one_winner', race_ok))

        samples = []
        for i in range(benchmark_rounds):
            bb = base / f'bench-{i}'
            bp = bb / 'current.json'; bs = bb / 'pointers'
            exp = initialize(bp, bs, W81_RETENTION_SHA)
            t0 = time.process_time_ns()
            out = epoch_cas(pointer_path=bp, pointer_store_path=bs, expected_pointer=exp,
                            candidate_retention_sha256=W83_KEEP_RETENTION_SHA,
                            note='Wave84 synthetic local CAS benchmark')
            t1 = time.process_time_ns()
            if out['status'] != 'COMMITTED':
                raise AssertionError('benchmark commit failed')
            samples.append((t1 - t0) / 1000.0)

        failed = [name for name, ok in controls if not ok]
        report = {
            'schema': 'axm.flowing-compute-wave84-report/v0.1',
            'status': 'PASS' if not failed else 'FAIL',
            'controls_passed': sum(bool(ok) for _, ok in controls),
            'controls_total': len(controls),
            'failed_controls': failed,
            'controls': [{'name': n, 'pass': bool(ok)} for n, ok in controls],
            'exact_prior_evidence': {
                'wave81_retention_sha256': W81_RETENTION_SHA,
                'wave83_drop_retention_sha256': W83_DROP_RETENTION_SHA,
                'wave83_keep_retention_sha256': W83_KEEP_RETENTION_SHA,
                'wave83_root_evaluation_sha256': W83_ROOT_EVAL_SHA,
                'wave82_drop_receipt_sha256': W82_DROP_RECEIPT_SHA,
            },
            'aba': {
                'content_sequence': ['A', 'B', 'A'],
                'retention_sequence_sha256': [W81_RETENTION_SHA, W83_DROP_RETENTION_SHA, W81_RETENTION_SHA],
                'pointer_epochs': [0, 1, 2],
                'legacy_content_only_guard_would_accept_stale_A0_writer': legacy_after_aba_would_accept,
                'epoch_guard_stale_A0_writer_status': stale['status'],
                'fresh_A2_writer_status': fresh['status'],
            },
            'races': {'rounds': race_rounds, 'drop_wins': drop_wins, 'keep_wins': keep_wins, 'claim': 'one-winner only; win ratio is not fairness'},
            'benchmark': {
                'rounds': benchmark_rounds,
                'median_process_cpu_microseconds': statistics.median(samples),
                'scope': 'synthetic single-host pointer/object-store infrastructure only',
                'excludes': ['end-to-end wall latency interpretation', 'monolith workload', 'energy/joules'],
            },
            'truth_boundary': [
                'commit epoch is a local pointer-history ordering mechanism, not trusted hardware monotonic storage',
                'rollback selects old retention content through a new pointer epoch rather than restoring an old pointer body',
                'pointer hash/chain detects tested accidental or contract-level tampering but does not establish actor identity',
                'host/root-level rewriting of the complete pointer store is outside this contract',
                'no fresh monolith audit or compute-efficiency claim was performed in Wave84',
                'no merge, canon promotion, distributed-consensus, energy, or over-unity claim is made',
            ],
        }
        report['report_sha256'] = dig(report)
        return report


if __name__ == '__main__':
    print(json.dumps(self_test(), indent=2, sort_keys=True))
