from __future__ import annotations
from pathlib import Path
from typing import Any
from AXM_FLOWING_COMPUTE_CHECKPOINT_INTENT import load_intents,_write_pointer
from AXM_FLOWING_COMPUTE_CHECKPOINT_TRANSACTION import recover,scan_segments,scan_checkpoint_spine,_validate_candidate
from AXM_FLOWING_COMPUTE_CHECKPOINT_SPINE import serialize_pointer,sha

def resolve_exact_intent(*,selected_intent_sha256:str,intent_dir:str|Path,pointer_a:str|Path,pointer_b:str|Path,segment_store:str|Path,checkpoint_spine:str|Path,execute:bool=True)->dict[str,Any]:
    current=recover(pointer_a=pointer_a,pointer_b=pointer_b,segment_store=segment_store,checkpoint_spine=checkpoint_spine);loaded=load_intents(intent_dir)
    matches=[i for i in loaded['valid'] if i['intent_sha256']==selected_intent_sha256]
    if len(matches)!=1:return {'status':'HOLD_SELECTED_INTENT_NOT_FOUND_OR_INVALID','current_sequence':current.get('selected_sequence'),'invalid_intents':loaded['invalid']}
    i=matches[0];current_sha=(current.get('record') or {}).get('checkpoint_sha256');current_seq=current.get('selected_sequence')
    if current_sha==i['checkpoint_sha256'] and int(current_seq)==int(i['target_sequence']):return {'status':'ALREADY_COMMITTED','current_sequence':current_seq,'intent_sha256':i['intent_sha256']}
    if i['parent_checkpoint_sha256']!=current_sha or i['parent_sequence']!=current_seq:return {'status':'HOLD_SELECTED_INTENT_PARENT_NOT_CURRENT','current_sequence':current_seq,'intent_sha256':i['intent_sha256']}
    segs=scan_segments(segment_store);cps=scan_checkpoint_spine(checkpoint_spine);fake={'sequence':i['target_sequence'],'offset':i['checkpoint_offset'],'length':i['checkpoint_len'],'checkpoint_sha256':i['checkpoint_sha256']};ok,reason,_=_validate_candidate(fake,cps,segs)
    if not ok:return {'status':'HOLD_SELECTED_INTENT_DEPENDENCIES_INVALID','current_sequence':current_seq,'intent_sha256':i['intent_sha256'],'reason':reason}
    praw=serialize_pointer(i['target_sequence'],i['checkpoint_offset'],i['checkpoint_len'],i['checkpoint_sha256'])
    if sha(praw)!=i['target_pointer_sha256']:raise ValueError('selected intent target pointer identity mismatch')
    if not execute:return {'status':'SELECTED_INTENT_RESUMABLE','current_sequence':current_seq,'target_sequence':i['target_sequence'],'intent_sha256':i['intent_sha256']}
    target=Path(pointer_b) if current.get('selected_slot')=='A' else Path(pointer_a);_write_pointer(target,praw);after=recover(pointer_a=pointer_a,pointer_b=pointer_b,segment_store=segment_store,checkpoint_spine=checkpoint_spine)
    if after.get('selected_sequence')!=i['target_sequence'] or (after.get('record') or {}).get('checkpoint_sha256')!=i['checkpoint_sha256']:raise RuntimeError('selected intent did not become exact current target')
    return {'status':'RESOLVED_SELECTED_INTENT','before_sequence':current_seq,'after_sequence':after['selected_sequence'],'intent_sha256':i['intent_sha256'],'checkpoint_sha256':i['checkpoint_sha256'],'truth':{'ambiguity_requires_explicit_intent_identity':True,'no_order_or_timestamp_tiebreak':True,'unselected_intents_preserved':True}}
