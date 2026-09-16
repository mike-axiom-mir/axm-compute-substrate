from __future__ import annotations
import fnmatch,json,hashlib
from pathlib import Path
from typing import Any
SCHEMA='axm.flowing-compute-contract-dependency-registry/v0.1'
def canon(v:Any)->bytes:return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def digest(v:Any)->str:return hashlib.sha256(canon(v)).hexdigest()
def validate_registry(r:dict[str,Any])->None:
    if r.get('schema')!=SCHEMA:raise ValueError('unsupported dependency registry')
    contracts=r.get('contracts') or []
    ids=[c.get('contract_id') for c in contracts]
    if any(not x for x in ids) or len(ids)!=len(set(ids)):raise ValueError('contract ids missing/duplicate')
    if not r.get('accepted_source_namespaces'):raise ValueError('source namespaces required')
    for c in contracts:
        sels=c.get('source_selectors') or []
        if not sels:raise ValueError('every known contract must declare at least one selector')
        if c.get('unknown_input_policy') not in ('not_affected_if_no_selector_match','hold'):raise ValueError('unknown input policy missing')
def load_registry(path:str|Path)->dict[str,Any]:
    r=json.loads(Path(path).read_text());validate_registry(r);return r
def _namespace(source:str)->str:return source.split(':',1)[0]+':' if ':' in source else ''
def route(registry:dict[str,Any], mutation_sources:list[str])->dict[str,Any]:
    validate_registry(registry)
    if not mutation_sources:raise ValueError('mutation_sources must not be empty')
    ns=set(registry['accepted_source_namespaces']);bad=[s for s in mutation_sources if _namespace(s) not in ns]
    if bad:return {'status':'HOLD_UNKNOWN_SOURCE_NAMESPACE','unknown_sources':bad,'mutation_sources':mutation_sources}
    affected=[];reuse=[];evidence={}
    for c in registry['contracts']:
        matched=[]
        for s in mutation_sources:
            if any(fnmatch.fnmatchcase(s,sel) for sel in c['source_selectors']):matched.append(s)
        evidence[c['contract_id']]={'selectors':c['source_selectors'],'matched_sources':matched}
        if matched:affected.append(c['contract_id'])
        elif c['unknown_input_policy']=='hold':return {'status':'HOLD_CONTRACT_CANNOT_PROVE_UNAFFECTED','contract_id':c['contract_id'],'mutation_sources':mutation_sources,'evidence':evidence}
        else:reuse.append(c['contract_id'])
    return {'status':'ROUTED','mutation_sources':mutation_sources,'affected_contracts':sorted(affected),'reuse_contracts':sorted(reuse),'evidence':evidence,'truth':{'reuse_means_no_declared_selector_matched_within_this_registry_version':True,'router_does_not_prove_artifact_integrity':True,'unknown_source_namespace_holds':True}}
def plan(registry_path,mutation_sources):
    r=load_registry(registry_path);out=route(r,mutation_sources);out['registry_id']=r['registry_id'];out['registry_sha256']=digest({k:v for k,v in r.items() if k!='registry_sha256'});return out
