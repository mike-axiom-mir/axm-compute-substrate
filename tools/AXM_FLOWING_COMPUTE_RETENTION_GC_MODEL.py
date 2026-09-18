from __future__ import annotations
import hashlib,json

LEGACY='axm.flowing-compute-receipt-retention/v0.1'; RET='axm.flowing-compute-retention-generation/v0.2'
DROP='axm.flowing-compute-retention-drop-receipt/v0.1'; MARK='axm.flowing-compute-gc-mark/v0.1'
R0='53d91b18e1a12eb27bd503bcfa70b4cd74add598ceaef522c88d7c075fdee4d4'
A='fb65ba5ad5cc0f4c33a851957ccc42a4142c64a3d0815abb1a4f0886dbf4ecf2'
B='27dc30ebd1172695c8873cb919efc59de9adde8a546533b64f6b7d6199c4ca1b'
C1='a28948258187a3e43e3b7841d71494e065894bacb79e70493df459aa47514799'
C3='43a63855b44b5a4983abc4cde38633550a6b36dc64c615c49bc924eeb63b0826'
REACH={C1:{A},C3:{B}}

def dig(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def roots(m):return set(m['retained_checkpoints'])
def rid(m):return m['retention_sha256']
def seq(m):return 0 if m['schema']==LEGACY else int(m['sequence'])
def reachable(m):
    out=set()
    for c in roots(m):
        if c not in REACH:raise ValueError('unknown checkpoint reachability mapping')
        out|=REACH[c]
    return out

def wave81():
    m={'schema':LEGACY,'retained_checkpoints':sorted([C1,C3]),'reason':'retain Wave80 rollback evidence + Wave81 later audited checkpoint','truth':{'retention_is_explicit_policy_state_not_inferred_from_receipt_presence':True}}
    m['retention_sha256']=dig(m)
    if rid(m)!=R0:raise ValueError('published Wave81 retention identity mismatch')
    return m

def validate_ret(m,pred=None):
    b=dict(m);key=b.pop('retention_sha256',None)
    if key!=dig(b):raise ValueError('retention integrity mismatch')
    if m['schema']==LEGACY:
        if key!=R0 or pred is not None:raise ValueError('legacy retention mismatch')
        return
    if m.get('schema')!=RET or pred is None:raise ValueError('retention predecessor required')
    if m.get('predecessor_retention_sha256')!=rid(pred):raise ValueError('retention predecessor identity mismatch')
    if int(m.get('sequence',-1))!=seq(pred)+1:raise ValueError('retention sequence gap')
    if set(m.get('drop_receipts',{}))!=(roots(pred)-roots(m)):raise ValueError('every removed rollback root requires exactly one drop receipt')

def make_drop(pred,c,reason):
    if c not in roots(pred):raise ValueError('drop target not retained')
    r={'schema':DROP,'action':'DROP_ROLLBACK_ROOT','checkpoint_sha256':c,'predecessor_retention_sha256':rid(pred),'next_retention_sequence':seq(pred)+1,'reason':reason,'truth':{'drop_receipt_is_explicit_intent_evidence_not_actor_authentication':True,'drop_receipt_does_not_by_itself_establish_constitutional_authority':True,'silent_root_drop_forbidden':True}}
    r['drop_receipt_sha256']=dig(r);return r

def validate_drop(r,pred,c):
    b=dict(r);key=b.pop('drop_receipt_sha256',None)
    if r.get('schema')!=DROP or key!=dig(b):raise ValueError('drop receipt integrity mismatch')
    if r.get('checkpoint_sha256')!=c:raise ValueError('drop receipt checkpoint mismatch')
    if r.get('predecessor_retention_sha256')!=rid(pred):raise ValueError('drop receipt predecessor mismatch')
    if int(r.get('next_retention_sequence',-1))!=seq(pred)+1:raise ValueError('drop receipt sequence mismatch')

def evolve(pred,new_roots,drops,reason):
    removed=roots(pred)-set(new_roots)
    if set(drops)!=removed:raise ValueError('every removed rollback root requires exactly one drop receipt')
    refs={}
    for c in sorted(removed):validate_drop(drops[c],pred,c);refs[c]=drops[c]['drop_receipt_sha256']
    m={'schema':RET,'sequence':seq(pred)+1,'predecessor_retention_sha256':rid(pred),'retained_checkpoints':sorted(new_roots),'drop_receipts':refs,'reason':reason,'truth':{'retention_change_is_append_only_and_predecessor_bound':True,'drop_receipt_presence_is_not_actor_authentication_or_authority':True,'retention_generation_does_not_rewrite_prior_retention_state':True}}
    m['retention_sha256']=dig(m);validate_ret(m,pred);return m

def can_select(m,inventory):
    missing=reachable(m)-set(inventory)
    if missing:raise ValueError(f'refusing retention pointer to missing receipt evidence: {sorted(missing)}')
    return True

def make_mark(current,inventory):
    can_select(current,inventory);live=reachable(current);inv=set(inventory)
    m={'schema':MARK,'retention_sha256':rid(current),'retention_sequence':seq(current),'receipt_inventory_sha256':dig(sorted(inv)),'reachable_receipts':sorted(live),'candidates':sorted(inv-live),'truth':{'mark_is_bound_to_one_exact_current_retention_generation':True,'mark_grants_no_authority_if_current_retention_pointer_changes':True}}
    m['mark_sha256']=dig(m);return m

def validate_mark(mark,current,inventory,exact_inventory=True):
    b=dict(mark);key=b.pop('mark_sha256',None)
    if key!=dig(b):raise ValueError('GC mark integrity mismatch')
    if mark['retention_sha256']!=rid(current) or int(mark['retention_sequence'])!=seq(current):raise ValueError('stale GC mark: current retention pointer changed')
    if set(mark['candidates'])&reachable(current):raise ValueError('GC mark candidate became reachable')
    if exact_inventory and mark['receipt_inventory_sha256']!=dig(sorted(set(inventory))):raise ValueError('stale GC mark: receipt inventory changed')

def recovery_action(staged_receipts,sweep_commit,current):
    staged=sorted(set(staged_receipts))
    if not sweep_commit:return {'action':'RESTORE','receipts':staged,'reason':'no committed sweep'}
    ok=(sweep_commit.get('retention_sha256')==rid(current) and int(sweep_commit.get('retention_sequence',-1))==seq(current))
    return {'action':'PURGE' if ok else 'RESTORE','receipts':staged,'reason':'exact current retention sweep' if ok else 'stale sweep'}

def fail(fn):
    try:fn()
    except Exception as e:return str(e)
    raise AssertionError('unexpected success')

def self_test():
    g0=wave81();inventory={A,B};d=make_drop(g0,C1,'test-only explicit rollback-root retirement for crash-safe GC probe')
    g1=evolve(g0,{C3},{C1:d},'Wave82 test generation: explicitly drop old Wave80/Wave79 rollback root')
    assert rid(g1)=='f9cb087d701268b4f7eb660161776f37d46d312f0e46c1fbc883c46a452d3eb5'
    fail(lambda:evolve(g0,{C3},{},'silent'))
    bad=make_drop(g0,C1,'wrong predecessor');bad['predecessor_retention_sha256']='0'*64;bad['drop_receipt_sha256']=dig({k:v for k,v in bad.items() if k!='drop_receipt_sha256'});fail(lambda:evolve(g0,{C3},{C1:bad},'bad'))
    mark=make_mark(g1,inventory);assert mark['candidates']==[A] and mark['reachable_receipts']==[B]
    fail(lambda:validate_mark(mark,g1,inventory|{dig({'late':'control'})}))
    g2=evolve(g1,{C1,C3},{},'re-add prior rollback root before GC');fail(lambda:validate_mark(mark,g2,inventory))
    assert recovery_action([A],None,g1)['action']=='RESTORE'
    sweep={'retention_sha256':rid(g1),'retention_sequence':seq(g1)};assert recovery_action([A],sweep,g1)['action']=='PURGE'
    assert recovery_action([A],sweep,g2)['action']=='RESTORE'
    can_select(g1,{B});fail(lambda:can_select(g2,{B}))
    tampered=dict(g1);tampered['reason']='tampered';fail(lambda:validate_ret(tampered,g0))
    fake=dict(g2);fake['sequence']=3;fake['predecessor_retention_sha256']=rid(g0);fake['retention_sha256']=dig({k:v for k,v in fake.items() if k!='retention_sha256'});fail(lambda:validate_ret(fake,g1))
    return {'status':'PASS','wave81_retention_sha256':rid(g0),'g1_retention_sha256':rid(g1),'drop_receipt_sha256':d['drop_receipt_sha256'],'g2_readd_retention_sha256':rid(g2),'gc_mark_sha256':mark['mark_sha256'],'truth':{'model_is_non_destructive_planner_validator':True,'drop_receipt_is_not_authorization':True,'no_auto_merge':True}}

if __name__=='__main__':print(json.dumps(self_test(),indent=2,sort_keys=True))
