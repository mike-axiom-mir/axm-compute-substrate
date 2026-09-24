from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EVALUATOR_SCHEMA = 'axm.flowing-compute-evaluator-provenance/v0.1'
REGISTRY_SCHEMA = 'axm.flowing-compute-evaluator-registry/v0.1'
REGISTRY_TRANSITION_SCHEMA = 'axm.flowing-compute-evaluator-registry-transition/v0.1'
ROOT_EVAL_SCHEMA = 'axm.flowing-compute-root-evaluation-provenance/v0.1'
AUTH_SCHEMA = 'axm.flowing-compute-membership-authorization-with-evaluator-provenance/v0.1'
REQUIRED_ROOTS = ('truth', 'agency_non_domination', 'continuity', 'wisdom_before_speed')
WITNESSES = ('registry-witness-a', 'registry-witness-b', 'registry-witness-c')

# Exact Wave 89 reusable source identity. Wave 90 is a provenance/lineage probe,
# intentionally not a fresh monolith audit or a compute-efficiency experiment.
WAVE89_TOOL_COMMIT = '22182ef762be05835d912ae48da40c6043fb81dc'
WAVE89_TOOL_BLOB_SHA = '71b62f37911a5c2c53a32ddf2a29bf5610833181'
WAVE89_TOOL_FILE_SHA256 = 'eef82f3db83954d97f15b4f7bda53cc01b75d63c0f289c9a94b4b2eff00d8066'


def canon(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def dig(value: Any) -> str:
    return hashlib.sha256(canon(value)).hexdigest()


def text_sha(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def seal(value: dict[str, Any], field: str) -> dict[str, Any]:
    out = dict(value)
    out.pop(field, None)
    out[field] = dig(out)
    return out


def validate_seal(value: dict[str, Any], field: str) -> None:
    body = dict(value)
    got = body.pop(field, None)
    if not isinstance(got, str) or len(got) != 64 or got != dig(body):
        raise ValueError(f'{field} mismatch')


def sha64(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError(f'{label} invalid')
    return value


def make_evaluator(evaluator_id: str, root_scope: list[str] | tuple[str, ...], tool_sha256: str,
                   source_sha256: str, *, label: str, predecessor_evaluator_sha256: str | None = None) -> dict[str, Any]:
    if not evaluator_id or not isinstance(evaluator_id, str):
        raise ValueError('evaluator_id invalid')
    roots = sorted(set(root_scope))
    if not roots or any(root not in REQUIRED_ROOTS for root in roots):
        raise ValueError('root_scope invalid')
    sha64(tool_sha256, 'evaluation_tool_sha256')
    sha64(source_sha256, 'evaluation_source_sha256')
    if predecessor_evaluator_sha256 is not None:
        sha64(predecessor_evaluator_sha256, 'predecessor_evaluator_sha256')
    return seal({
        'schema': EVALUATOR_SCHEMA,
        'evaluator_id': evaluator_id,
        'root_scope': roots,
        'evaluation_tool_sha256': tool_sha256,
        'evaluation_source_sha256': source_sha256,
        'predecessor_evaluator_sha256': predecessor_evaluator_sha256,
        'label': label,
        'test_only': True,
        'truth': {
            'content_identity_is_not_moral_legitimacy': True,
            'registry_membership_is_mechanical_provenance_only': True,
        },
        'evaluator_sha256': '',
    }, 'evaluator_sha256')


def validate_evaluator(evaluator: dict[str, Any]) -> None:
    validate_seal(evaluator, 'evaluator_sha256')
    if evaluator.get('schema') != EVALUATOR_SCHEMA:
        raise ValueError('evaluator schema')
    if not evaluator.get('evaluator_id'):
        raise ValueError('evaluator id')
    roots = evaluator.get('root_scope')
    if not isinstance(roots, list) or roots != sorted(set(roots)) or not roots or any(r not in REQUIRED_ROOTS for r in roots):
        raise ValueError('evaluator root_scope')
    sha64(evaluator.get('evaluation_tool_sha256'), 'evaluation_tool_sha256')
    sha64(evaluator.get('evaluation_source_sha256'), 'evaluation_source_sha256')
    pred = evaluator.get('predecessor_evaluator_sha256')
    if pred is not None:
        sha64(pred, 'predecessor_evaluator_sha256')


class CASStore:
    def __init__(self, root: Path, seal_field: str):
        self.root = root
        self.seal_field = seal_field
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, oid: str) -> Path:
        return self.root / f'{oid}.json'

    def put(self, obj: dict[str, Any]) -> str:
        validate_seal(obj, self.seal_field)
        oid = obj[self.seal_field]
        raw = canon(obj) + b'\n'
        path = self.path_for(oid)
        if path.exists() and path.read_bytes() != raw:
            raise ValueError('content-address collision')
        path.write_bytes(raw)
        return oid

    def get(self, oid: str) -> dict[str, Any]:
        path = self.path_for(oid)
        if not path.is_file():
            raise FileNotFoundError(f'{self.seal_field} body missing')
        obj = json.loads(path.read_text('utf-8'))
        validate_seal(obj, self.seal_field)
        if obj.get(self.seal_field) != oid:
            raise ValueError('store key/body mismatch')
        return obj


def make_registry(generation: int, evaluator_entries: dict[str, str], root_assignments: dict[str, str],
                  predecessor_registry_sha256: str | None, kind: str) -> dict[str, Any]:
    if generation < 0:
        raise ValueError('registry generation')
    if generation == 0 and predecessor_registry_sha256 is not None:
        raise ValueError('genesis registry predecessor')
    if generation > 0:
        sha64(predecessor_registry_sha256, 'predecessor_registry_sha256')
    if kind not in ('GENESIS', 'ADD', 'REMOVE', 'REPLACE', 'MIXED', 'UNCHANGED'):
        raise ValueError('registry transition kind')
    if not evaluator_entries or any(not k for k in evaluator_entries):
        raise ValueError('registry entries')
    entries = {str(k): sha64(str(v), 'evaluator entry sha') for k, v in sorted(evaluator_entries.items())}
    if set(root_assignments) != set(REQUIRED_ROOTS):
        raise ValueError('registry must assign exactly four roots')
    assignments = {root: str(root_assignments[root]) for root in REQUIRED_ROOTS}
    if any(eid not in entries for eid in assignments.values()):
        raise ValueError('root assigned to unregistered evaluator id')
    return seal({
        'schema': REGISTRY_SCHEMA,
        'generation': generation,
        'predecessor_registry_sha256': predecessor_registry_sha256,
        'transition_kind': kind,
        'evaluator_entries': entries,
        'root_assignments': assignments,
        'wave89_source': {
            'commit': WAVE89_TOOL_COMMIT,
            'blob_sha': WAVE89_TOOL_BLOB_SHA,
            'file_sha256': WAVE89_TOOL_FILE_SHA256,
        },
        'test_only': True,
        'registry_sha256': '',
    }, 'registry_sha256')


def validate_registry(registry: dict[str, Any], evaluator_store: CASStore) -> None:
    validate_seal(registry, 'registry_sha256')
    if registry.get('schema') != REGISTRY_SCHEMA:
        raise ValueError('registry schema')
    if set(registry.get('root_assignments', {})) != set(REQUIRED_ROOTS):
        raise ValueError('registry must assign exactly four roots')
    entries = registry.get('evaluator_entries')
    if not isinstance(entries, dict) or not entries:
        raise ValueError('registry entries invalid')
    for eid, esha in entries.items():
        sha64(esha, 'evaluator entry sha')
        evaluator = evaluator_store.get(esha)
        validate_evaluator(evaluator)
        if evaluator['evaluator_id'] != eid:
            raise ValueError('registry evaluator id/body mismatch')
    for root in REQUIRED_ROOTS:
        eid = registry['root_assignments'][root]
        if eid not in entries:
            raise ValueError('root assigned to unregistered evaluator')
        evaluator = evaluator_store.get(entries[eid])
        if root not in evaluator['root_scope']:
            raise ValueError('root outside evaluator scope')


def transition_kind(old_entries: dict[str, str], target_entries: dict[str, str]) -> str:
    old_keys, new_keys = set(old_entries), set(target_entries)
    added, removed = new_keys - old_keys, old_keys - new_keys
    replaced = {k for k in old_keys & new_keys if old_entries[k] != target_entries[k]}
    flags = sum(bool(x) for x in (added, removed, replaced))
    if flags == 0:
        return 'UNCHANGED'
    if flags > 1:
        return 'MIXED'
    if added:
        return 'ADD'
    if removed:
        return 'REMOVE'
    return 'REPLACE'


def make_registry_transition(old_registry: dict[str, Any], target_registry: dict[str, Any]) -> dict[str, Any]:
    validate_seal(old_registry, 'registry_sha256')
    validate_seal(target_registry, 'registry_sha256')
    if target_registry['generation'] != old_registry['generation'] + 1:
        raise ValueError('target registry generation mismatch')
    if target_registry['predecessor_registry_sha256'] != old_registry['registry_sha256']:
        raise ValueError('target registry predecessor mismatch')
    old_entries = old_registry['evaluator_entries']
    target_entries = target_registry['evaluator_entries']
    added = sorted(set(target_entries) - set(old_entries))
    removed = sorted(set(old_entries) - set(target_entries))
    replaced = sorted(k for k in set(old_entries) & set(target_entries) if old_entries[k] != target_entries[k])
    retained = sorted(k for k in set(old_entries) & set(target_entries) if old_entries[k] == target_entries[k])
    kind = transition_kind(old_entries, target_entries)
    if target_registry['transition_kind'] != kind:
        raise ValueError('target registry kind mismatch')
    return seal({
        'schema': REGISTRY_TRANSITION_SCHEMA,
        'predecessor_generation': old_registry['generation'],
        'predecessor_registry_sha256': old_registry['registry_sha256'],
        'target_generation': target_registry['generation'],
        'target_registry_sha256': target_registry['registry_sha256'],
        'transition_kind': kind,
        'added_evaluator_ids': added,
        'removed_evaluator_ids': removed,
        'replaced_evaluator_ids': replaced,
        'retained_evaluator_ids': retained,
        'old_root_assignments': old_registry['root_assignments'],
        'target_root_assignments': target_registry['root_assignments'],
        'transition_sha256': '',
    }, 'transition_sha256')


def validate_registry_transition(t: dict[str, Any], old_registry: dict[str, Any], target_registry: dict[str, Any]) -> None:
    validate_seal(t, 'transition_sha256')
    expected = make_registry_transition(old_registry, target_registry)
    if t != expected:
        raise ValueError('registry transition exact binding mismatch')


@dataclass
class RegistryRuntime:
    current_registry_sha256: str
    witness_views: dict[str, str]


def registry_view_status(runtime: RegistryRuntime) -> dict[str, Any]:
    if set(runtime.witness_views) != set(WITNESSES):
        return {'status': 'HOLD', 'reason': 'required witness membership mismatch'}
    values = list(runtime.witness_views.values())
    if len(set(values)) == 1 and values[0] == runtime.current_registry_sha256:
        return {'status': 'CONSISTENT', 'registry_sha256': values[0]}
    return {'status': 'HOLD', 'reason': 'registry witnesses disagree; no vote/newest-wins'}


def apply_registry_transition(runtime: RegistryRuntime, transition: dict[str, Any], old_registry: dict[str, Any],
                              target_registry: dict[str, Any], *, count: int | None = None) -> dict[str, Any]:
    try:
        validate_registry_transition(transition, old_registry, target_registry)
    except Exception as exc:
        return {'status': 'INVALID_TRANSITION_HOLD', 'error': f'{type(exc).__name__}: {exc}'}
    old_sha = old_registry['registry_sha256']
    target_sha = target_registry['registry_sha256']
    if runtime.current_registry_sha256 == target_sha and all(v == target_sha for v in runtime.witness_views.values()):
        return {'status': 'CONSISTENT_TARGET'}
    if runtime.current_registry_sha256 != old_sha:
        return {'status': 'PREDECESSOR_REGISTRY_MISMATCH_HOLD'}
    if set(runtime.witness_views) != set(WITNESSES):
        return {'status': 'WITNESS_SET_MISMATCH_HOLD'}
    if any(v not in (old_sha, target_sha) for v in runtime.witness_views.values()):
        return {'status': 'COMPETING_OR_UNKNOWN_REGISTRY_HOLD'}
    lagging = [wid for wid in WITNESSES if runtime.witness_views[wid] == old_sha]
    limit = len(lagging) if count is None else max(0, min(count, len(lagging)))
    for wid in lagging[:limit]:
        runtime.witness_views[wid] = target_sha
    if any(runtime.witness_views[wid] != target_sha for wid in WITNESSES):
        return {
            'status': 'PARTIAL_REGISTRY_HANDOFF',
            'advanced_this_call': limit,
            'target_registry_sha256': target_sha,
            'transition_sha256': transition['transition_sha256'],
        }
    runtime.current_registry_sha256 = target_sha
    return {'status': 'COMMITTED', 'target_registry_sha256': target_sha}


def make_root_eval(root: str, verdict: str, fact: str, evidence_ref: str, registry: dict[str, Any], evaluator_store: CASStore,
                   *, evaluator_id_override: str | None = None, tool_override: str | None = None, source_override: str | None = None) -> dict[str, Any]:
    if root not in REQUIRED_ROOTS or verdict not in ('PASS', 'HOLD', 'FAIL'):
        raise ValueError('root/verdict invalid')
    evaluator_id = evaluator_id_override or registry['root_assignments'][root]
    esha = registry['evaluator_entries'].get(evaluator_id)
    if esha is None:
        esha = '0' * 64
        tool_sha = tool_override or ('1' * 64)
        source_sha = source_override or ('2' * 64)
    else:
        evaluator = evaluator_store.get(esha)
        tool_sha = tool_override or evaluator['evaluation_tool_sha256']
        source_sha = source_override or evaluator['evaluation_source_sha256']
    row = {
        'schema': ROOT_EVAL_SCHEMA,
        'root': root,
        'verdict': verdict,
        'fact': fact,
        'evidence_ref': evidence_ref,
        'registry_sha256': registry['registry_sha256'],
        'evaluator_id': evaluator_id,
        'evaluator_sha256': esha,
        'evaluation_tool_sha256': tool_sha,
        'evaluation_source_sha256': source_sha,
        'evaluation_sha256': '',
    }
    return seal(row, 'evaluation_sha256')


def validate_root_eval(row: dict[str, Any], registry: dict[str, Any], evaluator_store: CASStore) -> None:
    validate_seal(row, 'evaluation_sha256')
    if row.get('schema') != ROOT_EVAL_SCHEMA:
        raise ValueError('root evaluation schema')
    root = row.get('root')
    if root not in REQUIRED_ROOTS:
        raise ValueError('root evaluation root')
    if row.get('verdict') not in ('PASS', 'HOLD', 'FAIL'):
        raise ValueError('root evaluation verdict')
    if row.get('registry_sha256') != registry['registry_sha256']:
        raise ValueError('root evaluation registry mismatch')
    assigned = registry['root_assignments'][root]
    if row.get('evaluator_id') != assigned:
        raise ValueError('root evaluator assignment mismatch')
    esha = registry['evaluator_entries'].get(assigned)
    if not esha or row.get('evaluator_sha256') != esha:
        raise ValueError('root evaluator registry identity mismatch')
    evaluator = evaluator_store.get(esha)
    validate_evaluator(evaluator)
    if root not in evaluator['root_scope']:
        raise ValueError('root evaluator scope mismatch')
    if row.get('evaluation_tool_sha256') != evaluator['evaluation_tool_sha256']:
        raise ValueError('evaluation tool digest mismatch')
    if row.get('evaluation_source_sha256') != evaluator['evaluation_source_sha256']:
        raise ValueError('evaluation source digest mismatch')


def make_authorization(reconfiguration_sha256: str, registry: dict[str, Any], evaluator_store: CASStore,
                       verdict_overrides: dict[str, str] | None = None) -> dict[str, Any]:
    sha64(reconfiguration_sha256, 'reconfiguration_sha256')
    validate_registry(registry, evaluator_store)
    verdict_overrides = verdict_overrides or {}
    evaluations = {}
    for root in REQUIRED_ROOTS:
        evaluations[root] = make_root_eval(
            root, verdict_overrides.get(root, 'PASS'),
            f'Wave90 test-only evaluation for exact membership reconfiguration {reconfiguration_sha256}',
            f'wave90:{registry["registry_sha256"]}:{reconfiguration_sha256}:{root}',
            registry, evaluator_store,
        )
    return seal({
        'schema': AUTH_SCHEMA,
        'action': 'AUTHORIZE_WITNESS_MEMBERSHIP_RECONFIGURATION',
        'reconfiguration_sha256': reconfiguration_sha256,
        'evaluator_registry_sha256': registry['registry_sha256'],
        'evaluations': evaluations,
        'test_only': True,
        'truth': {
            'registered_provenance_does_not_prove_moral_legitimacy': True,
            'registry_lineage_does_not_create_canonical_root_judgment': True,
        },
        'authorization_sha256': '',
    }, 'authorization_sha256')


def validate_authorization(auth: dict[str, Any], expected_reconfiguration_sha256: str, registry_store: CASStore,
                           evaluator_store: CASStore, *, require_allow: bool = True) -> str:
    validate_seal(auth, 'authorization_sha256')
    if auth.get('schema') != AUTH_SCHEMA or auth.get('action') != 'AUTHORIZE_WITNESS_MEMBERSHIP_RECONFIGURATION':
        raise ValueError('authorization schema/action')
    if auth.get('reconfiguration_sha256') != expected_reconfiguration_sha256:
        raise ValueError('authorization reconfiguration mismatch')
    rsha = auth.get('evaluator_registry_sha256')
    sha64(rsha, 'authorization registry sha')
    registry = registry_store.get(rsha)
    validate_registry(registry, evaluator_store)
    evaluations = auth.get('evaluations')
    if not isinstance(evaluations, dict) or set(evaluations) != set(REQUIRED_ROOTS):
        raise ValueError('authorization must cover exactly four roots')
    verdicts = []
    for root in REQUIRED_ROOTS:
        row = evaluations[root]
        validate_root_eval(row, registry, evaluator_store)
        if row['root'] != root:
            raise ValueError('authorization root key/body mismatch')
        verdicts.append(row['verdict'])
    decision = 'ALLOW' if all(v == 'PASS' for v in verdicts) else ('FAIL' if 'FAIL' in verdicts else 'HOLD')
    if require_allow and decision != 'ALLOW':
        raise ValueError(f'authorization does not allow transition: {decision}')
    return decision


def fail_contains(fn, text: str) -> bool:
    try:
        fn()
    except Exception as exc:
        return text in str(exc)
    return False


def genesis_fixture(root: Path):
    evaluator_store = CASStore(root / 'evaluators', 'evaluator_sha256')
    registry_store = CASStore(root / 'registries', 'registry_sha256')
    entries: dict[str, str] = {}
    assignments: dict[str, str] = {}
    for root_name in REQUIRED_ROOTS:
        eid = f'axm-test-{root_name}-evaluator-v1'
        evaluator = make_evaluator(
            eid, [root_name],
            text_sha(f'wave90-test-evaluation-tool:{root_name}:v1'),
            text_sha(f'wave90-test-evaluation-source:{root_name}:v1'),
            label=f'Wave90 test-only {root_name} evaluator v1',
        )
        entries[eid] = evaluator_store.put(evaluator)
        assignments[root_name] = eid
    registry = make_registry(0, entries, assignments, None, 'GENESIS')
    registry_store.put(registry)
    return evaluator_store, registry_store, registry


def run_once(benchmark_rounds: int = 100) -> dict[str, Any]:
    checks: list[tuple[str, bool]] = []
    details: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix='axm-wave90-') as td:
        root = Path(td)
        evaluator_store, registry_store, registry0 = genesis_fixture(root)
        rconfig = text_sha('wave89-exact-membership-reconfiguration-fixture-for-wave90')

        checks += [
            ('exact_wave89_source_commit', WAVE89_TOOL_COMMIT == '22182ef762be05835d912ae48da40c6043fb81dc'),
            ('exact_wave89_source_blob', WAVE89_TOOL_BLOB_SHA == '71b62f37911a5c2c53a32ddf2a29bf5610833181'),
            ('exact_wave89_source_file_sha256', WAVE89_TOOL_FILE_SHA256 == 'eef82f3db83954d97f15b4f7bda53cc01b75d63c0f289c9a94b4b2eff00d8066'),
        ]
        validate_registry(registry0, evaluator_store)
        checks.append(('genesis_evaluator_registry_valid', True))

        auth0 = make_authorization(rconfig, registry0, evaluator_store)
        checks.append(('registered_evaluators_allow_exact_four_root_authorization', validate_authorization(auth0, rconfig, registry_store, evaluator_store) == 'ALLOW'))

        bad_unreg = json.loads(json.dumps(auth0))
        row = bad_unreg['evaluations']['truth']
        row['evaluator_id'] = 'unregistered-self-minted-evaluator'
        row['evaluator_sha256'] = '0' * 64
        row['evaluation_tool_sha256'] = '1' * 64
        row['evaluation_source_sha256'] = '2' * 64
        bad_unreg['evaluations']['truth'] = seal(row, 'evaluation_sha256')
        bad_unreg = seal(bad_unreg, 'authorization_sha256')
        checks.append(('unregistered_evaluator_fails_closed', fail_contains(lambda: validate_authorization(bad_unreg, rconfig, registry_store, evaluator_store), 'assignment mismatch')))

        bad_tool = json.loads(json.dumps(auth0))
        row = bad_tool['evaluations']['truth']
        row['evaluation_tool_sha256'] = '3' * 64
        bad_tool['evaluations']['truth'] = seal(row, 'evaluation_sha256')
        bad_tool = seal(bad_tool, 'authorization_sha256')
        checks.append(('wrong_evaluation_tool_digest_rejected', fail_contains(lambda: validate_authorization(bad_tool, rconfig, registry_store, evaluator_store), 'tool digest mismatch')))
        bad_source = json.loads(json.dumps(auth0))
        row = bad_source['evaluations']['truth']
        row['evaluation_source_sha256'] = '4' * 64
        bad_source['evaluations']['truth'] = seal(row, 'evaluation_sha256')
        bad_source = seal(bad_source, 'authorization_sha256')
        checks.append(('wrong_evaluation_source_digest_rejected', fail_contains(lambda: validate_authorization(bad_source, rconfig, registry_store, evaluator_store), 'source digest mismatch')))
        bad_evaluator_sha = json.loads(json.dumps(auth0))
        row = bad_evaluator_sha['evaluations']['truth']
        row['evaluator_sha256'] = '5' * 64
        bad_evaluator_sha['evaluations']['truth'] = seal(row, 'evaluation_sha256')
        bad_evaluator_sha = seal(bad_evaluator_sha, 'authorization_sha256')
        checks.append(('wrong_registered_evaluator_record_digest_rejected', fail_contains(lambda: validate_authorization(bad_evaluator_sha, rconfig, registry_store, evaluator_store), 'registry identity mismatch')))

        truth_eid = registry0['root_assignments']['truth']
        truth_esha = registry0['evaluator_entries'][truth_eid]
        ep = evaluator_store.path_for(truth_esha)
        saved_eval = ep.read_bytes()
        ep.unlink()
        checks.append(('missing_evaluator_body_rejected', fail_contains(lambda: validate_authorization(auth0, rconfig, registry_store, evaluator_store), 'body missing')))
        ep.write_bytes(saved_eval)
        rp = registry_store.path_for(registry0['registry_sha256'])
        saved_registry = rp.read_bytes()
        corrupt_registry = json.loads(saved_registry.decode('utf-8'))
        corrupt_registry['generation'] = 99
        rp.write_bytes(canon(corrupt_registry) + b'\n')
        checks.append(('corrupt_registry_body_rejected', fail_contains(lambda: validate_authorization(auth0, rconfig, registry_store, evaluator_store), 'registry_sha256 mismatch')))
        rp.write_bytes(saved_registry)

        observer = make_evaluator('axm-test-observer-v1', ['truth'], text_sha('observer-tool-v1'), text_sha('observer-source-v1'), label='test observer')
        observer_sha = evaluator_store.put(observer)
        add_entries = dict(registry0['evaluator_entries']); add_entries[observer['evaluator_id']] = observer_sha
        reg_add = make_registry(1, add_entries, registry0['root_assignments'], registry0['registry_sha256'], 'ADD')
        registry_store.put(reg_add)
        t_add = make_registry_transition(registry0, reg_add)
        checks.append(('evaluator_add_transition_predecessor_bound', t_add['predecessor_registry_sha256'] == registry0['registry_sha256'] and t_add['added_evaluator_ids'] == ['axm-test-observer-v1']))

        remove_entries = dict(reg_add['evaluator_entries']); remove_entries.pop('axm-test-observer-v1')
        reg_remove = make_registry(2, remove_entries, reg_add['root_assignments'], reg_add['registry_sha256'], 'REMOVE')
        registry_store.put(reg_remove)
        t_remove = make_registry_transition(reg_add, reg_remove)
        checks.append(('evaluator_remove_transition_predecessor_bound', t_remove['removed_evaluator_ids'] == ['axm-test-observer-v1']))

        old_truth = evaluator_store.get(reg_remove['evaluator_entries'][truth_eid])
        truth_v2 = make_evaluator(truth_eid, ['truth'], text_sha('wave90-test-evaluation-tool:truth:v2'), text_sha('wave90-test-evaluation-source:truth:v2'), label='Wave90 test-only truth evaluator v2', predecessor_evaluator_sha256=old_truth['evaluator_sha256'])
        truth_v2_sha = evaluator_store.put(truth_v2)
        replace_entries = dict(reg_remove['evaluator_entries']); replace_entries[truth_eid] = truth_v2_sha
        reg_replace = make_registry(3, replace_entries, reg_remove['root_assignments'], reg_remove['registry_sha256'], 'REPLACE')
        registry_store.put(reg_replace)
        t_replace = make_registry_transition(reg_remove, reg_replace)
        checks.append(('evaluator_replace_transition_predecessor_bound', t_replace['replaced_evaluator_ids'] == [truth_eid] and truth_v2['predecessor_evaluator_sha256'] == old_truth['evaluator_sha256']))

        wrong_reg = dict(reg_replace); wrong_reg['predecessor_registry_sha256'] = '9' * 64; wrong_reg = seal(wrong_reg, 'registry_sha256')
        checks.append(('wrong_registry_predecessor_rejected', fail_contains(lambda: make_registry_transition(reg_remove, wrong_reg), 'predecessor mismatch')))
        tampered_t = dict(t_replace); tampered_t['target_generation'] = 50; tampered_t = seal(tampered_t, 'transition_sha256')
        checks.append(('rehashed_transition_semantic_tamper_rejected', fail_contains(lambda: validate_registry_transition(tampered_t, reg_remove, reg_replace), 'exact binding mismatch')))

        rt = RegistryRuntime(reg_remove['registry_sha256'], {wid: reg_remove['registry_sha256'] for wid in WITNESSES})
        checks.append(('consistent_registry_views_are_accepted', registry_view_status(rt)['status'] == 'CONSISTENT'))
        partial = apply_registry_transition(rt, t_replace, reg_remove, reg_replace, count=1)
        checks.append(('partial_registry_handoff_recorded', partial['status'] == 'PARTIAL_REGISTRY_HANDOFF'))
        checks.append(('partial_registry_disagreement_holds_not_votes', registry_view_status(rt)['status'] == 'HOLD'))
        checks.append(('two_vs_one_registry_split_holds', rt.current_registry_sha256 == reg_remove['registry_sha256'] and registry_view_status(rt)['status'] == 'HOLD'))
        repaired = apply_registry_transition(rt, t_replace, reg_remove, reg_replace)
        checks.append(('exact_transition_recovers_partial_handoff', repaired['status'] == 'COMMITTED' and rt.current_registry_sha256 == reg_replace['registry_sha256']))
        checks.append(('target_registry_views_consistent_after_commit', registry_view_status(rt)['status'] == 'CONSISTENT'))

        rt_lone = RegistryRuntime(reg_remove['registry_sha256'], {wid: reg_remove['registry_sha256'] for wid in WITNESSES})
        rt_lone.witness_views['registry-witness-c'] = reg_replace['registry_sha256']
        checks.append(('lone_newer_registry_view_holds', registry_view_status(rt_lone)['status'] == 'HOLD'))

        alt_truth = make_evaluator(truth_eid, ['truth'], text_sha('alternate-truth-tool'), text_sha('alternate-truth-source'), label='competing test truth evaluator', predecessor_evaluator_sha256=old_truth['evaluator_sha256'])
        alt_truth_sha = evaluator_store.put(alt_truth)
        alt_entries = dict(reg_remove['evaluator_entries']); alt_entries[truth_eid] = alt_truth_sha
        reg_alt = make_registry(3, alt_entries, reg_remove['root_assignments'], reg_remove['registry_sha256'], 'REPLACE')
        registry_store.put(reg_alt)
        t_alt = make_registry_transition(reg_remove, reg_alt)
        rt_compete = RegistryRuntime(reg_remove['registry_sha256'], {wid: reg_remove['registry_sha256'] for wid in WITNESSES})
        apply_registry_transition(rt_compete, t_replace, reg_remove, reg_replace, count=1)
        compete = apply_registry_transition(rt_compete, t_alt, reg_remove, reg_alt)
        checks.append(('competing_registry_histories_hold_instead_of_vote', compete['status'] == 'COMPETING_OR_UNKNOWN_REGISTRY_HOLD'))

        rt_missing_witness = RegistryRuntime(reg_remove['registry_sha256'], {'registry-witness-a': reg_remove['registry_sha256'], 'registry-witness-b': reg_remove['registry_sha256']})
        checks.append(('missing_registry_witness_holds', registry_view_status(rt_missing_witness)['status'] == 'HOLD'))

        rt_prepared = RegistryRuntime(reg_remove['registry_sha256'], {wid: reg_remove['registry_sha256'] for wid in WITNESSES})
        checks.append(('prepared_registry_target_has_zero_current_authority', rt_prepared.current_registry_sha256 == reg_remove['registry_sha256']))

        auth_old = make_authorization(rconfig, reg_remove, evaluator_store)
        auth_new = make_authorization(rconfig, reg_replace, evaluator_store)
        checks.append(('new_registry_exact_evaluator_provenance_allows', validate_authorization(auth_new, rconfig, registry_store, evaluator_store) == 'ALLOW'))
        old_truth_row = auth_old['evaluations']['truth']
        checks.append(('old_evaluator_record_differs_after_replacement', old_truth_row['evaluator_sha256'] != auth_new['evaluations']['truth']['evaluator_sha256']))
        stale = json.loads(json.dumps(auth_old)); stale['evaluator_registry_sha256'] = reg_replace['registry_sha256']; stale = seal(stale, 'authorization_sha256')
        checks.append(('stale_old_evaluator_evaluation_cannot_cross_registry_generation', fail_contains(lambda: validate_authorization(stale, rconfig, registry_store, evaluator_store), 'registry mismatch')))

        auth_hold = make_authorization(rconfig, reg_replace, evaluator_store, {'continuity': 'HOLD'})
        checks.append(('registered_root_hold_blocks_transition', fail_contains(lambda: validate_authorization(auth_hold, rconfig, registry_store, evaluator_store), 'does not allow')))
        auth_fail = make_authorization(rconfig, reg_replace, evaluator_store, {'truth': 'FAIL'})
        checks.append(('registered_root_fail_blocks_transition', fail_contains(lambda: validate_authorization(auth_fail, rconfig, registry_store, evaluator_store), 'does not allow')))

        self_evaluator = make_evaluator('self-minted-but-registered-test-evaluator', list(REQUIRED_ROOTS), text_sha('self-minted-tool'), text_sha('self-minted-source'), label='counterexample: structurally registered, moral legitimacy unknown')
        self_sha = evaluator_store.put(self_evaluator)
        self_entries = {'self-minted-but-registered-test-evaluator': self_sha}
        self_assign = {root_name: 'self-minted-but-registered-test-evaluator' for root_name in REQUIRED_ROOTS}
        reg_self = make_registry(4, self_entries, self_assign, reg_replace['registry_sha256'], 'MIXED')
        registry_store.put(reg_self)
        auth_self = make_authorization(rconfig, reg_self, evaluator_store)
        structural_accept = validate_authorization(auth_self, rconfig, registry_store, evaluator_store) == 'ALLOW'
        checks.append(('counterexample_registered_provenance_still_not_moral_legitimacy', structural_accept))
        details['legitimacy_counterexample'] = (
            'A self-minted evaluator can be made structurally valid if an explicit registry lineage registers it. '
            'Wave 90 therefore proves inspectable provenance/lineage and rejects unregistered or stale identities, '
            'but registry membership plus exact hashes still do not prove moral legitimacy or canonical AXM authority.'
        )

        samples: list[float] = []
        for _ in range(benchmark_rounds):
            start = time.process_time_ns()
            validate_registry(reg_replace, evaluator_store)
            a = make_authorization(rconfig, reg_replace, evaluator_store)
            validate_authorization(a, rconfig, registry_store, evaluator_store)
            samples.append((time.process_time_ns() - start) / 1000.0)

    failed = [name for name, ok in checks if not ok]
    return {
        'status': 'PASS' if not failed else 'FAIL',
        'passed_checks': sum(1 for _, ok in checks if ok),
        'total_checks': len(checks),
        'failed_checks': failed,
        'checks': [{'name': name, 'pass': ok} for name, ok in checks],
        'synthetic_single_host_registry_auth_cpu_us_median': statistics.median(samples),
        'benchmark_rounds': benchmark_rounds,
        'details': details,
    }


def self_test(benchmark_rounds: int = 100) -> dict[str, Any]:
    run1 = run_once(benchmark_rounds)
    run2 = run_once(benchmark_rounds)
    same_checks = [c['name'] for c in run1['checks']] == [c['name'] for c in run2['checks']]
    status = 'PASS' if run1['status'] == run2['status'] == 'PASS' and same_checks else 'FAIL'
    return {
        'schema': 'axm.flowing-compute-wave90-report/v0.1',
        'status': status,
        'checks': run1['checks'],
        'independent_runs': [
            {k: run1[k] for k in ('status', 'passed_checks', 'total_checks', 'benchmark_rounds', 'synthetic_single_host_registry_auth_cpu_us_median')},
            {k: run2[k] for k in ('status', 'passed_checks', 'total_checks', 'benchmark_rounds', 'synthetic_single_host_registry_auth_cpu_us_median')},
        ],
        'independent_check_name_match': same_checks,
        'source_provenance': {
            'wave89_tool_commit': WAVE89_TOOL_COMMIT,
            'wave89_tool_blob_sha': WAVE89_TOOL_BLOB_SHA,
            'wave89_tool_file_sha256': WAVE89_TOOL_FILE_SHA256,
        },
        'counterexample': run1['details']['legitimacy_counterexample'],
        'truth_boundary': {
            'fresh_monolith_audit': False,
            'compute_efficiency_claim': False,
            'energy_claim': False,
            'distributed_consensus_claim': False,
            'moral_evaluator_legitimacy_proven': False,
            'canonical_root_judgment_claim': False,
            'automatic_merge': False,
            'note': 'Evaluator provenance/registry lineage mechanics only. All evaluators and roots in this probe are test-only structural evidence.'
        },
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--benchmark-rounds', type=int, default=100)
    parser.add_argument('--json-out')
    args = parser.parse_args()
    report = self_test(args.benchmark_rounds)
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.json_out:
        Path(args.json_out).write_text(text + '\n', encoding='utf-8')
    raise SystemExit(0 if report['status'] == 'PASS' else 1)
