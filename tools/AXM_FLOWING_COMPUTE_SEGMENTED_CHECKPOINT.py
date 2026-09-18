from __future__ import annotations
import hashlib,json,struct
from pathlib import Path
from typing import Any
from AXM_FLOWING_COMPUTE_CRASH_RECOVERY import recover,scan_block_pack,scan_table_store,read_pointer_slot,_validate_candidate,scan_spine
from AXM_FLOWING_COMPUTE_ROOT_SPINE import parse_generation

SCHEMA='axm.flowing-compute-recovery-checkpoint/v0.2'

def canonical(v:Any)->bytes:return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def digest(v:Any)->str:return hashlib.sha256(canonical(v)).hexdigest()
def hash_range(path:str|Path,start:int,end:int)->str:
    if end<start:raise ValueError('invalid hash range')
    h=hashlib.sha256();left=end-start
    with Path(path).open('rb') as f:
        f.seek(start)
        while left:
            b=f.read(min(1024*1024,left))
            if not b:raise ValueError('spine shorter than checkpoint segment')
            h.update(b);left-=len(b)
    return h.hexdigest()

def _segment_root(segments:list[dict[str,Any]])->str:
    normalized=[{'start':int(x['start']),'end':int(x['end']),'sha256':x['sha256'],'start_sequence':int(x['start_sequence']),'end_sequence':int(x['end_sequence'])} for x in segments]
    return digest(normalized)

def validate_checkpoint(cp:dict[str,Any])->None:
    if cp.get('schema')!=SCHEMA:raise ValueError('unsupported segmented checkpoint schema')
    stored=cp.get('checkpoint_sha256');body=dict(cp);body.pop('checkpoint_sha256',None)
    if digest(body)!=stored:raise ValueError('segmented checkpoint integrity mismatch')
    segments=list(cp.get('segments') or [])
    if not segments:raise ValueError('segmented checkpoint requires segments')
    expected=0;last_seq=0
    for i,s in enumerate(segments):
        if int(s['start'])!=expected or int(s['end'])<=int(s['start']):raise ValueError('checkpoint segments are not contiguous')
        if i and int(s['start_sequence'])!=last_seq+1:raise ValueError('checkpoint segment sequence gap')
        expected=int(s['end']);last_seq=int(s['end_sequence'])
    if expected!=int(cp['spine_prefix_bytes']) or last_seq!=int(cp['sequence']):raise ValueError('checkpoint segment coverage mismatch')
    if _segment_root(segments)!=cp.get('segment_chain_root_sha256'):raise ValueError('checkpoint segment-chain identity mismatch')
    a=cp.get('anchor') or {}
    if int(a.get('generation_offset',-1))+int(a.get('generation_len',-1))!=int(cp.get('spine_prefix_bytes',-2)):raise ValueError('checkpoint anchor/prefix mismatch')
    if (a.get('generation') or {}).get('generation_sha256')!=a.get('generation_sha256'):raise ValueError('checkpoint anchor identity mismatch')

def write_checkpoint(path:str|Path,cp:dict[str,Any])->None:
    validate_checkpoint(cp);Path(path).write_text(json.dumps(cp,sort_keys=True,separators=(',',':'))+'\n')
def load_checkpoint(path:str|Path)->dict[str,Any]:
    cp=json.loads(Path(path).read_text());validate_checkpoint(cp);return cp

def _scan_to_sequence(spine_path:str|Path,start_offset:int,anchor:dict[str,Any],target_sequence:int)->dict[str,Any]:
    p=Path(spine_path);off=int(start_offset);records=[]
    prev_sha=anchor['generation_sha256'];prev_off=int(anchor['generation_offset']);prev_len=int(anchor['generation_len']);prev_seq=int(anchor['generation']['sequence'])
    if target_sequence<=prev_seq:raise ValueError('target sequence must advance parent checkpoint')
    with p.open('rb') as f:
        f.seek(off)
        while prev_seq<target_sequence:
            frame_start=off;lnraw=f.read(4)
            if len(lnraw)<4:raise ValueError('incomplete spine before checkpoint target')
            ln=struct.unpack('>I',lnraw)[0];payload=f.read(ln)
            if len(payload)<ln:raise ValueError('incomplete generation before checkpoint target')
            g=parse_generation(payload);rec_off=frame_start+4
            if g.get('parent_generation_sha256')!=prev_sha or int(g.get('parent_offset',-1))!=prev_off or int(g.get('parent_len',-1))!=prev_len or int(g.get('sequence',-1))!=prev_seq+1:raise ValueError('checkpoint advance parent chain mismatch')
            rec={'offset':rec_off,'length':ln,'parsed':g};records.append(rec);off=rec_off+ln;prev_sha=g['generation_sha256'];prev_off=rec_off;prev_len=ln;prev_seq=int(g['sequence'])
    return {'records':records,'end_offset':off,'anchor':records[-1]}

def bootstrap_checkpoint(spine_path:str|Path,*,sequence:int)->dict[str,Any]:
    scan=scan_spine(spine_path);matches=[r for r in scan['records'] if int(r['parsed']['sequence'])==int(sequence)]
    if len(matches)!=1:raise ValueError('bootstrap sequence not found uniquely')
    rec=matches[0];end=int(rec['offset'])+int(rec['length']);seg={'start':0,'end':end,'sha256':hash_range(spine_path,0,end),'start_sequence':1,'end_sequence':int(sequence)}
    cp={'schema':SCHEMA,'sequence':int(sequence),'spine_prefix_bytes':end,'segments':[seg],'segment_chain_root_sha256':_segment_root([seg]),'parent_checkpoint_sha256':None,'anchor':{'generation_sha256':rec['parsed']['generation_sha256'],'generation_offset':rec['offset'],'generation_len':rec['length'],'generation':rec['parsed']},'truth':{'checkpoint_not_authoritative':True,'bootstrap_is_full_admission':True,'incremental_advances_reuse_prior_verified_segments':True,'full_scan_fallback_required':True}}
    cp['checkpoint_sha256']=digest(cp);return cp

def advance_checkpoint(spine_path:str|Path,*,parent_checkpoint:dict[str,Any],target_sequence:int)->dict[str,Any]:
    validate_checkpoint(parent_checkpoint);step=_scan_to_sequence(spine_path,int(parent_checkpoint['spine_prefix_bytes']),parent_checkpoint['anchor'],int(target_sequence));end=int(step['end_offset']);start=int(parent_checkpoint['spine_prefix_bytes']);seg={'start':start,'end':end,'sha256':hash_range(spine_path,start,end),'start_sequence':int(parent_checkpoint['sequence'])+1,'end_sequence':int(target_sequence)};segments=list(parent_checkpoint['segments'])+[seg];last=step['anchor']
    cp={'schema':SCHEMA,'sequence':int(target_sequence),'spine_prefix_bytes':end,'segments':segments,'segment_chain_root_sha256':_segment_root(segments),'parent_checkpoint_sha256':parent_checkpoint['checkpoint_sha256'],'anchor':{'generation_sha256':last['parsed']['generation_sha256'],'generation_offset':last['offset'],'generation_len':last['length'],'generation':last['parsed']},'truth':{'checkpoint_not_authoritative':True,'bootstrap_is_full_admission':False,'incremental_advances_reuse_prior_verified_segments':True,'new_segment_only_hashed_and_parsed':True,'full_scan_fallback_required':True}}
    cp['checkpoint_sha256']=digest(cp);return cp

def audit_segments(spine_path:str|Path,cp:dict[str,Any])->bool:
    validate_checkpoint(cp);return all(hash_range(spine_path,int(s['start']),int(s['end']))==s['sha256'] for s in cp['segments'])

def scan_spine_tail(spine_path:str|Path,*,start_offset:int,anchor:dict[str,Any])->dict[str,Any]:
    p=Path(spine_path);size=p.stat().st_size
    if start_offset>size:raise ValueError('checkpoint prefix beyond current spine size')
    records=[];by_sha={};reason=None;off=int(start_offset);prev_sha=anchor['generation_sha256'];prev_off=int(anchor['generation_offset']);prev_len=int(anchor['generation_len']);prev_seq=int(anchor['generation']['sequence'])
    with p.open('rb') as f:
        f.seek(off)
        while off<size:
            frame_start=off;lnraw=f.read(4)
            if len(lnraw)<4:reason='incomplete_spine_length';break
            ln=struct.unpack('>I',lnraw)[0];payload=f.read(ln)
            if len(payload)<ln:reason='incomplete_spine_record';break
            try:g=parse_generation(payload)
            except Exception:reason='spine_record_invalid';break
            rec_off=frame_start+4
            if g.get('parent_generation_sha256')!=prev_sha or int(g.get('parent_offset',-1))!=prev_off or int(g.get('parent_len',-1))!=prev_len or int(g.get('sequence',-1))!=prev_seq+1:reason='tail_parent_chain_mismatch';break
            rec={'offset':rec_off,'length':ln,'raw':payload,'parsed':g};records.append(rec);by_sha[g['generation_sha256']]=rec;off=rec_off+ln;prev_sha=g['generation_sha256'];prev_off=rec_off;prev_len=ln;prev_seq=int(g['sequence'])
    return {'records':records,'by_sha':by_sha,'valid_prefix_bytes':off,'tail_bytes':size-off,'tail_reason':reason,'scanned_bytes':off-int(start_offset),'scanned_records':len(records)}

def _fallback(reason:str,**kwargs)->dict[str,Any]:
    r=recover(**kwargs);r['recovery_mode']='full_fallback';r['checkpoint_fallback_reason']=reason;return r

def recover_segmented(*,checkpoint_path:str|Path,pointer_a:str|Path,pointer_b:str|Path,spine_path:str|Path,table_path:str|Path,block_pack_path:str|Path,audit_prefix:bool=False)->dict[str,Any]:
    args={'pointer_a':pointer_a,'pointer_b':pointer_b,'spine_path':spine_path,'table_path':table_path,'block_pack_path':block_pack_path}
    try:cp=load_checkpoint(checkpoint_path)
    except Exception as e:return _fallback('checkpoint_invalid:'+str(e),**args)
    if audit_prefix:
        try:
            if not audit_segments(spine_path,cp):return _fallback('checkpoint_segment_hash_mismatch',**args)
        except Exception as e:return _fallback('checkpoint_segment_audit_failed:'+str(e),**args)
    try:tail=scan_spine_tail(spine_path,start_offset=int(cp['spine_prefix_bytes']),anchor=cp['anchor'])
    except Exception as e:return _fallback('checkpoint_tail_setup_failed:'+str(e),**args)
    tables=scan_table_store(table_path);blocks=scan_block_pack(block_pack_path);a=cp['anchor'];anchor_rec={'offset':a['generation_offset'],'length':a['generation_len'],'raw':None,'parsed':a['generation']};spine_view={'records':[anchor_rec]+tail['records'],'by_sha':{a['generation_sha256']:anchor_rec,**tail['by_sha']}}
    slots=[];older=False
    for name,path in [('A',pointer_a),('B',pointer_b)]:
        item=read_pointer_slot(path);row={'slot':name,**item}
        if item['valid']:
            ptr=item['pointer']
            if int(ptr['sequence'])<int(cp['sequence']):row['dependency_valid']=False;row['dependency_reason']='pointer_before_checkpoint';older=True
            else:
                ok,reason,g=_validate_candidate(ptr,spine_view,tables,blocks);row['dependency_valid']=ok;row['dependency_reason']=reason;row['generation']=g
        else:row['dependency_valid']=False
        slots.append(row)
    valid=[r for r in slots if r.get('valid') and r.get('dependency_valid')];valid.sort(key=lambda r:r['pointer']['sequence'],reverse=True)
    if not valid:return _fallback('no_checkpoint_resolvable_valid_pointer' if older else 'no_valid_pointer_in_checkpoint_or_tail',**args)
    selected=valid[0]
    return {'schema':'axm.flowing-compute-segmented-checkpoint-recovery/v0.1','status':'RECOVERED_COMMITTED','selected_sequence':selected['pointer']['sequence'],'selected_slot':selected['slot'],'recovery_mode':'segmented_checkpoint_audited' if audit_prefix else 'segmented_checkpoint_carried_proof','checkpoint_sequence':cp['sequence'],'checkpoint_segments':len(cp['segments']),'tail':{'scanned_records':tail['scanned_records'],'scanned_bytes':tail['scanned_bytes'],'tail_bytes':tail['tail_bytes'],'tail_reason':tail['tail_reason']},'truth':{'checkpoint_not_authority':True,'old_segments_reused_from_prior_checkpoint':True,'audit_rehashes_all_segments':bool(audit_prefix),'full_fallback_available':True}}
