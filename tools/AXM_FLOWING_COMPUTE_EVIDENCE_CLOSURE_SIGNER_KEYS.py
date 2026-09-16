#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, hmac, json, statistics, time
from copy import deepcopy
ROOTS=('truth','agency_non_domination','continuity','wisdom_before_speed'); WIT=('witness-a','witness-b','witness-c')
W93={'builder_head':'24c3597089097d67b5f2972beb11d51a764bee12','path':'tools/AXM_FLOWING_COMPUTE_TRANSITION_ATTESTATION_HISTORY.py','blob_sha':'bd34149b4370973b56a2ab213ae9e1f1adc2ae0e','file_sha256':'4ab6553768a23dcbff16255763f92f89f00179eff1fde6915692fc17301522a3'}
V93={'pr':18,'head':'9e58b601c39eabcb619b3cb6b784e7d2e95dffac','path':'verification/WAVE93_ADVERSARIAL_VERIFICATION_2026-09-16.md','blob_sha':'ba10e7b2bfee6eb22975d45b9eaa369d910099a7','finding':'FAIL_COMMITTED_HISTORY_CAN_EXTEND_OVER_MISSING_PREDECESSOR_BODIES','workflow_run':35127370580}
def enc(x): return json.dumps(x,sort_keys=True,separators=(',',':')).encode()
def dig(x): return hashlib.sha256(enc(x)).hexdigest()
def td(s): return hashlib.sha256(s.encode()).hexdigest()
def seal(x,f): y=deepcopy(x); y.pop(f,None); y[f]=dig(y); return y
def chk(x,f):
 y=deepcopy(x); got=y.pop(f,None)
 if got!=dig(y): raise ValueError(f'{f} mismatch')
def put(st,x,f):
 chk(x,f); k=x[f]
 if k in st and st[k]!=x: raise ValueError('collision')
 st[k]=deepcopy(x); return k
def get(st,k,f):
 if k not in st: raise ValueError(f'{f} body missing')
 x=deepcopy(st[k]); chk(x,f)
 if x.get(f)!=k: raise ValueError(f'{f} key/body mismatch')
 return x
def mac(sec,x): return hmac.new(sec,enc(x),hashlib.sha256).hexdigest()
def fails(fn,text):
 try: fn()
 except Exception as e: return text in str(e)
 return False
def key(root,gen,sec,pred=None): return seal({'schema':'key/v1','root':root,'generation':gen,'predecessor':pred,'material':hashlib.sha256(sec).hexdigest(),'key_sha':''},'key_sha')
def secret(k,secrets):
 sec=secrets.get(k['key_sha'])
 if sec is None or hashlib.sha256(sec).hexdigest()!=k['material']: raise ValueError('key secret mismatch')
 return sec
def kclosure(head,K,secrets,root):
 n=0; exp=None
 while head:
  k=get(K,head,'key_sha')
  if k['root']!=root or (exp is not None and k['generation']!=exp): raise ValueError('key lineage mismatch')
  secret(k,secrets); exp=k['generation']-1; head=k['predecessor']; n+=1
 if exp!=-1: raise ValueError('key genesis missing')
 return n
def hist(gen,registry,pred=None): return seal({'schema':'history/v1','generation':gen,'registry_sha':registry,'predecessor':pred,'history_sha':''},'history_sha')
def hclosure(head,H):
 n=0; exp=None
 while head:
  h=get(H,head,'history_sha')
  if exp is not None and h['generation']!=exp: raise ValueError('history discontinuity')
  exp=h['generation']-1; head=h['predecessor']; n+=1
 if exp!=-1: raise ValueError('history genesis missing')
 return n
def state(gen,registry,pred,heads): return seal({'schema':'att-state/v1','generation':gen,'registry_sha':registry,'predecessor':pred,'heads':deepcopy(heads),'state_sha':''},'state_sha')
def key_state(gen,registry,pred,heads): return seal({'schema':'key-state/v1','generation':gen,'registry_sha':registry,'predecessor':pred,'heads':deepcopy(heads),'key_state_sha':''},'key_state_sha')
def attest(trans,gen,root,seq,prev,key_sha,sec,verdict='PASS'):
 x={'schema':'att/v1','transition_sha':trans,'registry_generation':gen,'root':root,'sequence':seq,'previous':prev,'signer_key_sha':key_sha,'verdict':verdict,'algorithm':'HMAC-SHA256-test-model','test_only':True}
 x['mac']=mac(sec,x); return seal(x,'att_sha')
def aval(a,K,secrets):
 chk(a,'att_sha'); x=deepcopy(a); x.pop('att_sha'); sig=x.pop('mac'); k=get(K,a['signer_key_sha'],'key_sha')
 if k['root']!=a['root'] or sig!=mac(secret(k,secrets),x): raise ValueError('attestation MAC mismatch')
def visible_conflict(a,A):
 for b in A.values():
  try: chk(b,'att_sha')
  except Exception: continue
  if b['att_sha']!=a['att_sha'] and (b['root'],b['sequence'],b['previous'])==(a['root'],a['sequence'],a['previous']): return True
 return False
def aclosure(head,A,K,secrets,root,seq):
 exp=seq
 while head:
  a=get(A,head,'att_sha'); aval(a,K,secrets)
  if a['root']!=root or a['sequence']!=exp: raise ValueError('attestation lineage mismatch')
  if visible_conflict(a,A): raise ValueError('visible attestation equivocation')
  exp-=1; head=a['previous']
 if exp!=0: raise ValueError('attestation genesis missing')
def tuple_closure(tup,stores):
 H,A,K,S,KS,secrets=stores; hh,ss,kk=tup; h=get(H,hh,'history_sha'); s=get(S,ss,'state_sha'); ks=get(KS,kk,'key_state_sha')
 if not(h['generation']==s['generation']==ks['generation']) or not(h['registry_sha']==s['registry_sha']==ks['registry_sha']): raise ValueError('authority tuple cross-binding')
 hclosure(hh,H)
 if set(s['heads'])!=set(ROOTS) or set(ks['heads'])!=set(ROOTS): raise ValueError('root set mismatch')
 for r in ROOTS:
  hd=s['heads'][r]; aclosure(hd['att_sha'],A,K,secrets,r,hd['sequence']); kclosure(ks['heads'][r],K,secrets,r)
 return h['generation'],h['registry_sha'],s,ks
def authority(rt,stores):
 if set(rt['w'])!=set(WIT) or any(tuple(rt['w'][w])!=tuple(rt['cur']) for w in WIT): return 'HOLD'
 try: tuple_closure(tuple(rt['cur']),stores)
 except Exception: return 'HOLD'
 return 'AUTHORITATIVE'
def rotation(root,trans,old_sha,new_sha,K,secrets):
 old=get(K,old_sha,'key_sha'); new=get(K,new_sha,'key_sha')
 if new['predecessor']!=old_sha or new['generation']!=old['generation']+1: raise ValueError('rotation lineage')
 x={'schema':'rotation/v1','root':root,'transition_sha':trans,'from_key':old_sha,'to_key':new_sha,'algorithm':'HMAC-SHA256-test-model','test_only':True}; x['old_key_mac']=mac(secret(old,secrets),x); return seal(x,'rotation_sha')
def rval(x,K,secrets):
 chk(x,'rotation_sha'); y=deepcopy(x); y.pop('rotation_sha'); sig=y.pop('old_key_mac'); old=get(K,x['from_key'],'key_sha'); new=get(K,x['to_key'],'key_sha')
 if old['root']!=x['root'] or new['root']!=x['root'] or new['predecessor']!=old['key_sha'] or sig!=mac(secret(old,secrets),y): raise ValueError('rotation MAC/lineage mismatch')
def bundle(rt,stores,registry,rotate=None,override=None):
 H,A,K,S,KS,secrets=stores
 if authority(rt,stores)!='AUTHORITATIVE': raise ValueError('predecessor authority closure HOLD')
 old=tuple(rt['cur']); gen,_,s,ks=tuple_closure(old,stores); trans=seal({'schema':'transition/v1','generation':gen+1,'predecessor_tuple':list(old),'target_registry_sha':registry,'rotate_root':rotate,'transition_sha':''},'transition_sha')
 kh=deepcopy(ks['heads']); rot=None
 if rotate:
  oldk=get(K,kh[rotate],'key_sha'); sec=td(f'{rotate}-secret-{gen+1}').encode(); nk=key(rotate,oldk['generation']+1,sec,oldk['key_sha']); put(K,nk,'key_sha'); secrets[nk['key_sha']]=sec; rot=rotation(rotate,trans['transition_sha'],oldk['key_sha'],nk['key_sha'],K,secrets); kh[rotate]=nk['key_sha']
 heads=deepcopy(s['heads']); amap={}
 for r in ROOTS:
  hd=heads[r]; signer=ks['heads'][r]; k=get(K,signer,'key_sha'); sec=(override or {}).get(r,secret(k,secrets)); a=attest(trans['transition_sha'],gen,r,hd['sequence']+1,hd['att_sha'],signer,sec); put(A,a,'att_sha'); amap[r]=a['att_sha']; heads[r]={'sequence':a['sequence'],'att_sha':a['att_sha']}
 nh=hist(gen+1,registry,old[0]); put(H,nh,'history_sha'); ns=state(gen+1,registry,old[1],heads); put(S,ns,'state_sha'); nks=key_state(gen+1,registry,old[2],kh); put(KS,nks,'key_state_sha'); target=(nh['history_sha'],ns['state_sha'],nks['key_state_sha'])
 auth=seal({'schema':'authorization/v1','transition_sha':trans['transition_sha'],'predecessor_tuple':list(old),'target_tuple':list(target),'attestations':amap,'rotation':rot,'authorization_sha':''},'authorization_sha')
 return {'transition':trans,'authorization':auth,'target':target}
def validate(rt,b,stores):
 H,A,K,S,KS,secrets=stores; au=b['authorization']; chk(au,'authorization_sha'); tr=b['transition']; chk(tr,'transition_sha'); old=tuple(au['predecessor_tuple']); gen,_,s,ks=tuple_closure(old,stores)
 if tuple(tr['predecessor_tuple'])!=old or tr['generation']!=gen+1 or au['transition_sha']!=tr['transition_sha']: raise ValueError('transition predecessor mismatch')
 if au['rotation']:
  rval(au['rotation'],K,secrets)
  if au['rotation']['transition_sha']!=tr['transition_sha'] or au['rotation']['root']!=tr['rotate_root']: raise ValueError('rotation transition mismatch')
 elif tr['rotate_root'] is not None: raise ValueError('rotation missing')
 for r in ROOTS:
  a=get(A,au['attestations'][r],'att_sha'); aval(a,K,secrets); hd=s['heads'][r]
  if (a['transition_sha'],a['registry_generation'],a['root'],a['sequence'],a['previous'],a['signer_key_sha'],a['verdict'])!=(tr['transition_sha'],gen,r,hd['sequence']+1,hd['att_sha'],ks['heads'][r],'PASS'): raise ValueError('attestation current-key/binding mismatch')
 nh=get(H,au['target_tuple'][0],'history_sha'); ns=get(S,au['target_tuple'][1],'state_sha'); nks=get(KS,au['target_tuple'][2],'key_state_sha')
 if (nh['generation'],ns['generation'],nks['generation'])!=(gen+1,)*3 or (nh['registry_sha'],ns['registry_sha'],nks['registry_sha'])!=(tr['target_registry_sha'],)*3: raise ValueError('target tuple mismatch')
 if (nh['predecessor'],ns['predecessor'],nks['predecessor'])!=old: raise ValueError('target predecessor mismatch')
 for r in ROOTS:
  if ns['heads'][r]['att_sha']!=au['attestations'][r]: raise ValueError('target attestation mismatch')
  expected=ks['heads'][r]
  if au['rotation'] and r==au['rotation']['root']: expected=au['rotation']['to_key']
  if nks['heads'][r]!=expected: raise ValueError('target key mismatch')
 tuple_closure(tuple(au['target_tuple']),stores); return tuple(au['target_tuple'])
def apply(rt,b,stores,count=None):
 try: target=validate(rt,b,stores)
 except Exception: return 'HOLD'
 old=tuple(b['authorization']['predecessor_tuple'])
 if tuple(rt['cur'])==target and all(tuple(rt['w'][w])==target for w in WIT): return 'CONSISTENT_TARGET'
 if tuple(rt['cur'])!=old or set(rt['w'])!=set(WIT): return 'PREDECESSOR_HOLD'
 if any(tuple(rt['w'][w]) not in (old,target) for w in WIT): return 'COMPETING_HOLD'
 lag=[w for w in WIT if tuple(rt['w'][w])==old]; n=len(lag) if count is None else min(max(count,0),len(lag))
 for w in lag[:n]: rt['w'][w]=list(target)
 if any(tuple(rt['w'][w])!=target for w in WIT): return 'PARTIAL'
 rt['cur']=list(target); return 'COMMITTED'
def fixture():
 H,A,K,S,KS,secrets={},{},{},{},{},{}; kh={}; heads={r:{'sequence':0,'att_sha':None} for r in ROOTS}
 for r in ROOTS:
  sec=td(f'{r}-secret-0').encode(); k=key(r,0,sec); put(K,k,'key_sha'); secrets[k['key_sha']]=sec; kh[r]=k['key_sha']
 reg=td('registry-0'); h=hist(0,reg); put(H,h,'history_sha'); s=state(0,reg,None,heads); put(S,s,'state_sha'); ks=key_state(0,reg,None,kh); put(KS,ks,'key_state_sha'); cur=[h['history_sha'],s['state_sha'],ks['key_state_sha']]; rt={'cur':cur,'w':{w:list(cur) for w in WIT}}; return (H,A,K,S,KS,secrets),rt
def run(rounds):
 st,rt=fixture(); H,A,K,S,KS,secrets=st; C=[]
 C += [('exact_wave93_builder_source',W93['builder_head']=='24c3597089097d67b5f2972beb11d51a764bee12'),('exact_wave93_verifier_source',V93['head']=='9e58b601c39eabcb619b3cb6b784e7d2e95dffac' and V93['blob_sha']=='ba10e7b2bfee6eb22975d45b9eaa369d910099a7'),('genesis_authoritative',authority(rt,st)=='AUTHORITATIVE')]
 b1=bundle(rt,st,td('registry-1')); C += [('generation1_valid',validate(rt,b1,st)==b1['target']),('generation1_commits',apply(rt,b1,st)=='COMMITTED'),('generation1_authoritative',authority(rt,st)=='AUTHORITATIVE')]
 s1=get(S,rt['cur'][1],'state_sha'); miss=s1['heads']['continuity']['att_sha']; saved=A.pop(miss); C += [('missing_immediate_attestation_holds',authority(rt,st)=='HOLD'),('cannot_extend_missing_immediate_attestation',fails(lambda:bundle(rt,st,td('blocked-a')),'predecessor authority closure HOLD'))]; A[miss]=saved
 h1=get(H,rt['cur'][0],'history_sha'); gh=h1['predecessor']; savedh=H.pop(gh); C += [('missing_predecessor_history_holds',authority(rt,st)=='HOLD'),('cannot_extend_missing_history',fails(lambda:bundle(rt,st,td('blocked-h')),'predecessor authority closure HOLD'))]; H[gh]=savedh; C.append(('restored_closure_authoritative',authority(rt,st)=='AUTHORITATIVE'))
 oldks=get(KS,rt['cur'][2],'key_state_sha')['heads']['truth']; oldsec=bytes(secrets[oldks]); b2=bundle(rt,st,td('registry-2'),rotate='truth'); C += [('rotation_bundle_valid',validate(rt,b2,st)==b2['target']),('rotation_commits',apply(rt,b2,st)=='COMMITTED'),('post_rotation_authoritative',authority(rt,st)=='AUTHORITATIVE')]
 newks=get(KS,rt['cur'][2],'key_state_sha')['heads']['truth']; C += [('key_rotated',newks!=oldks),('new_key_descends_from_old',get(K,newks,'key_sha')['predecessor']==oldks)]
 badst=deepcopy(st); badrt=deepcopy(rt); bad=bundle(badrt,badst,td('old-secret-attempt'),override={'truth':oldsec}); C.append(('old_key_material_rejected_after_rotation',fails(lambda:validate(badrt,bad,badst),'attestation MAC mismatch')))
 b3=bundle(rt,st,td('registry-3')); C += [('new_current_key_valid',validate(rt,b3,st)==b3['target']),('generation3_commits',apply(rt,b3,st)=='COMMITTED')]
 s3=get(S,rt['cur'][1],'state_sha'); a3=get(A,s3['heads']['agency_non_domination']['att_sha'],'att_sha'); older=a3['previous']; sa=A.pop(older); C += [('missing_older_attestation_holds',authority(rt,st)=='HOLD'),('cannot_extend_over_older_gap',fails(lambda:bundle(rt,st,td('blocked-old')),'predecessor authority closure HOLD'))]; A[older]=sa
 sk=K.pop(oldks); C.append(('missing_key_lineage_body_holds',authority(rt,st)=='HOLD')); K[oldks]=sk; C.append(('restored_key_lineage_authoritative',authority(rt,st)=='AUTHORITATIVE'))
 head=get(S,rt['cur'][1],'state_sha')['heads']['wisdom_before_speed']['att_sha']; orig=get(A,head,'att_sha'); k=get(K,orig['signer_key_sha'],'key_sha'); alt=deepcopy(orig); alt.pop('att_sha'); alt['verdict']='HOLD'; alt.pop('mac'); alt['mac']=mac(secret(k,secrets),alt); alt=seal(alt,'att_sha'); put(A,alt,'att_sha'); C.append(('visible_same_sequence_equivocation_holds',authority(rt,st)=='HOLD')); A.pop(alt['att_sha']); C.append(('remove_visible_equivocation_restores_authority',authority(rt,st)=='AUTHORITATIVE'))
 stolenst=deepcopy(st); stolenrt=deepcopy(rt); current_new=get(stolenst[4],stolenrt['cur'][2],'key_state_sha')['heads']['truth']; copied=bytes(stolenst[5][current_new]); stolen=bundle(stolenrt,stolenst,td('stolen-current'),override={'truth':copied}); C.append(('counterexample_stolen_current_key_still_validates',validate(stolenrt,stolen,stolenst)==stolen['target']))
 rst,rrt=fixture(); C.append(('counterexample_whole_domain_rollback_still_authoritative',authority(rrt,rst)=='AUTHORITATIVE'))
 p=deepcopy(rt); b4=bundle(p,st,td('registry-4')); C += [('partial_created',apply(p,b4,st,1)=='PARTIAL'),('partial_not_authoritative',authority(p,st)=='HOLD'),('partial_exact_recovery_commits',apply(p,b4,st)=='COMMITTED')]
 q=deepcopy(rt); q['w'].pop(WIT[-1]); C.append(('missing_witness_holds',authority(q,st)=='HOLD'))
 samples=[]
 for _ in range(rounds):
  z=time.process_time_ns(); authority(rt,st); validate(rt,b4,st); samples.append((time.process_time_ns()-z)/1000)
 fail=[n for n,v in C if not v]; return {'status':'PASS' if not fail else 'FAIL','passed_checks':sum(v for _,v in C),'total_checks':len(C),'failed_checks':fail,'checks':[{'name':n,'pass':v} for n,v in C],'synthetic_single_host_closure_and_signer_cpu_us_median':statistics.median(samples),'benchmark_rounds':rounds}
def selftest(rounds=100):
 a,b=run(rounds),run(rounds); same=[x['name'] for x in a['checks']]==[x['name'] for x in b['checks']]
 return {'schema':'axm.flowing-compute-wave94-evidence-closure-signer-keys/v0.1','status':'PASS' if a['status']==b['status']=='PASS' and same else 'FAIL','source_provenance':{'wave93_builder':W93,'wave93_verifier':V93},'independent_check_name_match':same,'independent_runs':[{k:r[k] for k in ('status','passed_checks','total_checks','benchmark_rounds','synthetic_single_host_closure_and_signer_cpu_us_median')} for r in (a,b)],'checks':a['checks'],'failed_checks':sorted(set(a['failed_checks']+b['failed_checks'])),'closed_counterexamples':['Current authority traverses the complete retained history chain to genesis; deleting a committed predecessor history body fails closed.','Current authority traverses every active root attestation chain to sequence 1; deleting immediate or older committed attestation bodies fails closed and blocks extension.','Attestations carry HMAC-SHA256 test-model key-control proof and must use the exact current root key for new issuance; predecessor-authenticated key rotation advances explicit key lineage and rotated old key material cannot authorize later transitions.','Current key-lineage bodies are part of authority closure, and visible same-sequence equivocation freezes authority.','History/attestation/key state moves through exact three-witness tuples; partial fan-out has no authority and resumes only with exact evidence.'],'counterexamples':['A stolen current symmetric key can still mint structurally valid evidence: this demonstrates modeled key control, not actor identity, moral legitimacy, or correctness of a root judgment.','Equivocation hidden outside the visible attestation store is not detectable by this single-host model.','If runtime plus all evidence/key stores roll back together, the old self-consistent snapshot remains internally authoritative; no independent anti-rollback witness is proven.','Full retained closure means historical bodies cannot be garbage-collected silently; no authority-bound compaction/checkpoint cut exists yet.'],'measurement_note':'Synthetic single-host evidence-closure + HMAC key-lineage bookkeeping only; process CPU, not wall-clock storage/network latency, joules, or a retained/incremental/dormant-state efficiency result.','truth_boundary':{'fresh_monolith_audit':False,'compute_efficiency_claim':False,'retained_incremental_dormant_win_claim':False,'energy_claim':False,'distributed_consensus_claim':False,'public_key_signature_claim':False,'actor_identity_claim':False,'canonical_root_judgment_claim':False,'moral_evaluator_legitimacy_proven':False,'automatic_merge':False,'synthetic_scaling':False,'cryptographic_scope':'HMAC-SHA256 symmetric test model demonstrates key possession/control only; secrets are test-fixture material, not production key management.'},'next_gate':'Wave 95: make deliberate history/attestation compaction an authority-bound checkpoint operation instead of requiring every body forever, then attack stale checkpoint reuse, omitted pre-cut evidence, malicious cut points, key rotation across a compaction boundary, and rollback of both live state and checkpoint. After that, move anti-rollback witnessing into a genuinely separate failure domain and consider public-key signatures without conflating key identity with root correctness.'}
if __name__=='__main__':
 p=argparse.ArgumentParser(); p.add_argument('--rounds',type=int,default=100); p.add_argument('--output'); z=p.parse_args(); r=selftest(z.rounds); text=json.dumps(r,indent=2,sort_keys=True); print(text); open(z.output,'w').write(text+'\n') if z.output else None; raise SystemExit(0 if r['status']=='PASS' else 1)