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

AUTH_SCHEMA = 'axm.flowing-compute-witness-membership-authorization/v0.1'
MEMBERSHIP_SCHEMA = 'axm.flowing-compute-witness-membership/v0.1'
POINTER_SCHEMA = 'axm.flowing-compute-witness-membership-pointer/v0.1'
RECONFIG_SCHEMA = 'axm.flowing-compute-witness-reconfiguration/v0.1'
REQUIRED_ROOTS = ('truth', 'agency_non_domination', 'continuity', 'wisdom_before_speed')

# Exact Wave 88 source identity. Wave 89 is an authorization-seam probe and
# intentionally does not claim a fresh monolith audit.
WAVE88_TOOL_COMMIT = '76ed78a64825a5c71ff2017ef9383d389b878192'
WAVE88_TOOL_BLOB_SHA = 'efabee7b9c9724e1bd23f37cfc909cc9ed54cf1a'
WAVE81_RETENTION_SHA = '53d91b18e1a12eb27bd503bcfa70b4cd74add598ceaef522c88d7c075fdee4d4'


def canon(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def dig(value: Any) -> str:
    return hashlib.sha256(canon(value)).hexdigest()


def seal(value: dict[str, Any], field: str) -> dict[str, Any]:
    out = dict(value)
    out.pop(field, None)
    out[field] = dig(out)
    return out


def validate_seal(value: dict[str, Any], field: str) -> None:
    body = dict(value)
    key = body.pop(field, None)
    if not isinstance(key, str) or len(key) != 64 or key != dig(body):
        raise ValueError(f'{field} mismatch')


def exact_ids(values: list[str] | tuple[str, ...]) -> list[str]:
    out = sorted(str(x) for x in values)
    if len(out) < 2 or len(out) != len(set(out)) or any(not x for x in out):
        raise ValueError('membership ids invalid')
    return out


def make_membership(generation: int, ids: list[str] | tuple[str, ...], predecessor: str | None, kind: str) -> dict[str, Any]:
    ids2 = exact_ids(ids)
    if generation < 0:
        raise ValueError('membership generation')
    if kind not in ('GENESIS', 'ADD', 'REMOVE', 'REPLACE', 'UNCHANGED'):
        raise ValueError('membership kind')
    if generation == 0 and predecessor is not None:
        raise ValueError('genesis predecessor')
    if generation > 0 and not predecessor:
        raise ValueError('membership predecessor required')
    return seal({
        'schema': MEMBERSHIP_SCHEMA,
        'generation': generation,
        'witness_ids': ids2,
        'predecessor_membership_sha256': predecessor,
        'transition_kind': kind,
        'wave88_source': {'commit': WAVE88_TOOL_COMMIT, 'blob_sha': WAVE88_TOOL_BLOB_SHA},
        'membership_sha256': '',
    }, 'membership_sha256')


def make_pointer(epoch: int, membership_sha256: str, predecessor: str | None, kind: str) -> dict[str, Any]:
    if kind not in ('GENESIS', 'RECONFIGURE'):
        raise ValueError('pointer kind')
    return seal({
        'schema': POINTER_SCHEMA,
        'commit_epoch': epoch,
        'retention_sha256': WAVE81_RETENTION_SHA,
        'membership_sha256': membership_sha256,
        'predecessor_pointer_sha256': predecessor,
        'selection_kind': kind,
        'pointer_sha256': '',
    }, 'pointer_sha256')


def make_reconfiguration(old_m: dict[str, Any], target_m: dict[str, Any], old_p: dict[str, Any], target_p: dict[str, Any]) -> dict[str, Any]:
    for obj, field in ((old_m, 'membership_sha256'), (target_m, 'membership_sha256'), (old_p, 'pointer_sha256'), (target_p, 'pointer_sha256')):
        validate_seal(obj, field)
    old_ids = exact_ids(old_m['witness_ids'])
    new_ids = exact_ids(target_m['witness_ids'])
    if target_m['predecessor_membership_sha256'] != old_m['membership_sha256']:
        raise ValueError('target membership predecessor mismatch')
    if target_p['predecessor_pointer_sha256'] != old_p['pointer_sha256']:
        raise ValueError('target pointer predecessor mismatch')
    if old_p['membership_sha256'] != old_m['membership_sha256'] or target_p['membership_sha256'] != target_m['membership_sha256']:
        raise ValueError('pointer/membership binding mismatch')
    if target_p['commit_epoch'] != old_p['commit_epoch'] + 1:
        raise ValueError('epoch mismatch')
    added = sorted(set(new_ids) - set(old_ids))
    removed = sorted(set(old_ids) - set(new_ids))
    retained = sorted(set(old_ids) & set(new_ids))
    expected_kind = ('ADD' if set(new_ids) > set(old_ids) else
                     'REMOVE' if set(new_ids) < set(old_ids) else
                     'REPLACE' if new_ids != old_ids else 'UNCHANGED')
    if target_m['transition_kind'] != expected_kind:
        raise ValueError('transition kind mismatch')
    return seal({
        'schema': RECONFIG_SCHEMA,
        'predecessor_epoch': old_p['commit_epoch'],
        'predecessor_pointer_sha256': old_p['pointer_sha256'],
        'predecessor_membership_sha256': old_m['membership_sha256'],
        'target_epoch': target_p['commit_epoch'],
        'target_pointer_sha256': target_p['pointer_sha256'],
        'target_membership_sha256': target_m['membership_sha256'],
        'transition_kind': expected_kind,
        'old_witness_ids': old_ids,
        'target_witness_ids': new_ids,
        'retained_witness_ids': retained,
        'added_witness_ids': added,
        'removed_witness_ids': removed,
        'wave88_source': {'commit': WAVE88_TOOL_COMMIT, 'blob_sha': WAVE88_TOOL_BLOB_SHA},
        'reconfiguration_sha256': '',
    }, 'reconfiguration_sha256')


def validate_reconfiguration(r: dict[str, Any]) -> None:
    validate_seal(r, 'reconfiguration_sha256')
    if r.get('schema') != RECONFIG_SCHEMA:
        raise ValueError('reconfiguration schema')
    old_ids = exact_ids(r['old_witness_ids'])
    new_ids = exact_ids(r['target_witness_ids'])
    if r['retained_witness_ids'] != sorted(set(old_ids) & set(new_ids)):
        raise ValueError('retained set mismatch')
    if r['added_witness_ids'] != sorted(set(new_ids) - set(old_ids)):
        raise ValueError('added set mismatch')
    if r['removed_witness_ids'] != sorted(set(old_ids) - set(new_ids)):
        raise ValueError('removed set mismatch')
    if r['target_epoch'] != r['predecessor_epoch'] + 1:
        raise ValueError('reconfiguration epoch mismatch')


def root_fact_hash(root: str, fact: str, evidence_ref: str) -> str:
    return dig({'root': root, 'fact': fact, 'evidence_ref': evidence_ref, 'scope': 'wave89-test-only-mechanical-root-evaluation'})


def test_root_evaluations(reconfig: dict[str, Any], *, verdict_override: dict[str, str] | None = None) -> dict[str, dict[str, str]]:
    facts = {
        'truth': 'exact predecessor membership, target membership, pointers, and reconfiguration identity are explicit and integrity checked',
        'agency_non_domination': 'membership change is explicit evidence; prepared objects alone do not silently mutate current witness membership',
        'continuity': 'old membership remains authoritative until exact authorized handoff and target pointer commit complete',
        'wisdom_before_speed': 'reconfiguration may HOLD; no majority vote, newest-wins shortcut, automatic merge, or canonical promotion is performed',
    }
    verdict_override = verdict_override or {}
    out: dict[str, dict[str, str]] = {}
    for root in REQUIRED_ROOTS:
        ref = f"wave89:{reconfig['reconfiguration_sha256']}:{root}"
        fact = facts[root]
        out[root] = {
            'verdict': verdict_override.get(root, 'PASS'),
            'fact': fact,
            'evidence_ref': ref,
            'evidence_sha256': root_fact_hash(root, fact, ref),
        }
    return out


def make_authorization(reconfig: dict[str, Any], evaluations: dict[str, dict[str, str]], *, label: str) -> dict[str, Any]:
    validate_reconfiguration(reconfig)
    return seal({
        'schema': AUTH_SCHEMA,
        'action': 'AUTHORIZE_WITNESS_MEMBERSHIP_RECONFIGURATION',
        'predecessor_epoch': reconfig['predecessor_epoch'],
        'predecessor_pointer_sha256': reconfig['predecessor_pointer_sha256'],
        'predecessor_membership_sha256': reconfig['predecessor_membership_sha256'],
        'target_epoch': reconfig['target_epoch'],
        'target_pointer_sha256': reconfig['target_pointer_sha256'],
        'target_membership_sha256': reconfig['target_membership_sha256'],
        'reconfiguration_sha256': reconfig['reconfiguration_sha256'],
        'transition_kind': reconfig['transition_kind'],
        'old_witness_ids': reconfig['old_witness_ids'],
        'target_witness_ids': reconfig['target_witness_ids'],
        'retained_witness_ids': reconfig['retained_witness_ids'],
        'added_witness_ids': reconfig['added_witness_ids'],
        'removed_witness_ids': reconfig['removed_witness_ids'],
        'evaluations': evaluations,
        'evaluation_label': label,
        'test_only': True,
        'truth': {
            'authorization_is_structural_test_evidence_not_actor_identity': True,
            'hash_integrity_does_not_make_the_evaluator_legitimate': True,
            'all_four_test_root_evaluations_must_pass': True,
            'prepared_authorization_has_no_state_authority_until_used_by_transition': True,
        },
        'authorization_sha256': '',
    }, 'authorization_sha256')


def validate_authorization(auth: dict[str, Any], reconfig: dict[str, Any], *, require_allow: bool = True) -> str:
    validate_reconfiguration(reconfig)
    validate_seal(auth, 'authorization_sha256')
    if auth.get('schema') != AUTH_SCHEMA or auth.get('action') != 'AUTHORIZE_WITNESS_MEMBERSHIP_RECONFIGURATION':
        raise ValueError('authorization schema/action mismatch')
    exact_fields = (
        'predecessor_epoch', 'predecessor_pointer_sha256', 'predecessor_membership_sha256',
        'target_epoch', 'target_pointer_sha256', 'target_membership_sha256',
        'reconfiguration_sha256', 'transition_kind', 'old_witness_ids', 'target_witness_ids',
        'retained_witness_ids', 'added_witness_ids', 'removed_witness_ids',
    )
    for field in exact_fields:
        if auth.get(field) != reconfig.get(field):
            raise ValueError(f'authorization {field} binding mismatch')
    ev = auth.get('evaluations')
    if not isinstance(ev, dict) or set(ev) != set(REQUIRED_ROOTS):
        raise ValueError('authorization must cover exactly four roots')
    verdicts: list[str] = []
    for root in REQUIRED_ROOTS:
        row = ev[root]
        verdict = row.get('verdict')
        if verdict not in ('PASS', 'HOLD', 'FAIL'):
            raise ValueError('root verdict invalid')
        fact = row.get('fact')
        ref = row.get('evidence_ref')
        evidence_sha = row.get('evidence_sha256')
        if not isinstance(fact, str) or not isinstance(ref, str) or evidence_sha != root_fact_hash(root, fact, ref):
            raise ValueError('root evidence identity mismatch')
        verdicts.append(verdict)
    decision = 'ALLOW' if all(v == 'PASS' for v in verdicts) else ('FAIL' if 'FAIL' in verdicts else 'HOLD')
    if require_allow and decision != 'ALLOW':
        raise ValueError(f'authorization does not allow transition: {decision}')
    return decision


class AuthStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, aid: str) -> Path:
        return self.root / f'{aid}.json'

    def put(self, auth: dict[str, Any]) -> str:
        validate_seal(auth, 'authorization_sha256')
        aid = auth['authorization_sha256']
        raw = canon(auth) + b'\n'
        path = self.path_for(aid)
        if path.exists() and path.read_bytes() != raw:
            raise ValueError('authorization content-address collision')
        path.write_bytes(raw)
        return aid

    def get(self, aid: str) -> dict[str, Any]:
        path = self.path_for(aid)
        if not path.is_file():
            raise FileNotFoundError('authorization missing')
        obj = json.loads(path.read_text('utf-8'))
        validate_seal(obj, 'authorization_sha256')
        if obj['authorization_sha256'] != aid:
            raise ValueError('authorization store key/body mismatch')
        return obj


@dataclass
class Runtime:
    current_pointer_sha256: str
    current_membership_sha256: str
    witness_heads: dict[str, str]


def apply_step(runtime: Runtime, reconfig: dict[str, Any], auth_store: AuthStore, authorization_sha256: str | None, *, count: int | None = None) -> dict[str, Any]:
    """Model Wave88 witness fan-out with an authorization gate before any mutation."""
    validate_reconfiguration(reconfig)
    if not authorization_sha256:
        return {'status': 'AUTHORIZATION_REQUIRED_HOLD'}
    try:
        auth = auth_store.get(authorization_sha256)
        validate_authorization(auth, reconfig, require_allow=True)
    except Exception as exc:
        return {'status': 'AUTHORIZATION_INVALID_HOLD', 'error': f'{type(exc).__name__}: {exc}'}
    if runtime.current_pointer_sha256 != reconfig['predecessor_pointer_sha256'] or runtime.current_membership_sha256 != reconfig['predecessor_membership_sha256']:
        return {'status': 'PREDECESSOR_STATE_MISMATCH_HOLD'}
    old = reconfig['old_witness_ids']
    target = reconfig['target_witness_ids']
    for wid in old:
        runtime.witness_heads.setdefault(wid, 'PREDECESSOR')
    todo = list(old) + [wid for wid in reconfig['added_witness_ids']]
    limit = len(todo) if count is None else min(count, len(todo))
    for wid in todo[:limit]:
        runtime.witness_heads[wid] = reconfig['reconfiguration_sha256']
    if limit < len(todo):
        return {'status': 'PARTIAL_AUTHORIZED_FANOUT', 'advanced': limit, 'total': len(todo), 'authorization_sha256': authorization_sha256}
    runtime.current_pointer_sha256 = reconfig['target_pointer_sha256']
    runtime.current_membership_sha256 = reconfig['target_membership_sha256']
    runtime.witness_heads = {wid: reconfig['reconfiguration_sha256'] for wid in target}
    return {'status': 'COMMITTED', 'authorization_sha256': authorization_sha256}


def recover(runtime: Runtime, reconfig: dict[str, Any], auth_store: AuthStore, authorization_sha256: str | None) -> dict[str, Any]:
    if runtime.current_pointer_sha256 == reconfig['target_pointer_sha256'] and runtime.current_membership_sha256 == reconfig['target_membership_sha256']:
        return {'status': 'CONSISTENT_TARGET'}
    return apply_step(runtime, reconfig, auth_store, authorization_sha256)


def fixture() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    old_m = make_membership(0, ('witness-a', 'witness-b', 'witness-c'), None, 'GENESIS')
    old_p = make_pointer(0, old_m['membership_sha256'], None, 'GENESIS')
    target_m = make_membership(1, ('witness-a', 'witness-b', 'witness-d'), old_m['membership_sha256'], 'REPLACE')
    target_p = make_pointer(1, target_m['membership_sha256'], old_p['pointer_sha256'], 'RECONFIGURE')
    reconfig = make_reconfiguration(old_m, target_m, old_p, target_p)
    return old_m, old_p, target_m, target_p, reconfig


def fail_contains(fn, text: str) -> bool:
    try:
        fn()
    except Exception as exc:
        return text in str(exc)
    return False


def self_test(benchmark_rounds: int = 100) -> dict[str, Any]:
    checks: list[tuple[str, bool]] = []
    details: dict[str, Any] = {}
    old_m, old_p, target_m, target_p, reconfig = fixture()
    checks.append(('exact_wave88_source_commit', WAVE88_TOOL_COMMIT == '76ed78a64825a5c71ff2017ef9383d389b878192'))
    checks.append(('exact_wave88_source_blob', WAVE88_TOOL_BLOB_SHA == 'efabee7b9c9724e1bd23f37cfc909cc9ed54cf1a'))

    ev = test_root_evaluations(reconfig)
    auth = make_authorization(reconfig, ev, label='Wave89 test-only exact membership reconfiguration gate')
    checks.append(('four_root_authorization_allows_exact_reconfiguration', validate_authorization(auth, reconfig) == 'ALLOW'))

    with tempfile.TemporaryDirectory(prefix='axm-wave89-') as td:
        store = AuthStore(Path(td) / 'auth')
        aid = store.put(auth)
        rt = Runtime(old_p['pointer_sha256'], old_m['membership_sha256'], {wid: 'PREDECESSOR' for wid in old_m['witness_ids']})
        before = json.loads(json.dumps(rt.__dict__))
        noauth = apply_step(rt, reconfig, store, None)
        checks.append(('missing_authorization_blocks_before_mutation', noauth['status'] == 'AUTHORIZATION_REQUIRED_HOLD' and rt.__dict__ == before))
        result = apply_step(rt, reconfig, store, aid)
        checks.append(('authorized_replacement_commits', result['status'] == 'COMMITTED'))
        checks.append(('committed_state_is_exact_target_membership', rt.current_membership_sha256 == target_m['membership_sha256'] and set(rt.witness_heads) == set(target_m['witness_ids'])))
        checks.append(('removed_witness_has_zero_current_authority', 'witness-c' not in rt.witness_heads))

        hold_ev = test_root_evaluations(reconfig, verdict_override={'continuity': 'HOLD'})
        hold_auth = make_authorization(reconfig, hold_ev, label='negative HOLD control')
        store.put(hold_auth)
        checks.append(('root_hold_blocks_transition', fail_contains(lambda: validate_authorization(hold_auth, reconfig), 'does not allow')))
        fail_ev = test_root_evaluations(reconfig, verdict_override={'truth': 'FAIL'})
        fail_auth = make_authorization(reconfig, fail_ev, label='negative FAIL control')
        store.put(fail_auth)
        checks.append(('root_fail_blocks_transition', fail_contains(lambda: validate_authorization(fail_auth, reconfig), 'does not allow')))

        missing = dict(auth)
        missing['evaluations'] = dict(auth['evaluations'])
        missing['evaluations'].pop('wisdom_before_speed')
        missing = seal(missing, 'authorization_sha256')
        checks.append(('missing_root_rejected', fail_contains(lambda: validate_authorization(missing, reconfig), 'exactly four roots')))
        extra = dict(auth)
        extra['evaluations'] = dict(auth['evaluations'])
        extra['evaluations']['speed'] = {'verdict': 'PASS', 'fact': 'x', 'evidence_ref': 'x', 'evidence_sha256': root_fact_hash('speed', 'x', 'x')}
        extra = seal(extra, 'authorization_sha256')
        checks.append(('extra_root_rejected', fail_contains(lambda: validate_authorization(extra, reconfig), 'exactly four roots')))

        for field, value in (
            ('predecessor_membership_sha256', '0' * 64),
            ('target_membership_sha256', '1' * 64),
            ('predecessor_pointer_sha256', '2' * 64),
            ('target_pointer_sha256', '3' * 64),
            ('reconfiguration_sha256', '4' * 64),
        ):
            wrong = dict(auth)
            wrong[field] = value
            wrong = seal(wrong, 'authorization_sha256')
            checks.append((f'wrong_{field}_binding_rejected', fail_contains(lambda w=wrong: validate_authorization(w, reconfig), 'binding mismatch')))

        wrong_sets = dict(auth)
        wrong_sets['removed_witness_ids'] = []
        wrong_sets = seal(wrong_sets, 'authorization_sha256')
        checks.append(('wrong_witness_set_binding_rejected', fail_contains(lambda: validate_authorization(wrong_sets, reconfig), 'binding mismatch')))
        wrong_kind = dict(auth)
        wrong_kind['transition_kind'] = 'ADD'
        wrong_kind = seal(wrong_kind, 'authorization_sha256')
        checks.append(('wrong_transition_kind_binding_rejected', fail_contains(lambda: validate_authorization(wrong_kind, reconfig), 'binding mismatch')))

        nested = json.loads(json.dumps(auth))
        nested['evaluations']['truth']['fact'] = 'rewritten fact without evidence identity update'
        nested = seal(nested, 'authorization_sha256')
        checks.append(('nested_root_evidence_tamper_rejected', fail_contains(lambda: validate_authorization(nested, reconfig), 'root evidence identity mismatch')))
        top_tamper = dict(auth)
        top_tamper['evaluation_label'] = 'tampered without reseal'
        checks.append(('top_level_tamper_rejected', fail_contains(lambda: validate_authorization(top_tamper, reconfig), 'authorization_sha256 mismatch')))

        # Stale receipt: same predecessor, different exact target.
        alt_m = make_membership(1, ('witness-a', 'witness-c', 'witness-e'), old_m['membership_sha256'], 'REPLACE')
        alt_p = make_pointer(1, alt_m['membership_sha256'], old_p['pointer_sha256'], 'RECONFIGURE')
        alt_r = make_reconfiguration(old_m, alt_m, old_p, alt_p)
        checks.append(('stale_authorization_cannot_cross_reconfiguration', fail_contains(lambda: validate_authorization(auth, alt_r), 'binding mismatch')))

        # Prepared object/receipt alone does not move state.
        rt2 = Runtime(old_p['pointer_sha256'], old_m['membership_sha256'], {wid: 'PREDECESSOR' for wid in old_m['witness_ids']})
        checks.append(('prepared_authorization_zero_authority_without_execution', rt2.current_pointer_sha256 == old_p['pointer_sha256'] and rt2.current_membership_sha256 == old_m['membership_sha256']))

        # Crash/recovery: some fan-out happened under exact authorization; losing the receipt freezes repair.
        partial = apply_step(rt2, reconfig, store, aid, count=2)
        checks.append(('authorized_partial_fanout_recorded', partial['status'] == 'PARTIAL_AUTHORIZED_FANOUT'))
        auth_path = store.path_for(aid)
        saved = auth_path.read_bytes()
        auth_path.unlink()
        frozen = recover(rt2, reconfig, store, aid)
        checks.append(('missing_authorization_after_crash_holds_recovery', frozen['status'] == 'AUTHORIZATION_INVALID_HOLD'))
        auth_path.write_bytes(saved)
        repaired = recover(rt2, reconfig, store, aid)
        checks.append(('restored_exact_authorization_allows_recovery', repaired['status'] == 'COMMITTED'))

        # Corrupt body under correct content-address path.
        rt3 = Runtime(old_p['pointer_sha256'], old_m['membership_sha256'], {wid: 'PREDECESSOR' for wid in old_m['witness_ids']})
        corrupt = json.loads(saved.decode('utf-8'))
        corrupt['evaluation_label'] = 'body corrupt under old key'
        auth_path.write_bytes(canon(corrupt) + b'\n')
        checks.append(('stored_body_corruption_rejected', recover(rt3, reconfig, store, aid)['status'] == 'AUTHORIZATION_INVALID_HOLD'))
        auth_path.write_bytes(saved)

        # Important unsolved counterexample: a party that can mint a fully rehashed structural PASS
        # receipt can satisfy this mechanical gate. Integrity is not evaluator legitimacy.
        forged_ev = test_root_evaluations(reconfig)
        forged_ev['truth'] = dict(forged_ev['truth'])
        forged_ev['truth']['fact'] = 'self-asserted PASS by an unverified evaluator; structure is valid but legitimacy is unknown'
        forged_ev['truth']['evidence_ref'] = 'unverified-evaluator:self-assertion'
        forged_ev['truth']['evidence_sha256'] = root_fact_hash('truth', forged_ev['truth']['fact'], forged_ev['truth']['evidence_ref'])
        forged_auth = make_authorization(reconfig, forged_ev, label='counterexample: structurally valid self-minted PASS')
        structural_accept = validate_authorization(forged_auth, reconfig) == 'ALLOW'
        checks.append(('counterexample_structural_pass_does_not_prove_legitimacy', structural_accept))
        details['evaluator_legitimacy_counterexample'] = (
            'The structural gate accepts a fully self-consistent rehashed PASS receipt. This is intentionally preserved as an unresolved counterexample: '
            'content integrity and exact binding do not prove who evaluated the four roots or whether that evaluator had legitimate authority.'
        )

    samples: list[float] = []
    for _ in range(benchmark_rounds):
        old_m_b, old_p_b, target_m_b, target_p_b, r_b = fixture()
        start = time.process_time_ns()
        ev_b = test_root_evaluations(r_b)
        a_b = make_authorization(r_b, ev_b, label='synthetic benchmark')
        validate_authorization(a_b, r_b)
        samples.append((time.process_time_ns() - start) / 1000.0)

    failed = [name for name, ok in checks if not ok]
    return {
        'schema': 'axm.flowing-compute-wave89-report/v0.1',
        'status': 'PASS' if not failed else 'FAIL',
        'passed_checks': sum(1 for _, ok in checks if ok),
        'total_checks': len(checks),
        'failed_checks': failed,
        'checks': [{'name': name, 'pass': ok} for name, ok in checks],
        'synthetic_single_host_authorization_cpu_us_median': statistics.median(samples),
        'benchmark_rounds': benchmark_rounds,
        'source_provenance': {
            'wave88_tool_commit': WAVE88_TOOL_COMMIT,
            'wave88_tool_blob_sha': WAVE88_TOOL_BLOB_SHA,
        },
        'truth_boundary': {
            'fresh_monolith_audit': False,
            'compute_efficiency_claim': False,
            'energy_claim': False,
            'distributed_consensus_claim': False,
            'actor_or_evaluator_identity_proven': False,
            'canonical_root_judgment_claim': False,
            'automatic_merge': False,
            'note': 'Authorization binding/recovery mechanics only. Root evaluations are test-only structural evidence, not proof of evaluator legitimacy.'
        },
        'details': details,
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
