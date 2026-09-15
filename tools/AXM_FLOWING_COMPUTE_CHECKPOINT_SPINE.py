from __future__ import annotations
import hashlib,json,os,struct
from pathlib import Path
from typing import Any
SEG_MAGIC=b'AXCS31S\x00';SPINE_MAGIC=b'AXCS31P\x00';PTR_MAGIC=b'AXCS31R\x00';SEG_SCHEMA='axm.flowing-compute-segment-proof/v0.1';REC_SCHEMA='axm.flowing-compute-checkpoint-spine-record/v0.1'
def canonical(v:Any)->bytes:return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def sh(raw:bytes)->bytes:return hashlib.sha256(raw).digest()
def sha(raw:bytes)->str:return hashlib.sha256(raw).hexdigest()
def make_segment(segment:dict[str,Any])->dict[str,Any]:
    body={'schema':SEG_SCHEMA,**{k:segment[k] for k in ('start','end','start_sequence','end_sequence','record_count','generation_chain_root_sha256')}};body['segment_sha256']=sha(canonical(body));return body
def validate_segment(seg:dict[str,Any])->None:
    if seg.get('schema')!=SEG_SCHEMA:raise ValueError('bad segment schema')
    stored=seg.get('segment_sha256');body=dict(seg);body.pop('segment_sha256',None)
    if sha(canonical(body))!=stored:raise ValueError('segment proof integrity mismatch')
    if int(seg['record_count'])!=int(seg['end_sequence'])-int(seg['start_sequence'])+1:raise ValueError('segment record count mismatch')
class SegmentStore:
    def __init__(self,path:str|Path):
        self.path=Path(path)
        if not self.path.exists():self.path.write_bytes(SEG_MAGIC)
        self.objects={};self._scan()
    def _scan(self):
        raw=self.path.read_bytes()
        if not raw.startswith(SEG_MAGIC):raise ValueError('bad segment store magic')
        off=len(SEG_MAGIC)
        while off<len(raw):
            if off+36>len(raw):raise ValueError('segment store torn tail')
            h=raw[off:off+32].hex();ln=struct.unpack('>I',raw[off+32:off+36])[0];start=off+36;end=start+ln
            if end>len(raw):raise ValueError('segment store torn object')
            body=raw[start:end]
            if sha(body)!=h:raise ValueError('segment object hash mismatch')
            obj=json.loads(body);validate_segment(obj);self.objects[h]=(start,ln,obj);off=end
    def put(self,seg:dict[str,Any])->dict[str,Any]:
        validate_segment(seg);raw=canonical(seg);h=sha(raw)
        if h in self.objects:return {'sha256':h,'new':False,'bytes_written':0}
        rec=bytes.fromhex(h)+struct.pack('>I',len(raw))+raw
        with self.path.open('ab') as f:start=f.tell();f.write(rec);f.flush();os.fsync(f.fileno())
        self.objects[h]=(start+36,len(raw),seg);return {'sha256':h,'new':True,'bytes_written':len(rec)}
    def get(self,h:str)->dict[str,Any]:
        if h not in self.objects:raise ValueError('missing segment object')
        return self.objects[h][2]
def make_record(*,sequence:int,spine_prefix_bytes:int,segment_sha256:str,anchor:dict[str,Any],parent:dict[str,Any]|None,parent_offset:int|None,parent_len:int|None)->dict[str,Any]:
    rec={'schema':REC_SCHEMA,'sequence':int(sequence),'spine_prefix_bytes':int(spine_prefix_bytes),'segment_sha256':segment_sha256,'anchor':anchor,'parent_checkpoint_sha256':parent['checkpoint_sha256'] if parent else None,'parent_offset':parent_offset,'parent_len':parent_len};rec['checkpoint_sha256']=sha(canonical(rec));return rec
def validate_record(rec:dict[str,Any])->None:
    if rec.get('schema')!=REC_SCHEMA:raise ValueError('bad checkpoint record schema')
    stored=rec.get('checkpoint_sha256');body=dict(rec);body.pop('checkpoint_sha256',None)
    if sha(canonical(body))!=stored:raise ValueError('checkpoint record integrity mismatch')
    a=rec['anchor']
    if int(a['generation_offset'])+int(a['generation_len'])!=int(rec['spine_prefix_bytes']):raise ValueError('checkpoint anchor prefix mismatch')
class CheckpointSpine:
    def __init__(self,path:str|Path):
        self.path=Path(path)
        if not self.path.exists():self.path.write_bytes(SPINE_MAGIC)
    def append(self,rec:dict[str,Any])->dict[str,Any]:
        validate_record(rec);raw=canonical(rec);frame=struct.pack('>I',len(raw))+raw
        with self.path.open('ab') as f:start=f.tell();f.write(frame);f.flush();os.fsync(f.fileno())
        return {'offset':start+4,'length':len(raw),'bytes_written':len(frame),'checkpoint_sha256':rec['checkpoint_sha256']}
    def read(self,offset:int,length:int,expected_sha:str)->dict[str,Any]:
        with self.path.open('rb') as f:f.seek(int(offset));raw=f.read(int(length))
        if len(raw)!=int(length):raise ValueError('checkpoint record truncated')
        rec=json.loads(raw);validate_record(rec)
        if rec['checkpoint_sha256']!=expected_sha:raise ValueError('checkpoint pointer hash mismatch')
        return rec
def serialize_pointer(sequence:int,offset:int,length:int,checkpoint_sha256:str)->bytes:
    body=PTR_MAGIC+struct.pack('>IQI',int(sequence),int(offset),int(length))+bytes.fromhex(checkpoint_sha256);return body+sh(body)
def parse_pointer(raw:bytes)->dict[str,Any]:
    if len(raw)!=len(PTR_MAGIC)+4+8+4+32+32 or not raw.startswith(PTR_MAGIC):raise ValueError('bad checkpoint pointer')
    body,stored=raw[:-32],raw[-32:]
    if sh(body)!=stored:raise ValueError('checkpoint pointer integrity mismatch')
    off=len(PTR_MAGIC);seq,po,pl=struct.unpack('>IQI',body[off:off+16]);off+=16;h=body[off:off+32].hex();return {'sequence':seq,'offset':po,'length':pl,'checkpoint_sha256':h}
def atomic_pointer(path:str|Path,raw:bytes)->None:
    p=Path(path);tmp=p.with_name(p.name+'.tmp')
    with tmp.open('wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    os.replace(tmp,p);fd=os.open(str(p.parent),os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)
def wake(pointer_raw:bytes,spine:CheckpointSpine,segments:SegmentStore)->dict[str,Any]:
    p=parse_pointer(pointer_raw);rec=spine.read(p['offset'],p['length'],p['checkpoint_sha256'])
    if int(rec['sequence'])!=int(p['sequence']):raise ValueError('checkpoint sequence mismatch')
    seg=segments.get(rec['segment_sha256'])
    if int(seg['end_sequence'])!=int(rec['sequence']) or int(seg['end'])!=int(rec['spine_prefix_bytes']):raise ValueError('segment/checkpoint mismatch')
    return {'pointer':p,'record':rec,'segment':seg}
def audit_chain(pointer_raw:bytes,spine:CheckpointSpine,segments:SegmentStore)->dict[str,Any]:
    cur=wake(pointer_raw,spine,segments);rows=[]
    while True:
        rec=cur['record'];seg=cur['segment'];rows.append({'record':rec,'segment':seg})
        if rec['parent_checkpoint_sha256'] is None:break
        parent=spine.read(rec['parent_offset'],rec['parent_len'],rec['parent_checkpoint_sha256']);pseg=segments.get(parent['segment_sha256']);cur={'record':parent,'segment':pseg}
    rows.reverse();expected_start=rows[0]['segment']['start'];prev_seq=rows[0]['segment']['start_sequence']-1
    for row in rows:
        seg=row['segment']
        if int(seg['start'])!=int(expected_start) or int(seg['start_sequence'])!=int(prev_seq)+1:raise ValueError('checkpoint spine history gap')
        expected_start=int(seg['end']);prev_seq=int(seg['end_sequence'])
    return {'passed':True,'segments':len(rows),'start_sequence':rows[0]['segment']['start_sequence'],'end_sequence':rows[-1]['segment']['end_sequence'],'rows':rows}
