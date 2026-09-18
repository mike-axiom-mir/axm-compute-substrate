from __future__ import annotations
import hashlib,json
from pathlib import Path
from typing import Any
from AXM_FLOWING_COMPUTE_LIVE_POINTER import seal_from_pointer
from AXM_FLOWING_COMPUTE_LIVE_SEGMENT_ACCUMULATOR import audit_spine_segment
SCHEMA='axm.flowing-compute-recovery-checkpoint/v0.3'

def canonical(v:Any)->bytes:return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def digest(v:Any)->str:return hashlib.sha256(canonical(v)).hexdigest()

def validate_checkpoint(cp:dict[str,Any])->None:
    if cp.get('schema')!=SCHEMA:raise ValueError('unsupported live checkpoint schema')
    stored=cp.get('checkpoint_sha256');body=dict(cp);body.pop('checkpoint_sha256',None)
    if digest(body)!=stored:raise ValueError('live checkpoint integrity mismatch')
    segs=list(cp.get('segments') or [])
    if not segs:raise ValueError('live checkpoint needs segment history')
    expected_start=8;prev_end_seq=0
    for s in segs:
        if int(s['start'])!=expected_start or int(s['start_sequence'])!=prev_end_seq+1:raise ValueError('live checkpoint segment history gap')
        if int(s['record_count'])!=int(s['end_sequence'])-int(s['start_sequence'])+1:raise ValueError('live checkpoint record-count mismatch')
        expected_start=int(s['end']);prev_end_seq=int(s['end_sequence'])
    if int(cp['sequence'])!=prev_end_seq or int(cp['spine_prefix_bytes'])!=expected_start:raise ValueError('live checkpoint coverage mismatch')
    a=cp.get('anchor') or {}
    if int(a.get('generation_offset',-1))+int(a.get('generation_len',-1))!=int(cp['spine_prefix_bytes']):raise ValueError('live checkpoint anchor/prefix mismatch')

def write_checkpoint(path:str|Path,cp:dict[str,Any])->None:
    validate_checkpoint(cp);Path(path).write_text(json.dumps(cp,sort_keys=True,separators=(',',':'))+'\n')
def load_checkpoint(path:str|Path)->dict[str,Any]:
    cp=json.loads(Path(path).read_text());validate_checkpoint(cp);return cp

def finalize_from_pointer(*,pointer:dict[str,Any],previous_checkpoint:dict[str,Any]|None)->dict[str,Any]:
    seal=seal_from_pointer(pointer);seg=seal['segment']
    if previous_checkpoint is None:
        if int(seg['start_sequence'])!=1 or int(seg['start'])!=8:raise ValueError('HOLD: previous checkpoint history required')
        segments=[seg];parent=None
    else:
        validate_checkpoint(previous_checkpoint)
        if int(seg['start_sequence'])!=int(previous_checkpoint['sequence'])+1 or int(seg['start'])!=int(previous_checkpoint['spine_prefix_bytes']):raise ValueError('HOLD: completed pointer segment does not extend previous checkpoint')
        segments=list(previous_checkpoint['segments'])+[seg];parent=previous_checkpoint['checkpoint_sha256']
    cp={'schema':SCHEMA,'sequence':int(pointer['sequence']),'spine_prefix_bytes':int(seg['end']),'segments':segments,'parent_checkpoint_sha256':parent,'anchor':seal['anchor'],'truth':{'newest_segment_sealed_from_committed_pointer':True,'newest_segment_spine_reread_required':False,'previous_history_required_after_first_segment':True,'checkpoint_not_state_authority':True}}
    cp['checkpoint_sha256']=digest(cp);validate_checkpoint(cp);return cp

def audit_checkpoint(spine_path:str|Path,cp:dict[str,Any])->dict[str,Any]:
    validate_checkpoint(cp);rows=[]
    for s in cp['segments']:
        r=audit_spine_segment(spine_path,s);rows.append(r)
        if not r['passed']:return {'passed':False,'rows':rows}
    return {'passed':True,'rows':rows,'segments':len(rows),'records':sum(x['records'] for x in rows)}
