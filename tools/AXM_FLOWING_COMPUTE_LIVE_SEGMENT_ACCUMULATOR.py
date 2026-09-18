from __future__ import annotations
import hashlib,struct
from pathlib import Path
from typing import Any
from AXM_FLOWING_COMPUTE_ROOT_SPINE import parse_generation
MAGIC=b'AXLA27\x00\x01';DOMAIN=b'AXM-LIVE-SEGMENT-27\x00'

def sh(raw:bytes)->bytes:return hashlib.sha256(raw).digest()
def _start_root(start_sequence:int,start_offset:int)->bytes:return sh(DOMAIN+struct.pack('>QQ',int(start_sequence),int(start_offset)))

def start(*,start_sequence:int,start_offset:int)->dict[str,Any]:
    return {'start_sequence':int(start_sequence),'start_offset':int(start_offset),'last_sequence':int(start_sequence)-1,'last_offset':int(start_offset),'last_len':0,'count':0,'root_sha256':_start_root(start_sequence,start_offset).hex()}

def advance(state:dict[str,Any],*,sequence:int,generation_sha256:str,generation_offset:int,generation_len:int)->dict[str,Any]:
    seq=int(sequence);off=int(generation_offset);ln=int(generation_len)
    if seq!=int(state['last_sequence'])+1:raise ValueError('live accumulator sequence gap')
    expected=(int(state['start_offset'])+4) if int(state['count'])==0 else (int(state['last_offset'])+int(state['last_len'])+4)
    if off!=expected:raise ValueError('live accumulator offset gap')
    if len(generation_sha256)!=64:raise ValueError('generation hash shape')
    root=sh(bytes.fromhex(state['root_sha256'])+bytes.fromhex(generation_sha256)+struct.pack('>QQI',seq,off,ln)).hex()
    return {'start_sequence':int(state['start_sequence']),'start_offset':int(state['start_offset']),'last_sequence':seq,'last_offset':off,'last_len':ln,'count':int(state['count'])+1,'root_sha256':root}

def serialize(state:dict[str,Any])->bytes:
    body=MAGIC+struct.pack('>QQQQII',int(state['start_sequence']),int(state['start_offset']),int(state['last_sequence']),int(state['last_offset']),int(state['last_len']),int(state['count']))+bytes.fromhex(state['root_sha256'])
    return body+sh(body)
def parse(raw:bytes)->dict[str,Any]:
    if len(raw)!=len(MAGIC)+8*4+4*2+32+32 or not raw.startswith(MAGIC):raise ValueError('bad live accumulator shape')
    body,stored=raw[:-32],raw[-32:]
    if sh(body)!=stored:raise ValueError('live accumulator integrity mismatch')
    off=len(MAGIC);ss,so,ls,lo,ll,count=struct.unpack('>QQQQII',body[off:off+40]);off+=40;root=body[off:off+32].hex()
    return {'start_sequence':ss,'start_offset':so,'last_sequence':ls,'last_offset':lo,'last_len':ll,'count':count,'root_sha256':root}

def seal(state:dict[str,Any])->dict[str,Any]:
    if int(state['count'])<=0:raise ValueError('cannot seal empty segment')
    end=int(state['last_offset'])+int(state['last_len'])
    return {'start':int(state['start_offset']),'end':end,'start_sequence':int(state['start_sequence']),'end_sequence':int(state['last_sequence']),'record_count':int(state['count']),'generation_chain_root_sha256':state['root_sha256']}

def audit_spine_segment(spine_path:str|Path,segment:dict[str,Any])->dict[str,Any]:
    p=Path(spine_path);state=start(start_sequence=int(segment['start_sequence']),start_offset=int(segment['start']));off=int(segment['start'])
    with p.open('rb') as f:
        f.seek(off)
        while int(state['last_sequence'])<int(segment['end_sequence']):
            frame=off;rawlen=f.read(4)
            if len(rawlen)<4:raise ValueError('incomplete frame during segment audit')
            ln=struct.unpack('>I',rawlen)[0];payload=f.read(ln)
            if len(payload)!=ln:raise ValueError('incomplete generation during segment audit')
            g=parse_generation(payload);go=frame+4
            state=advance(state,sequence=g['sequence'],generation_sha256=g['generation_sha256'],generation_offset=go,generation_len=ln);off=go+ln
    if off!=int(segment['end']) or int(state['count'])!=int(segment['record_count']):raise ValueError('segment audit coverage mismatch')
    ok=state['root_sha256']==segment['generation_chain_root_sha256']
    return {'passed':ok,'root_sha256':state['root_sha256'],'records':state['count'],'bytes':int(segment['end'])-int(segment['start'])}
