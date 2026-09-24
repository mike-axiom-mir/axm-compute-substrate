from __future__ import annotations
import hashlib,json
from pathlib import Path
from typing import Any
SCHEMA='axm.flowing-compute-reuse-proof/v0.1'

def canon(v:Any)->bytes:return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def digest(v:Any)->str:return hashlib.sha256(canon(v)).hexdigest()
def sha_file(path:str|Path,chunk:int=1024*1024)->str:
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(chunk),b''):h.update(b)
    return h.hexdigest()
def build_proof(*,contract_id:str,artifact_path:str|Path,source_identity:dict[str,Any],semantic_metadata:dict[str,Any])->dict[str,Any]:
    p=Path(artifact_path);body={'schema':SCHEMA,'contract_id':contract_id,'artifact_sha256':sha_file(p),'artifact_bytes':p.stat().st_size,'source_identity':source_identity,'semantic_metadata':semantic_metadata,'truth':{'created_by_full_artifact_audit':True,'carried_mode_assumes_verified_object_remains_immutable':True,'audited_mode_must_reread_bytes':True}}
    body['proof_sha256']=digest(body);return body
def validate_proof(proof:dict[str,Any])->None:
    if proof.get('schema')!=SCHEMA:raise ValueError('unsupported reuse proof schema')
    stored=proof.get('proof_sha256');body=dict(proof);body.pop('proof_sha256',None)
    if digest(body)!=stored:raise ValueError('reuse proof integrity mismatch')
def carried_validate(*,proof:dict[str,Any],contract_id:str,artifact_ref:dict[str,Any])->dict[str,Any]:
    validate_proof(proof)
    if proof['contract_id']!=contract_id:raise ValueError('reuse proof contract mismatch')
    if artifact_ref.get('artifact_sha256')!=proof['artifact_sha256'] or int(artifact_ref.get('artifact_bytes',-1))!=int(proof['artifact_bytes']):raise ValueError('reuse ref identity mismatch')
    return {'mode':'carried_immutable_proof','contract_id':contract_id,'artifact_sha256':proof['artifact_sha256'],'proof_sha256':proof['proof_sha256'],'bytes_rehashed':0,'truth':{'artifact_bytes_not_reread':True,'prior_verification_reused':True,'out_of_band_mutation_not_rediscovered':True}}
def audited_validate(*,proof:dict[str,Any],contract_id:str,artifact_ref:dict[str,Any],artifact_path:str|Path)->dict[str,Any]:
    row=carried_validate(proof=proof,contract_id=contract_id,artifact_ref=artifact_ref);actual=sha_file(artifact_path)
    if actual!=proof['artifact_sha256']:raise ValueError('audited reuse artifact hash mismatch')
    row['mode']='audited_reuse';row['bytes_rehashed']=Path(artifact_path).stat().st_size;row['truth']={'artifact_bytes_reread':True,'prior_proof_binding_checked':True,'out_of_band_mutation_rediscovered':True};return row
