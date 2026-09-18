from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

SCHEMA_REGISTRY = 'axm.flowing-compute-evaluator-registry/v0.1'
SCHEMA_AUTH = 'axm.flowing-compute-membership-authorization-with-evaluator-provenance/v0.1'
ROOTS = ('truth', 'agency_non_domination', 'continuity', 'wisdom_before_speed')
WITNESSES = ('registry-witness-a', 'registry-witness-b', 'registry-witness-c')
W90_COMMIT = '57435f3f21b017b6a532a39c31e0a8a58ca70182'
W90_BLOB = '35f756d023fcbfa1e24fff94a2dcf87b29d8962e'
W90_SHA256 = '35355bb17ab069cf1de5d32168e2bf8153bf489eda30b27057e82ccab9743679'


def canon(v: Any) -> bytes:
    return json.dumps(v, sort_keys=True, separators=(',', ':')).encode()


def digest(v: Any) -> str:
    return hashlib.sha256(canon(v)).hexdigest()


def text_digest(v: str) -> str:
    return hashlib.sha256(v.encode()).hexdigest()


def seal(v: dict[str, Any], field: str) -> dict[str, Any]:
    out = deepcopy(v)
    out.pop(field, None)
    out[field] = digest(out)
    return out


def check_seal(v: dict[str, Any], field: str) -> None:
    body = deepcopy(v)
    got = body.pop(field, None)
    if got != digest(body):
        raise ValueError(f'{field} mismatch')


def make_registry(generation: int, predecessor: str | None, evaluator_ids: dict[str, str], label: str) -> dict[str, Any]:
    if set(evaluator_ids) != set(ROOTS):
        raise ValueError('four roots required')
    if generation == 0 and predecessor is not None:
        raise ValueError('genesis predecessor')
    if generation > 0 and (not isinstance(predecessor, str) or len(predecessor) != 64):
        raise ValueError('successor predecessor')
    return seal({
        'schema': SCHEMA_REGISTRY,
        'generation': generation,
        'predecessor_registry_sha256': predecessor,
        'root_evaluator_ids': {r: evaluator_ids[r] for r in ROOTS},
        'label': label,
        'wave90_source': {'commit': W90_COMMIT, 'blob_sha': W90_BLOB, 'file_sha256': W90_SHA256},
        'test_only': True,
        'registry_sha256': '',
    }, 'registry_sha256')


def validate_registry(reg: dict[str, Any]) -> None:
    check_seal(reg, 'registry_sha256')
    if reg.get('schema') != SCHEMA_REGISTRY or set(reg.get('root_evaluator_ids', {})) != set(ROOTS):
        raise ValueError('registry body')


def make_auth(reg: dict[str, Any], reconfig: str, verdicts: dict[str, str] | None = None) -> dict[str, Any]:
    validate_registry(reg)
    verdicts = verdicts or {}
    rows = {}
    for root in ROOTS:
        verdict = verdicts.get(root, 'PASS')
        if verdict not in ('PASS', 'HOLD', 'FAIL'):
            raise ValueError('verdict')
        rows[root] = {
            'root': root,
            'verdict': verdict,
            'registry_sha256': reg['registry_sha256'],
            'evaluator_id': reg['root_evaluator_ids'][root],
        }
    return seal({
        'schema': SCHEMA_AUTH,
        'reconfiguration_sha256': reconfig,
        'evaluator_registry_sha256': reg['registry_sha256'],
        'evaluations': rows,
        'test_only': True,
        'authorization_sha256': '',
    }, 'authorization_sha256')


def validate_structural(auth: dict[str, Any], reconfig: str, store: dict[str, dict[str, Any]]) -> str:
    check_seal(auth, 'authorization_sha256')
    if auth.get('schema') != SCHEMA_AUTH or auth.get('reconfiguration_sha256') != reconfig:
        raise ValueError('authorization identity mismatch')
    rsha = auth.get('evaluator_registry_sha256')
    if rsha not in store:
        raise ValueError('registry body missing')
    reg = store[rsha]
    validate_registry(reg)
    rows = auth.get('evaluations')
    if not isinstance(rows, dict) or set(rows) != set(ROOTS):
        raise ValueError('four root evaluations required')
    verdicts = []
    for root in ROOTS:
        row = rows[root]
        if row.get('root') != root or row.get('registry_sha256') != rsha:
            raise ValueError('evaluation registry mismatch')
        if row.get('evaluator_id') != reg['root_evaluator_ids'][root]:
            raise ValueError('evaluation evaluator mismatch')
        verdicts.append(row.get('verdict'))
    if any(v not in ('PASS', 'HOLD', 'FAIL') for v in verdicts):
        raise ValueError('evaluation verdict')
    return 'ALLOW' if all(v == 'PASS' for v in verdicts) else ('FAIL' if 'FAIL' in verdicts else 'HOLD')


@dataclass
class Runtime:
    current_registry_sha256: str
    witness_views: dict[str, str]


def current_authority(rt: Runtime, store: dict[str, dict[str, Any]]) -> dict[str, str]:
    if set(rt.witness_views) != set(WITNESSES):
        return {'status': 'HOLD', 'reason': 'required witness membership mismatch'}
    if any(rt.witness_views[w] != rt.current_registry_sha256 for w in WITNESSES):
        return {'status': 'HOLD', 'reason': 'witness/current mismatch; no voting or newest-wins'}
    reg = store.get(rt.current_registry_sha256)
    if reg is None:
        return {'status': 'HOLD', 'reason': 'current registry body missing'}
    try:
        validate_registry(reg)
    except Exception as exc:
        return {'status': 'HOLD', 'reason': f'current registry invalid: {exc}'}
    return {'status': 'AUTHORITATIVE', 'registry_sha256': rt.current_registry_sha256}


def validate_current(auth: dict[str, Any], reconfig: str, rt: Runtime, store: dict[str, dict[str, Any]]) -> str:
    state = current_authority(rt, store)
    if state['status'] != 'AUTHORITATIVE':
        raise ValueError(f'registry authority HOLD: {state["reason"]}')
    if auth.get('evaluator_registry_sha256') != rt.current_registry_sha256:
        raise ValueError('authorization registry is not current authoritative registry')
    decision = validate_structural(auth, reconfig, store)
    if decision != 'ALLOW':
        raise ValueError(f'authorization does not allow transition: {decision}')
    return decision


def validate_successor(old: dict[str, Any], target: dict[str, Any]) -> None:
    validate_registry(old); validate_registry(target)
    if target['generation'] != old['generation'] + 1 or target['predecessor_registry_sha256'] != old['registry_sha256']:
        raise ValueError('successor lineage mismatch')


def advance(rt: Runtime, old: dict[str, Any], target: dict[str, Any], count: int | None = None) -> str:
    validate_successor(old, target)
    old_sha, target_sha = old['registry_sha256'], target['registry_sha256']
    if rt.current_registry_sha256 != old_sha or set(rt.witness_views) != set(WITNESSES):
        return 'HOLD'
    if any(v not in (old_sha, target_sha) for v in rt.witness_views.values()):
        return 'HOLD'
    lagging = [w for w in WITNESSES if rt.witness_views[w] == old_sha]
    n = len(lagging) if count is None else max(0, min(count, len(lagging)))
    for w in lagging[:n]:
        rt.witness_views[w] = target_sha
    if any(rt.witness_views[w] != target_sha for w in WITNESSES):
        return 'PARTIAL'
    rt.current_registry_sha256 = target_sha
    return 'COMMITTED'


def fails(fn, phrase: str) -> bool:
    try:
        fn()
    except Exception as exc:
        return phrase in str(exc)
    return False


def run_once(rounds: int) -> dict[str, Any]:
    reconfig = text_digest('wave91-membership-reconfiguration')
    base_ids = {r: f'wave90-{r}-evaluator-v1' for r in ROOTS}
    reg0 = make_registry(0, None, base_ids, 'current predecessor')
    ids1 = dict(base_ids); ids1['truth'] = 'wave91-truth-evaluator-v2'
    reg1 = make_registry(1, reg0['registry_sha256'], ids1, 'prepared successor')
    alt_ids = dict(base_ids); alt_ids['truth'] = 'competing-truth-evaluator'
    reg_alt = make_registry(1, reg0['registry_sha256'], alt_ids, 'competing successor')
    self_ids = {r: 'self-minted-evaluator' for r in ROOTS}
    reg_self = make_registry(1, reg0['registry_sha256'], self_ids, 'self-admission counterexample')
    store = {r['registry_sha256']: r for r in (reg0, reg1, reg_alt, reg_self)}
    rt = Runtime(reg0['registry_sha256'], {w: reg0['registry_sha256'] for w in WITNESSES})
    a0, a1, a_self = make_auth(reg0, reconfig), make_auth(reg1, reconfig), make_auth(reg_self, reconfig)
    checks: list[tuple[str, bool]] = []
    checks += [
        ('exact_wave90_commit', W90_COMMIT == '57435f3f21b017b6a532a39c31e0a8a58ca70182'),
        ('exact_wave90_blob', W90_BLOB == '35f756d023fcbfa1e24fff94a2dcf87b29d8962e'),
        ('exact_wave90_sha256', W90_SHA256 == '35355bb17ab069cf1de5d32168e2bf8153bf489eda30b27057e82ccab9743679'),
        ('stable_current_authoritative', current_authority(rt, store)['status'] == 'AUTHORITATIVE'),
        ('current_auth_allows', validate_current(a0, reconfig, rt, store) == 'ALLOW'),
        ('prepared_successor_structurally_valid', validate_structural(a1, reconfig, store) == 'ALLOW'),
        ('prepared_successor_zero_authority', fails(lambda: validate_current(a1, reconfig, rt, store), 'not current authoritative')),
        ('early_self_admission_zero_authority', fails(lambda: validate_current(a_self, reconfig, rt, store), 'not current authoritative')),
    ]
    checks.append(('partial_handoff_created', advance(rt, reg0, reg1, 1) == 'PARTIAL'))
    checks += [
        ('partial_handoff_holds', current_authority(rt, store)['status'] == 'HOLD'),
        ('predecessor_auth_holds_during_partial', fails(lambda: validate_current(a0, reconfig, rt, store), 'authority HOLD')),
        ('target_auth_holds_during_partial', fails(lambda: validate_current(a1, reconfig, rt, store), 'authority HOLD')),
    ]
    lone = Runtime(reg0['registry_sha256'], {w: reg0['registry_sha256'] for w in WITNESSES}); lone.witness_views[WITNESSES[-1]] = reg1['registry_sha256']
    missing = Runtime(reg0['registry_sha256'], {WITNESSES[0]: reg0['registry_sha256'], WITNESSES[1]: reg0['registry_sha256']})
    ahead = Runtime(reg1['registry_sha256'], {w: reg0['registry_sha256'] for w in WITNESSES})
    compete = Runtime(reg0['registry_sha256'], {WITNESSES[0]: reg1['registry_sha256'], WITNESSES[1]: reg_alt['registry_sha256'], WITNESSES[2]: reg0['registry_sha256']})
    checks += [
        ('lone_newer_witness_does_not_win', current_authority(lone, store)['status'] == 'HOLD'),
        ('missing_witness_holds', current_authority(missing, store)['status'] == 'HOLD'),
        ('pointer_ahead_holds', current_authority(ahead, store)['status'] == 'HOLD'),
        ('competing_histories_hold_no_vote', current_authority(compete, store)['status'] == 'HOLD'),
        ('exact_handoff_commits', advance(rt, reg0, reg1) == 'COMMITTED'),
        ('target_authoritative_after_commit', current_authority(rt, store)['status'] == 'AUTHORITATIVE'),
        ('target_auth_allows_after_commit', validate_current(a1, reconfig, rt, store) == 'ALLOW'),
        ('old_auth_rejected_after_commit', fails(lambda: validate_current(a0, reconfig, rt, store), 'not current authoritative')),
    ]
    hold_auth = make_auth(reg1, reconfig, {'continuity': 'HOLD'})
    checks.append(('root_hold_still_blocks', fails(lambda: validate_current(hold_auth, reconfig, rt, store), 'does not allow')))
    saved = store.pop(reg1['registry_sha256'])
    checks.append(('missing_current_body_holds', current_authority(rt, store)['status'] == 'HOLD')); store[reg1['registry_sha256']] = saved
    corrupt = deepcopy(reg1); corrupt['generation'] = 99; store[reg1['registry_sha256']] = corrupt
    checks.append(('corrupt_current_body_holds', current_authority(rt, store)['status'] == 'HOLD')); store[reg1['registry_sha256']] = reg1
    reg2 = make_registry(2, reg1['registry_sha256'], base_ids, 'forward-lineage rollback to old evaluator set'); store[reg2['registry_sha256']] = reg2
    a2 = make_auth(reg2, reconfig)
    checks += [
        ('rollback_uses_new_forward_identity', advance(rt, reg1, reg2) == 'COMMITTED' and reg2['registry_sha256'] != reg0['registry_sha256']),
        ('old_auth_not_revived_by_rollback', fails(lambda: validate_current(a0, reconfig, rt, store), 'not current authoritative')),
        ('fresh_rollback_successor_auth_allows', validate_current(a2, reconfig, rt, store) == 'ALLOW'),
    ]
    reg_self2 = make_registry(3, reg2['registry_sha256'], self_ids, 'unguarded transition counterexample'); store[reg_self2['registry_sha256']] = reg_self2
    a_self2 = make_auth(reg_self2, reconfig)
    self_commit = advance(rt, reg2, reg_self2)
    checks.append(('counterexample_unguarded_transition_can_admit_self_evaluator', self_commit == 'COMMITTED' and validate_current(a_self2, reconfig, rt, store) == 'ALLOW'))
    stable = Runtime(reg2['registry_sha256'], {w: reg2['registry_sha256'] for w in WITNESSES})
    samples = []
    for _ in range(rounds):
        t0 = time.process_time_ns(); validate_current(a2, reconfig, stable, store); samples.append((time.process_time_ns() - t0) / 1000)
    failed = [name for name, ok in checks if not ok]
    return {
        'status': 'PASS' if not failed else 'FAIL', 'passed_checks': sum(ok for _, ok in checks), 'total_checks': len(checks),
        'failed_checks': failed, 'checks': [{'name': n, 'pass': ok} for n, ok in checks],
        'synthetic_single_host_current_registry_auth_cpu_us_median': statistics.median(samples), 'benchmark_rounds': rounds,
    }


def self_test(rounds: int = 100) -> dict[str, Any]:
    a, b = run_once(rounds), run_once(rounds)
    names_match = [x['name'] for x in a['checks']] == [x['name'] for x in b['checks']]
    return {
        'schema': 'axm.flowing-compute-wave91-current-registry-authority/v0.1',
        'status': 'PASS' if a['status'] == b['status'] == 'PASS' and names_match else 'FAIL',
        'checks': a['checks'], 'independent_runs': [{k: r[k] for k in ('status', 'passed_checks', 'total_checks', 'benchmark_rounds', 'synthetic_single_host_current_registry_auth_cpu_us_median')} for r in (a, b)],
        'independent_check_name_match': names_match,
        'source_provenance': {'wave90_tool_commit': W90_COMMIT, 'wave90_tool_blob_sha': W90_BLOB, 'wave90_tool_file_sha256': W90_SHA256},
        'counterexample': 'Current-registry binding blocks prepared-successor authority and early self-admission, but the transition primitive is still not predecessor-root-authorized. If it commits a self-minted evaluator registry, that registry becomes mechanically current and can authorize afterward.',
        'truth_boundary': {'fresh_monolith_audit': False, 'compute_efficiency_claim': False, 'energy_claim': False, 'distributed_consensus_claim': False, 'moral_evaluator_legitimacy_proven': False, 'evaluator_registry_transition_authorization_proven': False, 'canonical_root_judgment_claim': False, 'automatic_merge': False, 'synthetic_scaling': False, 'note': 'Synthetic single-host authority-state probe only; no AXM workload or compute-savings claim.'},
    }


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--benchmark-rounds', type=int, default=100); p.add_argument('--json-out'); args = p.parse_args()
    report = self_test(args.benchmark_rounds); text = json.dumps(report, indent=2, sort_keys=True); print(text)
    if args.json_out: open(args.json_out, 'w', encoding='utf-8').write(text + '\n')
    raise SystemExit(0 if report['status'] == 'PASS' else 1)
