from __future__ import annotations
import hashlib, json
from typing import Any

SCHEMA='axm.flowing-compute-policy-generation/v0.1'

def canonical(v:Any)->bytes:
    return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()

def digest(v:Any)->str:
    return hashlib.sha256(canonical(v)).hexdigest()

def make_generation(*, profile:dict[str,Any], parent_generation_sha256:str|None, evidence_tail_sha256:str|None, evaluation:dict[str,Any], status:str)->dict[str,Any]:
    if status not in ('CURRENT','CANDIDATE','REJECTED','RETIRED'):
        raise ValueError('invalid generation status')
    value={'schema':SCHEMA,'contract_id':profile.get('contract_id'),'profile_id':profile.get('profile_id'),'parent_generation_sha256':parent_generation_sha256,'evidence_tail_sha256':evidence_tail_sha256,'evaluation':evaluation,'status':status,'profile':profile}
    value['generation_sha256']=digest(value)
    return value

def validate_generation(value:dict[str,Any])->None:
    if value.get('schema')!=SCHEMA: raise ValueError('unsupported generation schema')
    stored=value.get('generation_sha256'); body=dict(value); body.pop('generation_sha256',None)
    if digest(body)!=stored: raise ValueError('generation integrity mismatch')

def promotion_decision(*, current:dict[str,Any], candidate:dict[str,Any])->dict[str,Any]:
    validate_generation(current); validate_generation(candidate)
    if current.get('contract_id')!=candidate.get('contract_id'):
        return {'promote':False,'reason':'contract_mismatch'}
    ce=current.get('evaluation',{}); ne=candidate.get('evaluation',{})
    ca=ce.get('accuracy'); na=ne.get('accuracy'); cr=ce.get('max_regret_percent'); nr=ne.get('max_regret_percent')
    if None in (ca,na,cr,nr): return {'promote':False,'reason':'incomplete_evaluation'}
    if float(na)<float(ca): return {'promote':False,'reason':'accuracy_regressed'}
    if float(nr)>float(cr): return {'promote':False,'reason':'max_regret_regressed'}
    return {'promote':True,'reason':'no_regression_gate_passed'}

def pointer(contract_id:str,generation_sha256:str)->dict[str,Any]:
    return {'schema':'axm.flowing-compute-current-profile-pointer/v0.1','contract_id':contract_id,'generation_sha256':generation_sha256}
