from __future__ import annotations
import hashlib, json
from pathlib import Path
from typing import Any

LEDGER_SCHEMA='axm.flowing-compute-calibration-ledger-entry/v0.1'
GEN_SCHEMA='axm.flowing-compute-policy-generation/v0.1'

def canonical(value:Any)->bytes:
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()

def digest(value:Any)->str:
    return hashlib.sha256(canonical(value)).hexdigest()

def read_entries(path:str|Path)->list[dict[str,Any]]:
    p=Path(path)
    if not p.is_file(): return []
    out=[]; prev=None
    for line_no,line in enumerate(p.read_text().splitlines(),1):
        if not line.strip(): continue
        e=json.loads(line)
        if e.get('schema')!=LEDGER_SCHEMA: raise ValueError(f'bad ledger schema line {line_no}')
        stored=e.get('entry_sha256'); body=dict(e); body.pop('entry_sha256',None)
        if digest(body)!=stored: raise ValueError(f'ledger hash mismatch line {line_no}')
        if e.get('prev_entry_sha256')!=prev: raise ValueError(f'ledger chain mismatch line {line_no}')
        prev=stored; out.append(e)
    return out

def append_observation(path:str|Path, observation:dict[str,Any], *, expected_contract_id:str)->dict[str,Any]:
    entries=read_entries(path); prev=entries[-1]['entry_sha256'] if entries else None
    reasons=[]
    if observation.get('contract_id')!=expected_contract_id: reasons.append('contract_mismatch')
    if observation.get('equivalence_passed') is not True: reasons.append('equivalence_not_verified')
    feats=observation.get('features')
    if not isinstance(feats,dict) or not feats: reasons.append('missing_features')
    for key in ('actual_global_cpu_ns','actual_incremental_cpu_ns'):
        try:
            if float(observation.get(key,0))<=0: reasons.append('invalid_'+key)
        except Exception: reasons.append('invalid_'+key)
    entry={'schema':LEDGER_SCHEMA,'sequence':len(entries)+1,'prev_entry_sha256':prev,'status':'REJECTED' if reasons else 'ACCEPTED','reasons':reasons,'observation':observation}
    entry['entry_sha256']=digest(entry)
    with Path(path).open('a',encoding='utf-8') as f: f.write(json.dumps(entry,sort_keys=True,separators=(',',':'))+'\n')
    return entry

def _cost(model:dict[str,Any], features:dict[str,float])->float:
    total=float(model.get('intercept',0.0))
    for k,v in features.items(): total+=float(model.get(k,0.0))*float(v)
    return total

def route(profile:dict[str,Any], features:dict[str,float])->str:
    pg=_cost(profile['models']['global_cpu_ns'],features); pi=_cost(profile['models']['incremental_cpu_ns'],features)
    return 'incremental' if pi<pg else 'global'

def evaluate(profile:dict[str,Any], observations:list[dict[str,Any]])->dict[str,Any]:
    rows=[]
    for o in observations:
        decision=route(profile,o['features'])
        g=float(o['actual_global_cpu_ns']); i=float(o['actual_incremental_cpu_ns']); actual='incremental' if i<g else 'global'
        regret=0.0 if decision==actual else abs(g-i)/min(g,i)*100.0
        rows.append({'decision':decision,'actual':actual,'correct':decision==actual,'regret_percent':regret,'features':o['features']})
    return {'decisions':len(rows),'correct':sum(x['correct'] for x in rows),'accuracy':sum(x['correct'] for x in rows)/len(rows) if rows else None,'mean_regret_percent':sum(x['regret_percent'] for x in rows)/len(rows) if rows else None,'max_regret_percent':max((x['regret_percent'] for x in rows),default=0.0),'rows':rows}
