from __future__ import annotations
import hashlib,os,struct
from pathlib import Path
from typing import Any
from AXM_FLOWING_COMPUTE_CHECKPOINT_SPINE import parse_pointer as parse_legacy_pointer
from AXM_FLOWING_COMPUTE_AUTHORIZED_POINTER import parse_authorized_pointer,validate_pointer_provenance
from AXM_FLOWING_COMPUTE_CHECKPOINT_TRANSACTION import scan_segments,scan_checkpoint_spine,_validate_candidate
from AXM_FLOWING_COMPUTE_CHECKPOINT_INTENT import load_intents,validate_intent
from AXM_FLOWING_COMPUTE_AUTHORIZATION_RECEIPTS import ReceiptStore,make_receipt,validate_receipt_chain,validate_receipt

MAGIC=b'AXAR38P\x00'
def sh(raw:bytes)->bytes:return hashlib.sha256(raw).digest()
def serialize_fast_pointer(sequence:int,checkpoint_offset:int,checkpoint_len:int,checkpoint_sha256:str,receipt_offset:int,receipt_len:int,receipt_sha256:str)->bytes:
    body=MAGIC+struct.pack('>IQI',int(sequence),int(checkpoint_offset),int(checkpoint_len))+bytes.fromhex(checkpoint_sha256)+struct.pack('>QI',int(receipt_offset),int(receipt_len))+bytes.fromhex(receipt_sha256);return body+sh(body)
def parse_fast_pointer(raw:bytes)->dict[str,Any]:
    need=len(MAGIC)+16+32+12+32+32
    if len(raw)!=need or not raw.startswith(MAGIC):raise ValueError('bad fast authorization pointer shape')
    body,stored=raw[:-32],raw[-32:]
    if sh(body)!=stored:raise ValueError('fast authorization pointer integrity mismatch')
    off=len(MAGIC);seq,co,cl=struct.unpack('>IQI',body[off:off+16]);off+=16;ch=body[off:off+32].hex();off+=32;ro,rl=struct.unpack('>QI',body[off:off+12]);off+=12;rh=body[off:off+32].hex()
    return {'schema':'axm.flowing-compute-fast-authorization-pointer/v0.1','sequence':seq,'offset':co,'length':cl,'checkpoint_sha256':ch,'receipt_offset':ro,'receipt_len':rl,'receipt_sha256':rh}
def parse_any(raw:bytes)->dict[str,Any]:
    try:return parse_fast_pointer(raw)
    except Exception:pass
    try:
        p=parse_authorized_pointer(raw);return {**p,'receipt_sha256':None}
    except Exception:pass
    p=parse_legacy_pointer(raw);return {'schema':'axm.flowing-compute-legacy-checkpoint-pointer/v0.1',**p,'intent_sha256':None,'receipt_sha256':None}
def read_pointer(path:str|Path)->dict[str,Any]:
    p=Path(path)
    if not p.is_file():return {'valid':False,'reason':'missing'}
    try:return {'valid':True,'pointer':parse_any(p.read_bytes())}
    except Exception as e:return {'valid':False,'reason':str(e)}
def _intent(intent_dir:str|Path,h:str)->dict[str,Any]|None:
    m=[i for i in load_intents(intent_dir)['valid'] if i['intent_sha256']==h];return m[0] if len(m)==1 else None
def validate_tip(*,pointer:dict[str,Any],record:dict[str,Any],store:ReceiptStore,intent_dir:str|Path)->tuple[bool,str,dict[str,Any]|None]:
    try:r=store.get_at(pointer['receipt_offset'],pointer['receipt_len'],pointer['receipt_sha256']);validate_receipt(r)
    except Exception as e:return False,'current_receipt_invalid:'+str(e),None
    if int(r['sequence'])!=int(pointer['sequence']) or r['checkpoint_sha256']!=pointer['checkpoint_sha256'] or int(r['checkpoint_offset'])!=int(pointer['offset']) or int(r['checkpoint_len'])!=int(pointer['length']):return False,'current_receipt_pointer_mismatch',None
    if r['parent_checkpoint_sha256']!=record.get('parent_checkpoint_sha256'):return False,'current_receipt_parent_mismatch',None
    i=_intent(intent_dir,r['intent_sha256'])
    if i is None:return False,'current_receipt_intent_missing_or_invalid',None
    try:validate_intent(i)
    except Exception as e:return False,'current_receipt_intent_invalid:'+str(e),None
    if i['checkpoint_sha256']!=r['checkpoint_sha256'] or int(i['target_sequence'])!=int(r['sequence']):return False,'current_receipt_intent_target_mismatch',None
    return True,'carried_current_receipt_verified',r

def recover_fast(*,mode:str,pointer_a:str|Path,pointer_b:str|Path,segment_store:str|Path,checkpoint_spine:str|Path,intent_dir:str|Path,receipt_store:str|Path)->dict[str,Any]:
    if mode not in ('carried','audited'):raise ValueError('mode must be carried or audited')
    segs=scan_segments(segment_store);cps=scan_checkpoint_spine(checkpoint_spine);store=ReceiptStore(receipt_store);slots=[]
    for name,path in [('A',pointer_a),('B',pointer_b)]:
        item=read_pointer(path);row={'slot':name,**item}
        if not item['valid']:row['valid_for_mode']=False;slots.append(row);continue
        p=item['pointer'];ok,reason,rec=_validate_candidate(p,cps,segs);row['dependency_valid']=ok;row['dependency_reason']=reason;row['record']=rec
        if not ok:row['valid_for_mode']=False;slots.append(row);continue
        if p.get('receipt_sha256') and 'receipt_offset' in p:
            if mode=='carried':pok,preason,r=validate_tip(pointer=p,record=rec,store=store,intent_dir=intent_dir);row['provenance_valid']=pok;row['provenance_reason']=preason;row['current_receipt']=r
            else:
                try:chain=validate_receipt_chain(receipt_sha256=p['receipt_sha256'],store=store,intent_dir=intent_dir,cps=cps,segs=segs);pok=True;preason='audited_full_receipt_chain';row['receipt_chain']=chain
                except Exception as e:pok=False;preason='receipt_chain_invalid:'+str(e)
                row['provenance_valid']=pok;row['provenance_reason']=preason
        elif p.get('intent_sha256'):
            pok,preason,intent=validate_pointer_provenance(p,rec,intent_dir);row['provenance_valid']=pok;row['provenance_reason']=preason;row['intent']=intent
        else:row['provenance_valid']=True;row['provenance_reason']='legacy_unbound'
        row['valid_for_mode']=bool(row.get('dependency_valid') and row.get('provenance_valid'));slots.append(row)
    valid=[r for r in slots if r.get('valid_for_mode')];valid.sort(key=lambda r:int(r['pointer']['sequence']),reverse=True)
    if not valid:return {'status':'HOLD_NO_VALID_POINTER_FOR_AUTHORIZATION_MODE','mode':mode,'selected_sequence':None,'pointer_slots':slots}
    s=valid[0];p=s['pointer'];return {'status':'RECOVERED_COMMITTED','mode':mode,'selected_slot':s['slot'],'selected_sequence':int(p['sequence']),'pointer':p,'record':s['record'],'provenance_status':s['provenance_reason'],'pointer_slots':slots}

def _atomic(path:Path,raw:bytes)->None:
    tmp=path.with_name(path.name+'.tmp')
    with tmp.open('wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path);fd=os.open(str(path.parent),os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)

def commit_selected_fast(*,selected_intent_sha256:str,intent_dir:str|Path,receipt_store:str|Path,pointer_a:str|Path,pointer_b:str|Path,segment_store:str|Path,checkpoint_spine:str|Path)->dict[str,Any]:
    current=recover_fast(mode='carried',pointer_a=pointer_a,pointer_b=pointer_b,segment_store=segment_store,checkpoint_spine=checkpoint_spine,intent_dir=intent_dir,receipt_store=receipt_store);m=[i for i in load_intents(intent_dir)['valid'] if i['intent_sha256']==selected_intent_sha256]
    if len(m)!=1:return {'status':'HOLD_SELECTED_INTENT_NOT_FOUND_OR_INVALID'}
    i=m[0];cursha=(current.get('record') or {}).get('checkpoint_sha256');curseq=current.get('selected_sequence')
    if i['parent_checkpoint_sha256']!=cursha or i['parent_sequence']!=curseq:return {'status':'HOLD_SELECTED_INTENT_PARENT_NOT_CURRENT'}
    segs=scan_segments(segment_store);cps=scan_checkpoint_spine(checkpoint_spine);fake={'sequence':i['target_sequence'],'offset':i['checkpoint_offset'],'length':i['checkpoint_len'],'checkpoint_sha256':i['checkpoint_sha256']};ok,reason,_=_validate_candidate(fake,cps,segs)
    if not ok:return {'status':'HOLD_SELECTED_INTENT_DEPENDENCIES_INVALID','reason':reason}
    parent_receipt=current['pointer'].get('receipt_sha256');receipt=make_receipt(intent=i,parent_receipt_sha256=parent_receipt);store=ReceiptStore(receipt_store);put=store.put(receipt)
    raw=serialize_fast_pointer(i['target_sequence'],i['checkpoint_offset'],i['checkpoint_len'],i['checkpoint_sha256'],put['offset'],put['length'],receipt['receipt_sha256']);target=Path(pointer_b) if current.get('selected_slot')=='A' else Path(pointer_a);_atomic(target,raw)
    after=recover_fast(mode='carried',pointer_a=pointer_a,pointer_b=pointer_b,segment_store=segment_store,checkpoint_spine=checkpoint_spine,intent_dir=intent_dir,receipt_store=receipt_store)
    if after.get('selected_sequence')!=i['target_sequence']:raise RuntimeError('fast authorization commit failed')
    return {'status':'COMMITTED_FAST_AUTHORIZATION_POINTER','sequence':after['selected_sequence'],'receipt_sha256':receipt['receipt_sha256'],'receipt_offset':put['offset'],'receipt_len':put['length'],'pointer_bytes':len(raw)}
