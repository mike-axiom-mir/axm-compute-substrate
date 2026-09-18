from __future__ import annotations
import hashlib,json,struct
from pathlib import Path
from typing import Any
from AXM_FLOWING_COMPUTE_CRASH_RECOVERY import recover,scan_block_pack,scan_table_store,read_pointer_slot,_validate_candidate
from AXM_FLOWING_COMPUTE_ROOT_SPINE import parse_generation

SCHEMA='axm.flowing-compute-recovery-checkpoint/v0.1'

def canonical(v:Any)->bytes:return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def digest(v:Any)->str:return hashlib.sha256(canonical(v)).hexdigest()

def hash_prefix(path:str|Path,n:int)->str:
    h=hashlib.sha256();left=int(n)
    with Path(path).open('rb') as f:
        while left:
            b=f.read(min(1024*1024,left))
            if not b:raise ValueError('spine shorter than checkpoint prefix')
            h.update(b);left-=len(b)
    return h.hexdigest()

def create_checkpoint(spine_path:str|Path, *, sequence:int)->dict[str,Any]:
    # Creation is intentionally authoritative/full; Wave 25 measures this as a cost, not a free operation.
    from AXM_FLOWING_COMPUTE_CRASH_RECOVERY import scan_spine
    scan=scan_spine(spine_path)
    matches=[r for r in scan['records'] if int(r['parsed']['sequence'])==int(sequence)]
    if len(matches)!=1:raise ValueError('checkpoint sequence not found uniquely in valid spine prefix')
    rec=matches[0];prefix_bytes=int(rec['offset'])+int(rec['length'])
    cp={'schema':SCHEMA,'sequence':int(sequence),'spine_prefix_bytes':prefix_bytes,'spine_prefix_sha256':hash_prefix(spine_path,prefix_bytes),'anchor':{'generation_sha256':rec['parsed']['generation_sha256'],'generation_offset':rec['offset'],'generation_len':rec['length'],'generation':rec['parsed']},'trust_modes':{'carried_proof':'assumes previously verified prefix remains immutable','audited':'rehashes checkpoint prefix before using carried parsed anchor'},'truth':{'checkpoint_not_authoritative':True,'full_scan_fallback_required':True,'rollback_before_checkpoint_requires_full_fallback':True,'carried_proof_does_not_rediscover_same_size_historical_mutation':True,'checkpoint_creation_currently_scans_from_zero':True}}
    cp['checkpoint_sha256']=digest(cp);return cp

def validate_checkpoint(cp:dict[str,Any])->None:
    if cp.get('schema')!=SCHEMA:raise ValueError('unsupported recovery checkpoint schema')
    stored=cp.get('checkpoint_sha256');body=dict(cp);body.pop('checkpoint_sha256',None)
    if digest(body)!=stored:raise ValueError('recovery checkpoint integrity mismatch')
    a=cp.get('anchor') or {}
    if int(a.get('generation_offset',-1))+int(a.get('generation_len',-1))!=int(cp.get('spine_prefix_bytes',-2)):raise ValueError('checkpoint anchor/prefix mismatch')
    if (a.get('generation') or {}).get('generation_sha256')!=a.get('generation_sha256'):raise ValueError('checkpoint anchor identity mismatch')

def write_checkpoint(path:str|Path,cp:dict[str,Any])->None:
    validate_checkpoint(cp);Path(path).write_text(json.dumps(cp,sort_keys=True,separators=(',',':'))+'\n')

def load_checkpoint(path:str|Path)->dict[str,Any]:
    cp=json.loads(Path(path).read_text());validate_checkpoint(cp);return cp

def scan_spine_tail(spine_path:str|Path, *, start_offset:int, anchor:dict[str,Any])->dict[str,Any]:
    p=Path(spine_path);size=p.stat().st_size
    if start_offset>size:raise ValueError('checkpoint prefix beyond current spine size')
    records=[];by_sha={};reason=None;off=int(start_offset)
    prev_sha=anchor['generation_sha256'];prev_off=int(anchor['generation_offset']);prev_len=int(anchor['generation_len']);prev_seq=int(anchor['generation']['sequence'])
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
            if g.get('parent_generation_sha256')!=prev_sha or int(g.get('parent_offset',-1))!=prev_off or int(g.get('parent_len',-1))!=prev_len or int(g.get('sequence',-1))!=prev_seq+1:
                reason='tail_parent_chain_mismatch';break
            rec={'offset':rec_off,'length':ln,'raw':payload,'parsed':g};records.append(rec);by_sha[g['generation_sha256']]=rec
            off=rec_off+ln;prev_sha=g['generation_sha256'];prev_off=rec_off;prev_len=ln;prev_seq=int(g['sequence'])
    return {'valid':True,'records':records,'by_sha':by_sha,'valid_prefix_bytes':off,'tail_bytes':size-off,'tail_reason':reason,'scanned_bytes':off-int(start_offset),'scanned_records':len(records)}

def _full_fallback(reason:str,**kwargs)->dict[str,Any]:
    r=recover(**kwargs);r['recovery_mode']='full_fallback';r['checkpoint_fallback_reason']=reason;return r

def recover_checkpointed(*,checkpoint_path:str|Path,pointer_a:str|Path,pointer_b:str|Path,spine_path:str|Path,table_path:str|Path,block_pack_path:str|Path,audit_prefix:bool=False)->dict[str,Any]:
    args={'pointer_a':pointer_a,'pointer_b':pointer_b,'spine_path':spine_path,'table_path':table_path,'block_pack_path':block_pack_path}
    try:cp=load_checkpoint(checkpoint_path)
    except Exception as e:return _full_fallback('checkpoint_invalid:'+str(e),**args)
    try:
        if audit_prefix and hash_prefix(spine_path,int(cp['spine_prefix_bytes']))!=cp['spine_prefix_sha256']:
            return _full_fallback('checkpoint_prefix_hash_mismatch',**args)
        tail=scan_spine_tail(spine_path,start_offset=int(cp['spine_prefix_bytes']),anchor=cp['anchor'])
    except Exception as e:return _full_fallback('checkpoint_tail_setup_failed:'+str(e),**args)
    tables=scan_table_store(table_path);blocks=scan_block_pack(block_pack_path)
    anchor=cp['anchor'];anchor_rec={'offset':anchor['generation_offset'],'length':anchor['generation_len'],'raw':None,'parsed':anchor['generation']}
    spine_view={'records':[anchor_rec]+tail['records'],'by_sha':{anchor['generation_sha256']:anchor_rec,**tail['by_sha']}}
    slots=[];needs_older_fallback=False
    for name,path in [('A',pointer_a),('B',pointer_b)]:
        item=read_pointer_slot(path);row={'slot':name,**item}
        if item['valid']:
            ptr=item['pointer']
            if int(ptr['sequence'])<int(cp['sequence']):
                row['dependency_valid']=False;row['dependency_reason']='pointer_before_checkpoint';needs_older_fallback=True
            else:
                ok,reason,g=_validate_candidate(ptr,spine_view,tables,blocks);row['dependency_valid']=ok;row['dependency_reason']=reason;row['generation']=g
        else:row['dependency_valid']=False
        slots.append(row)
    valid=[r for r in slots if r.get('valid') and r.get('dependency_valid')];valid.sort(key=lambda r:r['pointer']['sequence'],reverse=True)
    if not valid:
        return _full_fallback('no_checkpoint_resolvable_valid_pointer' if needs_older_fallback else 'no_valid_pointer_in_checkpoint_or_tail',**args)
    selected=valid[0];selected_seq=selected['pointer']['sequence'];pointed={r['pointer']['generation_sha256'] for r in slots if r.get('valid')}
    unpointed=[]
    for rec in tail['records']:
        g=rec['parsed']
        if g['generation_sha256'] not in pointed and int(g['sequence'])>int(selected_seq):
            ptr={'generation_sha256':g['generation_sha256'],'generation_offset':rec['offset'],'generation_len':rec['length'],'sequence':g['sequence']}
            ok,reason,_=_validate_candidate(ptr,spine_view,tables,blocks);unpointed.append({'sequence':g['sequence'],'generation_sha256':g['generation_sha256'],'dependency_valid':ok,'reason':reason})
    return {'schema':'axm.flowing-compute-checkpointed-recovery/v0.1','status':'RECOVERED_COMMITTED','selected_sequence':selected_seq,'selected_slot':selected['slot'],'pointer_slots':slots,'unpointed_newer_generations':unpointed,'recovery_mode':'checkpoint_audited' if audit_prefix else 'checkpoint_carried_proof','checkpoint_sequence':cp['sequence'],'checkpoint_prefix_bytes':cp['spine_prefix_bytes'],'checkpoint_prefix_rehashed':bool(audit_prefix),'tail':{'scanned_records':tail['scanned_records'],'scanned_bytes':tail['scanned_bytes'],'tail_bytes':tail['tail_bytes'],'tail_reason':tail['tail_reason']},'truth':{'checkpoint_is_not_authority':True,'checkpoint_prefix_was_verified_when_created':True,'carried_proof_mode_assumes_prefix_immutability':not audit_prefix,'audited_mode_rehashes_prefix':bool(audit_prefix),'full_authoritative_fallback_available':True}}
