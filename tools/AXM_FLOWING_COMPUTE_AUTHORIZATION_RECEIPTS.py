from __future__ import annotations
import hashlib,json,os,struct
from pathlib import Path
from typing import Any
from AXM_FLOWING_COMPUTE_CHECKPOINT_SPINE import canonical,sha,serialize_pointer as serialize_legacy_pointer
from AXM_FLOWING_COMPUTE_CHECKPOINT_INTENT import validate_intent,load_intents
from AXM_FLOWING_COMPUTE_CHECKPOINT_TRANSACTION import scan_segments,scan_checkpoint_spine,_validate_candidate

STORE_MAGIC=b'AXAR37S\x00';PTR_MAGIC=b'AXAR37P\x00';SCHEMA='axm.flowing-compute-authorization-receipt/v0.1'
def sh(raw:bytes)->bytes:return hashlib.sha256(raw).digest()
def digest(v:Any)->str:return hashlib.sha256(canonical(v)).hexdigest()

def make_receipt(*,intent:dict[str,Any],parent_receipt_sha256:str|None)->dict[str,Any]:
    validate_intent(intent)
    r={'schema':SCHEMA,'sequence':int(intent['target_sequence']),'checkpoint_sha256':intent['checkpoint_sha256'],'checkpoint_offset':int(intent['checkpoint_offset']),'checkpoint_len':int(intent['checkpoint_len']),'intent_sha256':intent['intent_sha256'],'parent_checkpoint_sha256':intent['parent_checkpoint_sha256'],'parent_receipt_sha256':parent_receipt_sha256,'truth':{'receipt_is_provenance_evidence_not_state_authority':True,'intent_identity_preserved':True}}
    r['receipt_sha256']=digest(r);return r

def validate_receipt(r:dict[str,Any])->None:
    if r.get('schema')!=SCHEMA:raise ValueError('bad authorization receipt schema')
    stored=r.get('receipt_sha256');body=dict(r);body.pop('receipt_sha256',None)
    if digest(body)!=stored:raise ValueError('authorization receipt integrity mismatch')

class ReceiptStore:
    def __init__(self,path:str|Path):
        self.path=Path(path)
        if not self.path.exists():self.path.write_bytes(STORE_MAGIC)
        self.objects={};self.scan()
    def scan(self)->dict[str,Any]:
        raw=self.path.read_bytes()
        if not raw.startswith(STORE_MAGIC):raise ValueError('bad receipt store magic')
        off=len(STORE_MAGIC);objs={};rows=[];reason=None
        while off<len(raw):
            start=off
            if off+36>len(raw):reason='incomplete_receipt_header';break
            h=raw[off:off+32].hex();ln=struct.unpack('>I',raw[off+32:off+36])[0];bo=off+36;end=bo+ln
            if end>len(raw):reason='incomplete_receipt_object';break
            body=raw[bo:end]
            try:r=json.loads(body);validate_receipt(r)
            except Exception:reason='receipt_object_invalid';break
            if r['receipt_sha256']!=h:reason='receipt_content_address_mismatch';break
            row={'frame_start':start,'offset':bo,'length':ln,'sha256':h,'receipt':r};rows.append(row);objs[h]=row;off=end
        self.objects=objs;return {'valid':True,'objects':objs,'records':rows,'valid_prefix_bytes':off,'tail_bytes':len(raw)-off,'reason':reason}
    def put(self,r:dict[str,Any])->dict[str,Any]:
        validate_receipt(r);raw=canonical(r);h=r['receipt_sha256']
        if h in self.objects:
            row=self.objects[h];return {'sha256':h,'new':False,'bytes_written':0,'offset':row['offset'],'length':row['length']}
        frame=bytes.fromhex(h)+struct.pack('>I',len(raw))+raw
        with self.path.open('ab') as f:f.write(frame);f.flush();os.fsync(f.fileno())
        self.scan();row=self.objects[h];return {'sha256':h,'new':True,'bytes_written':len(frame),'offset':row['offset'],'length':row['length']}
    def get_at(self,offset:int,length:int,expected_sha:str)->dict[str,Any]:
        bo=int(offset);ln=int(length);start=bo-36
        if start<len(STORE_MAGIC):raise ValueError('receipt direct offset before store body')
        with self.path.open('rb') as f:
            f.seek(start);hdr=f.read(36);body=f.read(ln)
        if len(hdr)!=36 or len(body)!=ln:raise ValueError('receipt direct read truncated')
        h=hdr[:32].hex();declared=struct.unpack('>I',hdr[32:])[0]
        if h!=expected_sha or declared!=ln:raise ValueError('receipt direct header mismatch')
        r=json.loads(body);validate_receipt(r)
        if r['receipt_sha256']!=expected_sha:raise ValueError('receipt direct identity mismatch')
        return r
    def get(self,h:str)->dict[str,Any]:
        if h not in self.objects:raise ValueError('missing authorization receipt')
        return self.objects[h]['receipt']

def serialize_receipted_pointer(sequence:int,offset:int,length:int,checkpoint_sha256:str,receipt_sha256:str)->bytes:
    if len(checkpoint_sha256)!=64 or len(receipt_sha256)!=64:raise ValueError('receipt pointer hash shape')
    body=PTR_MAGIC+struct.pack('>IQI',int(sequence),int(offset),int(length))+bytes.fromhex(checkpoint_sha256)+bytes.fromhex(receipt_sha256);return body+sh(body)

def parse_receipted_pointer(raw:bytes)->dict[str,Any]:
    need=len(PTR_MAGIC)+4+8+4+32+32+32
    if len(raw)!=need or not raw.startswith(PTR_MAGIC):raise ValueError('bad receipted pointer shape')
    body,stored=raw[:-32],raw[-32:]
    if sh(body)!=stored:raise ValueError('receipted pointer integrity mismatch')
    off=len(PTR_MAGIC);seq,po,pl=struct.unpack('>IQI',body[off:off+16]);off+=16;ch=body[off:off+32].hex();off+=32;rh=body[off:off+32].hex()
    return {'schema':'axm.flowing-compute-receipted-checkpoint-pointer/v0.1','sequence':seq,'offset':po,'length':pl,'checkpoint_sha256':ch,'receipt_sha256':rh,'provenance_bound':True}

def _intent_by_hash(intent_dir:str|Path,h:str)->dict[str,Any]|None:
    loaded=load_intents(intent_dir);m=[i for i in loaded['valid'] if i['intent_sha256']==h];return m[0] if len(m)==1 else None

def validate_receipt_chain(*,receipt_sha256:str,store:ReceiptStore,intent_dir:str|Path,cps:dict[str,Any],segs:dict[str,Any])->dict[str,Any]:
    rows=[];seen=set();h=receipt_sha256
    while h is not None:
        if h in seen:raise ValueError('authorization receipt cycle')
        seen.add(h);r=store.get(h);validate_receipt(r)
        i=_intent_by_hash(intent_dir,r['intent_sha256'])
        if i is None:raise ValueError('authorization receipt intent missing or invalid')
        if int(i['target_sequence'])!=int(r['sequence']) or i['checkpoint_sha256']!=r['checkpoint_sha256'] or int(i['checkpoint_offset'])!=int(r['checkpoint_offset']) or int(i['checkpoint_len'])!=int(r['checkpoint_len']):raise ValueError('authorization receipt intent target mismatch')
        if i['parent_checkpoint_sha256']!=r['parent_checkpoint_sha256']:raise ValueError('authorization receipt parent checkpoint mismatch')
        legacy=serialize_legacy_pointer(r['sequence'],r['checkpoint_offset'],r['checkpoint_len'],r['checkpoint_sha256'])
        if sha(legacy)!=i['target_pointer_sha256']:raise ValueError('authorization receipt intent pointer mismatch')
        fake={'sequence':r['sequence'],'offset':r['checkpoint_offset'],'length':r['checkpoint_len'],'checkpoint_sha256':r['checkpoint_sha256']};ok,reason,rec=_validate_candidate(fake,cps,segs)
        if not ok:raise ValueError('authorization receipt checkpoint invalid:'+reason)
        if rec.get('parent_checkpoint_sha256')!=r['parent_checkpoint_sha256']:raise ValueError('authorization receipt checkpoint parent mismatch')
        rows.append({'receipt':r,'intent':i,'record':rec});h=r['parent_receipt_sha256']
    rows.reverse()
    for a,b in zip(rows,rows[1:]):
        if b['receipt']['parent_checkpoint_sha256']!=a['receipt']['checkpoint_sha256']:raise ValueError('authorization receipt chain checkpoint gap')
    return {'passed':True,'depth':len(rows),'rows':rows,'root_receipt_sha256':rows[0]['receipt']['receipt_sha256'] if rows else None,'tip_receipt_sha256':receipt_sha256}
