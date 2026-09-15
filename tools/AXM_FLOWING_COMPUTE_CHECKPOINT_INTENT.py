from __future__ import annotations
import hashlib,json,os
from pathlib import Path
from typing import Any
from AXM_FLOWING_COMPUTE_CHECKPOINT_SPINE import make_segment,make_record,canonical,sha,serialize_pointer
from AXM_FLOWING_COMPUTE_CHECKPOINT_TRANSACTION import recover,scan_segments,scan_checkpoint_spine,_validate_candidate
SCHEMA='axm.flowing-compute-checkpoint-commit-intent/v0.1'
def digest(v:Any)->str:return hashlib.sha256(canonical(v)).hexdigest()
def make_intent(*,current_recovery:dict[str,Any],segment:dict[str,Any],anchor:dict[str,Any],checkpoint_spine_path:str|Path)->dict[str,Any]:
    parent=current_recovery.get('record');pp=current_recovery.get('pointer')
    if parent is None:
        if int(segment['start_sequence'])!=1:raise ValueError('first intent must start at generation1')
        po=pl=None;parent_sha=None;parent_seq=None
    else:
        if int(segment['start_sequence'])!=int(parent['sequence'])+1 or int(segment['start'])!=int(parent['spine_prefix_bytes']):raise ValueError('intent target does not extend current parent')
        po=int(pp['offset']);pl=int(pp['length']);parent_sha=parent['checkpoint_sha256'];parent_seq=int(parent['sequence'])
    sobj=make_segment(segment);sraw=canonical(sobj);ssha=sha(sraw)
    rec=make_record(sequence=segment['end_sequence'],spine_prefix_bytes=segment['end'],segment_sha256=ssha,anchor=anchor,parent=parent,parent_offset=po,parent_len=pl);rraw=canonical(rec)
    spine_before=Path(checkpoint_spine_path).stat().st_size;ro=spine_before+4;rl=len(rraw);praw=serialize_pointer(rec['sequence'],ro,rl,rec['checkpoint_sha256'])
    body={'schema':SCHEMA,'parent_sequence':parent_seq,'parent_checkpoint_sha256':parent_sha,'target_sequence':int(rec['sequence']),'segment_sha256':ssha,'checkpoint_sha256':rec['checkpoint_sha256'],'checkpoint_offset':ro,'checkpoint_len':rl,'checkpoint_spine_before_bytes':spine_before,'target_pointer_sha256':sha(praw),'segment_object':sobj,'checkpoint_record':rec};body['intent_sha256']=digest(body);return body
def validate_intent(intent:dict[str,Any])->None:
    if intent.get('schema')!=SCHEMA:raise ValueError('bad intent schema')
    stored=intent.get('intent_sha256');body=dict(intent);body.pop('intent_sha256',None)
    if digest(body)!=stored:raise ValueError('intent integrity mismatch')
    if intent['segment_sha256']!=sha(canonical(intent['segment_object'])):raise ValueError('intent segment identity mismatch')
    if intent['checkpoint_sha256']!=intent['checkpoint_record']['checkpoint_sha256']:raise ValueError('intent checkpoint identity mismatch')
    praw=serialize_pointer(intent['target_sequence'],intent['checkpoint_offset'],intent['checkpoint_len'],intent['checkpoint_sha256'])
    if sha(praw)!=intent['target_pointer_sha256']:raise ValueError('intent pointer identity mismatch')
def write_intent(directory:str|Path,intent:dict[str,Any])->Path:
    validate_intent(intent);d=Path(directory);d.mkdir(parents=True,exist_ok=True);p=d/(intent['intent_sha256']+'.json')
    if p.exists():
        if json.loads(p.read_text())!=intent:raise ValueError('intent hash collision/content mismatch')
        return p
    tmp=p.with_name(p.name+'.tmp');raw=json.dumps(intent,sort_keys=True,separators=(',',':')).encode()
    with tmp.open('wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    os.replace(tmp,p);fd=os.open(str(d),os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)
    return p
def load_intents(directory:str|Path)->dict[str,Any]:
    valid=[];invalid=[]
    for p in sorted(Path(directory).glob('*.json')):
        try:i=json.loads(p.read_text());validate_intent(i);valid.append(i)
        except Exception as e:invalid.append({'path':p.name,'reason':str(e)})
    return {'valid':valid,'invalid':invalid}
def _write_pointer(path:Path,raw:bytes)->None:
    tmp=path.with_name(path.name+'.tmp')
    with tmp.open('wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path);fd=os.open(str(path.parent),os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)
def resume_intended_commit(*,intent_dir:str|Path,pointer_a:str|Path,pointer_b:str|Path,segment_store:str|Path,checkpoint_spine:str|Path,execute:bool=True)->dict[str,Any]:
    current=recover(pointer_a=pointer_a,pointer_b=pointer_b,segment_store=segment_store,checkpoint_spine=checkpoint_spine);loaded=load_intents(intent_dir);segs=scan_segments(segment_store);cps=scan_checkpoint_spine(checkpoint_spine)
    completed=[];eligible=[];pending=[];current_sha=(current.get('record') or {}).get('checkpoint_sha256');current_seq=current.get('selected_sequence')
    for i in loaded['valid']:
        if current_sha==i['checkpoint_sha256'] and int(current_seq)==int(i['target_sequence']):completed.append(i);continue
        if i['parent_checkpoint_sha256']!=current_sha or i['parent_sequence']!=current_seq:continue
        fake={'sequence':i['target_sequence'],'offset':i['checkpoint_offset'],'length':i['checkpoint_len'],'checkpoint_sha256':i['checkpoint_sha256']};ok,reason,_=_validate_candidate(fake,cps,segs)
        if ok:eligible.append(i)
        else:pending.append({'intent_sha256':i['intent_sha256'],'reason':reason})
    targets={(i['target_sequence'],i['checkpoint_sha256']) for i in eligible}
    if len(targets)>1:return {'status':'HOLD_AMBIGUOUS_INTENTS','current_sequence':current_seq,'eligible_intents':[i['intent_sha256'] for i in eligible],'invalid_intents':loaded['invalid']}
    if completed:return {'status':'ALREADY_COMMITTED','current_sequence':current_seq,'completed_intent_sha256':completed[0]['intent_sha256'],'invalid_intents':loaded['invalid']}
    if not eligible:return {'status':'NO_RESUMABLE_INTENT','current_sequence':current_seq,'pending':pending,'invalid_intents':loaded['invalid']}
    i=eligible[0];praw=serialize_pointer(i['target_sequence'],i['checkpoint_offset'],i['checkpoint_len'],i['checkpoint_sha256'])
    if sha(praw)!=i['target_pointer_sha256']:raise ValueError('resumed pointer does not match intent')
    if not execute:return {'status':'RESUMABLE_INTENT_FOUND','current_sequence':current_seq,'target_sequence':i['target_sequence'],'intent_sha256':i['intent_sha256']}
    target=Path(pointer_b) if current.get('selected_slot')=='A' else Path(pointer_a);_write_pointer(target,praw);after=recover(pointer_a=pointer_a,pointer_b=pointer_b,segment_store=segment_store,checkpoint_spine=checkpoint_spine)
    if after.get('selected_sequence')!=i['target_sequence']:raise RuntimeError('intent resume pointer commit failed')
    return {'status':'RESUMED_COMMIT','before_sequence':current_seq,'after_sequence':after['selected_sequence'],'intent_sha256':i['intent_sha256'],'target_slot':target.name,'truth':{'only_exact_durable_intent_can_resume':True,'arbitrary_unpointed_checkpoint_not_promoted':True,'parent_must_still_be_current':True}}
