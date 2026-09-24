from __future__ import annotations
import hashlib,json
from typing import Any

def canon(v:Any)->bytes:
    return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def digest(v:Any)->str:
    return hashlib.sha256(canon(v)).hexdigest()
def bytes_sha(raw:bytes)->str:
    return hashlib.sha256(raw).hexdigest()

def build_execution_receipt(*,plan_receipt:dict[str,Any],contract_rows:list[dict[str,Any]])->dict[str,Any]:
    plan_hash=plan_receipt.get('plan_receipt_sha256')
    if not plan_hash: raise ValueError('plan receipt identity required')
    actions=plan_receipt['plan']['actions']
    by_contract={r['contract_id']:r for r in contract_rows}
    if set(by_contract)!=set(actions):raise ValueError('execution contract set does not match plan')
    normalized=[]
    for cid in sorted(actions):
        row=by_contract[cid]
        if row.get('planned_action')!=actions[cid]['action']:raise ValueError('execution row planned_action disagrees with plan for '+cid)
        if row.get('actual_action')!=actions[cid]['action']:raise ValueError('actual execution action disagrees with plan for '+cid)
        if not row.get('executor_id'):raise ValueError('executor identity required')
        if float(row.get('cpu_ns',-1))<0:raise ValueError('cpu_ns invalid')
        if not row.get('result_ref'):raise ValueError('result_ref required')
        normalized.append(row)
    body={'schema':'axm.flowing-compute-plan-execution-receipt/v0.1','plan_receipt_sha256':plan_hash,'contracts':normalized,'truth':{'execution_path_is_evidence_not_authority':True,'plan_action_must_equal_actual_action':True,'artifact_validation_remains_separate':True,'cpu_time_is_not_joules':True}}
    body['execution_receipt_sha256']=digest(body);return body

def validate_execution_receipt(receipt:dict[str,Any],plan_receipt:dict[str,Any])->None:
    if receipt.get('schema')!='axm.flowing-compute-plan-execution-receipt/v0.1':raise ValueError('unsupported execution receipt schema')
    stored=receipt.get('execution_receipt_sha256');body=dict(receipt);body.pop('execution_receipt_sha256',None)
    if digest(body)!=stored:raise ValueError('execution receipt integrity mismatch')
    if receipt.get('plan_receipt_sha256')!=plan_receipt.get('plan_receipt_sha256'):raise ValueError('execution receipt bound to wrong plan')
    actions=plan_receipt['plan']['actions'];rows=receipt.get('contracts') or []
    if len(rows)!=len(actions):raise ValueError('execution receipt contract count mismatch')
    seen=set()
    for row in rows:
        cid=row.get('contract_id')
        if cid in seen:raise ValueError('duplicate execution contract row')
        seen.add(cid)
        if cid not in actions:raise ValueError('unexpected execution contract')
        expected=actions[cid]['action']
        if row.get('planned_action')!=expected or row.get('actual_action')!=expected:raise ValueError('execution action mismatch for '+cid)
        if not row.get('result_ref'):raise ValueError('missing result ref')
    if seen!=set(actions):raise ValueError('missing execution contract row')
