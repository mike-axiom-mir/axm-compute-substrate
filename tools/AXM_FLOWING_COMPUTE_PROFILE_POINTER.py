from __future__ import annotations
from typing import Any

def move_pointer(*, current_pointer:dict[str,Any]|None, target_generation:dict[str,Any], known_generations:dict[str,dict[str,Any]], mode:str)->dict[str,Any]:
    if mode not in ('promote','rollback'): raise ValueError('mode must be promote or rollback')
    target=target_generation.get('generation_sha256'); contract=target_generation.get('contract_id')
    if not target or known_generations.get(target) is not target_generation: raise ValueError('target generation is not in known generation store')
    if current_pointer and current_pointer.get('contract_id')!=contract: raise ValueError('pointer contract mismatch')
    current_hash=current_pointer.get('generation_sha256') if current_pointer else None
    if mode=='promote':
        if target_generation.get('parent_generation_sha256')!=current_hash: raise ValueError('promotion target is not direct child of current generation')
        if target_generation.get('status') not in ('CURRENT','CANDIDATE'): raise ValueError('promotion target status is not promotable')
    else:
        if not current_hash: raise ValueError('rollback requires current generation')
        cursor=known_generations.get(current_hash); found=False
        while cursor:
            parent=cursor.get('parent_generation_sha256')
            if parent==target: found=True; break
            cursor=known_generations.get(parent)
        if not found: raise ValueError('rollback target is not an ancestor of current generation')
    return {'schema':'axm.flowing-compute-current-profile-pointer/v0.1','contract_id':contract,'generation_sha256':target,'move':mode,'previous_generation_sha256':current_hash}
