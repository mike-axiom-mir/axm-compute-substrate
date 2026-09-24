from __future__ import annotations
import hashlib,struct
from pathlib import Path
from typing import Any
from AXM_FLOWING_COMPUTE_CAS_HEAD import parse_root,PAGE_WIDTH,CATEGORY_CODE,CODE_CATEGORY
from AXM_FLOWING_COMPUTE_CAS_PACK import PackedCAS
from AXM_FLOWING_COMPUTE_PACKED_CAS_HEAD import _load
from AXM_FLOWING_COMPUTE_NATIVE_PACKED_STATE import parse_native
from AXM_FLOWING_COMPUTE_NATIVE_OVERLAY import parse_overlay,shahex
from AXM_FLOWING_COMPUTE_PROVEN_OVERLAY import CHECKPOINT_SCHEMA,validate_hashed
from AXM_FLOWING_COMPUTE_PROOF_MANIFEST import validate_manifest

TABLE_MAGIC=b'AXBT22\x00\x01';TABLE_STORE_MAGIC=b'AXTS22\x00\x01';GEN_MAGIC=b'AXGS22\x00\x01';SPINE_MAGIC=b'AXSP22\x00\x01';PTR_MAGIC=b'AXPT22\x00\x01'

def sh(raw:bytes)->bytes:return hashlib.sha256(raw).digest()
def shahex2(raw:bytes)->str:return hashlib.sha256(raw).hexdigest()

def serialize_table(root:dict[str,Any])->bytes:
    h=root['header'];refs=root['refs']
    prefix=TABLE_MAGIC+bytes.fromhex(h['base_artifact_sha256'])+bytes.fromhex(h['base_source_sha256'])+bytes.fromhex(h['base_native_semantic_sha256'])+struct.pack('>HHHH',PAGE_WIDTH['edge'],PAGE_WIDTH['local'],PAGE_WIDTH['signature'],len(refs))
    records=[]
    for (cat,page),ref in sorted(refs.items(),key=lambda x:(CATEGORY_CODE[x[0][0]],x[0][1])):
        records.append(struct.pack('>BHH',CATEGORY_CODE[cat],page,int(ref['entry_count']))+bytes.fromhex(ref['sha256']))
    body=prefix+b''.join(records);return body+sh(body)

def parse_table(raw:bytes)->dict[str,Any]:
    if len(raw)<len(TABLE_MAGIC)+32*3+8+32 or not raw.startswith(TABLE_MAGIC):raise ValueError('bad block-table magic')
    body,stored=raw[:-32],raw[-32:]
    if sh(body)!=stored:raise ValueError('block-table integrity mismatch')
    off=len(TABLE_MAGIC);base_art=body[off:off+32].hex();off+=32;base_source=body[off:off+32].hex();off+=32;base_sem=body[off:off+32].hex();off+=32
    ew,lw,sw,n=struct.unpack('>HHHH',body[off:off+8]);off+=8
    if [ew,lw,sw]!=[PAGE_WIDTH['edge'],PAGE_WIDTH['local'],PAGE_WIDTH['signature']]:raise ValueError('block-table page width mismatch')
    refs={}
    for _ in range(n):
        code,page,count=struct.unpack('>BHH',body[off:off+5]);off+=5;sha=body[off:off+32].hex();off+=32;cat=CODE_CATEGORY.get(code)
        if cat is None:raise ValueError('block-table category mismatch')
        refs[(cat,page)]={'sha256':sha,'entry_count':count}
    if off!=len(body):raise ValueError('block-table trailing bytes')
    return {'base_artifact_sha256':base_art,'base_source_sha256':base_source,'base_native_semantic_sha256':base_sem,'refs':refs,'artifact_sha256':shahex2(raw)}

class TableStore:
    def __init__(self,path:str|Path,*,create=False):
        self.path=Path(path);self.map={}
        if create:self.path.write_bytes(TABLE_STORE_MAGIC)
        raw=self.path.read_bytes()
        if not raw.startswith(TABLE_STORE_MAGIC):raise ValueError('bad table-store magic')
        off=len(TABLE_STORE_MAGIC)
        while off<len(raw):
            sha=raw[off:off+32].hex();off+=32;ln=struct.unpack('>I',raw[off:off+4])[0];off+=4;pos=off;payload=raw[pos:pos+ln];off+=ln
            if shahex2(payload)!=sha:raise ValueError('table-store payload mismatch')
            self.map[sha]=(pos,ln)
    def add(self,raw:bytes)->tuple[str,bool,int,int,int]:
        sha=shahex2(raw)
        if sha in self.map:
            pos,ln=self.map[sha];return sha,False,0,pos,ln
        record=bytes.fromhex(sha)+struct.pack('>I',len(raw))+raw
        with self.path.open('ab') as f:start=f.tell();f.write(record)
        pos=start+32+4;self.map[sha]=(pos,len(raw));return sha,True,len(record),pos,len(raw)
    def get_at(self,pos:int,ln:int,expected_sha:str)->bytes:
        with self.path.open('rb') as f:f.seek(pos);raw=f.read(ln)
        if len(raw)!=ln or shahex2(raw)!=expected_sha:raise ValueError('table-store referenced object mismatch')
        return raw

def serialize_generation(*,sequence:int,parent_sha:str|None,parent_offset:int,parent_len:int,table_sha:str,table_offset:int,table_len:int,overlay_sha:str,history_root:str,proof_manifest_sha:str,final_source:str,final_semantic:str)->bytes:
    parent=bytes.fromhex(parent_sha) if parent_sha else bytes(32)
    body=GEN_MAGIC+struct.pack('>I',sequence)+parent+struct.pack('>QI',parent_offset,parent_len)+bytes.fromhex(table_sha)+struct.pack('>QI',table_offset,table_len)+bytes.fromhex(overlay_sha)+bytes.fromhex(history_root)+bytes.fromhex(proof_manifest_sha)+bytes.fromhex(final_source)+bytes.fromhex(final_semantic)
    return body+sh(body)

def parse_generation(raw:bytes)->dict[str,Any]:
    if len(raw)<len(GEN_MAGIC)+4+32+12+32+12+32*5+32 or not raw.startswith(GEN_MAGIC):raise ValueError('bad generation record magic')
    body,stored=raw[:-32],raw[-32:]
    if sh(body)!=stored:raise ValueError('generation record integrity mismatch')
    off=len(GEN_MAGIC);seq=struct.unpack('>I',body[off:off+4])[0];off+=4;parent=body[off:off+32].hex();off+=32;po,pl=struct.unpack('>QI',body[off:off+12]);off+=12;table=body[off:off+32].hex();off+=32;to,tl=struct.unpack('>QI',body[off:off+12]);off+=12;overlay=body[off:off+32].hex();off+=32;history=body[off:off+32].hex();off+=32;proof=body[off:off+32].hex();off+=32;source=body[off:off+32].hex();off+=32;sem=body[off:off+32].hex();off+=32
    if off!=len(body):raise ValueError('generation record trailing bytes')
    return {'sequence':seq,'parent_generation_sha256':None if parent==bytes(32).hex() else parent,'parent_offset':po,'parent_len':pl,'table_sha256':table,'table_offset':to,'table_len':tl,'overlay_artifact_sha256':overlay,'history_chain_root_sha256':history,'proof_manifest_sha256':proof,'final_source_sha256':source,'final_native_semantic_sha256':sem,'generation_sha256':shahex2(raw)}

class SpineStore:
    def __init__(self,path:str|Path,*,create=False):
        self.path=Path(path)
        if create:self.path.write_bytes(SPINE_MAGIC)
        if not self.path.read_bytes()[:len(SPINE_MAGIC)]==SPINE_MAGIC:raise ValueError('bad spine magic')
    def append(self,raw:bytes)->tuple[int,int,int]:
        frame=struct.pack('>I',len(raw))+raw
        with self.path.open('ab') as f:start=f.tell();f.write(frame)
        return start+4,len(raw),len(frame)
    def get(self,offset:int,ln:int,expected_sha:str)->bytes:
        with self.path.open('rb') as f:f.seek(offset);raw=f.read(ln)
        if len(raw)!=ln or shahex2(raw)!=expected_sha:raise ValueError('spine generation ref mismatch')
        return raw

def serialize_pointer(sequence:int,offset:int,ln:int,generation_sha:str)->bytes:
    body=PTR_MAGIC+struct.pack('>IQI',sequence,offset,ln)+bytes.fromhex(generation_sha);return body+sh(body)
def parse_pointer(raw:bytes)->dict[str,Any]:
    if len(raw)!=len(PTR_MAGIC)+4+8+4+32+32 or not raw.startswith(PTR_MAGIC):raise ValueError('bad spine pointer')
    body,stored=raw[:-32],raw[-32:]
    if sh(body)!=stored:raise ValueError('spine pointer integrity mismatch')
    off=len(PTR_MAGIC);seq,offset,ln=struct.unpack('>IQI',body[off:off+16]);off+=16;sha=body[off:off+32].hex()
    return {'sequence':seq,'generation_offset':offset,'generation_len':ln,'generation_sha256':sha}

def persist_root_generation(*,root_raw:bytes,overlay_sha:str,table_store:TableStore,spine_store:SpineStore,previous:dict[str,Any]|None)->tuple[bytes,dict[str,Any]]:
    root=parse_root(root_raw);h=root['header'];table_raw=serialize_table(root);table_sha,new_table,table_written,to,tl=table_store.add(table_raw)
    psha=previous['generation_sha256'] if previous else None;po=previous['generation_offset'] if previous else 0;pl=previous['generation_len'] if previous else 0
    gen_raw=serialize_generation(sequence=int(h['overlay_count']),parent_sha=psha,parent_offset=po,parent_len=pl,table_sha=table_sha,table_offset=to,table_len=tl,overlay_sha=overlay_sha,history_root=h['history_chain_root_sha256'],proof_manifest_sha=h['proof_manifest_sha256'],final_source=h['final_source_sha256'],final_semantic=h['final_native_semantic_sha256'])
    go,gl,spine_written=spine_store.append(gen_raw);gsha=shahex2(gen_raw);pointer=serialize_pointer(int(h['overlay_count']),go,gl,gsha)
    state={'generation_sha256':gsha,'generation_offset':go,'generation_len':gl,'sequence':int(h['overlay_count'])}
    return pointer,{'state':state,'new_table':new_table,'table_write_bytes':table_written,'spine_write_bytes':spine_written,'pointer_write_bytes':len(pointer),'total_persistent_write_bytes':table_written+spine_written+len(pointer),'table_bytes':len(table_raw),'generation_bytes':len(gen_raw),'pointer_bytes':len(pointer)}

def wake_pointer(*,pointer_raw:bytes,base_raw:bytes,base_proof:dict[str,Any],table_store:TableStore,spine_store:SpineStore,block_store:PackedCAS)->tuple[dict[str,Any],dict[str,Any]]:
    validate_hashed(base_proof,CHECKPOINT_SCHEMA,'proof_sha256');ptr=parse_pointer(pointer_raw);gen=parse_generation(spine_store.get(ptr['generation_offset'],ptr['generation_len'],ptr['generation_sha256']))
    if gen['sequence']!=ptr['sequence']:raise ValueError('pointer sequence mismatch')
    table=parse_table(table_store.get_at(gen['table_offset'],gen['table_len'],gen['table_sha256']));base=parse_native(base_raw,validate_semantic=False);bh=base['header'];base_sha=shahex(base_raw)
    if base_sha!=base_proof['artifact_sha256'] or table['base_artifact_sha256']!=base_sha:raise ValueError('spine base artifact mismatch')
    if bh['source_sha256']!=base_proof['source_sha256'] or bh['native_semantic_sha256']!=base_proof['native_semantic_sha256']:raise ValueError('spine base proof mismatch')
    entries={'edge':{},'local':{},'signature':{}}
    for (cat,page),ref in table['refs'].items():entries[cat].update(_load(block_store,ref)['entries'])
    view={'base':base,'header':dict(bh),'edge_overrides':entries['edge'],'local_overrides':entries['local'],'signature_overrides':entries['signature']};view['header']['source_sha256']=gen['final_source_sha256'];view['header']['legacy_json_state_sha256']=None;view['header']['native_semantic_sha256']=gen['final_native_semantic_sha256']
    receipt={'schema':'axm.flowing-compute-root-spine-wake/v0.1','sequence':gen['sequence'],'generation_sha256':gen['generation_sha256'],'block_table_sha256':gen['table_sha256'],'final_source_sha256':gen['final_source_sha256'],'final_native_semantic_sha256':gen['final_native_semantic_sha256'],'history_chain_root_sha256':gen['history_chain_root_sha256'],'truth':{'generation_history_append_only':True,'block_table_content_addressed':True,'pointer_is_only_mutable_spine_surface':True,'full_overlay_history_preserved_separately':True}}
    return view,receipt
