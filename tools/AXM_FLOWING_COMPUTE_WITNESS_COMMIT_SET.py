from __future__ import annotations

import hashlib
import json
import os
import shutil
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable

SCHEMA = 'axm.flowing-compute-witness-commit-set/v0.1'
POINTER_SCHEMA = 'axm.flowing-compute-witness-commit-set-pointer/v0.1'
WITNESS_RECORD_SCHEMA = 'axm.flowing-compute-witness-commit-set-record/v0.1'
DEFAULT_WITNESS_IDS = ('witness-a', 'witness-b', 'witness-c')

# Exact provenance carried forward from Wave 86 evidence.
WAVE86_TOOL_COMMIT = '23870591e0a8fae2e1bbf9b5b598ffbb3bac9eea'
WAVE86_TOOL_BLOB_SHA = '0059e3ab5d5e069a959a3571d50461f7309ead10'
W81_RETENTION_SHA = '53d91b18e1a12eb27bd503bcfa70b4cd74add598ceaef522c88d7c075fdee4d4'
W83_DROP_RETENTION_SHA = '4078169dce33c5816c7dd1073eaff5920bcfb07284a023726322e67970378dd1'
W83_KEEP_RETENTION_SHA = '0f918393dc9d4dfb33fe150bbdca9bd4ecbdca8fab0317becdf94fb9296b1721'


def canon(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def identity(value: dict[str, Any], field: str) -> str:
    body = dict(value)
    body.pop(field, None)
    return sha256_bytes(canon(body))


def seal(value: dict[str, Any], field: str) -> dict[str, Any]:
    out = dict(value)
    out[field] = identity(out, field)
    return out


def validate_seal(value: dict[str, Any], field: str) -> None:
    if value.get(field) != identity(value, field):
        raise ValueError(f'{field} mismatch')


def durable_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f'.tmp-{os.getpid()}-{time.time_ns()}')
    with tmp.open('wb') as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    try:
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


class ObjectStore:
    def __init__(self, root: str | Path, identity_field: str):
        self.root = Path(root)
        self.identity_field = identity_field
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, object_id: str) -> Path:
        return self.root / f'{object_id}.json'

    def put(self, value: dict[str, Any]) -> str:
        validate_seal(value, self.identity_field)
        object_id = value[self.identity_field]
        path = self.path_for(object_id)
        encoded = canon(value) + b'\n'
        if path.exists():
            existing = path.read_bytes()
            if existing != encoded:
                raise ValueError('content-addressed object collision')
            return object_id
        durable_write(path, encoded)
        return object_id

    def get(self, object_id: str) -> dict[str, Any]:
        path = self.path_for(object_id)
        if not path.is_file():
            raise FileNotFoundError(f'object missing: {object_id}')
        value = json.loads(path.read_text('utf-8'))
        validate_seal(value, self.identity_field)
        if value[self.identity_field] != object_id:
            raise ValueError('object key/content identity mismatch')
        return value


def pointer_id(pointer: dict[str, Any]) -> str:
    validate_seal(pointer, 'pointer_sha256')
    return pointer['pointer_sha256']


def make_pointer(*, commit_epoch: int, retention_sha256: str,
                 predecessor_pointer_sha256: str | None,
                 selection_kind: str, note: str = '') -> dict[str, Any]:
    if commit_epoch < 0:
        raise ValueError('commit_epoch')
    if selection_kind not in ('GENESIS', 'FORWARD', 'ROLLBACK'):
        raise ValueError('selection_kind')
    return seal({
        'schema': POINTER_SCHEMA,
        'commit_epoch': commit_epoch,
        'retention_sha256': retention_sha256,
        'predecessor_pointer_sha256': predecessor_pointer_sha256,
        'selection_kind': selection_kind,
        'note': note,
        'pointer_sha256': '',
    }, 'pointer_sha256')


class Primary:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.objects = ObjectStore(self.root / 'objects', 'pointer_sha256')
        self.current_path = self.root / 'current.json'

    def initialize(self, retention_sha256: str = W81_RETENTION_SHA) -> dict[str, Any]:
        if self.current_path.exists():
            raise ValueError('primary already initialized')
        pointer = make_pointer(commit_epoch=0, retention_sha256=retention_sha256,
                               predecessor_pointer_sha256=None, selection_kind='GENESIS',
                               note='Wave87 genesis derived from exact Wave86/Wave81 provenance')
        self.objects.put(pointer)
        durable_write(self.current_path, canon(pointer) + b'\n')
        return pointer

    def current(self) -> dict[str, Any]:
        if not self.current_path.is_file():
            raise FileNotFoundError('current pointer missing')
        pointer = json.loads(self.current_path.read_text('utf-8'))
        validate_seal(pointer, 'pointer_sha256')
        stored = self.objects.get(pointer['pointer_sha256'])
        if stored != pointer:
            raise ValueError('current pointer body differs from stored object')
        return pointer

    def stage(self, pointer: dict[str, Any]) -> str:
        return self.objects.put(pointer)

    def commit(self, pointer: dict[str, Any]) -> None:
        self.objects.get(pointer_id(pointer))
        durable_write(self.current_path, canon(pointer) + b'\n')


class Witness:
    def __init__(self, root: str | Path, witness_id: str):
        self.root = Path(root)
        self.witness_id = witness_id
        self.records = ObjectStore(self.root / 'records', 'record_sha256')
        self.head_path = self.root / 'HEAD'

    def initialize(self, pointer: dict[str, Any]) -> dict[str, Any]:
        if self.head_path.exists():
            raise ValueError('witness already initialized')
        record = seal({
            'schema': WITNESS_RECORD_SCHEMA,
            'witness_id': self.witness_id,
            'anchor_epoch': pointer['commit_epoch'],
            'pointer_sha256': pointer_id(pointer),
            'retention_sha256': pointer['retention_sha256'],
            'predecessor_record_sha256': None,
            'commit_set_sha256': None,
            'record_sha256': '',
        }, 'record_sha256')
        self.records.put(record)
        durable_write(self.head_path, (record['record_sha256'] + '\n').encode())
        return record

    def head(self) -> dict[str, Any]:
        if not self.head_path.is_file():
            raise FileNotFoundError(f'{self.witness_id} HEAD missing')
        record_id = self.head_path.read_text('utf-8').strip()
        record = self.records.get(record_id)
        if record['witness_id'] != self.witness_id:
            raise ValueError('witness id mismatch')
        return record

    def append_for_commit_set(self, commit_set: dict[str, Any]) -> dict[str, Any]:
        validate_commit_set(commit_set)
        predecessor = commit_set['predecessor_witness_heads'][self.witness_id]
        current = self.head()
        if current['record_sha256'] != predecessor:
            raise ValueError('witness is not at commit-set predecessor')
        record = seal({
            'schema': WITNESS_RECORD_SCHEMA,
            'witness_id': self.witness_id,
            'anchor_epoch': commit_set['target_epoch'],
            'pointer_sha256': commit_set['target_pointer_sha256'],
            'retention_sha256': commit_set['target_retention_sha256'],
            'predecessor_record_sha256': predecessor,
            'commit_set_sha256': commit_set['commit_set_sha256'],
            'record_sha256': '',
        }, 'record_sha256')
        self.records.put(record)
        durable_write(self.head_path, (record['record_sha256'] + '\n').encode())
        return record


def witness_map(root: str | Path, ids: Iterable[str] = DEFAULT_WITNESS_IDS) -> dict[str, Witness]:
    base = Path(root)
    return {wid: Witness(base / wid, wid) for wid in ids}


def initialize(primary: Primary, witnesses: dict[str, Witness]) -> dict[str, Any]:
    if len(witnesses) < 2:
        raise ValueError('at least two witnesses required')
    pointer = primary.initialize(W81_RETENTION_SHA)
    for wid in sorted(witnesses):
        witnesses[wid].initialize(pointer)
    return pointer


def make_commit_set(*, current: dict[str, Any], target: dict[str, Any],
                    witnesses: dict[str, Witness], transition_kind: str,
                    note: str = '') -> dict[str, Any]:
    if transition_kind not in ('FORWARD', 'ROLLBACK'):
        raise ValueError('transition_kind')
    if target['commit_epoch'] != current['commit_epoch'] + 1:
        raise ValueError('target epoch must be predecessor + 1')
    if target['predecessor_pointer_sha256'] != pointer_id(current):
        raise ValueError('target predecessor mismatch')
    ids = sorted(witnesses)
    predecessor_heads = {wid: witnesses[wid].head()['record_sha256'] for wid in ids}
    return seal({
        'schema': SCHEMA,
        'provenance': {
            'wave86_tool_commit': WAVE86_TOOL_COMMIT,
            'wave86_tool_blob_sha': WAVE86_TOOL_BLOB_SHA,
        },
        'transition_kind': transition_kind,
        'predecessor_epoch': current['commit_epoch'],
        'predecessor_pointer_sha256': pointer_id(current),
        'predecessor_retention_sha256': current['retention_sha256'],
        'target_epoch': target['commit_epoch'],
        'target_pointer_sha256': pointer_id(target),
        'target_retention_sha256': target['retention_sha256'],
        'witness_ids': ids,
        'predecessor_witness_heads': predecessor_heads,
        'note': note,
        'commit_set_sha256': '',
    }, 'commit_set_sha256')


def validate_commit_set(commit_set: dict[str, Any]) -> None:
    validate_seal(commit_set, 'commit_set_sha256')
    if commit_set.get('schema') != SCHEMA:
        raise ValueError('commit-set schema')
    if commit_set.get('provenance', {}).get('wave86_tool_commit') != WAVE86_TOOL_COMMIT:
        raise ValueError('Wave86 tool commit provenance mismatch')
    if commit_set.get('provenance', {}).get('wave86_tool_blob_sha') != WAVE86_TOOL_BLOB_SHA:
        raise ValueError('Wave86 tool blob provenance mismatch')
    ids = commit_set.get('witness_ids')
    if not isinstance(ids, list) or ids != sorted(ids) or len(ids) != len(set(ids)) or len(ids) < 2:
        raise ValueError('witness ids invalid')
    if sorted(commit_set.get('predecessor_witness_heads', {})) != ids:
        raise ValueError('predecessor witness-set mismatch')
    if commit_set['target_epoch'] != commit_set['predecessor_epoch'] + 1:
        raise ValueError('commit-set epoch discontinuity')


def prepare_transition(*, primary: Primary, witnesses: dict[str, Witness],
                       commit_sets: ObjectStore, target_retention_sha256: str,
                       transition_kind: str = 'FORWARD', note: str = '') -> tuple[dict[str, Any], dict[str, Any]]:
    state = recovery_status(primary=primary, witnesses=witnesses, commit_sets=commit_sets)
    if state['status'] != 'CONSISTENT':
        raise RuntimeError(f'cannot prepare from non-consistent state: {state["status"]}')
    current = primary.current()
    target = make_pointer(commit_epoch=current['commit_epoch'] + 1,
                          retention_sha256=target_retention_sha256,
                          predecessor_pointer_sha256=pointer_id(current),
                          selection_kind=transition_kind, note=note)
    primary.stage(target)
    commit_set = make_commit_set(current=current, target=target, witnesses=witnesses,
                                 transition_kind=transition_kind, note=note)
    commit_sets.put(commit_set)
    return target, commit_set


def _validate_advanced_record(record: dict[str, Any], wid: str,
                              commit_set: dict[str, Any]) -> None:
    validate_seal(record, 'record_sha256')
    if record['witness_id'] != wid:
        raise ValueError('witness record id mismatch')
    expected = {
        'anchor_epoch': commit_set['target_epoch'],
        'pointer_sha256': commit_set['target_pointer_sha256'],
        'retention_sha256': commit_set['target_retention_sha256'],
        'predecessor_record_sha256': commit_set['predecessor_witness_heads'][wid],
        'commit_set_sha256': commit_set['commit_set_sha256'],
    }
    for key, value in expected.items():
        if record.get(key) != value:
            raise ValueError(f'advanced witness semantic mismatch: {key}')


def _candidate_commit_set_ids(primary: Primary, witnesses: dict[str, Witness]) -> tuple[set[str], list[str]]:
    current = primary.current()
    ids: set[str] = set()
    errors: list[str] = []
    for wid in sorted(witnesses):
        try:
            head = witnesses[wid].head()
        except Exception as exc:
            errors.append(f'{wid}: {type(exc).__name__}: {exc}')
            continue
        if head['anchor_epoch'] > current['commit_epoch'] and head.get('commit_set_sha256'):
            ids.add(head['commit_set_sha256'])
    return ids, errors


def recovery_status(*, primary: Primary, witnesses: dict[str, Witness],
                    commit_sets: ObjectStore, repair: bool = False) -> dict[str, Any]:
    try:
        current = primary.current()
    except Exception as exc:
        return {'status': 'PRIMARY_INVALID_HOLD', 'error': f'{type(exc).__name__}: {exc}', 'authority_selected': False}
    expected_ids = sorted(witnesses)
    if len(expected_ids) < 2:
        return {'status': 'WITNESS_SET_INVALID_HOLD', 'authority_selected': False}

    heads: dict[str, dict[str, Any]] = {}
    for wid in expected_ids:
        try:
            heads[wid] = witnesses[wid].head()
        except Exception as exc:
            return {'status': 'WITNESS_INCOMPLETE_HOLD', 'witness_id': wid,
                    'error': f'{type(exc).__name__}: {exc}', 'authority_selected': False}

    # Normal steady state: all witness records bind exactly to the current primary.
    if all(h['anchor_epoch'] == current['commit_epoch'] and h['pointer_sha256'] == pointer_id(current) for h in heads.values()):
        commit_ids = {h.get('commit_set_sha256') for h in heads.values()}
        if current['commit_epoch'] == 0:
            if commit_ids != {None}:
                return {'status': 'GENESIS_WITNESS_MISMATCH_HOLD', 'authority_selected': False}
            return {'status': 'CONSISTENT', 'epoch': 0, 'pointer_sha256': pointer_id(current), 'commit_set_sha256': None}
        if len(commit_ids) != 1 or None in commit_ids:
            return {'status': 'WITNESS_COMMIT_SET_DIVERGENCE_HOLD', 'authority_selected': False}
        commit_id = next(iter(commit_ids))
        try:
            cs = commit_sets.get(commit_id)
            validate_commit_set(cs)
        except Exception as exc:
            return {'status': 'COMMIT_SET_MISSING_OR_INVALID_HOLD', 'commit_set_sha256': commit_id,
                    'error': f'{type(exc).__name__}: {exc}', 'authority_selected': False}
        if cs['witness_ids'] != expected_ids:
            return {'status': 'COMMIT_SET_WITNESS_SET_MISMATCH_HOLD', 'authority_selected': False}
        if cs['target_pointer_sha256'] != pointer_id(current) or cs['target_epoch'] != current['commit_epoch']:
            return {'status': 'CURRENT_BINDING_MISMATCH_HOLD', 'authority_selected': False}
        try:
            for wid, record in heads.items():
                _validate_advanced_record(record, wid, cs)
        except Exception as exc:
            return {'status': 'CURRENT_WITNESS_RECORD_INVALID_HOLD', 'error': str(exc), 'authority_selected': False}
        return {'status': 'CONSISTENT', 'epoch': current['commit_epoch'], 'pointer_sha256': pointer_id(current),
                'commit_set_sha256': commit_id}

    candidate_ids = {h.get('commit_set_sha256') for h in heads.values()
                     if h['anchor_epoch'] == current['commit_epoch'] + 1 and h.get('commit_set_sha256')}
    if len(candidate_ids) > 1:
        return {'status': 'WITNESS_COMPETING_COMMIT_SET_HOLD', 'commit_set_ids': sorted(candidate_ids),
                'authority_selected': False, 'majority_vote_used': False, 'newest_witness_wins': False}
    if not candidate_ids:
        # This includes primary-ahead/older-than-predecessor/otherwise unrelated states.
        return {'status': 'NO_RECOVERABLE_COMMIT_SET_HOLD', 'primary_epoch': current['commit_epoch'],
                'witness_epochs': {wid: heads[wid]['anchor_epoch'] for wid in expected_ids}, 'authority_selected': False}

    commit_id = next(iter(candidate_ids))
    try:
        cs = commit_sets.get(commit_id)
        validate_commit_set(cs)
    except Exception as exc:
        return {'status': 'COMMIT_SET_MISSING_OR_INVALID_HOLD', 'commit_set_sha256': commit_id,
                'error': f'{type(exc).__name__}: {exc}', 'authority_selected': False}
    if cs['witness_ids'] != expected_ids:
        return {'status': 'COMMIT_SET_WITNESS_SET_MISMATCH_HOLD', 'authority_selected': False}
    if cs['predecessor_pointer_sha256'] != pointer_id(current) or cs['predecessor_epoch'] != current['commit_epoch']:
        return {'status': 'COMMIT_SET_PREDECESSOR_MISMATCH_HOLD', 'authority_selected': False}
    try:
        target = primary.objects.get(cs['target_pointer_sha256'])
    except Exception as exc:
        return {'status': 'TARGET_POINTER_MISSING_OR_INVALID_HOLD', 'error': f'{type(exc).__name__}: {exc}', 'authority_selected': False}
    if target['commit_epoch'] != cs['target_epoch'] or target['retention_sha256'] != cs['target_retention_sha256'] \
            or target['predecessor_pointer_sha256'] != pointer_id(current):
        return {'status': 'TARGET_POINTER_BINDING_MISMATCH_HOLD', 'authority_selected': False}

    advanced: list[str] = []
    lagging: list[str] = []
    for wid in expected_ids:
        head = heads[wid]
        predecessor = cs['predecessor_witness_heads'][wid]
        if head['record_sha256'] == predecessor:
            # Exact predecessor only: an arbitrarily older head is not a repair target.
            if head['anchor_epoch'] != current['commit_epoch'] or head['pointer_sha256'] != pointer_id(current):
                return {'status': 'LAGGING_WITNESS_PREDECESSOR_BINDING_HOLD', 'witness_id': wid, 'authority_selected': False}
            lagging.append(wid)
            continue
        try:
            _validate_advanced_record(head, wid, cs)
        except Exception as exc:
            # If a different valid commit-set is present, name the competition explicitly even if
            # it is from a different epoch or malformed relative to this candidate.
            other = head.get('commit_set_sha256')
            if other and other != commit_id:
                return {'status': 'WITNESS_COMPETING_COMMIT_SET_HOLD', 'commit_set_ids': sorted({commit_id, other}),
                        'authority_selected': False, 'majority_vote_used': False, 'newest_witness_wins': False}
            return {'status': 'WITNESS_RECORD_NOT_PREDECESSOR_OR_TARGET_HOLD', 'witness_id': wid,
                    'error': str(exc), 'authority_selected': False}
        advanced.append(wid)

    if not advanced:
        return {'status': 'PREPARED_COMMIT_SET_NO_AUTHORITY', 'commit_set_sha256': commit_id,
                'authority_selected': False}

    if repair:
        for wid in lagging:
            witnesses[wid].append_for_commit_set(cs)
        # Re-read all witness heads and require exact same commit-set before moving primary.
        for wid in expected_ids:
            _validate_advanced_record(witnesses[wid].head(), wid, cs)
        primary.commit(target)
        return {'status': 'RECOVERED_COMMIT_SET', 'epoch': target['commit_epoch'],
                'commit_set_sha256': commit_id, 'repaired_witnesses': lagging}

    if lagging:
        return {'status': 'PARTIAL_COMMIT_SET_RECOVERABLE', 'commit_set_sha256': commit_id,
                'advanced_witnesses': advanced, 'lagging_witnesses': lagging,
                'authority_selected': False, 'majority_vote_used': False, 'newest_witness_wins': False}
    return {'status': 'UNANIMOUS_COMMIT_SET_PENDING_POINTER_MOVE', 'commit_set_sha256': commit_id,
            'advanced_witnesses': advanced, 'lagging_witnesses': [], 'authority_selected': False}


def fanout(commit_set: dict[str, Any], witnesses: dict[str, Witness], witness_ids: Iterable[str]) -> list[str]:
    validate_commit_set(commit_set)
    advanced: list[str] = []
    for wid in witness_ids:
        if wid not in witnesses:
            raise KeyError(wid)
        witnesses[wid].append_for_commit_set(commit_set)
        advanced.append(wid)
    return advanced


def commit_prepared(*, primary: Primary, witnesses: dict[str, Witness], commit_sets: ObjectStore,
                    commit_set: dict[str, Any], crash_after_witness_count: int | None = None) -> dict[str, Any]:
    validate_commit_set(commit_set)
    ordered = sorted(witnesses)
    if crash_after_witness_count is not None and not (0 <= crash_after_witness_count <= len(ordered)):
        raise ValueError('crash_after_witness_count')
    if crash_after_witness_count == 0:
        return {'status': 'CRASH_BEFORE_WITNESS_FANOUT', 'commit_set_sha256': commit_set['commit_set_sha256']}
    count = 0
    for wid in ordered:
        witnesses[wid].append_for_commit_set(commit_set)
        count += 1
        if crash_after_witness_count == count:
            return {'status': 'CRASH_DURING_WITNESS_FANOUT', 'witnesses_appended': count,
                    'commit_set_sha256': commit_set['commit_set_sha256']}
    target = primary.objects.get(commit_set['target_pointer_sha256'])
    primary.commit(target)
    return {'status': 'COMMITTED', 'epoch': target['commit_epoch'],
            'commit_set_sha256': commit_set['commit_set_sha256']}


def _setup(root: Path) -> tuple[Primary, dict[str, Witness], ObjectStore, dict[str, Any]]:
    primary = Primary(root / 'primary')
    witnesses = witness_map(root / 'witnesses')
    commit_sets = ObjectStore(root / 'commit_sets', 'commit_set_sha256')
    genesis = initialize(primary, witnesses)
    return primary, witnesses, commit_sets, genesis


def _snapshot(root: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(root, dst, ignore=shutil.ignore_patterns(dst.name))


def _restore(src: Path, dst: Path) -> None:
    hold = dst.parent / (dst.name + '-restore-tmp')
    if hold.exists():
        shutil.rmtree(hold)
    shutil.copytree(src, hold)
    for child in list(dst.iterdir()):
        if child == src:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    for child in list(hold.iterdir()):
        shutil.move(str(child), str(dst / child.name))
    shutil.rmtree(hold)


def self_test(benchmark_rounds: int = 60) -> dict[str, Any]:
    checks: list[tuple[str, bool]] = []
    details: dict[str, Any] = {}

    with tempfile.TemporaryDirectory(prefix='axm-wave87-core-') as tmp:
        root = Path(tmp)
        primary, witnesses, commit_sets, genesis = _setup(root)
        checks.append(('exact_wave86_tool_commit_provenance', WAVE86_TOOL_COMMIT == '23870591e0a8fae2e1bbf9b5b598ffbb3bac9eea'))
        checks.append(('genesis_exact_wave81_retention', genesis['retention_sha256'] == W81_RETENTION_SHA))
        checks.append(('genesis_consistent', recovery_status(primary=primary, witnesses=witnesses, commit_sets=commit_sets)['status'] == 'CONSISTENT'))

        target1, cs1 = prepare_transition(primary=primary, witnesses=witnesses, commit_sets=commit_sets,
                                          target_retention_sha256=W83_DROP_RETENTION_SHA, note='Wave87 C1 exact DROP target')
        checks.append(('prepared_commit_set_has_zero_authority', recovery_status(primary=primary, witnesses=witnesses, commit_sets=commit_sets)['status'] == 'CONSISTENT'))

        # Persist an unused competitor: mere object existence must grant no authority and must not block C1.
        target2 = make_pointer(commit_epoch=1, retention_sha256=W83_KEEP_RETENTION_SHA,
                               predecessor_pointer_sha256=pointer_id(genesis), selection_kind='FORWARD', note='unused competitor')
        primary.stage(target2)
        cs2 = make_commit_set(current=genesis, target=target2, witnesses=witnesses,
                              transition_kind='FORWARD', note='unused competing object')
        commit_sets.put(cs2)
        checks.append(('unused_competing_commit_set_object_has_zero_authority', recovery_status(primary=primary, witnesses=witnesses, commit_sets=commit_sets)['status'] == 'CONSISTENT'))

        fanout(cs1, witnesses, ['witness-a'])
        s = recovery_status(primary=primary, witnesses=witnesses, commit_sets=commit_sets)
        checks.append(('one_witness_partial_fanout_now_recoverable', s['status'] == 'PARTIAL_COMMIT_SET_RECOVERABLE' and s['lagging_witnesses'] == ['witness-b', 'witness-c']))
        repaired = recovery_status(primary=primary, witnesses=witnesses, commit_sets=commit_sets, repair=True)
        checks.append(('one_witness_partial_recovery_completes_exact_set', repaired['status'] == 'RECOVERED_COMMIT_SET' and repaired['repaired_witnesses'] == ['witness-b', 'witness-c']))
        checks.append(('recovered_state_is_consistent', recovery_status(primary=primary, witnesses=witnesses, commit_sets=commit_sets)['status'] == 'CONSISTENT'))
        subset = {wid: witnesses[wid] for wid in ('witness-a', 'witness-b')}
        checks.append(('steady_state_witness_omission_holds',
                       recovery_status(primary=primary, witnesses=subset, commit_sets=commit_sets)['status'] == 'COMMIT_SET_WITNESS_SET_MISMATCH_HOLD'))

        # Intentional rollback remains legal while epoch advances.
        cur1 = primary.current()
        target_rb, cs_rb = prepare_transition(primary=primary, witnesses=witnesses, commit_sets=commit_sets,
                                               target_retention_sha256=W81_RETENTION_SHA, transition_kind='ROLLBACK',
                                               note='Wave87 intentional rollback')
        fanout(cs_rb, witnesses, ['witness-a', 'witness-b'])
        s = recovery_status(primary=primary, witnesses=witnesses, commit_sets=commit_sets)
        checks.append(('two_witness_partial_rollback_recoverable_without_vote', s['status'] == 'PARTIAL_COMMIT_SET_RECOVERABLE' and not s['majority_vote_used']))
        recovery_status(primary=primary, witnesses=witnesses, commit_sets=commit_sets, repair=True)
        checks.append(('rollback_content_with_forward_epoch_preserved', primary.current()['retention_sha256'] == W81_RETENTION_SHA and primary.current()['commit_epoch'] == cur1['commit_epoch'] + 1))

    # Competing commit sets on different witnesses from the same predecessor must freeze.
    with tempfile.TemporaryDirectory(prefix='axm-wave87-compete-') as tmp:
        root = Path(tmp); primary, witnesses, commit_sets, genesis = _setup(root)
        t1, c1 = prepare_transition(primary=primary, witnesses=witnesses, commit_sets=commit_sets,
                                    target_retention_sha256=W83_DROP_RETENTION_SHA, note='competing C1')
        # Build C2 while all witness heads are still at the same exact predecessor.
        t2 = make_pointer(commit_epoch=1, retention_sha256=W83_KEEP_RETENTION_SHA,
                          predecessor_pointer_sha256=pointer_id(genesis), selection_kind='FORWARD', note='competing C2')
        primary.stage(t2)
        c2 = make_commit_set(current=genesis, target=t2, witnesses=witnesses, transition_kind='FORWARD', note='competing C2')
        commit_sets.put(c2)
        fanout(c1, witnesses, ['witness-a'])
        fanout(c2, witnesses, ['witness-b'])
        s = recovery_status(primary=primary, witnesses=witnesses, commit_sets=commit_sets)
        checks.append(('competing_commit_sets_freeze', s['status'] == 'WITNESS_COMPETING_COMMIT_SET_HOLD'))
        checks.append(('competing_set_uses_no_majority_or_newest_authority', not s.get('authority_selected', True) and not s.get('majority_vote_used', True) and not s.get('newest_witness_wins', True)))

    # Exact predecessor requirement: a lagging witness older than declared predecessor cannot be swept forward.
    with tempfile.TemporaryDirectory(prefix='axm-wave87-oldlag-') as tmp:
        root = Path(tmp); primary, witnesses, commit_sets, genesis = _setup(root)
        # Save witness-c genesis directory.
        wc_snap = root / 'wc-genesis'; shutil.copytree(witnesses['witness-c'].root, wc_snap)
        _, c1 = prepare_transition(primary=primary, witnesses=witnesses, commit_sets=commit_sets,
                                   target_retention_sha256=W83_DROP_RETENTION_SHA, note='first')
        fanout(c1, witnesses, sorted(witnesses)); primary.commit(primary.objects.get(c1['target_pointer_sha256']))
        _, c2 = prepare_transition(primary=primary, witnesses=witnesses, commit_sets=commit_sets,
                                   target_retention_sha256=W83_KEEP_RETENTION_SHA, note='second')
        fanout(c2, witnesses, ['witness-a'])
        # Rewind C to epoch0 rather than exact epoch1 predecessor.
        shutil.rmtree(witnesses['witness-c'].root); shutil.copytree(wc_snap, witnesses['witness-c'].root)
        s = recovery_status(primary=primary, witnesses=witnesses, commit_sets=commit_sets)
        checks.append(('older_than_declared_predecessor_refuses_repair', s['status'] == 'WITNESS_RECORD_NOT_PREDECESSOR_OR_TARGET_HOLD'))

    # Missing/tampered commit-set object and semantic witness forgery fail closed.
    with tempfile.TemporaryDirectory(prefix='axm-wave87-tamper-') as tmp:
        root = Path(tmp); primary, witnesses, commit_sets, genesis = _setup(root)
        _, cs = prepare_transition(primary=primary, witnesses=witnesses, commit_sets=commit_sets,
                                   target_retention_sha256=W83_DROP_RETENTION_SHA, note='tamper base')
        fanout(cs, witnesses, ['witness-a'])
        cs_path = commit_sets.path_for(cs['commit_set_sha256'])
        original_cs = cs_path.read_bytes()
        cs_path.unlink()
        checks.append(('missing_commit_set_object_holds', recovery_status(primary=primary, witnesses=witnesses, commit_sets=commit_sets)['status'] == 'COMMIT_SET_MISSING_OR_INVALID_HOLD'))
        durable_write(cs_path, original_cs)
        tampered = json.loads(original_cs.decode())
        tampered['note'] = 'tampered but kept old filename/id'
        tampered = seal(tampered, 'commit_set_sha256')
        # Store under the old key deliberately, simulating content replacement at an address.
        durable_write(cs_path, canon(tampered) + b'\n')
        checks.append(('rehashed_commit_set_under_old_address_holds', recovery_status(primary=primary, witnesses=witnesses, commit_sets=commit_sets)['status'] == 'COMMIT_SET_MISSING_OR_INVALID_HOLD'))

    with tempfile.TemporaryDirectory(prefix='axm-wave87-forge-') as tmp:
        root = Path(tmp); primary, witnesses, commit_sets, genesis = _setup(root)
        _, cs = prepare_transition(primary=primary, witnesses=witnesses, commit_sets=commit_sets,
                                   target_retention_sha256=W83_DROP_RETENTION_SHA, note='forge base')
        rec = witnesses['witness-a'].append_for_commit_set(cs)
        forged = dict(rec); forged['retention_sha256'] = W83_KEEP_RETENTION_SHA; forged = seal(forged, 'record_sha256')
        witnesses['witness-a'].records.put(forged)
        durable_write(witnesses['witness-a'].head_path, (forged['record_sha256'] + '\n').encode())
        checks.append(('validly_rehashed_witness_semantic_forgery_holds', recovery_status(primary=primary, witnesses=witnesses, commit_sets=commit_sets)['status'] == 'WITNESS_RECORD_NOT_PREDECESSOR_OR_TARGET_HOLD'))

    # Missing witness + primary-ahead impossible ordering both fail closed.
    with tempfile.TemporaryDirectory(prefix='axm-wave87-order-') as tmp:
        root = Path(tmp); primary, witnesses, commit_sets, genesis = _setup(root)
        _, cs = prepare_transition(primary=primary, witnesses=witnesses, commit_sets=commit_sets,
                                   target_retention_sha256=W83_DROP_RETENTION_SHA, note='order base')
        fanout(cs, witnesses, ['witness-a'])
        shutil.rmtree(witnesses['witness-c'].root)
        checks.append(('missing_witness_holds', recovery_status(primary=primary, witnesses=witnesses, commit_sets=commit_sets)['status'] == 'WITNESS_INCOMPLETE_HOLD'))

    with tempfile.TemporaryDirectory(prefix='axm-wave87-primaryahead-') as tmp:
        root = Path(tmp); primary, witnesses, commit_sets, genesis = _setup(root)
        _, cs = prepare_transition(primary=primary, witnesses=witnesses, commit_sets=commit_sets,
                                   target_retention_sha256=W83_DROP_RETENTION_SHA, note='ahead base')
        fanout(cs, witnesses, ['witness-a'])
        primary.commit(primary.objects.get(cs['target_pointer_sha256']))
        s = recovery_status(primary=primary, witnesses=witnesses, commit_sets=commit_sets)
        checks.append(('primary_ahead_of_partial_witnesses_holds', s['status'] == 'NO_RECOVERABLE_COMMIT_SET_HOLD'))

    # Crash point progression: before witness = no authority; 1/2/all witness fanout are recoverable.
    crash_results: dict[str, str] = {}
    for count in (0, 1, 2, 3):
        with tempfile.TemporaryDirectory(prefix=f'axm-wave87-crash{count}-') as tmp:
            root = Path(tmp); primary, witnesses, commit_sets, genesis = _setup(root)
            _, cs = prepare_transition(primary=primary, witnesses=witnesses, commit_sets=commit_sets,
                                       target_retention_sha256=W83_DROP_RETENTION_SHA, note=f'crash count {count}')
            if count:
                fanout(cs, witnesses, sorted(witnesses)[:count])
            s = recovery_status(primary=primary, witnesses=witnesses, commit_sets=commit_sets)
            crash_results[str(count)] = s['status']
            if count == 0:
                checks.append(('crash_before_fanout_leaves_no_authority', s['status'] == 'CONSISTENT'))
            elif count < 3:
                checks.append((f'crash_after_{count}_witness_recoverable', s['status'] == 'PARTIAL_COMMIT_SET_RECOVERABLE'))
            else:
                checks.append(('crash_after_all_witnesses_pending_pointer', s['status'] == 'UNANIMOUS_COMMIT_SET_PENDING_POINTER_MOVE'))
                rr = recovery_status(primary=primary, witnesses=witnesses, commit_sets=commit_sets, repair=True)
                checks.append(('all_witness_pending_pointer_recovery_commits', rr['status'] == 'RECOVERED_COMMIT_SET'))
    details['crash_statuses'] = crash_results

    # Preserve the software-only all-domain rollback limitation: restore every modeled domain together.
    with tempfile.TemporaryDirectory(prefix='axm-wave87-alldomain-') as tmp:
        root = Path(tmp); primary, witnesses, commit_sets, genesis = _setup(root)
        snapshot = Path(tmp + '-genesis-snapshot')
        shutil.copytree(root, snapshot)
        _, cs = prepare_transition(primary=primary, witnesses=witnesses, commit_sets=commit_sets,
                                   target_retention_sha256=W83_DROP_RETENTION_SHA, note='future state')
        fanout(cs, witnesses, sorted(witnesses)); primary.commit(primary.objects.get(cs['target_pointer_sha256']))
        # Full rollback includes primary, all witnesses, and commit-set store.
        for child in list(root.iterdir()):
            if child.is_dir(): shutil.rmtree(child)
            else: child.unlink()
        for child in snapshot.iterdir():
            if child.is_dir(): shutil.copytree(child, root / child.name)
            else: shutil.copy2(child, root / child.name)
        primary = Primary(root/'primary'); witnesses = witness_map(root/'witnesses'); commit_sets = ObjectStore(root/'commit_sets', 'commit_set_sha256')
        checks.append(('counterexample_all_modeled_domains_rollback_still_looks_consistent', recovery_status(primary=primary, witnesses=witnesses, commit_sets=commit_sets)['status'] == 'CONSISTENT'))
        shutil.rmtree(snapshot)

    samples: list[float] = []
    for _ in range(benchmark_rounds):
        with tempfile.TemporaryDirectory(prefix='axm-wave87-bench-') as tmp:
            root = Path(tmp); primary, witnesses, commit_sets, _ = _setup(root)
            start = time.process_time_ns()
            _, cs = prepare_transition(primary=primary, witnesses=witnesses, commit_sets=commit_sets,
                                       target_retention_sha256=W83_DROP_RETENTION_SHA, note='synthetic benchmark')
            fanout(cs, witnesses, sorted(witnesses))
            primary.commit(primary.objects.get(cs['target_pointer_sha256']))
            end = time.process_time_ns()
            samples.append((end - start) / 1000.0)
    details['benchmark'] = {
        'rounds': benchmark_rounds,
        'median_process_cpu_us': statistics.median(samples),
        'min_process_cpu_us': min(samples),
        'max_process_cpu_us': max(samples),
        'scope': 'synthetic single-host JSON/hash/fsync commit-set prepare + three-witness fanout + primary pointer move',
    }

    passed = sum(1 for _, ok in checks if ok)
    failed = [name for name, ok in checks if not ok]
    return {
        'schema': 'axm.flowing-compute-wave87-report/v0.1',
        'wave': 87,
        'status': 'PASS' if not failed else 'FAIL',
        'passed': passed,
        'total': len(checks),
        'failed': failed,
        'checks': [{'name': name, 'passed': ok} for name, ok in checks],
        'details': details,
        'truth_boundary': {
            'single_host': True,
            'synthetic_orchestration_benchmark': True,
            'fresh_monolith_audit': False,
            'compute_efficiency_claim': False,
            'energy_claim': False,
            'distributed_consensus_claim': False,
            'actor_identity_claim': False,
        },
    }


if __name__ == '__main__':
    print(json.dumps(self_test(), indent=2, sort_keys=True))
