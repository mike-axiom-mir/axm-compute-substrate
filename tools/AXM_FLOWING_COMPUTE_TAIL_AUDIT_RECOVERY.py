from __future__ import annotations
import struct
from pathlib import Path
from typing import Any
from AXM_FLOWING_COMPUTE_LIVE_POINTER import read_slot
from AXM_FLOWING_COMPUTE_LIVE_CHECKPOINT import validate_checkpoint
from AXM_FLOWING_COMPUTE_LIVE_SEGMENT_ACCUMULATOR import start,advance
from AXM_FLOWING_COMPUTE_ROOT_SPINE import parse_generation

def audit_pointer_tail(*,pointer:dict[str,Any],checkpoint:dict[str,Any],spine_path:str|Path)->dict[str,Any]:
    validate_checkpoint(checkpoint);seq=int(pointer['sequence']);cpseq=int(checkpoint['sequence'])
    if seq<=cpseq:return {'passed':False,'reason':'pointer_not_newer_than_checkpoint'}
    expected_start_sequence=cpseq+1;expected_start_offset=int(checkpoint['spine_prefix_bytes']);claimed=pointer['accumulator']
    if int(claimed['start_sequence'])!=expected_start_sequence or int(claimed['start_offset'])!=expected_start_offset:return {'passed':False,'reason':'accumulator_start_does_not_extend_checkpoint'}
    state=start(start_sequence=expected_start_sequence,start_offset=expected_start_offset);off=expected_start_offset;prev=checkpoint['anchor'];records=0
    with Path(spine_path).open('rb') as f:
        f.seek(off)
        while int(state['last_sequence'])<seq:
            frame=off;lr=f.read(4)
            if len(lr)!=4:return {'passed':False,'reason':'tail_truncated_before_pointer'}
            ln=struct.unpack('>I',lr)[0];raw=f.read(ln)
            if len(raw)!=ln:return {'passed':False,'reason':'tail_generation_truncated'}
            g=parse_generation(raw);go=frame+4
            if int(g['sequence'])!=int(state['last_sequence'])+1:return {'passed':False,'reason':'tail_sequence_gap'}
            if g.get('parent_generation_sha256')!=prev['generation_sha256'] or int(g.get('parent_offset',-1))!=int(prev['generation_offset']) or int(g.get('parent_len',-1))!=int(prev['generation_len']):return {'passed':False,'reason':'tail_parent_chain_mismatch'}
            state=advance(state,sequence=g['sequence'],generation_sha256=g['generation_sha256'],generation_offset=go,generation_len=ln);prev={'generation_sha256':g['generation_sha256'],'generation_offset':go,'generation_len':ln};off=go+ln;records+=1
    actual={'generation_sha256':pointer['generation_sha256'],'generation_offset':int(pointer['generation_offset']),'generation_len':int(pointer['generation_len'])}
    if prev!=actual:return {'passed':False,'reason':'pointer_generation_does_not_match_audited_tail','records':records}
    fields=('start_sequence','start_offset','last_sequence','last_offset','last_len','count','root_sha256');mismatches=[k for k in fields if state[k]!=claimed[k]]
    if mismatches:return {'passed':False,'reason':'pointer_accumulator_semantic_mismatch','mismatches':mismatches,'records':records,'computed':state}
    return {'passed':True,'reason':'tail_accumulator_matches_pointer','records':records,'bytes':off-expected_start_offset,'computed':state}

def recover_audited_tail(*,pointer_a:str|Path,pointer_b:str|Path,checkpoint:dict[str,Any],spine_path:str|Path)->dict[str,Any]:
    rows=[]
    for name,path in [('A',pointer_a),('B',pointer_b)]:
        item=read_slot(path);row={'slot':name,**item}
        if item.get('valid'):
            audit=audit_pointer_tail(pointer=item['pointer'],checkpoint=checkpoint,spine_path=spine_path);row['tail_audit']=audit;row['semantic_valid']=bool(audit['passed'])
        else:row['semantic_valid']=False
        rows.append(row)
    valid=[r for r in rows if r.get('valid') and r.get('semantic_valid')];valid.sort(key=lambda r:int(r['pointer']['sequence']),reverse=True)
    if not valid:return {'schema':'axm.flowing-compute-tail-audited-recovery/v0.1','status':'HOLD','pointer_slots':rows,'reason':'no semantically valid pointer tail'}
    s=valid[0]
    return {'schema':'axm.flowing-compute-tail-audited-recovery/v0.1','status':'RECOVERED_COMMITTED','selected_slot':s['slot'],'selected_sequence':int(s['pointer']['sequence']),'pointer':s['pointer'],'tail_audit':s['tail_audit'],'pointer_slots':rows,'truth':{'checkpoint_is_prior_proof_anchor':True,'tail_semantics_reestablished_from_spine':True,'outer_pointer_checksum_alone_is_not_semantic_proof':True,'later_history_outside_pointer_target_not_scanned':True}}
