from __future__ import annotations
import json, math
from pathlib import Path
from typing import Any
import AXM_FLOWING_COMPUTE_POLICY_ABI as legacy_v02

REGISTRY_SCHEMA='axm.flowing-compute-policy-registry/v0.3'
PROFILE_SCHEMA='axm.flowing-compute-policy-profile/v0.1'
SUPPORTED_NEW={'setup_amortization_v1'}

def readj(p):return json.loads(Path(p).read_text())
def load_registry(path):
    r=readj(path)
    if r.get('schema')!=REGISTRY_SCHEMA:raise ValueError('unsupported policy registry schema')
    seen=set()
    for x in r.get('profiles',[]):
        if not x.get('contract_id') or not x.get('profile_path'):raise ValueError('profile registration incomplete')
        if x['contract_id'] in seen:raise ValueError('duplicate contract')
        if x.get('evaluator_kind') not in SUPPORTED_NEW:raise ValueError('unsupported v0.3 evaluator kind')
        seen.add(x['contract_id'])
    if not r.get('legacy_registry'):raise ValueError('v0.3 registry must name preserved legacy registry')
    return r

def _new_registration(r,contract_id):
    m=[x for x in r.get('profiles',[]) if x['contract_id']==contract_id]
    if len(m)>1:raise ValueError('duplicate exact contract')
    return m[0] if m else None

def _shape(req,features):
    if set(req)!=set(features):raise ValueError(f'feature contract mismatch expected={req} got={list(features)}')

def _setup(p,f):
    _shape(p['features'],f)
    n=int(f['expected_fresh_starts']);available=bool(f['artifact_available']);audit=bool(f['audit_source_each_start'])
    if n<1:raise ValueError('expected_fresh_starts must be >=1')
    c=p['costs'];setup=float(c['setup_cpu_ns']);cold=float(c['cold_per_start_cpu_ns']);service=float(c['audited_per_start_cpu_ns'] if audit else c['dormant_per_start_cpu_ns'])
    if min(setup,cold,service)<0 or cold<=0 or service<=0:raise ValueError('invalid setup-amortization costs')
    compile_total=setup+n*service;cold_total=n*cold
    if available:decision='audited_dormant' if audit else 'dormant'
    else:decision='compile_dormant' if compile_total<cold_total else 'cold_parse'
    be=max(1,int(math.ceil(setup/(cold-service)))) if cold>service else None
    return {'decision':decision,'confidence':'measured_profile','expected_fresh_starts':n,'artifact_available':available,'audit_source_each_start':audit,'predicted_setup_cpu_ns':setup,'predicted_cold_total_cpu_ns':cold_total,'predicted_dormant_total_cpu_ns':n*service+(0 if available else setup),'estimated_setup_break_even_starts':be,'artifact_bytes':p.get('artifact_bytes'),'truth':{'expected_future_starts_are_input_not_fact':True,'setup_cost_not_hidden':True,'artifact_availability_changes_decision':True}}

def decide(registry_path,*,contract_id,features):
    rp=Path(registry_path);r=load_registry(rp);reg=_new_registration(r,contract_id)
    if reg is None:
        legacy_path=rp.parent.parent/r['legacy_registry']
        result=legacy_v02.decide(legacy_path,contract_id=contract_id,features=features)
        result.setdefault('truth',{})['delegated_to_preserved_v0_2_policy']=True
        return result
    p=readj(rp.parent.parent/reg['profile_path'])
    if p.get('schema')!=PROFILE_SCHEMA or p.get('profile_id')!=reg.get('profile_id') or p.get('contract_id')!=contract_id:raise ValueError('setup profile binding mismatch')
    body=_setup(p,features)
    return {'contract_id':contract_id,'profile_id':p['profile_id'],'evaluator_kind':'setup_amortization_v1','features':features,**body,'truth':{'exact_contract_binding':True,'prediction_not_proof':True,'one_model_family_for_all_contracts':False,'legacy_policies_not_reimplemented':True}}
