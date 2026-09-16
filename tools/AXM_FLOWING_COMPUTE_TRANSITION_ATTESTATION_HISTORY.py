import argparse, hashlib, importlib.util, json, statistics, time
from copy import deepcopy
from pathlib import Path

ROOTS=('truth','agency_non_domination','continuity','wisdom_before_speed')
WIT=('registry-witness-a','registry-witness-b','registry-witness-c')
HS='axm.flowing-compute-evaluator-id-history/v0.1'; ATS='axm.flowing-compute-root-attestation/v0.1'
SS='axm.flowing-compute-attestation-state/v0.1'; AUS='axm.flowing-compute-attested-transition-authorization/v0.1'
W92={'path':'tools/AXM_FLOWING_COMPUTE_PREDECESSOR_AUTHORIZED_REGISTRY_TRANSITION.py','commit':'d06988d200315ec8824e18aa31baadf8c1bf7114','blob_sha':'82904139cb532245f241f0bdafaf2ea89cac529c','file_sha256':'4d0e73f86086bda5341f9153e2713ac6d65ba82dc2f163e8ba1f8507539bd320','builder_head':'f94d563fe5339316e3362bccf988e83c950f161d'}
V92={'pr':17,'head':'b59bd5e9d58250f204d81a4ae93a74d1aa597a9d','path':'verification/WAVE92_ADVERSARIAL_VERIFICATION_2026-09-16.md','blob_sha':'d06a64dced1c30a7278491a1e0f7847248a8300a','finding':'FAIL_REMOVED_EVALUATOR_IDENTITY_CAN_BE_RESURRECTED_AS_ADD','workflow_run':35120821858}

def load_w92():
    p=Path(__file__).with_name('AXM_FLOWING_COMPUTE_PREDECESSOR_AUTHORIZED_REGISTRY_TRANSITION.py')
    if not p.exists(): p=Path(__file__).parent/'tools'/'AXM_FLOWING_COMPUTE_PREDECESSOR_AUTHORIZED_REGISTRY_TRANSITION.py'
    if not p.exists(): raise FileNotFoundError('Wave92 tool missing beside this tool or under tools/')
    if hashlib.sha256(p.read_bytes()).hexdigest()!=W92['file_sha256']: raise ValueError('Wave92 file SHA-256 mismatch')
    s=importlib.util.spec_from_file_location('axm_wave92',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
W=load_w92()

def seal(v,f): return W.seal(v,f)
def check(v,f): return W.check(v,f)
def put(s,o,f): return W.put(s,o,f)
def get(s,k,f,val=None): return W.get(s,k,f,val)
def td(s): return W.td(s)

def hist0(r):
    ids=sorted(r['evaluator_entries'])
    return seal({'schema':HS,'generation':r['generation'],'registry_sha256':r['registry_sha256'],'predecessor_history_sha256':None,'seen_evaluator_ids':ids,'retired_evaluator_ids':[],'history_sha256':''},'history_sha256')
def val_hist(h):
    check(h,'history_sha256')
    if h.get('schema')!=HS or not isinstance(h.get('generation'),int): raise ValueError('history schema')
    W.sha(h.get('registry_sha256'),'history registry')
    seen=h.get('seen_evaluator_ids'); retired=h.get('retired_evaluator_ids')
    if not isinstance(seen,list) or seen!=sorted(set(seen)) or not isinstance(retired,list) or retired!=sorted(set(retired)) or not set(retired)<=set(seen): raise ValueError('history sets')
    if h['generation']==0 and h.get('predecessor_history_sha256') is not None: raise ValueError('genesis history predecessor')
    if h['generation']>0: W.sha(h.get('predecessor_history_sha256'),'history predecessor')
def hist_step(old,t):
    val_hist(old)
    if old['registry_sha256']!=t['predecessor_registry_sha256'] or old['generation']!=t['predecessor_generation']: raise ValueError('history predecessor registry mismatch')
    seen=set(old['seen_evaluator_ids']); retired=set(old['retired_evaluator_ids'])
    for eid in t['added_evaluator_ids']:
        if eid in seen: raise ValueError('historical evaluator id resurrection forbidden')
        seen.add(eid)
    retired.update(t['removed_evaluator_ids'])
    if any(eid in retired for eid in t['retained_evaluator_ids']+t['replaced_evaluator_ids']): raise ValueError('retired evaluator active')
    return seal({'schema':HS,'generation':t['target_generation'],'registry_sha256':t['target_registry_sha256'],'predecessor_history_sha256':old['history_sha256'],'seen_evaluator_ids':sorted(seen),'retired_evaluator_ids':sorted(retired),'history_sha256':''},'history_sha256')

def state0(r):
    return seal({'schema':SS,'generation':r['generation'],'registry_sha256':r['registry_sha256'],'predecessor_attestation_state_sha256':None,'heads':{eid:{'sequence':0,'last_attestation_sha256':None} for eid in sorted(r['evaluator_entries'])},'attestation_state_sha256':''},'attestation_state_sha256')
def val_state(s):
    check(s,'attestation_state_sha256')
    if s.get('schema')!=SS or not isinstance(s.get('generation'),int): raise ValueError('attestation state')
    W.sha(s.get('registry_sha256'),'attestation state registry')
    if s['generation']>0: W.sha(s.get('predecessor_attestation_state_sha256'),'state predecessor')
    for h in s.get('heads',{}).values():
        if not isinstance(h.get('sequence'),int) or h['sequence']<0: raise ValueError('attestation sequence')
        if h.get('last_attestation_sha256') is not None: W.sha(h['last_attestation_sha256'],'attestation predecessor')
def att(t,r,root,e,seq,prev,verdict='PASS',note=''):
    return seal({'schema':ATS,'transition_sha256':t['transition_sha256'],'predecessor_registry_sha256':r['registry_sha256'],'predecessor_registry_generation':r['generation'],'root':root,'verdict':verdict,'evaluator_id':e['evaluator_id'],'evaluator_sha256':e['evaluator_sha256'],'evaluation_tool_sha256':e['evaluation_tool_sha256'],'evaluation_source_sha256':e['evaluation_source_sha256'],'evaluator_sequence':seq,'previous_attestation_sha256':prev,'note':note,'test_only':True,'attestation_sha256':''},'attestation_sha256')
def competing(store,a):
    for x in store.values():
        try: check(x,'attestation_sha256')
        except Exception: continue
        if x['attestation_sha256']==a['attestation_sha256']: continue
        if x.get('evaluator_id')==a.get('evaluator_id') and x.get('evaluator_sequence')==a.get('evaluator_sequence') and x.get('previous_attestation_sha256')==a.get('previous_attestation_sha256'): return True
    return False

def derive_state(pred,mapping,t,r,E,AT):
    val_state(pred); heads=deepcopy(pred['heads'])
    if pred['generation']!=r['generation'] or pred['registry_sha256']!=r['registry_sha256']: raise ValueError('state registry mismatch')
    for root in ROOTS:
        if root not in mapping: raise ValueError('four root attestations required')
        a=get(AT,mapping[root],'attestation_sha256',lambda x:check(x,'attestation_sha256'))
        if competing(AT,a): raise ValueError('competing same-sequence attestation')
        eid=r['root_assignments'][root]; ek=r['evaluator_entries'][eid]; e=get(E,ek,'evaluator_sha256',W.val_ev); h=heads[eid]
        exp={'transition_sha256':t['transition_sha256'],'predecessor_registry_sha256':r['registry_sha256'],'predecessor_registry_generation':r['generation'],'root':root,'evaluator_id':eid,'evaluator_sha256':ek,'evaluation_tool_sha256':e['evaluation_tool_sha256'],'evaluation_source_sha256':e['evaluation_source_sha256'],'evaluator_sequence':h['sequence']+1,'previous_attestation_sha256':h['last_attestation_sha256']}
        if any(a.get(k)!=v for k,v in exp.items()): raise ValueError('attestation exact binding mismatch')
        if a.get('verdict')!='PASS': raise ValueError('attestation verdict blocks transition')
        heads[eid]={'sequence':a['evaluator_sequence'],'last_attestation_sha256':a['attestation_sha256']}
    for eid in t['added_evaluator_ids']:
        heads.setdefault(eid,{'sequence':0,'last_attestation_sha256':None})
    return seal({'schema':SS,'generation':t['target_generation'],'registry_sha256':t['target_registry_sha256'],'predecessor_attestation_state_sha256':pred['attestation_state_sha256'],'heads':{k:heads[k] for k in sorted(heads)},'attestation_state_sha256':''},'attestation_state_sha256')
def make_auth(t,r,pred,E,AT,S,verdict=None):
    verdict=verdict or {}; heads=deepcopy(pred['heads']); m={}
    for root in ROOTS:
        eid=r['root_assignments'][root]; e=get(E,r['evaluator_entries'][eid],'evaluator_sha256',W.val_ev); h=heads[eid]
        a=att(t,r,root,e,h['sequence']+1,h['last_attestation_sha256'],verdict.get(root,'PASS')); put(AT,a,'attestation_sha256'); m[root]=a['attestation_sha256']; heads[eid]={'sequence':a['evaluator_sequence'],'last_attestation_sha256':a['attestation_sha256']}
    target=derive_state(pred,m,t,r,E,AT); put(S,target,'attestation_state_sha256')
    au=seal({'schema':AUS,'transition_sha256':t['transition_sha256'],'predecessor_registry_sha256':r['registry_sha256'],'target_registry_sha256':t['target_registry_sha256'],'predecessor_attestation_state_sha256':pred['attestation_state_sha256'],'target_attestation_state_sha256':target['attestation_state_sha256'],'attestation_sha256_by_root':m,'test_only':True,'authorization_sha256':''},'authorization_sha256')
    return au,target,m

def validate(ak,tk,hk,AU,T,R,E,H,AT,S):
    au=get(AU,ak,'authorization_sha256',lambda x:check(x,'authorization_sha256')); t,old,new=W.rtrans(tk,T,R,E); h=get(H,hk,'history_sha256',val_hist)
    if h['generation']!=old['generation']: raise ValueError('history registry generation mismatch')
    th=hist_step(h,t); target_h=get(H,au.get('target_history_sha256'),'history_sha256',val_hist)
    if th!=target_h: raise ValueError('target history mismatch')
    if au.get('transition_sha256')!=t['transition_sha256'] or au.get('predecessor_registry_sha256')!=old['registry_sha256'] or au.get('target_registry_sha256')!=new['registry_sha256']: raise ValueError('authorization transition mismatch')
    ps=get(S,au.get('predecessor_attestation_state_sha256'),'attestation_state_sha256',val_state); ts=derive_state(ps,au.get('attestation_sha256_by_root',{}),t,old,E,AT); stored=get(S,au.get('target_attestation_state_sha256'),'attestation_state_sha256',val_state)
    if ts!=stored: raise ValueError('target attestation state mismatch')
    return au,t,old,new,target_h,ps,stored

def bind_history(au,target_h):
    x=deepcopy(au); x['target_history_sha256']=target_h['history_sha256']; return seal(x,'authorization_sha256')
def authority(rt,R,E,H,S):
    if set(rt['w'])!=set(WIT): return 'HOLD'
    p=(rt['registry'],rt['history'],rt['state'])
    if any(tuple(rt['w'][w])!=p for w in WIT): return 'HOLD'
    try:
        r=W.rreg(rt['registry'],R,E); h=get(H,rt['history'],'history_sha256',val_hist); s=get(S,rt['state'],'attestation_state_sha256',val_state)
        if not (r['generation']==h['generation']==s['generation']): return 'HOLD'
        if not (r['registry_sha256']==h['registry_sha256']==s['registry_sha256']): return 'HOLD'
        if any(eid not in h['seen_evaluator_ids'] for eid in r['evaluator_entries']): return 'HOLD'
        if any(eid in h['retired_evaluator_ids'] for eid in r['evaluator_entries']): return 'HOLD'
    except Exception: return 'HOLD'
    return 'AUTHORITATIVE'
def apply(rt,tk,hk,ak,stores,count=None):
    E,R,T,H,AT,S,AU=stores
    try: _,_,old,new,th,ps,ts=validate(ak,tk,hk,AU,T,R,E,H,AT,S)
    except Exception: return 'AUTH_OR_TRANSITION_HOLD'
    a=(old['registry_sha256'],hk,ps['attestation_state_sha256']); b=(new['registry_sha256'],th['history_sha256'],ts['attestation_state_sha256'])
    if set(rt['w'])!=set(WIT): return 'WITNESS_SET_HOLD'
    if (rt['registry'],rt['history'],rt['state'])==b and all(tuple(rt['w'][w])==b for w in WIT): return 'CONSISTENT_TARGET'
    if (rt['registry'],rt['history'],rt['state'])!=a: return 'PREDECESSOR_HOLD'
    if any(tuple(rt['w'][w]) not in (a,b) for w in WIT): return 'COMPETING_OR_UNKNOWN_HOLD'
    lag=[w for w in WIT if tuple(rt['w'][w])==a]; n=len(lag) if count is None else max(0,min(count,len(lag)))
    for w in lag[:n]: rt['w'][w]=list(b)
    if any(tuple(rt['w'][w])!=b for w in WIT): return 'PARTIAL'
    rt['registry'],rt['history'],rt['state']=b; return 'COMMITTED'
def fails(fn,txt):
    try: fn()
    except Exception as e: return txt in str(e)
    return False

def fixture():
    E,R,T,H,AT,S,AU={},{},{},{},{},{},{}; tools={r:td('tool-'+r) for r in ROOTS}; src={r:td('src-'+r) for r in ROOTS}; ent={}; ass={}
    for root in ROOTS:
        eid='eval-'+root; e=W.ev(eid,[root],tools[root],src[root],root+' v1'); put(E,e,'evaluator_sha256'); ent[eid]=e['evaluator_sha256']; ass[root]=eid
    r0=W.reg(0,None,ent,ass,'GENESIS','current'); put(R,r0,'registry_sha256'); h0=hist0(r0); put(H,h0,'history_sha256'); s0=state0(r0); put(S,s0,'attestation_state_sha256')
    rt={'registry':r0['registry_sha256'],'history':h0['history_sha256'],'state':s0['attestation_state_sha256'],'w':{w:[r0['registry_sha256'],h0['history_sha256'],s0['attestation_state_sha256']] for w in WIT}}
    return (E,R,T,H,AT,S,AU),{'r0':r0,'h0':h0,'s0':s0,'rt':rt,'tools':tools,'src':src,'truth0':ent['eval-truth']}
def successor(stores,old,entries,ass,kind,label):
    E,R,T,H,_,_,_=stores; r=W.reg(old['generation']+1,old['registry_sha256'],entries,ass,kind,label); put(R,r,'registry_sha256'); t=W.trans(old,r); put(T,t,'transition_sha256'); return r,t
def auth_with_history(stores,t,old,h,s,verdict=None):
    E,_,_,H,AT,S,AU=stores; th=hist_step(h,t); put(H,th,'history_sha256'); au,ts,m=make_auth(t,old,s,E,AT,S,verdict); au=bind_history(au,th); put(AU,au,'authorization_sha256'); return au,th,ts,m

def run(rounds):
    stores,x=fixture(); E,R,T,H,AT,S,AU=stores; r0,h0,s0=x['r0'],x['h0'],x['s0']; rt=deepcopy(x['rt']); C=[]
    C += [('wave92_exact_source',W92['builder_head']=='f94d563fe5339316e3362bccf988e83c950f161d'),('wave92_verifier_exact_source',V92['head']=='b59bd5e9d58250f204d81a4ae93a74d1aa597a9d' and V92['blob_sha']=='d06a64dced1c30a7278491a1e0f7847248a8300a'),('genesis_authoritative',authority(rt,R,E,H,S)=='AUTHORITATIVE')]
    fakeh=deepcopy(h0); fakeh['registry_sha256']='0'*64; fakeh=seal(fakeh,'history_sha256'); Hx=deepcopy(H); put(Hx,fakeh,'history_sha256'); rx=deepcopy(rt); rx['history']=fakeh['history_sha256']; rx['w']={w:[rx['registry'],rx['history'],rx['state']] for w in WIT}; C.append(('history_registry_cross_binding_holds',authority(rx,R,E,Hx,S)=='HOLD'))
    bridge=W.ev('eval-truth-bridge',['truth'],td('bridge-tool'),td('bridge-src'),'bridge'); put(E,bridge,'evaluator_sha256'); e1=dict(r0['evaluator_entries']); a1=dict(r0['root_assignments']); e1.pop('eval-truth'); e1['eval-truth-bridge']=bridge['evaluator_sha256']; a1['truth']='eval-truth-bridge'; r1,t1=successor(stores,r0,e1,a1,'MIXED','bridge'); au1,h1,s1,m1=auth_with_history(stores,t1,r0,h0,s0)
    C += [('attested_transition_valid',validate(au1['authorization_sha256'],t1['transition_sha256'],h0['history_sha256'],AU,T,R,E,H,AT,S)[0]['authorization_sha256']==au1['authorization_sha256']),('bridge_commit',apply(rt,t1['transition_sha256'],h0['history_sha256'],au1['authorization_sha256'],stores)=='COMMITTED'),('bridge_authoritative',authority(rt,R,E,H,S)=='AUTHORITATIVE'),('removed_id_tombstoned','eval-truth' in h1['retired_evaluator_ids']),('truth_sequence_recorded',s1['heads']['eval-truth']['sequence']==1)]
    oldres=dict(r1['evaluator_entries']); oldres.pop('eval-truth-bridge'); oldres['eval-truth']=x['truth0']; rr,tr=successor(stores,r1,oldres,{**r1['root_assignments'],'truth':'eval-truth'},'MIXED','old resurrection'); C.append(('exact_old_identity_resurrection_rejected',fails(lambda:hist_step(h1,tr),'historical evaluator id resurrection forbidden')))
    fresh=W.ev('eval-truth',['truth'],x['tools']['truth'],td('fresh'),'fresh'); put(E,fresh,'evaluator_sha256'); fr=dict(r1['evaluator_entries']); fr.pop('eval-truth-bridge'); fr['eval-truth']=fresh['evaluator_sha256']; rf,tf=successor(stores,r1,fr,{**r1['root_assignments'],'truth':'eval-truth'},'MIXED','fresh resurrection'); C.append(('fresh_same_id_resurrection_rejected',fails(lambda:hist_step(h1,tf),'historical evaluator id resurrection forbidden')))
    cid=r1['root_assignments']['continuity']; cold=r1['evaluator_entries'][cid]; ce=get(E,cold,'evaluator_sha256',W.val_ev); c2=W.ev(cid,['continuity'],ce['evaluation_tool_sha256'],td('continuity-v2'),'continuity v2',cold); put(E,c2,'evaluator_sha256'); e2=dict(r1['evaluator_entries']); e2[cid]=c2['evaluator_sha256']; r2,t2=successor(stores,r1,e2,r1['root_assignments'],'REPLACE','continuous replace'); au2,h2,s2,m2=auth_with_history(stores,t2,r1,h1,s1)
    C += [('continuous_replace_valid',validate(au2['authorization_sha256'],t2['transition_sha256'],h1['history_sha256'],AU,T,R,E,H,AT,S)[0]['authorization_sha256']==au2['authorization_sha256']),('continuous_replace_commits',apply(rt,t2['transition_sha256'],h1['history_sha256'],au2['authorization_sha256'],stores)=='COMMITTED'),('bridge_sequence_starts_at_one_after_admission',s2['heads']['eval-truth-bridge']['sequence']==1)]
    replay=deepcopy(au2); replay['attestation_sha256_by_root']['truth']=m1['truth']; replay=seal(replay,'authorization_sha256'); AUr=deepcopy(AU); put(AUr,replay,'authorization_sha256'); C.append(('stale_replay_rejected',fails(lambda:validate(replay['authorization_sha256'],t2['transition_sha256'],h1['history_sha256'],AUr,T,R,E,H,AT,S),'attestation exact binding mismatch')))
    truth2=get(AT,m2['truth'],'attestation_sha256'); comp=deepcopy(truth2); comp['note']='competing'; comp=seal(comp,'attestation_sha256'); ATc=deepcopy(AT); put(ATc,comp,'attestation_sha256'); C.append(('same_sequence_competition_holds',fails(lambda:validate(au2['authorization_sha256'],t2['transition_sha256'],h1['history_sha256'],AU,T,R,E,H,ATc,S),'competing same-sequence attestation')))
    copy=deepcopy(au2); copy['attestation_sha256_by_root']['continuity']=copy['attestation_sha256_by_root']['truth']; copy=seal(copy,'authorization_sha256'); AUc=deepcopy(AU); put(AUc,copy,'authorization_sha256'); C.append(('cross_root_copy_rejected',fails(lambda:validate(copy['authorization_sha256'],t2['transition_sha256'],h1['history_sha256'],AUc,T,R,E,H,AT,S),'attestation exact binding mismatch')))
    bad=deepcopy(truth2); bad['evaluation_tool_sha256']=td('wrong-tool'); bad=seal(bad,'attestation_sha256'); ATb=deepcopy(AT); ATb.pop(m2['truth']); put(ATb,bad,'attestation_sha256'); aub=deepcopy(au2); aub['attestation_sha256_by_root']['truth']=bad['attestation_sha256']; aub=seal(aub,'authorization_sha256'); AUb=deepcopy(AU); put(AUb,aub,'authorization_sha256'); C.append(('tool_substitution_rejected',fails(lambda:validate(aub['authorization_sha256'],t2['transition_sha256'],h1['history_sha256'],AUb,T,R,E,H,ATb,S),'attestation exact binding mismatch')))
    hold=deepcopy(truth2); hold['verdict']='HOLD'; hold=seal(hold,'attestation_sha256'); ATh=deepcopy(AT); ATh.pop(m2['truth']); put(ATh,hold,'attestation_sha256'); auh=deepcopy(au2); auh['attestation_sha256_by_root']['truth']=hold['attestation_sha256']; auh=seal(auh,'authorization_sha256'); AUh=deepcopy(AU); put(AUh,auh,'authorization_sha256'); C.append(('hold_verdict_blocks',fails(lambda:validate(auh['authorization_sha256'],t2['transition_sha256'],h1['history_sha256'],AUh,T,R,E,H,ATh,S),'verdict blocks transition')))
    miss=deepcopy(AT); miss.pop(m2['truth']); C.append(('missing_attestation_rejected',fails(lambda:validate(au2['authorization_sha256'],t2['transition_sha256'],h1['history_sha256'],AU,T,R,E,H,miss,S),'body missing')))
    part={'registry':r1['registry_sha256'],'history':h1['history_sha256'],'state':s1['attestation_state_sha256'],'w':{w:[r1['registry_sha256'],h1['history_sha256'],s1['attestation_state_sha256']] for w in WIT}}; C += [('partial_created',apply(part,t2['transition_sha256'],h1['history_sha256'],au2['authorization_sha256'],stores,1)=='PARTIAL'),('partial_not_authoritative',authority(part,R,E,H,S)=='HOLD'),('partial_exact_recovery_commits',apply(part,t2['transition_sha256'],h1['history_sha256'],au2['authorization_sha256'],stores)=='COMMITTED')]
    arb=W.ev('eval-arbitrary',['truth'],td('arb-tool'),td('arb-src'),'arbitrary'); put(E,arb,'evaluator_sha256'); e3=dict(r2['evaluator_entries']); oldtruth=r2['root_assignments']['truth']; e3.pop(oldtruth); e3['eval-arbitrary']=arb['evaluator_sha256']; a3={**r2['root_assignments'],'truth':'eval-arbitrary'}; r3,t3=successor(stores,r2,e3,a3,'MIXED','boundary'); au3,h3,s3,m3=auth_with_history(stores,t3,r2,h2,s2); br={'registry':r2['registry_sha256'],'history':h2['history_sha256'],'state':s2['attestation_state_sha256'],'w':{w:[r2['registry_sha256'],h2['history_sha256'],s2['attestation_state_sha256']] for w in WIT}}; C.append(('counterexample_mechanical_pass_still_admits_arbitrary_new_evaluator',apply(br,t3['transition_sha256'],h2['history_sha256'],au3['authorization_sha256'],stores)=='COMMITTED'))
    sm=[]
    for _ in range(rounds): q=time.process_time_ns(); validate(au2['authorization_sha256'],t2['transition_sha256'],h1['history_sha256'],AU,T,R,E,H,AT,S); sm.append((time.process_time_ns()-q)/1000)
    fail=[n for n,ok in C if not ok]; return {'status':'PASS' if not fail else 'FAIL','passed_checks':sum(ok for _,ok in C),'total_checks':len(C),'failed_checks':fail,'checks':[{'name':n,'pass':ok} for n,ok in C],'synthetic_single_host_attestation_history_cpu_us_median':statistics.median(sm),'benchmark_rounds':rounds}
def selftest(rounds=120):
    a,b=run(rounds),run(rounds); same=[x['name'] for x in a['checks']]==[x['name'] for x in b['checks']]
    return {'schema':'axm.flowing-compute-wave93-transition-attestation-history/v0.1','status':'PASS' if a['status']==b['status']=='PASS' and same else 'FAIL','source_provenance':{'wave92_tool':W92,'wave92_verifier':V92},'independent_check_name_match':same,'independent_runs':[{k:r[k] for k in ('status','passed_checks','total_checks','benchmark_rounds','synthetic_single_host_attestation_history_cpu_us_median')} for r in (a,b)],'checks':a['checks'],'failed_checks':sorted(set(a['failed_checks']+b['failed_checks'])),'closed_counterexamples':['Wave92 removed evaluator IDs remain tombstoned in append-only evaluator-ID history, so exact-old and fresh-predecessorless same-ID resurrection are rejected.','Each root PASS is a content-addressed transition-specific attestation binding evaluator, exact tool/source, registry generation, sequence and predecessor attestation.','Stale replay, cross-root copy, tool substitution, HOLD, missing bodies and visible same-sequence competition fail closed.','Registry + evaluator-ID history + attestation state move as one witnessed authority tuple; partial fan-out has no current authority and exact evidence can resume it.'],'counterexample':'Mechanical provenance is still not moral/canonical legitimacy: mechanically current evaluators can mint structurally valid PASS attestations and admit an arbitrary genuinely new evaluator ID.','known_limitations':['This wave conservatively forbids reusing a retired evaluator ID; legitimate same-ID reactivation is not yet supported.','Same-sequence equivocation is detected only when competing attestation objects are visible in the local attestation store.','No cryptographic signer/key-control proof exists yet; evaluator/tool/source hashes are provenance identities, not actor authentication.','Whole-failure-domain rollback of registry+history+attestation stores is not proven detectable.'],'measurement_note':'Synthetic single-host authorization/history validation only; process CPU, not wall-clock storage/network latency, joules, or a retained/incremental/dormant-state efficiency result.','truth_boundary':{'fresh_monolith_audit':False,'compute_efficiency_claim':False,'retained_incremental_dormant_win_claim':False,'energy_claim':False,'distributed_consensus_claim':False,'cryptographic_signer_claim':False,'canonical_root_judgment_claim':False,'moral_evaluator_legitimacy_proven':False,'automatic_merge':False,'synthetic_scaling':False},'next_gate':'Wave 94: add explicit signer/key provenance and key-rotation lineage for attestation issuance, then attack stolen/rotated keys, hidden equivocation and whole-store rollback. Keep proof-of-key-control separate from proof that a root judgment is correct; only after that reconsider an explicitly authorized same-ID reactivation path.'}
if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--rounds',type=int,default=120); p.add_argument('--output'); z=p.parse_args(); r=selftest(z.rounds); s=json.dumps(r,indent=2,sort_keys=True); print(s); open(z.output,'w').write(s+'\n') if z.output else None; raise SystemExit(0 if r['status']=='PASS' else 1)
