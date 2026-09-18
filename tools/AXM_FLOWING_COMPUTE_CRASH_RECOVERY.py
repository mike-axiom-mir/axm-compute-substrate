from __future__ import annotations
import hashlib,struct
from pathlib import Path
from typing import Any
from AXM_FLOWING_COMPUTE_CAS_PACK import PACK_MAGIC,RECORD_MAGIC,shahex
from AXM_FLOWING_COMPUTE_CAS_HEAD import parse_block
from AXM_FLOWING_COMPUTE_ROOT_SPINE import TABLE_STORE_MAGIC,SPINE_MAGIC,parse_table,parse_generation,parse_pointer,shahex2

def scan_block_pack(path:str|Path)->dict[str,Any]:
    raw=Path(path).read_bytes()
    if not raw.startswith(PACK_MAGIC):return {'valid':False,'reason':'bad_pack_magic','objects':{},'valid_prefix_bytes':0,'tail_bytes':len(raw)}
    off=len(PACK_MAGIC);objects={};reason=None
    while off<len(raw):
        start=off
        need=len(RECORD_MAGIC)+32+4
        if len(raw)-off<need:reason='incomplete_pack_record_header';break
        if raw[off:off+len(RECORD_MAGIC)]!=RECORD_MAGIC:reason='pack_record_magic_mismatch';break
        off+=len(RECORD_MAGIC);sha=raw[off:off+32].hex();off+=32;ln=struct.unpack('>I',raw[off:off+4])[0];off+=4
        if len(raw)-off<ln:off=start;reason='incomplete_pack_record_payload';break
        payload=raw[off:off+ln]
        if shahex(payload)!=sha:off=start;reason='pack_payload_hash_mismatch';break
        objects[sha]={'offset':off,'length':ln,'raw':payload};off+=ln
    return {'valid':True,'objects':objects,'valid_prefix_bytes':off,'tail_bytes':len(raw)-off,'tail_reason':reason}

def scan_table_store(path:str|Path)->dict[str,Any]:
    raw=Path(path).read_bytes()
    if not raw.startswith(TABLE_STORE_MAGIC):return {'valid':False,'reason':'bad_table_store_magic','objects':{},'valid_prefix_bytes':0,'tail_bytes':len(raw)}
    off=len(TABLE_STORE_MAGIC);objects={};reason=None
    while off<len(raw):
        start=off
        if len(raw)-off<36:reason='incomplete_table_record_header';break
        sha=raw[off:off+32].hex();off+=32;ln=struct.unpack('>I',raw[off:off+4])[0];off+=4
        if len(raw)-off<ln:off=start;reason='incomplete_table_record_payload';break
        payload=raw[off:off+ln]
        try: parsed=parse_table(payload)
        except Exception:off=start;reason='table_payload_invalid';break
        if parsed['artifact_sha256']!=sha:off=start;reason='table_payload_hash_mismatch';break
        objects[sha]={'offset':off,'length':ln,'raw':payload,'parsed':parsed};off+=ln
    return {'valid':True,'objects':objects,'valid_prefix_bytes':off,'tail_bytes':len(raw)-off,'tail_reason':reason}

def scan_spine(path:str|Path)->dict[str,Any]:
    raw=Path(path).read_bytes()
    if not raw.startswith(SPINE_MAGIC):return {'valid':False,'reason':'bad_spine_magic','records':[],'by_sha':{},'valid_prefix_bytes':0,'tail_bytes':len(raw)}
    off=len(SPINE_MAGIC);records=[];by_sha={};reason=None
    while off<len(raw):
        frame_start=off
        if len(raw)-off<4:reason='incomplete_spine_length';break
        ln=struct.unpack('>I',raw[off:off+4])[0];off+=4
        if len(raw)-off<ln:off=frame_start;reason='incomplete_spine_record';break
        payload=raw[off:off+ln]
        try:g=parse_generation(payload)
        except Exception:off=frame_start;reason='spine_record_invalid';break
        rec={'offset':off,'length':ln,'raw':payload,'parsed':g};records.append(rec);by_sha[g['generation_sha256']]=rec;off+=ln
    return {'valid':True,'records':records,'by_sha':by_sha,'valid_prefix_bytes':off,'tail_bytes':len(raw)-off,'tail_reason':reason}

def read_pointer_slot(path:str|Path)->dict[str,Any]:
    p=Path(path)
    if not p.is_file():return {'valid':False,'reason':'missing'}
    try:q=parse_pointer(p.read_bytes());return {'valid':True,'pointer':q}
    except Exception as e:return {'valid':False,'reason':str(e)}

def _validate_candidate(ptr:dict[str,Any],spine:dict[str,Any],tables:dict[str,Any],blocks:dict[str,Any])->tuple[bool,str,dict[str,Any]|None]:
    rec=spine['by_sha'].get(ptr['generation_sha256'])
    if rec is None:return False,'generation_not_in_valid_spine_prefix',None
    g=rec['parsed']
    if rec['offset']!=ptr['generation_offset'] or rec['length']!=ptr['generation_len'] or g['sequence']!=ptr['sequence']:return False,'pointer_generation_location_or_sequence_mismatch',None
    table=tables['objects'].get(g['table_sha256'])
    if table is None:return False,'generation_table_not_in_valid_table_prefix',g
    if table['offset']!=g['table_offset'] or table['length']!=g['table_len']:return False,'generation_table_location_mismatch',g
    for key,ref in table['parsed']['refs'].items():
        block=blocks['objects'].get(ref['sha256'])
        if block is None:return False,'referenced_state_block_missing_from_valid_pack_prefix',g
        try:b=parse_block(block['raw'])
        except Exception:return False,'referenced_state_block_invalid',g
        if len(b['entries'])!=int(ref['entry_count']):return False,'referenced_state_block_entry_count_mismatch',g
    return True,'ok',g

def recover(*,pointer_a:str|Path,pointer_b:str|Path,spine_path:str|Path,table_path:str|Path,block_pack_path:str|Path)->dict[str,Any]:
    spine=scan_spine(spine_path);tables=scan_table_store(table_path);blocks=scan_block_pack(block_pack_path)
    slots=[]
    for name,path in [('A',pointer_a),('B',pointer_b)]:
        item=read_pointer_slot(path);row={'slot':name,**item}
        if item['valid']:
            ok,reason,g=_validate_candidate(item['pointer'],spine,tables,blocks);row['dependency_valid']=ok;row['dependency_reason']=reason;row['generation']=g
        else:row['dependency_valid']=False
        slots.append(row)
    valid=[r for r in slots if r.get('valid') and r.get('dependency_valid')]
    valid.sort(key=lambda r:r['pointer']['sequence'],reverse=True)
    selected=valid[0] if valid else None
    selected_seq=selected['pointer']['sequence'] if selected else None
    unpointed=[]
    pointed={r['pointer']['generation_sha256'] for r in slots if r.get('valid')}
    for rec in spine['records']:
        g=rec['parsed']
        if g['generation_sha256'] not in pointed and (selected_seq is None or g['sequence']>selected_seq):
            p={'generation_sha256':g['generation_sha256'],'generation_offset':rec['offset'],'generation_len':rec['length'],'sequence':g['sequence']}
            ok,reason,_=_validate_candidate(p,spine,tables,blocks);unpointed.append({'sequence':g['sequence'],'generation_sha256':g['generation_sha256'],'dependency_valid':ok,'reason':reason})
    return {'schema':'axm.flowing-compute-crash-recovery/v0.1','selected_sequence':selected_seq,'selected_slot':selected['slot'] if selected else None,'status':'RECOVERED_COMMITTED' if selected else 'HOLD_NO_VALID_POINTER','pointer_slots':slots,'unpointed_newer_generations':unpointed,'valid_prefix':{'block_pack_bytes':blocks.get('valid_prefix_bytes'),'block_pack_tail_bytes':blocks.get('tail_bytes'),'block_pack_tail_reason':blocks.get('tail_reason'),'table_store_bytes':tables.get('valid_prefix_bytes'),'table_store_tail_bytes':tables.get('tail_bytes'),'table_store_tail_reason':tables.get('tail_reason'),'spine_bytes':spine.get('valid_prefix_bytes'),'spine_tail_bytes':spine.get('tail_bytes'),'spine_tail_reason':spine.get('tail_reason')},'truth':{'unpointed_generation_is_not_auto_promoted':True,'highest_valid_committed_pointer_wins':True,'invalid_newer_pointer_can_fall_back_to_older_valid_slot':True,'append_only_corrupt_tail_does_not_invalidate_valid_prefix':True}}
