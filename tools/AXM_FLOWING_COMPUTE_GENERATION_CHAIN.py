from __future__ import annotations
import hashlib,json
from typing import Any
SCHEMA='axm.flowing-compute-generation-chain/v0.1'
def canon(v:Any)->bytes: return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def h(v:Any)->str: return hashlib.sha256(canon(v)).hexdigest()
def make_chain(*,contract_id:str,initial_source_sha256:str,initial_state_sha256:str,transitions:list[dict[str,Any]])->dict[str,Any]:
    prev_source=initial_source_sha256; prev_state=initial_state_sha256; seen={initial_source_sha256:initial_state_sha256}; rows=[]
    for i,t in enumerate(transitions,1):
        if t.get('from_source_sha256')!=prev_source: raise ValueError(f'chain source discontinuity at {i}')
        if t.get('from_state_sha256')!=prev_state: raise ValueError(f'chain state discontinuity at {i}')
        if t.get('equivalence_passed') is not True: raise ValueError(f'cold equivalence missing at {i}')
        to_source=t['to_source_sha256']; to_state=t['to_state_sha256']
        if to_source in seen and seen[to_source]!=to_state: raise ValueError(f'deterministic drift: same source generation maps to different state at {i}')
        seen[to_source]=to_state
        row=dict(t); row['sequence']=i; row['prev_transition_sha256']=rows[-1]['transition_sha256'] if rows else None
        body=dict(row); body.pop('transition_sha256',None); row['transition_sha256']=h(body); rows.append(row); prev_source=to_source; prev_state=to_state
    value={'schema':SCHEMA,'contract_id':contract_id,'initial_source_sha256':initial_source_sha256,'initial_state_sha256':initial_state_sha256,'transition_count':len(rows),'transitions':rows,'final_source_sha256':prev_source,'final_state_sha256':prev_state,'truth':{'contiguous_source_generations':True,'contiguous_state_generations':True,'cold_equivalence_required_each_generation':True,'same_source_requires_same_deterministic_state':True}}
    value['chain_sha256']=h(value); return value
def validate_chain(value:dict[str,Any])->None:
    if value.get('schema')!=SCHEMA: raise ValueError('unsupported generation chain schema')
    stored=value.get('chain_sha256'); body=dict(value); body.pop('chain_sha256',None)
    if h(body)!=stored: raise ValueError('generation chain integrity mismatch')
    rebuilt=make_chain(contract_id=value['contract_id'],initial_source_sha256=value['initial_source_sha256'],initial_state_sha256=value['initial_state_sha256'],transitions=[{k:v for k,v in r.items() if k not in ('sequence','prev_transition_sha256','transition_sha256')} for r in value['transitions']])
    if rebuilt['chain_sha256']!=stored: raise ValueError('generation chain semantic validation mismatch')
