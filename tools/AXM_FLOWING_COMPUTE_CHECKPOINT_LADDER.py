from __future__ import annotations
import hashlib,json,struct
from pathlib import Path
from typing import Any
from AXM_FLOWING_COMPUTE_CRASH_RECOVERY import recover,scan_block_pack,scan_table_store,read_pointer_slot,_validate_candidate
from AXM_FLOWING_COMPUTE_ROOT_SPINE import parse_generation

SCHEMA = "axm.flowing-compute-checkpoint-ladder-entry/v0.1"

def canonical(v:Any)->bytes:return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def digest(v:Any)->str:return hashlib.sha256(canonical(v)).hexdigest()

def hash_range(path:str|Path,start:int,end:int)->str:
    if end<start:raise ValueError('invalid hash range')
    h=hashlib.sha256();left=end-start
    with Path(path).open('rb') as f:
        f.seek(start)
        while left:
            b=f.read(min(1024*1024,left))
            if not b:raise ValueError('spine shorter than requested hash range')
            h.update(b);left-=len(b)
    return h.hexdigest()

def _scan_segment_to_sequence(spine_path:str|Path, *, start_offset:int, parent_generation:dict[str,Any]|None, target_sequence:int)->dict[str,Any]:
    p=Path(spine_path);size=p.stat().st_size
    if start_offset>size:raise ValueError('checkpoint start beyond spine size')
    records=[];off=int(start_offset)
    prev_sha=(parent_generation or {}).get('generation_sha256');prev_off=(parent_generation or {}).get('generation_offset');prev_len=(parent_generation or {}).get('generation_len');prev_seq=(parent_generation or {}).get('sequence')
    first=True
    with p.open('rb') as f:
        f.seek(off)
        while off<size:
            frame_start=off;lnraw=f.read(4)
            if len(lnraw)<4:raise ValueError('incomplete spine length before checkpoint target')
            ln=struct.unpack('>I',lnraw)[0];payload=f.read(ln)
            if len(payload)<ln:raise ValueError('incomplete spine record before checkpoint target')
            g=parse_generation(payload);rec_off=frame_start+4
            if first and parent_generation is None:
                # Genesis-side root checkpoint: first valid record establishes chain start.
                pass
            else:
                if g.get('parent_generation_sha256')!=prev_sha or int(g.get('parent_offset',-1))!=int(prev_off) or int(g.get('parent_len',-1))!=int(prev_len) or int(g.get('sequence',-1))!=int(prev_seq)+1:
                    raise ValueError('checkpoint segment parent chain mismatch')
            records.append({'offset':rec_off,'length':ln,'parsed':g})
            off=rec_off+ln;prev_sha=g['generation_sha256'];prev_off=rec_off;prev_len=ln;prev_seq=int(g['sequence']);first=False
            if int(prev_seq)==int(target_sequence):
                return {'records':records,'end_offset':off,'anchor':{'generation_sha256':prev_sha,'generation_offset':prev_off,'generation_len':prev_len,'generation':g}}
            if int(prev_seq)>int(target_sequence):raise ValueError('checkpoint target sequence skipped')
    raise ValueError('checkpoint target sequence not found')

def _chain_root(parent_root:str|None, *, segment_sha256:str, sequence:int, anchor_sha256:str)->str:
    return hashlib.sha256(canonical({'parent_chain_root':parent_root,'segment_sha256':segment_sha256,'sequence':int(sequence),'anchor_generation_sha256':anchor_sha256})).hexdigest()

def make_root_checkpoint(spine_path:str|Path, *, sequence:int)->dict[str,Any]:
    scan=_scan_segment_to_sequence(spine_path,start_offset=0,parent_generation=None,target_sequence=sequence);end=int(scan['end_offset']);seg_sha=hash_range(spine_path,0,end);a=scan['anchor']
    cp={'schema':SCHEMA,'sequence':int(sequence),'segment_start':0,'segment_end':end,'segment_sha256':seg_sha,'parent_checkpoint_sha256':None,'parent_sequence':None,'chain_root_sha256':_chain_root(None,segment_sha256=seg_sha,sequence=sequence,anchor_sha256=a['generation_sha256']),'anchor':a,'truth':{'checkpoint_not_authority':True,'root_checkpoint_scans_only_to_its_early_anchor':True,'child_checkpoints_validate_only_new_segments':True}}
    cp['checkpoint_sha256']=digest(cp);return cp

def make_child_checkpoint(spine_path:str|Path, *, parent:dict[str,Any], sequence:int)->dict[str,Any]:
    validate_checkpoint(parent)
    if int(sequence)<=int(parent['sequence']):raise ValueError('child checkpoint sequence must advance')
    start=int(parent['segment_end']);pg={'generation_sha256':parent['anchor']['generation_sha256'],'generation_offset':parent['anchor']['generation_offset'],'generation_len':parent['anchor']['generation_len'],'sequence':parent['sequence']}
    scan=_scan_segment_to_sequence(spine_path,start_offset=start,parent_generation=pg,target_sequence=sequence);end=int(scan['end_offset']);seg_sha=hash_range(spine_path,start,end);a=scan['anchor']
    cp={'schema':SCHEMA,'sequence':int(sequence),'segment_start':start,'segment_end':end,'segment_sha256':seg_sha,'parent_checkpoint_sha256':parent['checkpoint_sha256'],'parent_sequence':int(parent['sequence']),'chain_root_sha256':_chain_root(parent['chain_root_sha256'],segment_sha256=seg_sha,sequence=sequence,anchor_sha256=a['generation_sha256']),'anchor':a,'truth':{'checkpoint_not_authority':True,'parent_checkpoint_required':True,'child_checkpoint_scans_only_new_segment':True}}
    cp['checkpoint_sha256']=digest(cp);return cp

def validate_checkpoint(cp:dict[str,Any])->None:
    if cp.get('schema')!=SCHEMA:raise ValueError('unsupported checkpoint ladder schema')
    stored=cp.get('checkpoint_sha256');body=dict(cp);body.pop('checkpoint_sha256',None)
    if digest(body)!=stored:raise ValueError('checkpoint integrity mismatch')
    if int(cp.get('segment_end',-1))<int(cp.get('segment_start',0)):raise ValueError('checkpoint segment bounds mismatch')
    a=cp.get('anchor') or {}
    if int(a.get('generation_offset',-1))+int(a.get('generation_len',-1))!=int(cp.get('segment_end',-2)):raise ValueError('checkpoint anchor/prefix mismatch')
    if int((a.get('generation') or {}).get('sequence',-1))!=int(cp.get('sequence',-2)):raise ValueError('checkpoint anchor sequence mismatch')
    if (a.get('generation') or {}).get('generation_sha256')!=a.get('generation_sha256'):raise ValueError('checkpoint anchor generation identity mismatch')

def write_checkpoint(path:str|Path,cp:dict[str,Any])->None:validate_checkpoint(cp);Path(path).write_text(json.dumps(cp,sort_keys=True,separators=(',',':'))+'\n')
def load_checkpoint(path:str|Path)->dict[str,Any]:cp=json.loads(Path(path).read_text());validate_checkpoint(cp);return cp

def build_ladder(spine_path:str|Path, checkpoint_dir:str|Path, *, interval:int, max_sequence:int)->list[dict[str,Any]]:
    checkpoint_dir=Path(checkpoint_dir);checkpoint_dir.mkdir(parents=True,exist_ok=True)
    if interval<1:raise ValueError('interval must be positive')
    seqs=list(range(interval,max_sequence+1,interval))
    if not seqs:return []
    parent=make_root_checkpoint(spine_path,sequence=seqs[0]);write_checkpoint(checkpoint_dir/f'cp-{seqs[0]:08d}.json',parent);out=[parent]
    for seq in seqs[1:]:
        child=make_child_checkpoint(spine_path,parent=parent,sequence=seq);write_checkpoint(checkpoint_dir/f'cp-{seq:08d}.json',child);out.append(child);parent=child
    return out

def load_valid_ladder(checkpoint_dir:str|Path, *, spine_path:str|Path|None=None, audit_segments:bool=False)->dict[str,Any]:
    files=sorted(Path(checkpoint_dir).glob('cp-*.json'));valid=[];previous=None;reason=None
    for path in files:
        try:cp=load_checkpoint(path)
        except Exception as exc:reason=f'checkpoint_invalid:{path.name}:{exc}';break
        if previous is None:
            if cp.get('parent_checkpoint_sha256') is not None or int(cp['segment_start'])!=0:reason='root_checkpoint_parent_mismatch';break
        else:
            if cp.get('parent_checkpoint_sha256')!=previous.get('checkpoint_sha256'):reason=f'checkpoint_parent_mismatch:{path.name}';break
            if int(cp.get('parent_sequence',-1))!=int(previous['sequence']):reason=f'checkpoint_parent_sequence_mismatch:{path.name}';break
            if int(cp['segment_start'])!=int(previous['segment_end']):reason=f'checkpoint_segment_gap:{path.name}';break
        expected=_chain_root(previous['chain_root_sha256'] if previous else None,segment_sha256=cp['segment_sha256'],sequence=cp['sequence'],anchor_sha256=cp['anchor']['generation_sha256'])
        if expected!=cp.get('chain_root_sha256'):reason=f'checkpoint_chain_root_mismatch:{path.name}';break
        if audit_segments:
            if spine_path is None:raise ValueError('audit_segments requires spine_path')
            if hash_range(spine_path,int(cp['segment_start']),int(cp['segment_end']))!=cp['segment_sha256']:reason=f'checkpoint_segment_hash_mismatch:{path.name}';break
        valid.append(cp);previous=cp
    return {'valid_checkpoints':valid,'last_valid_sequence':int(valid[-1]['sequence']) if valid else None,'break_reason':reason,'audit_segments':bool(audit_segments)}

def _full_fallback(reason:str,**kwargs)->dict[str,Any]:r=recover(**kwargs);r['recovery_mode']='full_fallback';r['checkpoint_ladder_fallback_reason']=reason;return r

def _view_from_checkpoint_to_sequence(spine_path:str|Path, cp:dict[str,Any], target_sequence:int)->dict[str,Any]:
    if int(target_sequence)<int(cp['sequence']):raise ValueError('target before checkpoint')
    anchor=cp['anchor'];anchor_rec={'offset':anchor['generation_offset'],'length':anchor['generation_len'],'raw':None,'parsed':anchor['generation']}
    if int(target_sequence)==int(cp['sequence']):return {'records':[anchor_rec],'by_sha':{anchor['generation_sha256']:anchor_rec},'scanned_records':0,'scanned_bytes':0}
    pg={'generation_sha256':anchor['generation_sha256'],'generation_offset':anchor['generation_offset'],'generation_len':anchor['generation_len'],'sequence':cp['sequence']}
    seg=_scan_segment_to_sequence(spine_path,start_offset=int(cp['segment_end']),parent_generation=pg,target_sequence=target_sequence)
    records=[anchor_rec]+[{'offset':r['offset'],'length':r['length'],'raw':None,'parsed':r['parsed']} for r in seg['records']]
    return {'records':records,'by_sha':{r['parsed']['generation_sha256']:r for r in records},'scanned_records':len(seg['records']),'scanned_bytes':int(seg['end_offset'])-int(cp['segment_end'])}

def recover_with_ladder(*, checkpoint_dir:str|Path,pointer_a:str|Path,pointer_b:str|Path,spine_path:str|Path,table_path:str|Path,block_pack_path:str|Path,audit_segments:bool=False)->dict[str,Any]:
    args={'pointer_a':pointer_a,'pointer_b':pointer_b,'spine_path':spine_path,'table_path':table_path,'block_pack_path':block_pack_path}
    ladder=load_valid_ladder(checkpoint_dir,spine_path=spine_path,audit_segments=audit_segments);checkpoints=ladder['valid_checkpoints']
    if audit_segments and ladder.get('break_reason'):return _full_fallback('audited_checkpoint_chain_failed:'+str(ladder['break_reason']),**args)
    if not checkpoints:return _full_fallback('no_valid_checkpoint_ladder',**args)
    tables=scan_table_store(table_path);blocks=scan_block_pack(block_pack_path);slots=[];groups={}
    for name,path in [('A',pointer_a),('B',pointer_b)]:
        item=read_pointer_slot(path);row={'slot':name,**item}
        if not item['valid']:row['dependency_valid']=False;slots.append(row);continue
        ptr=item['pointer'];eligible=[cp for cp in checkpoints if int(cp['sequence'])<=int(ptr['sequence'])]
        if not eligible:row['dependency_valid']=False;row['dependency_reason']='pointer_before_first_valid_checkpoint';slots.append(row);continue
        cp=eligible[-1];row['checkpoint_sequence']=int(cp['sequence']);row['_checkpoint']=cp;slots.append(row)
        g=groups.setdefault(int(cp['sequence']),{'checkpoint':cp,'target':int(ptr['sequence'])});g['target']=max(int(g['target']),int(ptr['sequence']))
    views={}
    try:
        for key,g in groups.items():views[key]=_view_from_checkpoint_to_sequence(spine_path,g['checkpoint'],g['target'])
    except Exception as exc:return _full_fallback('checkpoint_ladder_target_scan_failed:'+str(exc),**args)
    for row in slots:
        if not row.get('valid') or '_checkpoint' not in row:continue
        cp=row.pop('_checkpoint');view=views[int(cp['sequence'])];ptr=row['pointer'];ok,reason,g=_validate_candidate(ptr,view,tables,blocks);row['dependency_valid']=ok;row['dependency_reason']=reason;row['generation']=g;row['tail_scanned_records']=view['scanned_records'];row['tail_scanned_bytes']=view['scanned_bytes']
    valid=[r for r in slots if r.get('valid') and r.get('dependency_valid')];valid.sort(key=lambda r:int(r['pointer']['sequence']),reverse=True)
    if not valid:return _full_fallback('no_pointer_resolved_by_valid_checkpoint_ladder',**args)
    s=valid[0]
    return {'schema':'axm.flowing-compute-checkpoint-ladder-recovery/v0.1','status':'RECOVERED_COMMITTED','selected_sequence':int(s['pointer']['sequence']),'selected_slot':s['slot'],'selected_checkpoint_sequence':int(s['checkpoint_sequence']),'pointer_slots':slots,'recovery_mode':'checkpoint_ladder_audited' if audit_segments else 'checkpoint_ladder_carried_proof','ladder_last_valid_sequence':ladder['last_valid_sequence'],'ladder_break_reason':ladder['break_reason'],'truth':{'checkpoint_ladder_is_not_authority':True,'pointer_commit_remains_authority':True,'checkpoint_selection_is_at_or_before_pointer_target':True,'tail_scan_stops_at_required_pointer_target':True,'later_history_is_not_reparsed_for_older_rollback':True,'carried_mode_reuses_prior_segment_proofs':not audit_segments,'audited_mode_rehashes_all_checkpoint_segments':bool(audit_segments),'full_authoritative_fallback_available':True}}
