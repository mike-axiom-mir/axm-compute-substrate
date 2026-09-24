from __future__ import annotations
import hashlib, os, struct
from pathlib import Path
from typing import Any
from AXM_FLOWING_COMPUTE_CHECKPOINT_SPINE import parse_pointer as parse_legacy_pointer, serialize_pointer as serialize_legacy_pointer, sha
from AXM_FLOWING_COMPUTE_CHECKPOINT_TRANSACTION import scan_segments, scan_checkpoint_spine, _validate_candidate
from AXM_FLOWING_COMPUTE_CHECKPOINT_INTENT import load_intents, validate_intent

MAGIC=b'AXAP36\x00\x01'

def sh(raw:bytes)->bytes:return hashlib.sha256(raw).digest()

def serialize_authorized_pointer(sequence:int,offset:int,length:int,checkpoint_sha256:str,intent_sha256:str)->bytes:
    if len(checkpoint_sha256)!=64 or len(intent_sha256)!=64:raise ValueError('authorized pointer hash shape')
    body=MAGIC+struct.pack('>IQI',int(sequence),int(offset),int(length))+bytes.fromhex(checkpoint_sha256)+bytes.fromhex(intent_sha256)
    return body+sh(body)

def parse_authorized_pointer(raw:bytes)->dict[str,Any]:
    need=len(MAGIC)+4+8+4+32+32+32
    if len(raw)!=need or not raw.startswith(MAGIC):raise ValueError('bad authorized pointer shape')
    body,stored=raw[:-32],raw[-32:]
    if sh(body)!=stored:raise ValueError('authorized pointer integrity mismatch')
    off=len(MAGIC);seq,po,pl=struct.unpack('>IQI',body[off:off+16]);off+=16
    checkpoint=body[off:off+32].hex();off+=32;intent=body[off:off+32].hex()
    return {'schema':'axm.flowing-compute-authorized-checkpoint-pointer/v0.1','sequence':seq,'offset':po,'length':pl,'checkpoint_sha256':checkpoint,'intent_sha256':intent,'provenance_bound':True}

def parse_any_pointer(raw:bytes)->dict[str,Any]:
    try:return parse_authorized_pointer(raw)
    except Exception:
        p=parse_legacy_pointer(raw);return {'schema':'axm.flowing-compute-legacy-checkpoint-pointer/v0.1',**p,'intent_sha256':None,'provenance_bound':False}

def _load_exact_intent(intent_dir:str|Path,intent_sha256:str)->dict[str,Any]|None:
    loaded=load_intents(intent_dir)
    matches=[i for i in loaded['valid'] if i['intent_sha256']==intent_sha256]
    return matches[0] if len(matches)==1 else None

def validate_pointer_provenance(pointer:dict[str,Any],record:dict[str,Any],intent_dir:str|Path)->tuple[bool,str,dict[str,Any]|None]:
    if not pointer.get('provenance_bound'):
        return True,'legacy_unbound',None
    i=_load_exact_intent(intent_dir,pointer['intent_sha256'])
    if i is None:return False,'bound_intent_missing_or_invalid',None
    try:validate_intent(i)
    except Exception:return False,'bound_intent_invalid',None
    if int(i['target_sequence'])!=int(pointer['sequence']) or i['checkpoint_sha256']!=pointer['checkpoint_sha256'] or int(i['checkpoint_offset'])!=int(pointer['offset']) or int(i['checkpoint_len'])!=int(pointer['length']):
        return False,'bound_intent_target_mismatch',None
    if i['checkpoint_record']['checkpoint_sha256']!=record['checkpoint_sha256']:
        return False,'bound_intent_record_mismatch',None
    if i['parent_checkpoint_sha256']!=record.get('parent_checkpoint_sha256'):
        return False,'bound_intent_parent_mismatch',None
    legacy=serialize_legacy_pointer(pointer['sequence'],pointer['offset'],pointer['length'],pointer['checkpoint_sha256'])
    if sha(legacy)!=i['target_pointer_sha256']:
        return False,'bound_intent_legacy_target_mismatch',None
    return True,'verified_intent',i

def read_pointer(path:str|Path)->dict[str,Any]:
    p=Path(path)
    if not p.is_file():return {'valid':False,'reason':'missing'}
    try:return {'valid':True,'pointer':parse_any_pointer(p.read_bytes())}
    except Exception as e:return {'valid':False,'reason':str(e)}

def recover_authorized(*,pointer_a:str|Path,pointer_b:str|Path,segment_store:str|Path,checkpoint_spine:str|Path,intent_dir:str|Path)->dict[str,Any]:
    segs=scan_segments(segment_store);cps=scan_checkpoint_spine(checkpoint_spine);slots=[]
    for name,path in [('A',pointer_a),('B',pointer_b)]:
        item=read_pointer(path);row={'slot':name,**item}
        if item['valid']:
            ok,reason,rec=_validate_candidate(item['pointer'],cps,segs);row['dependency_valid']=ok;row['dependency_reason']=reason;row['record']=rec
            if ok:
                pok,preason,intent=validate_pointer_provenance(item['pointer'],rec,intent_dir);row['provenance_valid']=pok;row['provenance_reason']=preason;row['intent']=intent
            else:
                row['provenance_valid']=False;row['provenance_reason']='dependency_invalid'
        else:
            row['dependency_valid']=False;row['provenance_valid']=False
        slots.append(row)
    valid=[r for r in slots if r.get('valid') and r.get('dependency_valid') and r.get('provenance_valid')];valid.sort(key=lambda r:int(r['pointer']['sequence']),reverse=True)
    if not valid:return {'status':'HOLD_NO_VALID_PROVENANCE_POINTER','selected_sequence':None,'pointer_slots':slots}
    s=valid[0]
    return {'schema':'axm.flowing-compute-authorized-pointer-recovery/v0.1','status':'RECOVERED_COMMITTED','selected_slot':s['slot'],'selected_sequence':int(s['pointer']['sequence']),'pointer':s['pointer'],'record':s['record'],'intent_sha256':s['pointer'].get('intent_sha256'),'provenance_status':'VERIFIED_INTENT' if s['pointer'].get('provenance_bound') else 'LEGACY_UNBOUND','pointer_slots':slots,'truth':{'current_checkpoint_identity_bound_to_prior_intent_when_available':True,'legacy_pointer_never_falsely_claims_intent_provenance':True,'missing_or_corrupt_bound_intent_invalidates_provenance_pointer':True}}

def _atomic(path:Path,raw:bytes)->None:
    tmp=path.with_name(path.name+'.tmp')
    with tmp.open('wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path);fd=os.open(str(path.parent),os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)

def resolve_exact_intent_authorized(*,selected_intent_sha256:str,intent_dir:str|Path,pointer_a:str|Path,pointer_b:str|Path,segment_store:str|Path,checkpoint_spine:str|Path,execute:bool=True)->dict[str,Any]:
    current=recover_authorized(pointer_a=pointer_a,pointer_b=pointer_b,segment_store=segment_store,checkpoint_spine=checkpoint_spine,intent_dir=intent_dir)
    loaded=load_intents(intent_dir);matches=[i for i in loaded['valid'] if i['intent_sha256']==selected_intent_sha256]
    if len(matches)!=1:return {'status':'HOLD_SELECTED_INTENT_NOT_FOUND_OR_INVALID','current_sequence':current.get('selected_sequence')}
    i=matches[0];current_sha=(current.get('record') or {}).get('checkpoint_sha256');current_seq=current.get('selected_sequence')
    if current_sha==i['checkpoint_sha256'] and int(current_seq)==int(i['target_sequence']):
        if current.get('intent_sha256')==i['intent_sha256']:return {'status':'ALREADY_COMMITTED_WITH_INTENT','current_sequence':current_seq,'intent_sha256':i['intent_sha256']}
        return {'status':'HOLD_TARGET_ALREADY_CURRENT_WITH_DIFFERENT_OR_LEGACY_PROVENANCE','current_sequence':current_seq,'intent_sha256':i['intent_sha256']}
    if i['parent_checkpoint_sha256']!=current_sha or i['parent_sequence']!=current_seq:return {'status':'HOLD_SELECTED_INTENT_PARENT_NOT_CURRENT','current_sequence':current_seq,'intent_sha256':i['intent_sha256']}
    segs=scan_segments(segment_store);cps=scan_checkpoint_spine(checkpoint_spine);fake={'sequence':i['target_sequence'],'offset':i['checkpoint_offset'],'length':i['checkpoint_len'],'checkpoint_sha256':i['checkpoint_sha256']};ok,reason,_=_validate_candidate(fake,cps,segs)
    if not ok:return {'status':'HOLD_SELECTED_INTENT_DEPENDENCIES_INVALID','reason':reason,'current_sequence':current_seq,'intent_sha256':i['intent_sha256']}
    raw=serialize_authorized_pointer(i['target_sequence'],i['checkpoint_offset'],i['checkpoint_len'],i['checkpoint_sha256'],i['intent_sha256'])
    if not execute:return {'status':'SELECTED_INTENT_AUTHORIZED_POINTER_READY','target_sequence':i['target_sequence'],'intent_sha256':i['intent_sha256'],'pointer_bytes':len(raw)}
    target=Path(pointer_b) if current.get('selected_slot')=='A' else Path(pointer_a);_atomic(target,raw)
    after=recover_authorized(pointer_a=pointer_a,pointer_b=pointer_b,segment_store=segment_store,checkpoint_spine=checkpoint_spine,intent_dir=intent_dir)
    if after.get('selected_sequence')!=i['target_sequence'] or after.get('intent_sha256')!=i['intent_sha256']:raise RuntimeError('authorized intent pointer commit failed')
    return {'status':'RESOLVED_SELECTED_INTENT_WITH_PROVENANCE','before_sequence':current_seq,'after_sequence':after['selected_sequence'],'intent_sha256':i['intent_sha256'],'checkpoint_sha256':i['checkpoint_sha256'],'target_slot':target.name,'pointer_bytes':len(raw),'truth':{'intent_identity_committed_atomically_with_checkpoint_pointer':True,'post_recovery_can_name_prior_authorization':True,'unselected_intents_preserved':True}}
