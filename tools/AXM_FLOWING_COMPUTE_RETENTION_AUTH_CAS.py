from __future__ import annotations
import fcntl, json, os, tempfile, time, statistics
from pathlib import Path
from multiprocessing import get_context
from typing import Any

from AXM_FLOWING_COMPUTE_RETENTION_GC_MODEL import (
    C1, C3, dig, make_drop, rid, roots, seq, validate_drop, wave81
)

ROOT_EVAL='axm.flowing-compute-root-evaluation-receipt/v0.1'
AUTH_RET='axm.flowing-compute-authorized-retention-generation/v0.3'
PTR='axm.flowing-compute-retention-cas-pointer/v0.1'
REQUIRED_ROOTS=('truth','agency_non_domination','continuity','wisdom_before_speed')
W82_DROP_SHA='9a60bbfb8302bbdc4e06eb39fd7898366b5fc1ef3963978dd857b845946b31a0'


def _hash_fact(root:str,fact:str)->str:
    return dig({'root':root,'fact':fact,'scope':'wave83-test-only-mechanical-evaluation'})


def test_root_evaluations()->dict[str,dict[str,str]]:
    facts={
        'truth':'exact predecessor, checkpoint, and drop-receipt identities are explicit and integrity-checked',
        'agency_non_domination':'root removal is explicit evidence, not silent mutation; no merge or external user action is performed',
        'continuity':'the later rollback checkpoint remains retained and its receipt remains reachable before any later GC',
        'wisdom_before_speed':'Wave83 tests pointer authorization/CAS only; it does not execute garbage collection or promote the test drop to canon',
    }
    return {r:{'verdict':'PASS','evidence_sha256':_hash_fact(r,facts[r]),'fact':facts[r]} for r in REQUIRED_ROOTS}


def make_root_evaluation(pred:dict[str,Any],drop:dict[str,Any],evaluations:dict[str,dict[str,str]],*,label:str)->dict[str,Any]:
    c=drop['checkpoint_sha256']
    validate_drop(drop,pred,c)
    r={
        'schema':ROOT_EVAL,
        'action':'EVALUATE_ROLLBACK_ROOT_DROP',
        'checkpoint_sha256':c,
        'drop_receipt_sha256':drop['drop_receipt_sha256'],
        'predecessor_retention_sha256':rid(pred),
        'next_retention_sequence':seq(pred)+1,
        'evaluations':evaluations,
        'evaluation_label':label,
        'test_only':True,
        'truth':{
            'receipt_records_explicit_root_evaluation_mechanics':True,
            'receipt_is_not_actor_identity_or_signature':True,
            'test_passes_are_not_canonical_axm_root_judgments':True,
            'hash_integrity_does_not_make_the_evaluator_authoritative':True,
        },
    }
    r['root_evaluation_sha256']=dig(r)
    return r


def validate_root_evaluation(r:dict[str,Any],pred:dict[str,Any],drop:dict[str,Any],checkpoint:str,*,require_allow:bool=True)->str:
    body=dict(r); key=body.pop('root_evaluation_sha256',None)
    if r.get('schema')!=ROOT_EVAL or key!=dig(body): raise ValueError('root-evaluation integrity mismatch')
    validate_drop(drop,pred,checkpoint)
    if r.get('checkpoint_sha256')!=checkpoint: raise ValueError('root-evaluation checkpoint mismatch')
    if r.get('drop_receipt_sha256')!=drop.get('drop_receipt_sha256'): raise ValueError('root-evaluation drop binding mismatch')
    if r.get('predecessor_retention_sha256')!=rid(pred): raise ValueError('root-evaluation predecessor mismatch')
    if int(r.get('next_retention_sequence',-1))!=seq(pred)+1: raise ValueError('root-evaluation sequence mismatch')
    ev=r.get('evaluations',{})
    if tuple(sorted(ev))!=tuple(sorted(REQUIRED_ROOTS)): raise ValueError('root-evaluation must cover exactly four roots')
    decisions=[]
    for root in REQUIRED_ROOTS:
        row=ev[root]
        if row.get('verdict') not in ('PASS','HOLD','FAIL'): raise ValueError('root-evaluation verdict invalid')
        h=row.get('evidence_sha256'); fact=row.get('fact')
        if not isinstance(h,str) or len(h)!=64: raise ValueError('root-evaluation evidence hash malformed')
        if not isinstance(fact,str) or h!=_hash_fact(root,fact): raise ValueError('root-evaluation evidence identity mismatch')
        decisions.append(row['verdict'])
    decision='ALLOW' if all(v=='PASS' for v in decisions) else ('FAIL' if 'FAIL' in decisions else 'HOLD')
    if require_allow and decision!='ALLOW': raise ValueError(f'root-evaluation does not authorize transition: {decision}')
    return decision


class ObjectStore:
    def __init__(self,path:str|Path):
        self.path=Path(path); self.path.mkdir(parents=True,exist_ok=True)
    def put(self,obj:dict[str,Any],key_field:str)->tuple[str,bool]:
        key=obj.get(key_field)
        if not isinstance(key,str) or len(key)!=64: raise ValueError('object key shape')
        body=dict(obj); body.pop(key_field,None)
        if dig(body)!=key: raise ValueError('content-address object integrity mismatch')
        p=self.path/f'{key}.json'; raw=json.dumps(obj,sort_keys=True,separators=(',',':')).encode()
        if p.exists():
            if p.read_bytes()!=raw: raise ValueError('content-address collision or object-store corruption')
            return key,False
        with p.open('xb') as f:
            f.write(raw); f.flush(); os.fsync(f.fileno())
        return key,True
    def get(self,key:str)->dict[str,Any]:
        p=self.path/f'{key}.json'
        if not p.exists(): raise ValueError('missing content-address evidence object')
        return json.loads(p.read_text())
    def has(self,key:str)->bool: return (self.path/f'{key}.json').exists()


def make_authorized_retention(pred:dict[str,Any],new_roots:set[str],drops:dict[str,dict[str,Any]],root_evals:dict[str,dict[str,Any]],reason:str)->dict[str,Any]:
    removed=roots(pred)-set(new_roots)
    if set(drops)!=removed: raise ValueError('every removed rollback root requires exactly one drop receipt')
    if set(root_evals)!=removed: raise ValueError('every removed rollback root requires exactly one root-evaluation receipt')
    drefs={}; arefs={}
    for c in sorted(removed):
        validate_drop(drops[c],pred,c)
        validate_root_evaluation(root_evals[c],pred,drops[c],c,require_allow=True)
        drefs[c]=drops[c]['drop_receipt_sha256']; arefs[c]=root_evals[c]['root_evaluation_sha256']
    m={
        'schema':AUTH_RET,'sequence':seq(pred)+1,'predecessor_retention_sha256':rid(pred),
        'retained_checkpoints':sorted(new_roots),'drop_receipts':drefs,'drop_root_evaluations':arefs,'reason':reason,
        'truth':{
            'retention_change_is_append_only_and_predecessor_bound':True,
            'rollback_drop_requires_explicit_four_root_evaluation_receipt':True,
            'root_evaluation_receipt_is_mechanical_gate_evidence_not_actor_authentication':True,
            'candidate_evidence_has_no_current_state_authority_until_pointer_cas_succeeds':True,
        },
    }
    m['retention_sha256']=dig(m)
    return m


def validate_authorized_retention(m:dict[str,Any],pred:dict[str,Any],store:ObjectStore)->None:
    body=dict(m); key=body.pop('retention_sha256',None)
    if m.get('schema')!=AUTH_RET or key!=dig(body): raise ValueError('authorized-retention integrity mismatch')
    if m.get('predecessor_retention_sha256')!=rid(pred): raise ValueError('authorized-retention predecessor mismatch')
    if int(m.get('sequence',-1))!=seq(pred)+1: raise ValueError('authorized-retention sequence mismatch')
    removed=roots(pred)-set(m.get('retained_checkpoints',[]))
    if set(m.get('drop_receipts',{}))!=removed or set(m.get('drop_root_evaluations',{}))!=removed:
        raise ValueError('authorized-retention removed roots/evidence mismatch')
    for c in removed:
        dr=store.get(m['drop_receipts'][c]); ar=store.get(m['drop_root_evaluations'][c])
        if dr.get('drop_receipt_sha256')!=m['drop_receipts'][c]: raise ValueError('stored drop receipt identity mismatch')
        if ar.get('root_evaluation_sha256')!=m['drop_root_evaluations'][c]: raise ValueError('stored root evaluation identity mismatch')
        validate_root_evaluation(ar,pred,dr,c,require_allow=True)


def make_pointer(retention:dict[str,Any])->dict[str,Any]:
    p={'schema':PTR,'sequence':seq(retention),'retention_sha256':rid(retention),'truth':{'pointer_is_only_current_state_authority_surface_in_this_model':True}}
    p['pointer_sha256']=dig(p); return p


def validate_pointer(p:dict[str,Any])->None:
    body=dict(p); key=body.pop('pointer_sha256',None)
    if p.get('schema')!=PTR or key!=dig(body): raise ValueError('retention pointer integrity mismatch')
    if not isinstance(p.get('retention_sha256'),str) or len(p['retention_sha256'])!=64: raise ValueError('retention pointer hash shape')


def _durable_replace(path:Path,raw:bytes,*,crash_before_replace:bool=False)->str:
    tmp=path.with_name(f'.{path.name}.{os.getpid()}.{time.time_ns()}.tmp')
    with tmp.open('xb') as f:
        f.write(raw); f.flush(); os.fsync(f.fileno())
    if crash_before_replace:
        return str(tmp)
    os.replace(tmp,path)
    dfd=os.open(str(path.parent),os.O_DIRECTORY)
    try: os.fsync(dfd)
    finally: os.close(dfd)
    return str(path)


def initialize_pointer(path:str|Path,retention:dict[str,Any])->None:
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True); raw=json.dumps(make_pointer(retention),sort_keys=True,separators=(',',':')).encode()
    _durable_replace(path,raw)


def read_pointer(path:str|Path)->dict[str,Any]:
    p=json.loads(Path(path).read_text()); validate_pointer(p); return p


def cas_commit(*,pointer_path:str|Path,expected_predecessor:dict[str,Any],candidate:dict[str,Any],store_path:str|Path,crash_before_replace:bool=False)->dict[str,Any]:
    store=ObjectStore(store_path); validate_authorized_retention(candidate,expected_predecessor,store)
    if not store.has(candidate['retention_sha256']): raise ValueError('candidate retention object must be staged before CAS')
    pointer_path=Path(pointer_path); lock_path=pointer_path.with_suffix(pointer_path.suffix+'.lock')
    lock_path.touch(exist_ok=True)
    with lock_path.open('rb') as lf:
        fcntl.flock(lf.fileno(),fcntl.LOCK_EX)
        current=read_pointer(pointer_path)
        if current['retention_sha256']!=rid(expected_predecessor):
            return {'status':'CONFLICT','current_retention_sha256':current['retention_sha256'],'candidate_retention_sha256':candidate['retention_sha256']}
        raw=json.dumps(make_pointer(candidate),sort_keys=True,separators=(',',':')).encode()
        where=_durable_replace(pointer_path,raw,crash_before_replace=crash_before_replace)
        if crash_before_replace:
            return {'status':'CRASH_SIMULATED_BEFORE_REPLACE','staged_temp_path':where,'current_retention_sha256':current['retention_sha256'],'candidate_retention_sha256':candidate['retention_sha256']}
        return {'status':'COMMITTED','previous_retention_sha256':current['retention_sha256'],'candidate_retention_sha256':candidate['retention_sha256']}


def _race_worker(pointer_path:str,store_path:str,pred:dict[str,Any],candidate:dict[str,Any],gate,q,label:str):
    gate.wait()
    try:r=cas_commit(pointer_path=pointer_path,expected_predecessor=pred,candidate=candidate,store_path=store_path)
    except Exception as e:r={'status':'ERROR','error':str(e)}
    r['writer']=label; q.put(r)


def fail(fn):
    try: fn()
    except Exception as e: return str(e)
    raise AssertionError('unexpected success')


def build_fixture(base:Path):
    g0=wave81(); store=ObjectStore(base/'objects')
    drop=make_drop(g0,C1,'test-only explicit rollback-root retirement for crash-safe GC probe')
    assert drop['drop_receipt_sha256']==W82_DROP_SHA
    ev=test_root_evaluations(); auth=make_root_evaluation(g0,drop,ev,label='Wave83 test-only four-root gate over exact Wave82 drop intent')
    drop_candidate=make_authorized_retention(g0,{C3},{C1:drop},{C1:auth},'Wave83 writer DROP: root-gated retirement candidate; not canon')
    keep_candidate=make_authorized_retention(g0,{C1,C3},{},{},'Wave83 writer KEEP: retain both rollback roots; no drop requested')
    for obj,key in [(drop,'drop_receipt_sha256'),(auth,'root_evaluation_sha256'),(drop_candidate,'retention_sha256'),(keep_candidate,'retention_sha256')]: store.put(obj,key)
    validate_authorized_retention(drop_candidate,g0,store); validate_authorized_retention(keep_candidate,g0,store)
    return g0,store,drop,auth,drop_candidate,keep_candidate


def self_test(*,race_rounds:int=40,benchmark_rounds:int=100)->dict[str,Any]:
    controls=[]
    with tempfile.TemporaryDirectory(prefix='axm-wave83-') as td:
        base=Path(td); g0,store,drop,auth,drop_c,keep_c=build_fixture(base)
        controls.append(('exact_wave82_drop_reused',drop['drop_receipt_sha256']==W82_DROP_SHA))
        controls.append(('drop_candidate_valid',True)); controls.append(('keep_candidate_valid_without_fake_auth',True))

        missing=dict(drop_c); missing['drop_root_evaluations']={}; missing['retention_sha256']=dig({k:v for k,v in missing.items() if k!='retention_sha256'})
        controls.append(('missing_root_eval_rejected','root' in fail(lambda:validate_authorized_retention(missing,g0,store))))

        hold_ev=test_root_evaluations(); hold_ev['continuity']=dict(hold_ev['continuity']); hold_ev['continuity']['verdict']='HOLD'
        hold_auth=make_root_evaluation(g0,drop,hold_ev,label='negative HOLD control')
        store.put(hold_auth,'root_evaluation_sha256')
        controls.append(('root_hold_rejected','does not authorize' in fail(lambda:make_authorized_retention(g0,{C3},{C1:drop},{C1:hold_auth},'hold'))))

        wrong=dict(auth); wrong['drop_receipt_sha256']='0'*64; wrong['root_evaluation_sha256']=dig({k:v for k,v in wrong.items() if k!='root_evaluation_sha256'})
        controls.append(('wrong_drop_binding_rejected','drop binding' in fail(lambda:validate_root_evaluation(wrong,g0,drop,C1))))

        tampered=dict(auth); tampered['evaluation_label']='tampered'
        controls.append(('root_eval_tamper_rejected','integrity' in fail(lambda:validate_root_evaluation(tampered,g0,drop,C1))))
        fake_fact=test_root_evaluations(); fake_fact['truth']=dict(fake_fact['truth']); fake_fact['truth']['fact']='rewritten fact without corresponding evidence identity'
        fake_auth=make_root_evaluation(g0,drop,fake_fact,label='negative fact/evidence mismatch control')
        controls.append(('nested_root_evidence_mismatch_rejected','evidence identity' in fail(lambda:validate_root_evaluation(fake_auth,g0,drop,C1))))

        ptr=base/'current.json'; initialize_pointer(ptr,g0)
        crash=cas_commit(pointer_path=ptr,expected_predecessor=g0,candidate=drop_c,store_path=store.path,crash_before_replace=True)
        controls.append(('crash_before_replace_keeps_predecessor',crash['status'].startswith('CRASH_') and read_pointer(ptr)['retention_sha256']==rid(g0)))
        controls.append(('staged_candidate_has_no_authority',store.has(drop_c['retention_sha256']) and read_pointer(ptr)['retention_sha256']!=drop_c['retention_sha256']))

        first=cas_commit(pointer_path=ptr,expected_predecessor=g0,candidate=drop_c,store_path=store.path)
        second=cas_commit(pointer_path=ptr,expected_predecessor=g0,candidate=keep_c,store_path=store.path)
        controls.append(('first_writer_commits',first['status']=='COMMITTED'))
        controls.append(('stale_second_writer_conflicts',second['status']=='CONFLICT'))
        controls.append(('losing_evidence_preserved_no_authority',store.has(keep_c['retention_sha256']) and read_pointer(ptr)['retention_sha256']==drop_c['retention_sha256']))

        ptr2=base/'current-reverse.json'; initialize_pointer(ptr2,g0)
        a=cas_commit(pointer_path=ptr2,expected_predecessor=g0,candidate=keep_c,store_path=store.path)
        b=cas_commit(pointer_path=ptr2,expected_predecessor=g0,candidate=drop_c,store_path=store.path)
        controls.append(('reverse_keep_can_win',a['status']=='COMMITTED' and b['status']=='CONFLICT' and read_pointer(ptr2)['retention_sha256']==keep_c['retention_sha256']))

        badp=make_pointer(g0); badp['retention_sha256']='f'*64
        badpath=base/'badpointer.json'; badpath.write_text(json.dumps(badp))
        controls.append(('pointer_tamper_rejected','integrity' in fail(lambda:read_pointer(badpath))))

        ctx=get_context('fork'); race_wins={'DROP':0,'KEEP':0}; race_conflicts=0
        for i in range(race_rounds):
            rp=base/f'race-{i}.json'; initialize_pointer(rp,g0); gate=ctx.Barrier(2); q=ctx.Queue()
            ps=[ctx.Process(target=_race_worker,args=(str(rp),str(store.path),g0,drop_c,gate,q,'DROP')),ctx.Process(target=_race_worker,args=(str(rp),str(store.path),g0,keep_c,gate,q,'KEEP'))]
            [p.start() for p in ps]; rows=[q.get(timeout=10) for _ in ps]; [p.join(10) for p in ps]
            statuses=sorted(r['status'] for r in rows)
            if statuses!=['COMMITTED','CONFLICT']: raise AssertionError(f'bad concurrent race statuses {rows}')
            winner=[r for r in rows if r['status']=='COMMITTED'][0]['writer']; race_wins[winner]+=1; race_conflicts+=1
            if read_pointer(rp)['retention_sha256'] not in (drop_c['retention_sha256'],keep_c['retention_sha256']): raise AssertionError('race pointer unknown winner')
        controls.append(('concurrent_exactly_one_winner',race_conflicts==race_rounds))
        controls.append(('concurrent_both_candidate_types_can_win',sum(race_wins.values())==race_rounds and all(v>0 for v in race_wins.values())))

        timings=[]
        for i in range(benchmark_rounds):
            bp=base/f'bench-{i}.json'; initialize_pointer(bp,g0); t0=time.process_time_ns(); r=cas_commit(pointer_path=bp,expected_predecessor=g0,candidate=keep_c,store_path=store.path); t1=time.process_time_ns()
            if r['status']!='COMMITTED': raise AssertionError('benchmark CAS failed')
            timings.append((t1-t0)/1000.0)

        failed=[name for name,ok in controls if not ok]
        if failed: raise AssertionError(f'controls failed: {failed}')
        return {
            'status':'PASS','controls_passed':len(controls),'controls_total':len(controls),
            'wave81_predecessor_retention_sha256':rid(g0),'wave82_drop_receipt_sha256':drop['drop_receipt_sha256'],
            'root_evaluation_sha256':auth['root_evaluation_sha256'],'drop_candidate_retention_sha256':drop_c['retention_sha256'],'keep_candidate_retention_sha256':keep_c['retention_sha256'],
            'race_rounds':race_rounds,'race_wins':race_wins,'race_conflicts':race_conflicts,
            'cas_commit_median_cpu_us':statistics.median(timings),'benchmark_rounds':benchmark_rounds,
            'truth':{
                'root_evaluation_is_test_only_mechanical_gate_evidence_not_canonical_axm_judgment':True,
                'root_evaluation_is_not_actor_authentication_or_signature':True,
                'cas_is_single_host_posix_flock_plus_atomic_replace_not_distributed_consensus':True,
                'benchmark_is_synthetic_local_infrastructure_not_monolith_workload':True,
                'wave83_performs_no_gc_and_no_auto_merge':True,
            },
        }

if __name__=='__main__': print(json.dumps(self_test(),indent=2,sort_keys=True))
