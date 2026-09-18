from __future__ import annotations
import argparse, hashlib, json, os, shutil, statistics, tempfile, time
from pathlib import Path
from typing import Any

AUDIT='axm.flowing-compute-audit-work-receipt/v0.1'; AUDITED='audited_reuse'
CHECKPOINT='axm.flowing-compute-receipt-checkpoint/v0.1'; RETENTION='axm.flowing-compute-receipt-retention/v0.1'

def canon(v:Any)->bytes:return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def digest(v:Any)->str:return hashlib.sha256(canon(v)).hexdigest()
def sha(v:Any)->bool:
    if not isinstance(v,str) or len(v)!=64:return False
    try:int(v,16);return True
    except ValueError:return False

def atomic(path:Path,data:bytes):
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_name(path.name+'.tmp')
    with tmp.open('wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path); d=os.open(str(path.parent),os.O_RDONLY)
    try:os.fsync(d)
    finally:os.close(d)

def readj(path:Path)->dict[str,Any]:
    v=json.loads(path.read_text());
    if not isinstance(v,dict):raise ValueError('expected JSON object')
    return v

def validate_receipt(r:dict[str,Any]):
    if r.get('schema')!=AUDIT or r.get('status')!='AUDIT_PASS' or r.get('mode')!=AUDITED:raise ValueError('audit receipt contract mismatch')
    key=r.get('receipt_sha256'); body=dict(r);body.pop('receipt_sha256',None)
    if not sha(key) or digest(body)!=key:raise ValueError('audit receipt integrity mismatch')
    if int(r.get('bytes_read',-1))!=int(r.get('expected_artifact_bytes',-2)):raise ValueError('audit receipt byte-count mismatch')
    if r.get('observed_artifact_sha256')!=r.get('expected_artifact_sha256'):raise ValueError('audit receipt artifact digest mismatch')

def challenge(state:dict[str,Any],sequence:int)->str:
    return digest({'schema':'axm.flowing-compute-audit-challenge/v0.1','contract_id':state['contract_id'],'sequence':sequence,'mode':AUDITED,
                   'predecessor_state_sha256':state['state_sha256'],'artifact_sha256':state['artifact_sha256'],
                   'artifact_bytes':state['artifact_bytes'],'proof_sha256':state['proof_sha256']})

def audit(path:Path,state:dict[str,Any],sequence:int,truth_extra=None)->dict[str,Any]:
    h=hashlib.sha256(); n=chunks=0;t0=time.process_time_ns();w0=time.perf_counter_ns()
    with path.open('rb') as f:
        while b:=f.read(1024*1024):h.update(b);n+=len(b);chunks+=1
    truth={'receipt_created_after_full_local_byte_read':True,'receipt_digest_is_integrity_not_actor_authentication':True,'cpu_time_is_not_joules':True}
    truth.update(truth_extra or {}); observed=h.hexdigest()
    r={'schema':AUDIT,'status':'AUDIT_PASS' if n==state['artifact_bytes'] and observed==state['artifact_sha256'] else 'AUDIT_FAIL',
       'contract_id':state['contract_id'],'sequence':sequence,'mode':AUDITED,'challenge_sha256':challenge(state,sequence),
       'predecessor_state_sha256':state['state_sha256'],'proof_sha256':state['proof_sha256'],
       'expected_artifact_sha256':state['artifact_sha256'],'observed_artifact_sha256':observed,
       'expected_artifact_bytes':state['artifact_bytes'],'bytes_read':n,'chunks_read':chunks,'chunk_bytes':1048576,
       'audit_cpu_ns':time.process_time_ns()-t0,'audit_wall_ns':time.perf_counter_ns()-w0,'truth':truth}
    r['receipt_sha256']=digest(r);validate_receipt(r);return r

def rpath(root:Path,key:str)->Path:
    if not sha(key):raise ValueError('invalid receipt key')
    return root/'receipts'/f'{key}.json'
def cpath(root:Path,key:str)->Path:
    if not sha(key):raise ValueError('invalid checkpoint key')
    return root/'checkpoints'/f'{key}.json'
def put_receipt(root:Path,r:dict[str,Any])->str:
    validate_receipt(r);root.joinpath('receipts').mkdir(parents=True,exist_ok=True);p=rpath(root,r['receipt_sha256'])
    if p.exists():
        if readj(p)!=r:raise ValueError('append-only receipt key collision')
    else:atomic(p,(json.dumps(r,indent=2,sort_keys=True)+'\n').encode())
    return r['receipt_sha256']
def load_receipt(root:Path,key:str)->dict[str,Any]:
    p=rpath(root,key)
    if not p.exists():raise ValueError('reachable audit receipt body missing')
    r=readj(p);validate_receipt(r)
    if r['receipt_sha256']!=key:raise ValueError('audit receipt store key/body mismatch')
    return r

def checkpoint(pointer_sha:str,sequence:int,refs:dict[str,dict[str,Any]],provenance:str)->dict[str,Any]:
    if not sha(pointer_sha):raise ValueError('invalid source pointer')
    for ref in refs.values():
        if not sha(ref.get('receipt_sha256')) or not sha(ref.get('predecessor_state_sha256')) or int(ref.get('sequence',-1))!=sequence:raise ValueError('invalid receipt ref')
    c={'schema':CHECKPOINT,'sequence':sequence,'source_pointer_sha256':pointer_sha,'audit_receipts':refs,'provenance':provenance,
       'truth':{'checkpoint_does_not_replace_source_generation_pointer_validation':True,'checkpoint_only_preserves_receipt_recovery_roots':True}}
    c['checkpoint_sha256']=digest(c);return c
def validate_checkpoint(c:dict[str,Any]):
    if c.get('schema')!=CHECKPOINT:raise ValueError('checkpoint schema mismatch')
    body=dict(c);key=body.pop('checkpoint_sha256',None)
    if key!=digest(body):raise ValueError('checkpoint integrity mismatch')

def put_checkpoint(root:Path,c:dict[str,Any])->str:
    validate_checkpoint(c);root.joinpath('checkpoints').mkdir(parents=True,exist_ok=True);p=cpath(root,c['checkpoint_sha256'])
    if p.exists():
        if readj(p)!=c:raise ValueError('append-only checkpoint key collision')
    else:atomic(p,(json.dumps(c,indent=2,sort_keys=True)+'\n').encode())
    return c['checkpoint_sha256']
def load_checkpoint(root:Path,key:str)->dict[str,Any]:
    p=cpath(root,key)
    if not p.exists():raise ValueError('retained checkpoint body missing')
    c=readj(p);validate_checkpoint(c)
    if c['checkpoint_sha256']!=key:raise ValueError('checkpoint key/body mismatch')
    return c

def retention(ids:list[str],reason:str)->dict[str,Any]:
    roots=sorted(set(ids))
    if not roots or not all(sha(x) for x in roots):raise ValueError('invalid retention roots')
    m={'schema':RETENTION,'retained_checkpoints':roots,'reason':reason,'truth':{'retention_is_explicit_policy_state_not_inferred_from_receipt_presence':True}}
    m['retention_sha256']=digest(m);return m
def validate_retention(m:dict[str,Any]):
    if m.get('schema')!=RETENTION:raise ValueError('retention schema mismatch')
    b=dict(m);key=b.pop('retention_sha256',None)
    if key!=digest(b):raise ValueError('retention integrity mismatch')

def recover(root:Path,m:dict[str,Any])->dict[str,Any]:
    validate_retention(m);live={}
    for cid in m['retained_checkpoints']:
        c=load_checkpoint(root,cid)
        for contract,ref in c['audit_receipts'].items():
            r=load_receipt(root,ref['receipt_sha256'])
            if r['contract_id']!=contract or r['sequence']!=ref['sequence'] or r['predecessor_state_sha256']!=ref['predecessor_state_sha256']:raise ValueError('checkpoint/receipt semantic mismatch')
            live.setdefault(r['receipt_sha256'],[]).append({'checkpoint_sha256':cid,'contract_id':contract,'sequence':c['sequence']})
    return {'retention_sha256':m['retention_sha256'],'retained_checkpoint_count':len(m['retained_checkpoints']),'reachable_receipt_count':len(live),'reachable_receipts':live}
def keys(root:Path)->set[str]:return {p.stem for p in root.joinpath('receipts').glob('*.json')}
def candidates(root:Path,m:dict[str,Any])->set[str]:return keys(root)-set(recover(root,m)['reachable_receipts'])
def delete_if_unreachable(root:Path,m:dict[str,Any],key:str):
    if key in recover(root,m)['reachable_receipts']:raise ValueError('refusing to delete receipt reachable from retained checkpoint')
    p=rpath(root,key)
    if p.exists():p.unlink()
def fail(fn):
    try:fn()
    except Exception as e:return {'status':'PASS','detail':str(e)}
    return {'status':'FAIL','detail':'unexpected success'}

def wave79()->dict[str,Any]:
    return {'audit_cpu_ns':8543797,'audit_wall_ns':8543712,'bytes_read':11255808,'challenge_sha256':'50fc7dc88f497c3a555e5a67e0a542107ac6af596ebdfedfd828963f8d9fd8b0',
    'chunk_bytes':1048576,'chunks_read':11,'contract_id':'axm.execution-fabric.capability-index/v0.1','expected_artifact_bytes':11255808,
    'expected_artifact_sha256':'e676fafb2f825d946c10480ccd2184ab69daf9464ae77cf5703dfe59562644da','mode':AUDITED,
    'observed_artifact_sha256':'e676fafb2f825d946c10480ccd2184ab69daf9464ae77cf5703dfe59562644da',
    'predecessor_state_sha256':'58959e3053fe81c2686894296e542859a3a6d86a5591dfddde19110786bc7a01','proof_sha256':'0e90715689e43290371acc3d1608b58d179cd4c6e7bfc288b9bd41b718f353a2',
    'receipt_sha256':'fb65ba5ad5cc0f4c33a851957ccc42a4142c64a3d0815abb1a4f0886dbf4ecf2','schema':AUDIT,'sequence':1,'status':'AUDIT_PASS',
    'truth':{'cpu_time_is_not_joules':True,'receipt_created_after_full_local_byte_read':True,'receipt_digest_is_integrity_not_actor_authentication':True}}

def self_test()->dict[str,Any]:
    r1=wave79();validate_receipt(r1)
    with tempfile.TemporaryDirectory(prefix='axm-wave81-') as td:
        td=Path(td);root=td/'store';k1=put_receipt(root,r1)
        b=(json.dumps(r1,indent=2,sort_keys=True)+'\n').encode();p=td/'wave79.json';p.write_bytes(b)
        s2={'contract_id':'axm.compute-substrate.wave79-receipt-file/v0.1','state_sha256':digest({'source':'wave79-file'}),'proof_sha256':digest({'proof':'full-read'}),'artifact_sha256':hashlib.sha256(b).hexdigest(),'artifact_bytes':len(b)}
        r2=audit(p,s2,3,{'artifact_is_axm_evidence_file_not_monolith_workload':True});k2=put_receipt(root,r2)
        ob=b'wave81-unreferenced-control\n';op=td/'orphan';op.write_bytes(ob);so={'contract_id':'axm.compute-substrate.wave81-unreferenced-control/v0.1','state_sha256':digest({'s':'o'}),'proof_sha256':digest({'p':'o'}),'artifact_sha256':hashlib.sha256(ob).hexdigest(),'artifact_bytes':len(ob)}
        ro=audit(op,so,4,{'synthetic_control_artifact':True});ko=put_receipt(root,ro)
        c1=checkpoint('1b93525216e04d20e4b5556f8ada44aeefcbb8168b33c9d01c723dfcc6117c58',1,{r1['contract_id']:{'receipt_sha256':k1,'sequence':1,'predecessor_state_sha256':r1['predecessor_state_sha256']}},'exact Wave80 G1 + Wave79 receipt ref');i1=put_checkpoint(root,c1)
        cp=digest({'schema':'wave81-controlled-pointer','sequence':3,'receipt':k2});c3=checkpoint(cp,3,{r2['contract_id']:{'receipt_sha256':k2,'sequence':3,'predecessor_state_sha256':r2['predecessor_state_sha256']}},'controlled later audited generation; real full-byte AXM evidence-file audit');i3=put_checkpoint(root,c3)
        m=retention([i1,i3],'retain Wave80 rollback evidence + Wave81 later audited checkpoint');rec=recover(root,m);controls={}
        controls['real_wave79_receipt_recovers_after_restart']={'status':'PASS' if k1 in rec['reachable_receipts'] else 'FAIL','detail':k1}
        controls['second_full_byte_audit_receipt_recovers']={'status':'PASS' if k2 in rec['reachable_receipts'] else 'FAIL','detail':f'{k2}; bytes={len(b)}'}
        controls['unreferenced_receipt_presence_grants_no_authority']={'status':'PASS' if ko not in rec['reachable_receipts'] else 'FAIL','detail':f'stored={ko in keys(root)} reachable={ko in rec["reachable_receipts"]}'}
        controls['delete_reachable_wave79_receipt_blocked']=fail(lambda:delete_if_unreachable(root,m,k1))
        x=td/'missing';shutil.copytree(root,x);rpath(x,k1).unlink();controls['missing_reachable_receipt_after_restart_rejected']=fail(lambda:recover(x,m))
        x=td/'wrong';shutil.copytree(root,x);bad=dict(r1);bad['bytes_read']-=1;rpath(x,k1).write_text(json.dumps(bad));controls['wrong_body_under_correct_key_rejected']=fail(lambda:recover(x,m))
        x=td/'tamper';shutil.copytree(root,x);bad=readj(cpath(x,i1));bad['provenance']='tampered';cpath(x,i1).write_text(json.dumps(bad));controls['retained_checkpoint_tamper_rejected']=fail(lambda:recover(x,m))
        cb=candidates(root,m);delete_if_unreachable(root,m,ko);controls['gc_removes_only_provably_unreachable_receipt']={'status':'PASS' if cb=={ko} and recover(root,m)==rec else 'FAIL','detail':f'candidates={sorted(cb)}'}
        reduced=retention([i3],'explicit test-only rollback-root drop');cc=candidates(root,reduced);controls['explicit_root_drop_can_make_old_receipt_collectible']={'status':'PASS' if k1 in cc and k2 not in cc else 'FAIL','detail':f'collectible={sorted(cc)}'}
        samples=[]
        for _ in range(1000):t=time.process_time_ns();recover(root,m);samples.append(time.process_time_ns()-t)
        passed=sum(v['status']=='PASS' for v in controls.values())
        return {'schema':'axm.flowing-compute-receipt-store-wave81/v0.1','status':'PASS' if passed==len(controls) else 'FAIL','controls_passed':passed,'controls_total':len(controls),'controls':controls,
        'positive_case':{'retention_sha256':m['retention_sha256'],'retained_checkpoint_count':rec['retained_checkpoint_count'],'reachable_receipt_count':rec['reachable_receipt_count'],'real_wave79_monolith_receipt_sha256':k1,'second_audit_receipt_sha256':k2,'unreferenced_receipt_sha256':ko},
        'real_evidence_reused':{'wave79_receipt_sha256':k1,'wave79_contract_id':r1['contract_id'],'wave79_audited_monolith_artifact_bytes':r1['bytes_read'],'wave79_audited_monolith_artifact_sha256':r1['observed_artifact_sha256'],'wave80_g1_pointer_sha256':c1['source_pointer_sha256']},
        'second_audit':{'kind':'real local full-byte audit of fetched AXM Wave79 evidence-file text; not a monolith workload','artifact_bytes':len(b),'artifact_sha256':hashlib.sha256(b).hexdigest(),'receipt_sha256':k2},
        'benchmark':{'iterations':1000,'median_cpu_us':statistics.median(samples)/1000,'operation':'disk-backed recovery of 2 retained checkpoints + 2 reachable receipt bodies','includes_underlying_artifact_reread':False},
        'truth':{'receipt_store_integrity_is_not_actor_authentication':True,'receipt_presence_alone_grants_no_authority':True,'retention_manifest_is_explicit_policy_state':True,'wave79_receipt_is_real_prior_monolith_audit_evidence':True,'second_audit_is_axm_evidence_file_not_monolith_workload':True,'orphan_artifact_is_synthetic_control_only':True,'cpu_time_is_not_joules':True,'no_auto_merge':True},
        'next_gate':'Bind retention-manifest evolution to an append-only predecessor chain and require an explicit drop receipt before a rollback root can disappear; then test crash-safe mark/sweep GC against one exact retention generation.'}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--self-test',action='store_true');ap.add_argument('--out',type=Path);a=ap.parse_args()
    if not a.self_test:ap.error('use --self-test; store functions are importable')
    r=self_test();s=json.dumps(r,indent=2,sort_keys=True)+'\n';print(s,end='');
    if a.out:a.out.write_text(s)
    raise SystemExit(0 if r['status']=='PASS' else 1)
if __name__=='__main__':main()
