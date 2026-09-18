from __future__ import annotations
import hashlib,json
from typing import Any
SCHEMA='axm.flowing-compute-reuse-mode-plan/v0.1'
MODES={'carried_immutable_proof','audited_reuse'}
def canon(v:Any)->bytes:return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def digest(v:Any)->str:return hashlib.sha256(canon(v)).hexdigest()
def bind(*,base_plan_receipt:dict[str,Any],reuse_modes:dict[str,dict[str,Any]])->dict[str,Any]:
    plan=base_plan_receipt['plan'];reuse=set(plan['dependency_route']['reuse_contracts'])
    if set(reuse_modes)!=reuse:raise ValueError('reuse-mode contract set mismatch')
    rows={}
    for cid in sorted(reuse):
        row=reuse_modes[cid];mode=row.get('mode');proof=row.get('proof_sha256')
        if mode not in MODES:raise ValueError('unsupported reuse verification mode')
        if not proof:raise ValueError('reuse proof identity required')
        rows[cid]={'mode':mode,'proof_sha256':proof}
    body={'schema':SCHEMA,'base_plan_receipt_sha256':base_plan_receipt['plan_receipt_sha256'],'reuse_verification':rows,'truth':{'reuse_trust_mode_is_planned_not_executor_discretion':True,'carried_and_audited_modes_are_not_equivalent_claims':True}}
    body['reuse_mode_plan_sha256']=digest(body);return body
def validate(value:dict[str,Any],base_plan_receipt:dict[str,Any])->None:
    if value.get('schema')!=SCHEMA:raise ValueError('unsupported reuse-mode plan schema')
    stored=value.get('reuse_mode_plan_sha256');body=dict(value);body.pop('reuse_mode_plan_sha256',None)
    if digest(body)!=stored:raise ValueError('reuse-mode plan integrity mismatch')
    if value['base_plan_receipt_sha256']!=base_plan_receipt['plan_receipt_sha256']:raise ValueError('reuse-mode plan bound to wrong base plan')
    reuse=set(base_plan_receipt['plan']['dependency_route']['reuse_contracts'])
    if set(value.get('reuse_verification') or {})!=reuse:raise ValueError('reuse-mode plan contract set mismatch')
    for row in value['reuse_verification'].values():
        if row.get('mode') not in MODES or not row.get('proof_sha256'):raise ValueError('invalid reuse-mode row')
