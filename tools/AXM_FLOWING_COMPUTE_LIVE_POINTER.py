from __future__ import annotations
import hashlib,os,struct
from pathlib import Path
from typing import Any
from AXM_FLOWING_COMPUTE_LIVE_SEGMENT_ACCUMULATOR import serialize as serialize_acc,parse as parse_acc,seal as seal_acc,start as start_acc,advance as advance_acc
MAGIC=b'AXPT28\x00\x01'

def sh(raw:bytes)->bytes:return hashlib.sha256(raw).digest()

def serialize_pointer(*,sequence:int,generation_offset:int,generation_len:int,generation_sha256:str,accumulator:dict[str,Any])->bytes:
    acc=serialize_acc(accumulator)
    body=MAGIC+struct.pack('>IQI',int(sequence),int(generation_offset),int(generation_len))+bytes.fromhex(generation_sha256)+struct.pack('>H',len(acc))+acc
    return body+sh(body)
def parse_pointer(raw:bytes)->dict[str,Any]:
    if len(raw)<len(MAGIC)+4+8+4+32+2+32 or not raw.startswith(MAGIC):raise ValueError('bad live pointer shape')
    body,stored=raw[:-32],raw[-32:]
    if sh(body)!=stored:raise ValueError('live pointer integrity mismatch')
    off=len(MAGIC);seq,go,gl=struct.unpack('>IQI',body[off:off+16]);off+=16;gsha=body[off:off+32].hex();off+=32;aln=struct.unpack('>H',body[off:off+2])[0];off+=2;acc=parse_acc(body[off:off+aln]);off+=aln
    if off!=len(body):raise ValueError('live pointer trailing bytes')
    if int(acc['last_sequence'])!=int(seq):raise ValueError('live pointer accumulator sequence mismatch')
    return {'sequence':seq,'generation_offset':go,'generation_len':gl,'generation_sha256':gsha,'accumulator':acc}

def atomic_write(path:str|Path,raw:bytes)->None:
    path=Path(path);tmp=path.with_name(path.name+'.tmp')
    with tmp.open('wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)
    fd=os.open(str(path.parent),os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)

def read_slot(path:str|Path)->dict[str,Any]:
    p=Path(path)
    if not p.is_file():return {'valid':False,'reason':'missing'}
    try:return {'valid':True,'pointer':parse_pointer(p.read_bytes())}
    except Exception as e:return {'valid':False,'reason':str(e)}

def recover_slots(pointer_a:str|Path,pointer_b:str|Path)->dict[str,Any]:
    rows=[]
    for name,path in [('A',pointer_a),('B',pointer_b)]:rows.append({'slot':name,**read_slot(path)})
    valid=[x for x in rows if x['valid']];valid.sort(key=lambda x:x['pointer']['sequence'],reverse=True)
    if not valid:return {'status':'HOLD_NO_VALID_POINTER','selected':None,'slots':rows}
    return {'status':'RECOVERED_COMMITTED','selected':valid[0],'slots':rows}

def next_accumulator(*,current_pointer:dict[str,Any],next_sequence:int,next_frame_start:int,sealed_checkpoint_sequence:int|None)->dict[str,Any]:
    acc=current_pointer['accumulator']
    if int(acc['count'])<1024:return acc
    if int(acc['count'])!=1024:raise ValueError('unexpected accumulator segment length')
    if sealed_checkpoint_sequence!=int(current_pointer['sequence']):raise ValueError('completed segment must be sealed before starting next segment')
    return start_acc(start_sequence=int(next_sequence),start_offset=int(next_frame_start))

def advance_for_generation(*,previous_pointer:dict[str,Any]|None,sequence:int,generation_offset:int,generation_len:int,generation_sha256:str,sealed_checkpoint_sequence:int|None=None)->dict[str,Any]:
    frame_start=int(generation_offset)-4
    if previous_pointer is None:acc=start_acc(start_sequence=int(sequence),start_offset=frame_start)
    else:acc=next_accumulator(current_pointer=previous_pointer,next_sequence=int(sequence),next_frame_start=frame_start,sealed_checkpoint_sequence=sealed_checkpoint_sequence)
    acc=advance_acc(acc,sequence=int(sequence),generation_sha256=generation_sha256,generation_offset=int(generation_offset),generation_len=int(generation_len))
    return {'sequence':int(sequence),'generation_offset':int(generation_offset),'generation_len':int(generation_len),'generation_sha256':generation_sha256,'accumulator':acc}

def seal_from_pointer(pointer:dict[str,Any])->dict[str,Any]:
    if int(pointer['accumulator']['count'])!=1024:raise ValueError('pointer segment is not complete')
    seg=seal_acc(pointer['accumulator'])
    return {'schema':'axm.flowing-compute-live-segment-seal/v0.1','sequence':pointer['sequence'],'segment':seg,'anchor':{'generation_sha256':pointer['generation_sha256'],'generation_offset':pointer['generation_offset'],'generation_len':pointer['generation_len']},'truth':{'sealed_from_committed_pointer_state':True,'spine_reread_required':False}}
