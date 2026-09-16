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

MEMBERSHIP_SCHEMA = 'axm.flowing-compute-witness-membership/v0.1'
POINTER_SCHEMA = 'axm.flowing-compute-witness-membership-pointer/v0.1'
RECONFIG_SCHEMA = 'axm.flowing-compute-witness-reconfiguration/v0.1'
WITNESS_RECORD_SCHEMA = 'axm.flowing-compute-witness-membership-record/v0.1'
DEFAULT_WITNESS_IDS = ('witness-a', 'witness-b', 'witness-c')

# Exact Wave 87 provenance. This wave intentionally studies recovery/membership
# semantics and does not claim a fresh monolith audit.
WAVE87_TOOL_COMMIT = '357cc16fa6448b335f5586e69796583068a03f79'
WAVE87_TOOL_BLOB_SHA = '102a28b1f6961987f7e5707fd4ba82c524a73df3'
WAVE87_TOOL_FILE_SHA256 = '512ae95192cabd962a4744c94eee1e0f93fed6b49524963dd93ee3b5c20b6f9a'
W81_RETENTION_SHA = '53d91b18e1a12eb27bd503bcfa70b4cd74add598ceaef522c88d7c075fdee4d4'
W83_DROP_RETENTION_SHA = '4078169dce33c5816c7dd1073eaff5920bcfb07284a023726322e67970378dd1'


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
        encoded = canon(value) + b'\n'
        path = self.path_for(object_id)
        if path.exists():
            if path.read_bytes() != encoded:
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


def normalize_ids(ids: Iterable[str]) -> list[str]:
    out = sorted(str(x) for x in ids)
    if len(out) < 2 or len(out) != len(set(out)) or any(not x for x in out):
        raise ValueError('witness membership must contain at least two unique non-empty ids')
    return out


def make_membership(*, generation: int, witness_ids: Iterable[str],
                    predecessor_membership_sha256: str | None,
                    transition_kind: str, note: str = '') -> dict[str, Any]:
    ids = normalize_ids(witness_ids)
    if generation < 0:
        raise ValueError('generation')
    if transition_kind not in ('GENESIS', 'UNCHANGED', 'ADD', 'REMOVE', 'REPLACE'):
        raise ValueError('transition_kind')
    if generation == 0 and predecessor_membership_sha256 is not None:
        raise ValueError('genesis predecessor')
    if generation > 0 and not predecessor_membership_sha256:
        raise ValueError('membership predecessor required')
    return seal({
        'schema': MEMBERSHIP_SCHEMA,
        'generation': generation,
        'witness_ids': ids,
        'predecessor_membership_sha256': predecessor_membership_sha256,
        'transition_kind': transition_kind,
        'provenance': {
            'wave87_tool_commit': WAVE87_TOOL_COMMIT,
            'wave87_tool_blob_sha': WAVE87_TOOL_BLOB_SHA,
            'wave87_tool_file_sha256': WAVE87_TOOL_FILE_SHA256,
        },
        'note': note,
        'membership_sha256': '',
    }, 'membership_sha256')


def validate_membership(m: dict[str, Any]) -> None:
    validate_seal(m, 'membership_sha256')
    if m.get('schema') != MEMBERSHIP_SCHEMA:
        raise ValueError('membership schema')
    if normalize_ids(m.get('witness_ids', [])) != m.get('witness_ids'):
        raise ValueError('membership ids not canonical')
    prov = m.get('provenance', {})
    if prov.get('wave87_tool_commit') != WAVE87_TOOL_COMMIT or prov.get('wave87_tool_blob_sha') != WAVE87_TOOL_BLOB_SHA:
        raise ValueError('Wave87 provenance mismatch')


def make_pointer(*, commit_epoch: int, retention_sha256: str, membership_sha256: str,
                 predecessor_pointer_sha256: str | None, selection_kind: str,
                 note: str = '') -> dict[str, Any]:
    if commit_epoch < 0:
        raise ValueError('commit_epoch')
    if selection_kind not in ('GENESIS', 'FORWARD', 'ROLLBACK', 'RECONFIGURE'):
        raise ValueError('selection_kind')
    return seal({
        'schema': POINTER_SCHEMA,
        'commit_epoch': commit_epoch,
        'retention_sha256': retention_sha256,
        'membership_sha256': membership_sha256,
        'predecessor_pointer_sha256': predecessor_pointer_sha256,
        'selection_kind': selection_kind,
        'note': note,
        'pointer_sha256': '',
    }, 'pointer_sha256')


def validate_pointer(p: dict[str, Any]) -> None:
    validate_seal(p, 'pointer_sha256')
    if p.get('schema') != POINTER_SCHEMA:
        raise ValueError('pointer schema')


class Primary:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.objects = ObjectStore(self.root / 'objects', 'pointer_sha256')
        self.current_path = self.root / 'current.json'

    def initialize(self, membership_sha256: str) -> dict[str, Any]:
        if self.current_path.exists():
            raise ValueError('primary already initialized')
        p = make_pointer(commit_epoch=0, retention_sha256=W81_RETENTION_SHA,
                         membership_sha256=membership_sha256,
                         predecessor_pointer_sha256=None, selection_kind='GENESIS',
                         note='Wave88 genesis binds explicit membership state')
        self.objects.put(p)
        durable_write(self.current_path, canon(p) + b'\n')
        return p

    def current(self) -> dict[str, Any]:
        p = json.loads(self.current_path.read_text('utf-8'))
        validate_pointer(p)
        if self.objects.get(p['pointer_sha256']) != p:
            raise ValueError('current pointer differs from stored object')
        return p

    def stage(self, p: dict[str, Any]) -> None:
        self.objects.put(p)

    def commit(self, p: dict[str, Any]) -> None:
        self.objects.get(p['pointer_sha256'])
        durable_write(self.current_path, canon(p) + b'\n')


class Witness:
    def __init__(self, root: str | Path, witness_id: str):
        self.root = Path(root)
        self.witness_id = witness_id
        self.records = ObjectStore(self.root / 'records', 'record_sha256')
        self.head_path = self.root / 'HEAD'

    def exists(self) -> bool:
        return self.head_path.is_file()

    def head(self) -> dict[str, Any]:
        if not self.head_path.is_file():
            raise FileNotFoundError(f'{self.witness_id} HEAD missing')
        rid = self.head_path.read_text('utf-8').strip()
        record = self.records.get(rid)
        if record['witness_id'] != self.witness_id:
            raise ValueError('witness id mismatch')
        return record

    def _store_head(self, record: dict[str, Any]) -> dict[str, Any]:
        self.records.put(record)
        durable_write(self.head_path, (record['record_sha256'] + '\n').encode())
        return record

    def initialize(self, pointer: dict[str, Any], membership: dict[str, Any]) -> dict[str, Any]:
        if self.exists():
            raise ValueError('witness already initialized')
        if self.witness_id not in membership['witness_ids']:
            raise ValueError('witness not in membership')
        rec = seal({
            'schema': WITNESS_RECORD_SCHEMA,
            'witness_id': self.witness_id,
            'anchor_epoch': pointer['commit_epoch'],
            'pointer_sha256': pointer['pointer_sha256'],
            'retention_sha256': pointer['retention_sha256'],
            'membership_sha256': membership['membership_sha256'],
            'predecessor_record_sha256': None,
            'reconfiguration_sha256': None,
            'record_role': 'GENESIS',
            'record_sha256': '',
        }, 'record_sha256')
        return self._store_head(rec)

    def advance_existing(self, reconfig: dict[str, Any]) -> dict[str, Any]:
        validate_reconfiguration(reconfig)
        pred = reconfig['predecessor_witness_heads'].get(self.witness_id)
        if not pred:
            raise ValueError('not an old witness')
        current = self.head()
        if current['record_sha256'] != pred:
            raise ValueError('existing witness not at exact reconfiguration predecessor')
        role = 'RETAINED' if self.witness_id in reconfig['target_witness_ids'] else 'RETIRED'
        rec = seal({
            'schema': WITNESS_RECORD_SCHEMA,
            'witness_id': self.witness_id,
            'anchor_epoch': reconfig['target_epoch'],
            'pointer_sha256': reconfig['target_pointer_sha256'],
            'retention_sha256': reconfig['target_retention_sha256'],
            'membership_sha256': reconfig['target_membership_sha256'],
            'predecessor_record_sha256': pred,
            'reconfiguration_sha256': reconfig['reconfiguration_sha256'],
            'record_role': role,
            'record_sha256': '',
        }, 'record_sha256')
        return self._store_head(rec)

    def bootstrap_added(self, reconfig: dict[str, Any]) -> dict[str, Any]:
        validate_reconfiguration(reconfig)
        if self.witness_id not in reconfig['added_witness_ids']:
            raise ValueError('not an added witness')
        if self.exists():
            raise ValueError('added witness already has unrelated state; explicit replacement/reset required')
        rec = seal({
            'schema': WITNESS_RECORD_SCHEMA,
            'witness_id': self.witness_id,
            'anchor_epoch': reconfig['target_epoch'],
            'pointer_sha256': reconfig['target_pointer_sha256'],
            'retention_sha256': reconfig['target_retention_sha256'],
            'membership_sha256': reconfig['target_membership_sha256'],
            'predecessor_record_sha256': None,
            'reconfiguration_sha256': reconfig['reconfiguration_sha256'],
            'record_role': 'ADDED',
            'record_sha256': '',
        }, 'record_sha256')
        return self._store_head(rec)


class WitnessDirectory:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def witness(self, witness_id: str) -> Witness:
        return Witness(self.root / witness_id, witness_id)


def make_reconfiguration(*, current_pointer: dict[str, Any], target_pointer: dict[str, Any],
                         old_membership: dict[str, Any], target_membership: dict[str, Any],
                         witness_dir: WitnessDirectory, note: str = '') -> dict[str, Any]:
    validate_pointer(current_pointer)
    validate_pointer(target_pointer)
    validate_membership(old_membership)
    validate_membership(target_membership)
    old_ids = old_membership['witness_ids']
    new_ids = target_membership['witness_ids']
    if target_pointer['commit_epoch'] != current_pointer['commit_epoch'] + 1:
        raise ValueError('target epoch')
    if target_pointer['predecessor_pointer_sha256'] != current_pointer['pointer_sha256']:
        raise ValueError('target predecessor')
    if current_pointer['membership_sha256'] != old_membership['membership_sha256']:
        raise ValueError('old membership not current')
    if target_pointer['membership_sha256'] != target_membership['membership_sha256']:
        raise ValueError('target membership pointer mismatch')
    pred_heads = {wid: witness_dir.witness(wid).head()['record_sha256'] for wid in old_ids}
    added = sorted(set(new_ids) - set(old_ids))
    removed = sorted(set(old_ids) - set(new_ids))
    retained = sorted(set(old_ids) & set(new_ids))
    return seal({
        'schema': RECONFIG_SCHEMA,
        'provenance': {
            'wave87_tool_commit': WAVE87_TOOL_COMMIT,
            'wave87_tool_blob_sha': WAVE87_TOOL_BLOB_SHA,
        },
        'predecessor_epoch': current_pointer['commit_epoch'],
        'predecessor_pointer_sha256': current_pointer['pointer_sha256'],
        'predecessor_retention_sha256': current_pointer['retention_sha256'],
        'predecessor_membership_sha256': old_membership['membership_sha256'],
        'target_epoch': target_pointer['commit_epoch'],
        'target_pointer_sha256': target_pointer['pointer_sha256'],
        'target_retention_sha256': target_pointer['retention_sha256'],
        'target_membership_sha256': target_membership['membership_sha256'],
        'old_witness_ids': old_ids,
        'target_witness_ids': new_ids,
        'retained_witness_ids': retained,
        'added_witness_ids': added,
        'removed_witness_ids': removed,
        'predecessor_witness_heads': pred_heads,
        'note': note,
        'reconfiguration_sha256': '',
    }, 'reconfiguration_sha256')


def validate_reconfiguration(r: dict[str, Any]) -> None:
    validate_seal(r, 'reconfiguration_sha256')
    if r.get('schema') != RECONFIG_SCHEMA:
        raise ValueError('reconfiguration schema')
    old_ids = normalize_ids(r.get('old_witness_ids', []))
    new_ids = normalize_ids(r.get('target_witness_ids', []))
    if old_ids != r['old_witness_ids'] or new_ids != r['target_witness_ids']:
        raise ValueError('reconfiguration ids not canonical')
    if sorted(r.get('predecessor_witness_heads', {})) != old_ids:
        raise ValueError('predecessor head membership mismatch')
    if r['target_epoch'] != r['predecessor_epoch'] + 1:
        raise ValueError('epoch discontinuity')
    if r['added_witness_ids'] != sorted(set(new_ids) - set(old_ids)):
        raise ValueError('added witness derivation mismatch')
    if r['removed_witness_ids'] != sorted(set(old_ids) - set(new_ids)):
        raise ValueError('removed witness derivation mismatch')
    if r['retained_witness_ids'] != sorted(set(old_ids) & set(new_ids)):
        raise ValueError('retained witness derivation mismatch')


def current_membership(primary: Primary, memberships: ObjectStore) -> dict[str, Any]:
    p = primary.current()
    m = memberships.get(p['membership_sha256'])
    validate_membership(m)
    return m


def initialize(root: Path) -> tuple[Primary, ObjectStore, ObjectStore, WitnessDirectory, dict[str, Any], dict[str, Any]]:
    memberships = ObjectStore(root / 'memberships', 'membership_sha256')
    reconfigs = ObjectStore(root / 'reconfigurations', 'reconfiguration_sha256')
    witnesses = WitnessDirectory(root / 'witnesses')
    membership = make_membership(generation=0, witness_ids=DEFAULT_WITNESS_IDS,
                                 predecessor_membership_sha256=None, transition_kind='GENESIS',
                                 note='Wave88 exact explicit witness membership genesis')
    memberships.put(membership)
    primary = Primary(root / 'primary')
    pointer = primary.initialize(membership['membership_sha256'])
    for wid in membership['witness_ids']:
        witnesses.witness(wid).initialize(pointer, membership)
    return primary, memberships, reconfigs, witnesses, membership, pointer


def validate_steady_state(*, primary: Primary, memberships: ObjectStore,
                          witness_dir: WitnessDirectory, reconfigs: ObjectStore) -> dict[str, Any]:
    try:
        p = primary.current()
        m = memberships.get(p['membership_sha256'])
        validate_membership(m)
    except Exception as exc:
        return {'status': 'PRIMARY_OR_MEMBERSHIP_INVALID_HOLD', 'error': f'{type(exc).__name__}: {exc}'}
    for wid in m['witness_ids']:
        try:
            h = witness_dir.witness(wid).head()
        except Exception as exc:
            return {'status': 'REQUIRED_WITNESS_MISSING_HOLD', 'witness_id': wid, 'error': f'{type(exc).__name__}: {exc}'}
        if h['anchor_epoch'] != p['commit_epoch'] or h['pointer_sha256'] != p['pointer_sha256'] \
                or h['membership_sha256'] != m['membership_sha256']:
            return {'status': 'REQUIRED_WITNESS_BINDING_HOLD', 'witness_id': wid}
        if p['commit_epoch'] > 0:
            rid = h.get('reconfiguration_sha256')
            if not rid:
                return {'status': 'WITNESS_RECONFIGURATION_MISSING_HOLD', 'witness_id': wid}
            try:
                r = reconfigs.get(rid)
                validate_reconfiguration(r)
            except Exception as exc:
                return {'status': 'RECONFIGURATION_MISSING_OR_INVALID_HOLD', 'witness_id': wid,
                        'error': f'{type(exc).__name__}: {exc}'}
            if r['target_pointer_sha256'] != p['pointer_sha256'] or r['target_membership_sha256'] != m['membership_sha256'] \
                    or wid not in r['target_witness_ids']:
                return {'status': 'WITNESS_RECONFIGURATION_BINDING_HOLD', 'witness_id': wid}
    return {'status': 'CONSISTENT', 'epoch': p['commit_epoch'],
            'membership_sha256': m['membership_sha256'], 'witness_ids': m['witness_ids']}


def prepare_reconfiguration(*, primary: Primary, memberships: ObjectStore, reconfigs: ObjectStore,
                            witness_dir: WitnessDirectory, target_witness_ids: Iterable[str],
                            transition_kind: str, note: str = '') -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if validate_steady_state(primary=primary, memberships=memberships, witness_dir=witness_dir, reconfigs=reconfigs)['status'] != 'CONSISTENT':
        raise RuntimeError('cannot prepare from non-consistent state')
    current = primary.current()
    old = memberships.get(current['membership_sha256'])
    target_ids = normalize_ids(target_witness_ids)
    expected_kind = ('ADD' if set(target_ids) > set(old['witness_ids']) else
                     'REMOVE' if set(target_ids) < set(old['witness_ids']) else
                     'REPLACE' if target_ids != old['witness_ids'] else 'UNCHANGED')
    if transition_kind != expected_kind:
        raise ValueError(f'transition kind must be {expected_kind}')
    target_m = make_membership(generation=old['generation'] + 1, witness_ids=target_ids,
                               predecessor_membership_sha256=old['membership_sha256'],
                               transition_kind=transition_kind, note=note)
    memberships.put(target_m)
    target_p = make_pointer(commit_epoch=current['commit_epoch'] + 1,
                            retention_sha256=current['retention_sha256'],
                            membership_sha256=target_m['membership_sha256'],
                            predecessor_pointer_sha256=current['pointer_sha256'],
                            selection_kind='RECONFIGURE', note=note)
    primary.stage(target_p)
    r = make_reconfiguration(current_pointer=current, target_pointer=target_p,
                             old_membership=old, target_membership=target_m,
                             witness_dir=witness_dir, note=note)
    reconfigs.put(r)
    return target_m, target_p, r


def _record_matches_target(record: dict[str, Any], wid: str, r: dict[str, Any]) -> bool:
    try:
        validate_seal(record, 'record_sha256')
    except Exception:
        return False
    if record.get('witness_id') != wid or record.get('anchor_epoch') != r['target_epoch'] \
            or record.get('pointer_sha256') != r['target_pointer_sha256'] \
            or record.get('membership_sha256') != r['target_membership_sha256'] \
            or record.get('reconfiguration_sha256') != r['reconfiguration_sha256']:
        return False
    if wid in r['old_witness_ids']:
        return record.get('predecessor_record_sha256') == r['predecessor_witness_heads'][wid]
    return wid in r['added_witness_ids'] and record.get('predecessor_record_sha256') is None


def recovery_status(*, primary: Primary, memberships: ObjectStore, reconfigs: ObjectStore,
                    witness_dir: WitnessDirectory, repair: bool = False) -> dict[str, Any]:
    steady = validate_steady_state(primary=primary, memberships=memberships, witness_dir=witness_dir, reconfigs=reconfigs)
    if steady['status'] == 'CONSISTENT':
        return steady
    try:
        current = primary.current()
        old_m = memberships.get(current['membership_sha256'])
    except Exception as exc:
        return {'status': 'PRIMARY_OR_MEMBERSHIP_INVALID_HOLD', 'error': f'{type(exc).__name__}: {exc}'}

    candidates: set[str] = set()
    for wid in old_m['witness_ids']:
        w = witness_dir.witness(wid)
        if not w.exists():
            continue
        try:
            h = w.head()
        except Exception:
            continue
        if h.get('anchor_epoch') == current['commit_epoch'] + 1 and h.get('reconfiguration_sha256'):
            candidates.add(h['reconfiguration_sha256'])
    if len(candidates) > 1:
        return {'status': 'COMPETING_RECONFIGURATIONS_HOLD', 'reconfiguration_ids': sorted(candidates)}
    if not candidates:
        return steady
    rid = next(iter(candidates))
    try:
        r = reconfigs.get(rid)
        validate_reconfiguration(r)
        target_m = memberships.get(r['target_membership_sha256'])
        target_p = primary.objects.get(r['target_pointer_sha256'])
    except Exception as exc:
        return {'status': 'RECONFIGURATION_DEPENDENCY_INVALID_HOLD', 'error': f'{type(exc).__name__}: {exc}'}
    if r['predecessor_pointer_sha256'] != current['pointer_sha256'] or r['predecessor_membership_sha256'] != old_m['membership_sha256']:
        return {'status': 'RECONFIGURATION_PREDECESSOR_MISMATCH_HOLD'}
    if target_m['predecessor_membership_sha256'] != old_m['membership_sha256'] or target_p['predecessor_pointer_sha256'] != current['pointer_sha256']:
        return {'status': 'TARGET_LINEAGE_MISMATCH_HOLD'}

    old_advanced: list[str] = []
    old_lagging: list[str] = []
    for wid in r['old_witness_ids']:
        w = witness_dir.witness(wid)
        if not w.exists():
            return {'status': 'OLD_REQUIRED_WITNESS_MISSING_HOLD', 'witness_id': wid}
        h = w.head()
        if h['record_sha256'] == r['predecessor_witness_heads'][wid]:
            old_lagging.append(wid)
        elif _record_matches_target(h, wid, r):
            old_advanced.append(wid)
        else:
            other = h.get('reconfiguration_sha256')
            if other and other != rid:
                return {'status': 'COMPETING_RECONFIGURATIONS_HOLD', 'reconfiguration_ids': sorted({rid, other})}
            return {'status': 'OLD_WITNESS_NOT_PREDECESSOR_OR_TARGET_HOLD', 'witness_id': wid}

    if old_lagging:
        if not old_advanced:
            return {'status': 'PREPARED_RECONFIGURATION_NO_AUTHORITY', 'reconfiguration_sha256': rid}
        if repair:
            for wid in old_lagging:
                witness_dir.witness(wid).advance_existing(r)
            return recovery_status(primary=primary, memberships=memberships, reconfigs=reconfigs,
                                   witness_dir=witness_dir, repair=True)
        return {'status': 'OLD_MEMBERSHIP_HANDOFF_PARTIAL_RECOVERABLE',
                'advanced_old_witnesses': old_advanced, 'lagging_old_witnesses': old_lagging}

    added_missing: list[str] = []
    for wid in r['added_witness_ids']:
        w = witness_dir.witness(wid)
        if not w.exists():
            added_missing.append(wid)
            continue
        h = w.head()
        if not _record_matches_target(h, wid, r):
            return {'status': 'ADDED_WITNESS_HAS_UNRELATED_STATE_HOLD', 'witness_id': wid}
    if added_missing:
        if repair:
            for wid in added_missing:
                witness_dir.witness(wid).bootstrap_added(r)
            return recovery_status(primary=primary, memberships=memberships, reconfigs=reconfigs,
                                   witness_dir=witness_dir, repair=True)
        return {'status': 'NEW_MEMBERSHIP_BOOTSTRAP_RECOVERABLE', 'missing_added_witnesses': added_missing}

    if repair:
        primary.commit(target_p)
        return validate_steady_state(primary=primary, memberships=memberships,
                                     witness_dir=witness_dir, reconfigs=reconfigs)
    return {'status': 'RECONFIGURATION_PENDING_POINTER_MOVE', 'reconfiguration_sha256': rid}


def commit_reconfiguration(*, primary: Primary, memberships: ObjectStore, reconfigs: ObjectStore,
                           witness_dir: WitnessDirectory, r: dict[str, Any],
                           crash_after_old: int | None = None,
                           crash_after_added: int | None = None,
                           crash_before_pointer: bool = False) -> dict[str, Any]:
    validate_reconfiguration(r)
    old_ids = r['old_witness_ids']
    if crash_after_old is not None and not (0 <= crash_after_old <= len(old_ids)):
        raise ValueError('crash_after_old')
    if crash_after_old == 0:
        return {'status': 'CRASH_BEFORE_OLD_HANDOFF'}
    count = 0
    for wid in old_ids:
        witness_dir.witness(wid).advance_existing(r)
        count += 1
        if crash_after_old == count:
            return {'status': 'CRASH_DURING_OLD_HANDOFF', 'old_witnesses_advanced': count}
    added = r['added_witness_ids']
    if crash_after_added is not None and not (0 <= crash_after_added <= len(added)):
        raise ValueError('crash_after_added')
    if crash_after_added == 0 and added:
        return {'status': 'CRASH_BEFORE_ADDED_BOOTSTRAP'}
    count_added = 0
    for wid in added:
        witness_dir.witness(wid).bootstrap_added(r)
        count_added += 1
        if crash_after_added == count_added:
            return {'status': 'CRASH_DURING_ADDED_BOOTSTRAP', 'added_witnesses_bootstrapped': count_added}
    if crash_before_pointer:
        return {'status': 'CRASH_BEFORE_POINTER_MOVE'}
    target = primary.objects.get(r['target_pointer_sha256'])
    primary.commit(target)
    return {'status': 'COMMITTED', 'epoch': target['commit_epoch'],
            'membership_sha256': target['membership_sha256']}


def naive_runtime_subset_consistent(primary: Primary, witness_dir: WitnessDirectory, caller_ids: Iterable[str]) -> bool:
    """Preserved negative control: caller-selected membership can hide an omitted witness."""
    p = primary.current()
    ids = list(caller_ids)
    if len(ids) < 2:
        return False
    for wid in ids:
        h = witness_dir.witness(wid).head()
        if h['anchor_epoch'] != p['commit_epoch'] or h['pointer_sha256'] != p['pointer_sha256']:
            return False
    return True


def self_test(benchmark_rounds: int = 60) -> dict[str, Any]:
    checks: list[tuple[str, bool]] = []
    details: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix='axm-wave88-') as tmp:
        root = Path(tmp)
        primary, memberships, reconfigs, witnesses, genesis_m, genesis_p = initialize(root)
        checks += [
            ('exact_wave87_tool_commit_provenance', WAVE87_TOOL_COMMIT == '357cc16fa6448b335f5586e69796583068a03f79'),
            ('genesis_explicit_membership', genesis_p['membership_sha256'] == genesis_m['membership_sha256']),
            ('genesis_three_witnesses', genesis_m['witness_ids'] == list(DEFAULT_WITNESS_IDS)),
            ('genesis_consistent', validate_steady_state(primary=primary, memberships=memberships, witness_dir=witnesses, reconfigs=reconfigs)['status'] == 'CONSISTENT'),
        ]

        target_m, target_p, r = prepare_reconfiguration(
            primary=primary, memberships=memberships, reconfigs=reconfigs, witness_dir=witnesses,
            target_witness_ids=('witness-a', 'witness-b', 'witness-d'), transition_kind='REPLACE',
            note='Wave88 C->D explicit membership replacement')
        checks.append(('prepared_reconfiguration_has_zero_authority', recovery_status(primary=primary, memberships=memberships, reconfigs=reconfigs, witness_dir=witnesses)['status'] == 'CONSISTENT'))
        commit_reconfiguration(primary=primary, memberships=memberships, reconfigs=reconfigs, witness_dir=witnesses, r=r, crash_after_old=1)
        s = recovery_status(primary=primary, memberships=memberships, reconfigs=reconfigs, witness_dir=witnesses)
        checks.append(('partial_old_handoff_recoverable', s['status'] == 'OLD_MEMBERSHIP_HANDOFF_PARTIAL_RECOVERABLE'))
        repaired = recovery_status(primary=primary, memberships=memberships, reconfigs=reconfigs, witness_dir=witnesses, repair=True)
        checks.append(('repair_finishes_handoff_bootstrap_and_pointer', repaired['status'] == 'CONSISTENT' and repaired['witness_ids'] == ['witness-a','witness-b','witness-d']))
        checks.append(('removed_witness_no_longer_required', validate_steady_state(primary=primary, memberships=memberships, witness_dir=witnesses, reconfigs=reconfigs)['status'] == 'CONSISTENT'))
        checks.append(('retired_witness_record_preserved', witnesses.witness('witness-c').head()['record_role'] == 'RETIRED'))
        checks.append(('added_witness_record_bound', witnesses.witness('witness-d').head()['record_role'] == 'ADDED'))

        saved_d = witnesses.witness('witness-d').root
        backup_d = root / 'backup-witness-d'
        shutil.copytree(saved_d, backup_d)
        shutil.rmtree(saved_d)
        checks.append(('required_current_witness_missing_holds', validate_steady_state(primary=primary, memberships=memberships, witness_dir=witnesses, reconfigs=reconfigs)['status'] == 'REQUIRED_WITNESS_MISSING_HOLD'))
        checks.append(('legacy_caller_subset_negative_control_reproduced', naive_runtime_subset_consistent(primary, witnesses, ['witness-a','witness-b'])))
        if saved_d.exists():
            shutil.rmtree(saved_d)
        shutil.copytree(backup_d, saved_d)
        shutil.rmtree(backup_d)

        t2m, t2p, r2 = prepare_reconfiguration(primary=primary, memberships=memberships, reconfigs=reconfigs,
                                               witness_dir=witnesses,
                                               target_witness_ids=('witness-a','witness-b','witness-d','witness-e'),
                                               transition_kind='ADD', note='add E attack case')
        bogus = witnesses.witness('witness-e')
        bogus.root.mkdir(parents=True, exist_ok=True)
        bogus_rec = seal({'schema': WITNESS_RECORD_SCHEMA, 'witness_id':'witness-e', 'anchor_epoch':0,
                          'pointer_sha256': genesis_p['pointer_sha256'], 'retention_sha256':W81_RETENTION_SHA,
                          'membership_sha256':genesis_m['membership_sha256'], 'predecessor_record_sha256':None,
                          'reconfiguration_sha256':None, 'record_role':'UNRELATED', 'record_sha256':''}, 'record_sha256')
        bogus._store_head(bogus_rec)
        for wid in r2['old_witness_ids']:
            witnesses.witness(wid).advance_existing(r2)
        checks.append(('preexisting_added_witness_unrelated_state_holds', recovery_status(primary=primary, memberships=memberships, reconfigs=reconfigs, witness_dir=witnesses)['status'] == 'ADDED_WITNESS_HAS_UNRELATED_STATE_HOLD'))

    def fresh():
        td = tempfile.TemporaryDirectory(prefix='axm-wave88-case-')
        rr = Path(td.name)
        return td, rr, initialize(rr)

    td, rr, objs = fresh()
    try:
        p, ms, rs, ws, gm, gp = objs
        tm, tp, rc = prepare_reconfiguration(primary=p, memberships=ms, reconfigs=rs, witness_dir=ws,
                                              target_witness_ids=('witness-a','witness-b','witness-d'), transition_kind='REPLACE')
        commit_reconfiguration(primary=p, memberships=ms, reconfigs=rs, witness_dir=ws, r=rc, crash_before_pointer=True)
        checks.append(('all_handoff_done_pointer_not_moved_is_recoverable', recovery_status(primary=p,memberships=ms,reconfigs=rs,witness_dir=ws)['status'] == 'RECONFIGURATION_PENDING_POINTER_MOVE'))
        checks.append(('pointer_move_recovery_succeeds', recovery_status(primary=p,memberships=ms,reconfigs=rs,witness_dir=ws,repair=True)['status'] == 'CONSISTENT'))
    finally:
        td.cleanup()

    td, rr, objs = fresh()
    try:
        p, ms, rs, ws, gm, gp = objs
        tm, tp, rc = prepare_reconfiguration(primary=p,memberships=ms,reconfigs=rs,witness_dir=ws,
                                              target_witness_ids=('witness-a','witness-b','witness-d'), transition_kind='REPLACE')
        tm2 = make_membership(generation=1, witness_ids=('witness-a','witness-c','witness-e'),
                              predecessor_membership_sha256=gm['membership_sha256'], transition_kind='REPLACE')
        ms.put(tm2)
        tp2 = make_pointer(commit_epoch=1, retention_sha256=gp['retention_sha256'], membership_sha256=tm2['membership_sha256'],
                           predecessor_pointer_sha256=gp['pointer_sha256'], selection_kind='RECONFIGURE')
        p.stage(tp2)
        rc2 = make_reconfiguration(current_pointer=gp,target_pointer=tp2,old_membership=gm,target_membership=tm2,witness_dir=ws)
        rs.put(rc2)
        ws.witness('witness-a').advance_existing(rc)
        ws.witness('witness-b').advance_existing(rc2)
        checks.append(('competing_membership_reconfigurations_hold_no_vote', recovery_status(primary=p,memberships=ms,reconfigs=rs,witness_dir=ws)['status'] == 'COMPETING_RECONFIGURATIONS_HOLD'))
    finally:
        td.cleanup()

    td, rr, objs = fresh()
    try:
        p, ms, rs, ws, gm, gp = objs
        tm, tp, rc = prepare_reconfiguration(primary=p,memberships=ms,reconfigs=rs,witness_dir=ws,
                                              target_witness_ids=('witness-a','witness-b','witness-d'), transition_kind='REPLACE')
        path = ms.path_for(tm['membership_sha256'])
        forged = dict(tm); forged['note'] = 'forged'; forged = seal(forged, 'membership_sha256')
        path.write_bytes(canon(forged)+b'\n')
        checks.append(('corrupt_prepared_membership_has_zero_current_authority', validate_steady_state(primary=p,memberships=ms,witness_dir=ws,reconfigs=rs)['status'] == 'CONSISTENT'))
        ws.witness('witness-a').advance_existing(rc)
        checks.append(('referenced_membership_store_key_body_forgery_holds', recovery_status(primary=p,memberships=ms,reconfigs=rs,witness_dir=ws)['status'] == 'RECONFIGURATION_DEPENDENCY_INVALID_HOLD'))
        details['forgery_note'] = 'A corrupt prepared target has no authority before fan-out; after one old witness references that exact reconfiguration, recovery validates the target membership and fails closed.'
    finally:
        td.cleanup()

    td, rr, objs = fresh()
    try:
        p, ms, rs, ws, gm, gp = objs
        tm, tp, rc = prepare_reconfiguration(primary=p,memberships=ms,reconfigs=rs,witness_dir=ws,
                                              target_witness_ids=('witness-a','witness-b','witness-d','witness-e'), transition_kind='REPLACE')
        out = commit_reconfiguration(primary=p,memberships=ms,reconfigs=rs,witness_dir=ws,r=rc,crash_after_added=1)
        checks.append(('crash_during_added_bootstrap_recoverable', out['status'] == 'CRASH_DURING_ADDED_BOOTSTRAP' and recovery_status(primary=p,memberships=ms,reconfigs=rs,witness_dir=ws)['status'] == 'NEW_MEMBERSHIP_BOOTSTRAP_RECOVERABLE'))
        checks.append(('added_bootstrap_recovery_finishes_exact_missing_member', recovery_status(primary=p,memberships=ms,reconfigs=rs,witness_dir=ws,repair=True)['status'] == 'CONSISTENT'))
    finally:
        td.cleanup()

    td, rr, objs = fresh()
    try:
        p, ms, rs, ws, gm, gp = objs
        tm, tp, rc = prepare_reconfiguration(primary=p,memberships=ms,reconfigs=rs,witness_dir=ws,
                                              target_witness_ids=('witness-a','witness-b'), transition_kind='REMOVE')
        shutil.rmtree(ws.witness('witness-c').root)
        checks.append(('old_required_witness_cannot_vanish_before_handoff', recovery_status(primary=p,memberships=ms,reconfigs=rs,witness_dir=ws)['status'] == 'REQUIRED_WITNESS_MISSING_HOLD'))
    finally:
        td.cleanup()

    td, rr, objs = fresh()
    try:
        p, ms, rs, ws, gm, gp = objs
        tm, tp, rc = prepare_reconfiguration(primary=p,memberships=ms,reconfigs=rs,witness_dir=ws,
                                              target_witness_ids=('witness-a','witness-b'), transition_kind='REMOVE')
        out = commit_reconfiguration(primary=p,memberships=ms,reconfigs=rs,witness_dir=ws,r=rc)
        checks.append(('remove_only_commit_succeeds', out['status']=='COMMITTED' and validate_steady_state(primary=p,memberships=ms,witness_dir=ws,reconfigs=rs)['witness_ids']==['witness-a','witness-b']))
        checks.append(('removed_witness_existence_has_zero_current_authority', ws.witness('witness-c').exists() and validate_steady_state(primary=p,memberships=ms,witness_dir=ws,reconfigs=rs)['status']=='CONSISTENT'))
    finally:
        td.cleanup()

    td, rr, objs = fresh()
    try:
        p, ms, rs, ws, gm, gp = objs
        tm, tp, rc = prepare_reconfiguration(primary=p,memberships=ms,reconfigs=rs,witness_dir=ws,
                                              target_witness_ids=('witness-a','witness-b','witness-c','witness-d'), transition_kind='ADD')
        out = commit_reconfiguration(primary=p,memberships=ms,reconfigs=rs,witness_dir=ws,r=rc)
        checks.append(('add_only_commit_succeeds', out['status']=='COMMITTED' and validate_steady_state(primary=p,memberships=ms,witness_dir=ws,reconfigs=rs)['witness_ids']==['witness-a','witness-b','witness-c','witness-d']))
    finally:
        td.cleanup()

    samples: list[float] = []
    for _ in range(benchmark_rounds):
        with tempfile.TemporaryDirectory(prefix='axm-wave88-bench-') as tmp:
            rr = Path(tmp)
            p, ms, rs, ws, gm, gp = initialize(rr)
            start = time.process_time_ns()
            tm, tp, rc = prepare_reconfiguration(primary=p,memberships=ms,reconfigs=rs,witness_dir=ws,
                                                  target_witness_ids=('witness-a','witness-b','witness-d'), transition_kind='REPLACE')
            commit_reconfiguration(primary=p,memberships=ms,reconfigs=rs,witness_dir=ws,r=rc)
            elapsed = time.process_time_ns() - start
            if validate_steady_state(primary=p,memberships=ms,witness_dir=ws,reconfigs=rs)['status'] != 'CONSISTENT':
                raise AssertionError('benchmark produced invalid state')
            samples.append(elapsed / 1000.0)

    failed = [name for name, ok in checks if not ok]
    return {
        'schema': 'axm.flowing-compute-wave88-report/v0.1',
        'status': 'PASS' if not failed else 'FAIL',
        'passed_checks': sum(1 for _, ok in checks if ok),
        'total_checks': len(checks),
        'failed_checks': failed,
        'checks': [{'name': name, 'pass': ok} for name, ok in checks],
        'synthetic_single_host_reconfiguration_cpu_us_median': statistics.median(samples),
        'benchmark_rounds': benchmark_rounds,
        'truth_boundary': {
            'fresh_monolith_audit': False,
            'compute_efficiency_claim': False,
            'energy_claim': False,
            'distributed_consensus_claim': False,
            'independent_physical_witnesses': False,
            'note': 'Membership/reconfiguration orchestration only; local directories remain one host failure domain.'
        },
        'details': details,
    }


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--benchmark-rounds', type=int, default=60)
    parser.add_argument('--json-out')
    args = parser.parse_args()
    report = self_test(args.benchmark_rounds)
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.json_out:
        Path(args.json_out).write_text(text + '\n', encoding='utf-8')
    raise SystemExit(0 if report['status'] == 'PASS' else 1)
