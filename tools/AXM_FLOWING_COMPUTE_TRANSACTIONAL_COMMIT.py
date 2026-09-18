from __future__ import annotations
import os,struct
from pathlib import Path
from typing import Any
from AXM_FLOWING_COMPUTE_CAS_PACK import INDEX_MAGIC,RECORD_MAGIC,shahex,sh
from AXM_FLOWING_COMPUTE_CRASH_RECOVERY import recover,scan_block_pack,scan_table_store
from AXM_FLOWING_COMPUTE_ROOT_SPINE import serialize_generation,serialize_pointer,shahex2

class InjectedCrash(RuntimeError): pass

def _fsync_file_obj(f):
    f.flush(); os.fsync(f.fileno())

def _fsync_dir(path:Path):
    fd=os.open(str(path),os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)

def atomic_write(path:str|Path,raw:bytes):
    path=Path(path); tmp=path.with_name(path.name+'.tmp')
    with tmp.open('wb') as f:
        f.write(raw); _fsync_file_obj(f)
    os.replace(tmp,path); _fsync_dir(path.parent)

def _append_durable(path:Path,raw:bytes)->int:
    with path.open('ab') as f:
        start=f.tell(); f.write(raw); _fsync_file_obj(f)
    return start

def rebuild_cas_index_atomic(pack_path:str|Path,index_path:str|Path)->dict[str,Any]:
    scan=scan_block_pack(pack_path)
    if not scan.get('valid'): raise ValueError('cannot rebuild index from invalid pack magic')
    records=[bytes.fromhex(sha)+struct.pack('>QI',obj['offset'],obj['length']) for sha,obj in sorted(scan['objects'].items())]
    body=INDEX_MAGIC+struct.pack('>I',len(records))+b''.join(records); raw=body+sh(body)
    atomic_write(index_path,raw)
    return {'objects':len(records),'index_bytes':len(raw),'ignored_tail_bytes':scan['tail_bytes']}

def _choose_target_slot(pointer_a:Path,pointer_b:Path,recovery:dict[str,Any])->Path:
    if recovery.get('selected_slot')=='A': return pointer_b
    if recovery.get('selected_slot')=='B': return pointer_a
    return pointer_a

def commit_generation(*,pointer_a:str|Path,pointer_b:str|Path,spine_path:str|Path,table_path:str|Path,block_pack_path:str|Path,block_index_path:str|Path,new_block_raws:list[bytes],table_raw:bytes,parent_state:dict[str,Any],generation_fields:dict[str,Any],fail_after:str|None=None)->dict[str,Any]:
    pa,pb=Path(pointer_a),Path(pointer_b); sp=Path(spine_path); tp=Path(table_path); bp=Path(block_pack_path); bi=Path(block_index_path)
    before=recover(pointer_a=pa,pointer_b=pb,spine_path=sp,table_path=tp,block_pack_path=bp)
    if before['status']!='RECOVERED_COMMITTED' or before['selected_sequence']!=int(parent_state['sequence']):
        raise ValueError('transaction parent is not current committed generation')
    target=_choose_target_slot(pa,pb,before)

    # 1. immutable state blocks first
    bscan=scan_block_pack(bp); known=set(bscan['objects']); block_written=0
    for raw in new_block_raws:
        sha=shahex(raw)
        if sha in known: continue
        record=RECORD_MAGIC+bytes.fromhex(sha)+struct.pack('>I',len(raw))+raw
        _append_durable(bp,record); known.add(sha); block_written+=len(record)
    if fail_after=='blocks': raise InjectedCrash('after blocks')

    # Index is convenience only; recovery does not trust it as authority.
    index_info=rebuild_cas_index_atomic(bp,bi)
    if fail_after=='index': raise InjectedCrash('after index')

    # 2. content-addressed table
    tscan=scan_table_store(tp); table_sha=shahex2(table_raw)
    if table_sha in tscan['objects']:
        to=tscan['objects'][table_sha]['offset']; tl=tscan['objects'][table_sha]['length']; table_written=0
    else:
        rec=bytes.fromhex(table_sha)+struct.pack('>I',len(table_raw))+table_raw
        start=_append_durable(tp,rec); to=start+36; tl=len(table_raw); table_written=len(rec)
    if fail_after=='table': raise InjectedCrash('after table')

    # 3. generation spine becomes durable before pointer commit
    gf=generation_fields
    gen=serialize_generation(sequence=int(gf['sequence']),parent_sha=parent_state['generation_sha256'],parent_offset=int(parent_state['generation_offset']),parent_len=int(parent_state['generation_len']),table_sha=table_sha,table_offset=to,table_len=tl,overlay_sha=gf['overlay_sha256'],history_root=gf['history_root_sha256'],proof_manifest_sha=gf['proof_manifest_sha256'],final_source=gf['final_source_sha256'],final_semantic=gf['final_native_semantic_sha256'])
    frame=struct.pack('>I',len(gen))+gen; start=_append_durable(sp,frame); go=start+4; gl=len(gen); gsha=shahex2(gen)
    if fail_after=='spine': raise InjectedCrash('after spine')

    # 4. only pointer replacement commits current state
    ptr=serialize_pointer(int(gf['sequence']),go,gl,gsha); tmp=target.with_name(target.name+'.tmp')
    with tmp.open('wb') as f:
        f.write(ptr); _fsync_file_obj(f)
    if fail_after=='pointer_temp': raise InjectedCrash('after pointer temp')
    os.replace(tmp,target); _fsync_dir(target.parent)
    if fail_after=='pointer_commit': raise InjectedCrash('after pointer commit')

    after=recover(pointer_a=pa,pointer_b=pb,spine_path=sp,table_path=tp,block_pack_path=bp)
    return {'schema':'axm.flowing-compute-transaction-commit/v0.1','before_sequence':before['selected_sequence'],'after_sequence':after['selected_sequence'],'target_slot':target.name,'block_append_bytes':block_written,'table_append_bytes':table_written,'spine_append_bytes':len(frame),'pointer_bytes':len(ptr),'index':index_info,'generation_state':{'sequence':int(gf['sequence']),'generation_sha256':gsha,'generation_offset':go,'generation_len':gl},'truth':{'immutable_objects_before_pointer_commit':True,'spine_before_pointer_commit':True,'pointer_replace_same_directory_atomic_intent':True,'directory_fsync_requested':True,'recovery_not_index_dependent':True}}

def repair_invalid_tails(*,pointer_a:str|Path,pointer_b:str|Path,spine_path:str|Path,table_path:str|Path,block_pack_path:str|Path,block_index_path:str|Path|None=None,dry_run:bool=True)->dict[str,Any]:
    before=recover(pointer_a=pointer_a,pointer_b=pointer_b,spine_path=spine_path,table_path=table_path,block_pack_path=block_pack_path)
    actions=[]
    mapping=[('block_pack',Path(block_pack_path)),('table_store',Path(table_path)),('spine',Path(spine_path))]
    keys={'block_pack':'block_pack_bytes','table_store':'table_store_bytes','spine':'spine_bytes'}
    tails={'block_pack':'block_pack_tail_bytes','table_store':'table_store_tail_bytes','spine':'spine_tail_bytes'}
    for name,path in mapping:
        tail=int(before['valid_prefix'][tails[name]] or 0); valid=int(before['valid_prefix'][keys[name]] or 0)
        if tail>0:
            actions.append({'store':name,'truncate_from_bytes':path.stat().st_size,'truncate_to_bytes':valid,'removed_tail_bytes':tail})
            if not dry_run:
                with path.open('r+b') as f:
                    f.truncate(valid); _fsync_file_obj(f)
    if not dry_run and block_index_path is not None:
        rebuild_cas_index_atomic(block_pack_path,block_index_path)
    after=before if dry_run else recover(pointer_a=pointer_a,pointer_b=pointer_b,spine_path=spine_path,table_path=table_path,block_pack_path=block_pack_path)
    return {'schema':'axm.flowing-compute-tail-repair/v0.1','dry_run':dry_run,'selected_sequence_before':before['selected_sequence'],'selected_sequence_after':after['selected_sequence'],'actions':actions,'unpointed_newer_generations':before['unpointed_newer_generations'],'truth':{'only_scanner_proven_invalid_tail_is_truncated':True,'valid_unpointed_generations_are_not_truncated_as_tail':True,'unpointed_generations_not_auto_promoted':True,'committed_generation_must_survive_repair':True}}
