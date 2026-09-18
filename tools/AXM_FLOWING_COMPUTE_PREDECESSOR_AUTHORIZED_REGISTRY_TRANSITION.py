import argparse, hashlib, json, statistics, time
from copy import deepcopy

ROOTS=('truth','agency_non_domination','continuity','wisdom_before_speed')
WIT=('registry-witness-a','registry-witness-b','registry-witness-c')
ES='axm.flowing-compute-evaluator/v0.2'; RS='axm.flowing-compute-evaluator-registry/v0.2'
TS='axm.flowing-compute-evaluator-registry-transition/v0.2'; AS='axm.flowing-compute-evaluator-registry-transition-authorization/v0.2'
W91={'path':'tools/AXM_FLOWING_COMPUTE_CURRENT_REGISTRY_AUTHORITY.py','commit':'0e275b6ea43c6a8cfbd66266e210bcf93a9ecddb','blob_sha':'f378627bc2f8752fc8e20f73f0737c15f9e2ddff','file_sha256':'28b7da0d40b53f2ba9ec58161c0531530c2bfaa7e63eada4c5e7cd7eb27ad4f5','builder_head':'3b7ae7ce9751497666d8e85494ca72150c088882'}
V91={'pr':16,'head':'83c5a84d0286b8eadf4f5966e044606a23532fd5','path':'verification/WAVE91_ADVERSARIAL_VERIFICATION_2026-09-16.md','blob_sha':'8c0bd605c8f2be99c1d6c0b3f7b09ad988929ea6','finding':'FAIL_CURRENT_REGISTRY_KEY_BODY_IDENTITY_NOT_ENFORED'}
V90={'pr':15,'head':'5173a1d98a851f53b87b0012e43e43cd917a2006','path':'verification/WAVE90_ADVERSARIAL_VERIFICATION_2026-09-16.md','blob_sha':'882141599c09380d264578b643de027281165e7d','finding':'FAIL_REPLACEMENT_EVALUATOR_PREDECESSOR_NOT_ENFORCED'}

def can(v): return json.dumps(v,sort_keys=True,separators=(',',':')).encode()
def dg(v): return hashlib.sha256(can(v)).hexdigest()
def td(s): return hashlib.sha256(s.encode()).hexdigest()
def seal(v,f):
    x=deepcopy(v); x.pop(f,None); x[f]=dg(x); return x
def check(v,f):
    x=deepcopy(v); got=x.pop(f,None)
    if not isinstance(got,str) or len(got)!=64 or got!=dg(x): raise ValueError(f'{f} mismatch')
def sha(v,n='sha'):
    if not isinstance(v,str) or len(v)!=64 or any(c not in '0123456789abcdef' for c in v): raise ValueError(f'{n} invalid')
    return v
def put(s,o,f):
    check(o,f); k=o[f]
    if k in s and s[k]!=o: raise ValueError('content-address collision')
    s[k]=deepcopy(o); return k
def get(s,k,f,val=None):
    sha(k,'lookup key')
    if k not in s: raise ValueError(f'{f} body missing')
    o=deepcopy(s[k]); check(o,f)
    if o.get(f)!=k: raise ValueError(f'{f} store key/body mismatch')
    if val: val(o)
    return o

def ev(eid,roots,tool,source,label,pred=None):
    if pred is not None: sha(pred,'predecessor evaluator')
    return seal({'schema':ES,'evaluator_id':eid,'root_scope':sorted(set(roots)),'evaluation_tool_sha256':sha(tool),'evaluation_source_sha256':sha(source),'predecessor_evaluator_sha256':pred,'label':label,'test_only':True,'evaluator_sha256':''},'evaluator_sha256')
def val_ev(e):
    check(e,'evaluator_sha256')
    if e.get('schema')!=ES or not e.get('evaluator_id'): raise ValueError('evaluator schema/id')
    roots=e.get('root_scope');
    if not isinstance(roots,list) or not roots or roots!=sorted(set(roots)) or any(r not in ROOTS for r in roots): raise ValueError('evaluator scope')
    sha(e.get('evaluation_tool_sha256')); sha(e.get('evaluation_source_sha256'))
    if e.get('predecessor_evaluator_sha256') is not None: sha(e['predecessor_evaluator_sha256'])

def reg(gen,pred,entries,assign,kind,label):
    if gen==0 and pred is not None: raise ValueError('genesis predecessor')
    if gen>0: sha(pred,'registry predecessor')
    if set(assign)!=set(ROOTS) or any(assign[r] not in entries for r in ROOTS): raise ValueError('registry roots')
    return seal({'schema':RS,'generation':gen,'predecessor_registry_sha256':pred,'transition_kind':kind,'evaluator_entries':{k:sha(v) for k,v in sorted(entries.items())},'root_assignments':{r:assign[r] for r in ROOTS},'label':label,'wave91_source':W91,'test_only':True,'registry_sha256':''},'registry_sha256')
def val_reg(r):
    check(r,'registry_sha256')
    if r.get('schema')!=RS or set(r.get('root_assignments',{}))!=set(ROOTS): raise ValueError('registry body')
    if not isinstance(r.get('evaluator_entries'),dict) or not r['evaluator_entries']: raise ValueError('registry entries')
def rreg(k,RSs,ESs):
    r=get(RSs,k,'registry_sha256',val_reg)
    for eid,ek in r['evaluator_entries'].items():
        e=get(ESs,ek,'evaluator_sha256',val_ev)
        if e['evaluator_id']!=eid: raise ValueError('registry evaluator id/body mismatch')
    for root in ROOTS:
        eid=r['root_assignments'][root]; e=get(ESs,r['evaluator_entries'][eid],'evaluator_sha256',val_ev)
        if root not in e['root_scope']: raise ValueError('root outside evaluator scope')
    return r

def parts(a,b):
    A,B=set(a),set(b); add=sorted(B-A); rem=sorted(A-B); rep=sorted(i for i in A&B if a[i]!=b[i]); keep=sorted(i for i in A&B if a[i]==b[i])
    n=sum(bool(x) for x in (add,rem,rep)); kind='MIXED' if n>1 else ('ADD' if add else 'REMOVE' if rem else 'REPLACE' if rep else 'MIXED')
    return kind,add,rem,rep,keep
def trans(a,b):
    if b['generation']!=a['generation']+1 or b['predecessor_registry_sha256']!=a['registry_sha256']: raise ValueError('registry successor lineage')
    kind,add,rem,rep,keep=parts(a['evaluator_entries'],b['evaluator_entries'])
    if b['transition_kind']!=kind: raise ValueError('target transition kind mismatch')
    return seal({'schema':TS,'predecessor_generation':a['generation'],'predecessor_registry_sha256':a['registry_sha256'],'target_generation':b['generation'],'target_registry_sha256':b['registry_sha256'],'transition_kind':kind,'added_evaluator_ids':add,'removed_evaluator_ids':rem,'replaced_evaluator_ids':rep,'retained_evaluator_ids':keep,'old_root_assignments':a['root_assignments'],'target_root_assignments':b['root_assignments'],'transition_sha256':''},'transition_sha256')
def rtrans(k,TSs,RSs,ESs):
    t=get(TSs,k,'transition_sha256',lambda x: check(x,'transition_sha256'))
    a=rreg(t['predecessor_registry_sha256'],RSs,ESs); b=rreg(t['target_registry_sha256'],RSs,ESs)
    if t!=trans(a,b): raise ValueError('transition exact binding mismatch')
    for eid in t['replaced_evaluator_ids']:
        e=get(ESs,b['evaluator_entries'][eid],'evaluator_sha256',val_ev)
        if e.get('predecessor_evaluator_sha256')!=a['evaluator_entries'][eid]: raise ValueError('replacement evaluator predecessor mismatch')
    for eid in t['added_evaluator_ids']:
        e=get(ESs,b['evaluator_entries'][eid],'evaluator_sha256',val_ev)
        if e.get('predecessor_evaluator_sha256') is not None: raise ValueError('added evaluator predecessor mismatch')
    return t,a,b

def auth(t,a,ESs,verdict=None):
    verdict=verdict or {}; rows={}
    for root in ROOTS:
        eid=a['root_assignments'][root]; ek=a['evaluator_entries'][eid]; e=get(ESs,ek,'evaluator_sha256',val_ev)
        rows[root]={'root':root,'verdict':verdict.get(root,'PASS'),'authorizing_registry_sha256':a['registry_sha256'],'evaluator_id':eid,'evaluator_sha256':ek,'evaluation_tool_sha256':e['evaluation_tool_sha256'],'evaluation_source_sha256':e['evaluation_source_sha256']}
    return seal({'schema':AS,'transition_sha256':t['transition_sha256'],'predecessor_registry_sha256':t['predecessor_registry_sha256'],'target_registry_sha256':t['target_registry_sha256'],'transition_kind':t['transition_kind'],'added_evaluator_ids':t['added_evaluator_ids'],'removed_evaluator_ids':t['removed_evaluator_ids'],'replaced_evaluator_ids':t['replaced_evaluator_ids'],'retained_evaluator_ids':t['retained_evaluator_ids'],'authorizing_registry_sha256':a['registry_sha256'],'evaluations':rows,'test_only':True,'authorization_sha256':''},'authorization_sha256')
def rauth(ak,tk,ASs,TSs,RSs,ESs):
    a=get(ASs,ak,'authorization_sha256',lambda x: check(x,'authorization_sha256')); t,old,new=rtrans(tk,TSs,RSs,ESs)
    for f in ('transition_sha256','predecessor_registry_sha256','target_registry_sha256','transition_kind','added_evaluator_ids','removed_evaluator_ids','replaced_evaluator_ids','retained_evaluator_ids'):
        if a.get(f)!=t.get(f): raise ValueError(f'authorization {f} mismatch')
    if a.get('authorizing_registry_sha256')!=old['registry_sha256']: raise ValueError('authorization not issued by predecessor registry')
    if set(a.get('evaluations',{}))!=set(ROOTS): raise ValueError('four root evaluations required')
    for root in ROOTS:
        row=a['evaluations'][root]; eid=old['root_assignments'][root]; ek=old['evaluator_entries'][eid]; e=get(ESs,ek,'evaluator_sha256',val_ev)
        exp={'root':root,'authorizing_registry_sha256':old['registry_sha256'],'evaluator_id':eid,'evaluator_sha256':ek,'evaluation_tool_sha256':e['evaluation_tool_sha256'],'evaluation_source_sha256':e['evaluation_source_sha256']}
        if any(row.get(k)!=v for k,v in exp.items()): raise ValueError('evaluation binding mismatch')
        if row.get('verdict')!='PASS': raise ValueError('authorization root verdict does not allow transition')
    return a,t,old,new

def authority(rt,RSs,ESs):
    if set(rt['w'])!=set(WIT): return 'HOLD'
    if any(rt['w'][w]!=rt['cur'] for w in WIT): return 'HOLD'
    try: rreg(rt['cur'],RSs,ESs)
    except Exception: return 'HOLD'
    return 'AUTHORITATIVE'
def apply(rt,tk,ak,ESs,RSs,TSs,ASs,count=None):
    try: _,t,a,b=rauth(ak,tk,ASs,TSs,RSs,ESs)
    except Exception: return 'AUTH_OR_TRANSITION_HOLD'
    A,B=a['registry_sha256'],b['registry_sha256']
    if set(rt['w'])!=set(WIT): return 'WITNESS_SET_HOLD'
    if rt['cur']==B and all(rt['w'][w]==B for w in WIT): return 'CONSISTENT_TARGET'
    if rt['cur']!=A: return 'PREDECESSOR_HOLD'
    if any(rt['w'][w] not in (A,B) for w in WIT): return 'COMPETING_OR_UNKNOWN_HOLD'
    if all(rt['w'][w]==A for w in WIT) and authority(rt,RSs,ESs)!='AUTHORITATIVE': return 'CURRENT_AUTHORITY_HOLD'
    lag=[w for w in WIT if rt['w'][w]==A]; n=len(lag) if count is None else max(0,min(count,len(lag)))
    for w in lag[:n]: rt['w'][w]=B
    if any(rt['w'][w]!=B for w in WIT): return 'PARTIAL'
    rt['cur']=B; return 'COMMITTED'
def fails(fn,txt):
    try: fn()
    except Exception as e: return txt in str(e)
    return False

def fixture():
    E,R,T,A={},{},{},{}; tools={r:td('tool-'+r) for r in ROOTS}; src={r:td('src-'+r) for r in ROOTS}; ent={}; ass={}
    for root in ROOTS:
        eid='eval-'+root; x=ev(eid,[root],tools[root],src[root],root+' v1'); put(E,x,'evaluator_sha256'); ent[eid]=x['evaluator_sha256']; ass[root]=eid
    r0=reg(0,None,ent,ass,'GENESIS','current'); put(R,r0,'registry_sha256')
    v2=ev('eval-truth',['truth'],tools['truth'],td('truth-v2'),'truth v2',ent['eval-truth']); put(E,v2,'evaluator_sha256'); e1=dict(ent); e1['eval-truth']=v2['evaluator_sha256']
    r1=reg(1,r0['registry_sha256'],e1,ass,'REPLACE','target'); put(R,r1,'registry_sha256'); t1=trans(r0,r1); put(T,t1,'transition_sha256'); a1=auth(t1,r0,E); put(A,a1,'authorization_sha256')
    va=ev('eval-truth',['truth'],tools['truth'],td('truth-alt'),'truth alt',ent['eval-truth']); put(E,va,'evaluator_sha256'); ea=dict(ent); ea['eval-truth']=va['evaluator_sha256']; ra=reg(1,r0['registry_sha256'],ea,ass,'REPLACE','alt'); put(R,ra,'registry_sha256'); ta=trans(r0,ra); put(T,ta,'transition_sha256'); aa=auth(ta,r0,E); put(A,aa,'authorization_sha256')
    return E,R,T,A,{'r0':r0,'r1':r1,'t1':t1,'a1':a1,'alt':(ra,ta,aa),'truth0':ent['eval-truth'],'truth1':v2['evaluator_sha256']}

def run(rounds):
    E,R,T,A,x=fixture(); r0,r1,t1,a1=x['r0'],x['r1'],x['t1'],x['a1']; rt={'cur':r0['registry_sha256'],'w':{w:r0['registry_sha256'] for w in WIT}}; C=[]
    C += [('exact_wave91_tool_identity',W91['commit']=='0e275b6ea43c6a8cfbd66266e210bcf93a9ecddb' and W91['blob_sha']=='f378627bc2f8752fc8e20f73f0737c15f9e2ddff' and W91['file_sha256']=='28b7da0d40b53f2ba9ec58161c0531530c2bfaa7e63eada4c5e7cd7eb27ad4f5'),('exact_wave91_verifier_identity',V91['head']=='83c5a84d0286b8eadf4f5966e044606a23532fd5' and V91['blob_sha']=='8c0bd605c8f2be99c1d6c0b3f7b09ad988929ea6'),('exact_wave90_verifier_identity',V90['head']=='5173a1d98a851f53b87b0012e43e43cd917a2006' and V90['blob_sha']=='882141599c09380d264578b643de027281165e7d'),('stable_current_authoritative',authority(rt,R,E)=='AUTHORITATIVE'),('predecessor_authorization_valid',rauth(a1['authorization_sha256'],t1['transition_sha256'],A,T,R,E)[0]['authorization_sha256']==a1['authorization_sha256'])]
    badR=deepcopy(R); badR[r0['registry_sha256']]=deepcopy(r1); C.append(('registry_key_body_substitution_holds',authority(rt,badR,E)=='HOLD'))
    badE=deepcopy(E); badE[x['truth0']]=deepcopy(E[x['truth1']]); C.append(('evaluator_key_body_substitution_rejected',fails(lambda:rreg(r0['registry_sha256'],R,badE),'store key/body mismatch')))
    missE=deepcopy(E); missE.pop(x['truth0']); C.append(('missing_evaluator_body_rejected',fails(lambda:rreg(r0['registry_sha256'],R,missE),'body missing')))
    bm=ev('eval-truth',['truth'],td('tool-truth'),td('bad'),'bad missing'); put(E,bm,'evaluator_sha256'); em=dict(r0['evaluator_entries']); em['eval-truth']=bm['evaluator_sha256']; rm=reg(1,r0['registry_sha256'],em,r0['root_assignments'],'REPLACE','bad'); put(R,rm,'registry_sha256'); tm=trans(r0,rm); put(T,tm,'transition_sha256'); C.append(('replacement_missing_predecessor_rejected',fails(lambda:rtrans(tm['transition_sha256'],T,R,E),'replacement evaluator predecessor mismatch')))
    hist=ev('hist-truth',['truth'],td('hist-tool'),td('hist-src'),'historical'); put(E,hist,'evaluator_sha256'); bw=ev('eval-truth',['truth'],td('tool-truth'),td('bad2'),'bad wrong',hist['evaluator_sha256']); put(E,bw,'evaluator_sha256'); ew=dict(r0['evaluator_entries']); ew['eval-truth']=bw['evaluator_sha256']; rw=reg(1,r0['registry_sha256'],ew,r0['root_assignments'],'REPLACE','bad wrong'); put(R,rw,'registry_sha256'); tw=trans(r0,rw); put(T,tw,'transition_sha256'); C.append(('replacement_wrong_historical_predecessor_rejected',fails(lambda:rtrans(tw['transition_sha256'],T,R,E),'replacement evaluator predecessor mismatch')))
    hold=auth(t1,r0,E,{'continuity':'HOLD'}); put(A,hold,'authorization_sha256'); C += [('root_hold_blocks_transition',apply(deepcopy(rt),t1['transition_sha256'],hold['authorization_sha256'],E,R,T,A)=='AUTH_OR_TRANSITION_HOLD'),('missing_authorization_blocks_transition',apply(deepcopy(rt),t1['transition_sha256'],'0'*64,E,R,T,A)=='AUTH_OR_TRANSITION_HOLD')]
    targ=auth(t1,r1,E); put(A,targ,'authorization_sha256'); C.append(('target_cannot_authorize_own_admission',apply(deepcopy(rt),t1['transition_sha256'],targ['authorization_sha256'],E,R,T,A)=='AUTH_OR_TRANSITION_HOLD'))
    p=deepcopy(rt); C.append(('authorized_partial_fanout_created',apply(p,t1['transition_sha256'],a1['authorization_sha256'],E,R,T,A,1)=='PARTIAL')); C += [('partial_state_has_no_current_authority',authority(p,R,E)=='HOLD'),('partial_recovery_without_exact_auth_holds',apply(deepcopy(p),t1['transition_sha256'],'0'*64,E,R,T,A)=='AUTH_OR_TRANSITION_HOLD')]
    ra_,ta,aa=x['alt']; C.append(('competing_transition_cannot_take_over_partial',apply(deepcopy(p),ta['transition_sha256'],aa['authorization_sha256'],E,R,T,A)=='COMPETING_OR_UNKNOWN_HOLD')); C.append(('partial_recovery_with_exact_auth_commits',apply(p,t1['transition_sha256'],a1['authorization_sha256'],E,R,T,A)=='COMMITTED')); C += [('target_authoritative_after_commit',authority(p,R,E)=='AUTHORITATIVE'),('old_auth_not_reusable_for_competing_transition',apply(deepcopy(p),ta['transition_sha256'],a1['authorization_sha256'],E,R,T,A)=='AUTH_OR_TRANSITION_HOLD')]
    v3=ev('eval-truth',['truth'],E[x['truth0']]['evaluation_tool_sha256'],E[x['truth0']]['evaluation_source_sha256'],'rollback semantics',x['truth1']); put(E,v3,'evaluator_sha256'); e2=dict(r1['evaluator_entries']); e2['eval-truth']=v3['evaluator_sha256']; r2=reg(2,r1['registry_sha256'],e2,r1['root_assignments'],'REPLACE','rollback forward'); put(R,r2,'registry_sha256'); t2=trans(r1,r2); put(T,t2,'transition_sha256'); a2=auth(t2,r1,E); put(A,a2,'authorization_sha256'); C += [('rollback_new_registry_identity',r2['registry_sha256'] not in (r0['registry_sha256'],r1['registry_sha256'])),('rollback_new_evaluator_identity',v3['evaluator_sha256']!=x['truth0']),('rollback_authorized_by_current_predecessor_commits',apply(p,t2['transition_sha256'],a2['authorization_sha256'],E,R,T,A)=='COMMITTED'),('rollback_target_authoritative',authority(p,R,E)=='AUTHORITATIVE')]
    ne=dict(e2); na=dict(r2['root_assignments'])
    for root in ROOTS:
        old=na[root]; new='new-'+root; z=ev(new,[root],td('new-tool-'+root),td('new-src-'+root),'arbitrary new'); put(E,z,'evaluator_sha256'); ne.pop(old); ne[new]=z['evaluator_sha256']; na[root]=new
    r3=reg(3,r2['registry_sha256'],ne,na,'MIXED','boundary arbitrary set'); put(R,r3,'registry_sha256'); t3=trans(r2,r3); put(T,t3,'transition_sha256'); a3=auth(t3,r2,E); put(A,a3,'authorization_sha256'); C.append(('counterexample_predecessor_pass_can_mechanically_admit_arbitrary_new_evaluators',apply(deepcopy(p),t3['transition_sha256'],a3['authorization_sha256'],E,R,T,A)=='COMMITTED'))
    b={'cur':r0['registry_sha256'],'w':{w:r0['registry_sha256'] for w in WIT}}; sm=[]
    for _ in range(rounds):
        q=time.process_time_ns(); authority(b,R,E); rauth(a1['authorization_sha256'],t1['transition_sha256'],A,T,R,E); sm.append((time.process_time_ns()-q)/1000)
    fail=[n for n,ok in C if not ok]; return {'status':'PASS' if not fail else 'FAIL','passed_checks':sum(ok for _,ok in C),'total_checks':len(C),'failed_checks':fail,'checks':[{'name':n,'pass':ok} for n,ok in C],'synthetic_single_host_transition_authorization_cpu_us_median':statistics.median(sm),'benchmark_rounds':rounds}

def selftest(rounds=120):
    a,b=run(rounds),run(rounds); same=[x['name'] for x in a['checks']]==[x['name'] for x in b['checks']]
    return {'schema':'axm.flowing-compute-wave92-predecessor-authorized-registry-transition/v0.1','status':'PASS' if a['status']==b['status']=='PASS' and same else 'FAIL','source_provenance':{'wave91_tool':W91,'wave91_verifier':V91,'wave90_verifier':V90},'independent_check_name_match':same,'independent_runs':[{k:r[k] for k in ('status','passed_checks','total_checks','benchmark_rounds','synthetic_single_host_transition_authorization_cpu_us_median')} for r in (a,b)],'checks':a['checks'],'failed_checks':sorted(set(a['failed_checks']+b['failed_checks'])),'closed_counterexamples':['Wave91 registry lookup key/body substitution rejected before authority use.','Evaluator lookup key/body substitution rejected by the same resolver.','Wave90 replacement evaluator must descend from the exact replaced evaluator body.','Target/new registry cannot authorize its own admission; the exact current predecessor registry authorizes the transition.','Partial fan-out resumes only with the exact predecessor authorization and transition; competing transition holds.'],'counterexample':'Predecessor-bound PASS remains mechanical provenance, not moral/canonical legitimacy. A currently authoritative predecessor registry can still structurally PASS an arbitrary new evaluator set.','measurement_note':'Synthetic single-host content-addressed registry/evaluator transition authorization bookkeeping; process CPU only, not storage/network latency or energy.','truth_boundary':{'fresh_monolith_audit':False,'compute_efficiency_claim':False,'retained_incremental_dormant_win_claim':False,'energy_claim':False,'distributed_consensus_claim':False,'canonical_root_judgment_claim':False,'moral_evaluator_legitimacy_proven':False,'automatic_merge':False,'synthetic_scaling':False,'note':'Infrastructure semantics only; no AXM workload timing or scaling claim.'}}
if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--rounds',type=int,default=120); p.add_argument('--output'); z=p.parse_args(); r=selftest(z.rounds); s=json.dumps(r,indent=2,sort_keys=True); print(s); open(z.output,'w').write(s+'\n') if z.output else None; raise SystemExit(0 if r['status']=='PASS' else 1)
