from __future__ import annotations
import hashlib,json
from typing import Any
SCHEMA='axm.flowing-compute-verification-freshness/v0.1'
def canon(v:Any)->bytes:return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def digest(v:Any)->str:return hashlib.sha256(canon(v)).hexdigest()
def start(*,contract_id:str,artifact_sha256:str,artifact_bytes:int,proof_sha256:str,audited_sequence:int)->dict[str,Any]:
    body={'schema':SCHEMA,'contract_id':contract_id,'artifact_sha256':artifact_sha256,'artifact_bytes':int(artifact_bytes),'proof_sha256':proof_sha256,'last_strong_audit_sequence':int(audited_sequence),'current_sequence':int(audited_sequence),'carried_generations_since_audit':0,'cumulative_bytes_not_rehashed':0,'truth':{'freshness_is_reported_not_invented':True,'carried_generation_count_is_not_corruption_probability':True}}
    body['state_sha256']=digest(body);return body
def validate(s:dict[str,Any])->None:
    if s.get('schema')!=SCHEMA:raise ValueError('unsupported freshness schema')
    stored=s.get('state_sha256');b=dict(s);b.pop('state_sha256',None)
    if digest(b)!=stored:raise ValueError('freshness state integrity mismatch')
def advance(*,state:dict[str,Any],sequence:int,mode:str,artifact_sha256:str,proof_sha256:str,max_carried_generations:int|None=None)->dict[str,Any]:
    validate(state);seq=int(sequence)
    if seq!=int(state['current_sequence'])+1:raise ValueError('verification freshness sequence gap')
    if artifact_sha256!=state['artifact_sha256'] or proof_sha256!=state['proof_sha256']:raise ValueError('verification freshness artifact/proof identity changed')
    if mode not in ('carried_immutable_proof','audited_reuse'):raise ValueError('unsupported verification mode')
    carried=int(state['carried_generations_since_audit']);last=int(state['last_strong_audit_sequence']);skipped=int(state['cumulative_bytes_not_rehashed'])
    if mode=='carried_immutable_proof':
        if max_carried_generations is not None and carried+1>int(max_carried_generations):
            return {'status':'HOLD_AUDIT_REQUIRED','contract_id':state['contract_id'],'sequence':seq,'last_strong_audit_sequence':last,'carried_generations_since_audit':carried,'configured_max_carried_generations':int(max_carried_generations),'truth':{'limit_is_explicit_input_not_runtime_invention':True}}
        carried+=1;skipped+=int(state['artifact_bytes'])
    else:
        carried=0;last=seq
    b={k:v for k,v in state.items() if k!='state_sha256'};b.update({'current_sequence':seq,'last_strong_audit_sequence':last,'carried_generations_since_audit':carried,'cumulative_bytes_not_rehashed':skipped});b['state_sha256']=digest(b)
    return {'status':'ADVANCED','state':b}
def summary(state:dict[str,Any])->dict[str,Any]:
    validate(state);return {'contract_id':state['contract_id'],'current_sequence':state['current_sequence'],'last_strong_audit_sequence':state['last_strong_audit_sequence'],'audit_age_generations':int(state['current_sequence'])-int(state['last_strong_audit_sequence']),'carried_generations_since_audit':state['carried_generations_since_audit'],'artifact_bytes_under_carried_proof':state['artifact_bytes'] if state['carried_generations_since_audit'] else 0,'cumulative_bytes_not_rehashed':state['cumulative_bytes_not_rehashed'],'truth':{'audit_age_is_not_risk_probability':True}}
