from __future__ import annotations
import json,os,struct
from pathlib import Path
from typing import Any
from AXM_FLOWING_COMPUTE_CHECKPOINT_SPINE import SEG_MAGIC,SPINE_MAGIC,make_segment,validate_segment,make_record,validate_record,serialize_pointer,parse_pointer,canonical,sha
class InjectedCrash(RuntimeError):pass

def _fsync(f):f.flush();os.fsync(f.fileno())
def _fsync_dir(p:Path):
    fd=os.open(str(p),os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)
def scan_segments(path:str|Path)->dict[str,Any]:
    p=Path(path);raw=p.read_bytes()
    if not raw.startswith(SEG_MAGIC):return {'valid':False,'objects':{},'records':[],'valid_prefix_bytes':0,'tail_bytes':len(raw),'reason':'bad_magic'}
    off=len(SEG_MAGIC);objs={};records=[];reason=None
    while off<len(raw):
        start=off
        if off+36>len(raw):reason='incomplete_segment_header';break
        h=raw[off:off+32].hex();ln=struct.unpack('>I',raw[off+32:off+36])[0];bo=off+36;end=bo+ln
        if end>len(raw):reason='incomplete_segment_object';break
        body=raw[bo:end]
        if sha(body)!=h:reason='segment_object_hash_mismatch';break
        try:obj=json.loads(body);validate_segment(obj)
        except Exception:reason='segment_object_invalid';break
        records.append({'frame_start':start,'offset':bo,'length':ln,'sha256':h,'object':obj});objs[h]=records[-1];off=end
    return {'valid':True,'objects':objs,'records':records,'valid_prefix_bytes':off,'tail_bytes':len(raw)-off,'reason':reason}
def scan_checkpoint_spine(path:str|Path)->dict[str,Any]:
    p=Path(path);raw=p.read_bytes()
    if not raw.startswith(SPINE_MAGIC):return {'valid':False,'records':[],'by_offset':{},'valid_prefix_bytes':0,'tail_bytes':len(raw),'reason':'bad_magic'}
    off=len(SPINE_MAGIC);rows=[];by_offset={};reason=None
    while off<len(raw):
        frame=off
        if off+4>len(raw):reason='incomplete_checkpoint_length';break
        ln=struct.unpack('>I',raw[off:off+4])[0];bo=off+4;end=bo+ln
        if end>len(raw):reason='incomplete_checkpoint_record';break
        body=raw[bo:end]
        try:rec=json.loads(body);validate_record(rec)
        except Exception:reason='checkpoint_record_invalid';break
        row={'frame_start':frame,'offset':bo,'length':ln,'record':rec};rows.append(row);by_offset[(bo,ln,rec['checkpoint_sha256'])]=row;off=end
    return {'valid':True,'records':rows,'by_offset':by_offset,'valid_prefix_bytes':off,'tail_bytes':len(raw)-off,'reason':reason}
def _validate_candidate(ptr:dict[str,Any],cps:dict[str,Any],segs:dict[str,Any])->tuple[bool,str,dict[str,Any]|None]:
    key=(int(ptr['offset']),int(ptr['length']),ptr['checkpoint_sha256']);row=cps['by_offset'].get(key)
    if row is None:return False,'checkpoint_record_missing_or_invalid',None
    rec=row['record']
    if int(rec['sequence'])!=int(ptr['sequence']):return False,'checkpoint_sequence_mismatch',None
    if rec['segment_sha256'] not in segs['objects']:return False,'segment_object_missing_or_invalid',None
    seg=segs['objects'][rec['segment_sha256']]['object']
    if int(seg['end_sequence'])!=int(rec['sequence']) or int(seg['end'])!=int(rec['spine_prefix_bytes']):return False,'segment_checkpoint_mismatch',None
    cur=rec;seen=set()
    while cur['parent_checkpoint_sha256'] is not None:
        marker=cur['checkpoint_sha256']
        if marker in seen:return False,'checkpoint_parent_cycle',None
        seen.add(marker);pk=(int(cur['parent_offset']),int(cur['parent_len']),cur['parent_checkpoint_sha256']);prow=cps['by_offset'].get(pk)
        if prow is None:return False,'checkpoint_parent_missing_or_invalid',None
        parent=prow['record'];pseg=segs['objects'].get(parent['segment_sha256'])
        if pseg is None:return False,'checkpoint_parent_segment_missing_or_invalid',None
        child_seg=segs['objects'][cur['segment_sha256']]['object'];parent_seg=pseg['object']
        if int(parent_seg['end'])!=int(child_seg['start']) or int(parent_seg['end_sequence'])+1!=int(child_seg['start_sequence']):return False,'checkpoint_history_gap',None
        cur=parent
    return True,'ok',rec
def read_pointer(path:str|Path)->dict[str,Any]:
    p=Path(path)
    if not p.is_file():return {'valid':False,'reason':'missing'}
    try:return {'valid':True,'pointer':parse_pointer(p.read_bytes())}
    except Exception as e:return {'valid':False,'reason':str(e)}
def recover(*,pointer_a:str|Path,pointer_b:str|Path,segment_store:str|Path,checkpoint_spine:str|Path)->dict[str,Any]:
    segs=scan_segments(segment_store);cps=scan_checkpoint_spine(checkpoint_spine);slots=[]
    for name,path in [('A',pointer_a),('B',pointer_b)]:
        item=read_pointer(path);row={'slot':name,**item}
        if item['valid']:
            ok,reason,rec=_validate_candidate(item['pointer'],cps,segs);row['dependency_valid']=ok;row['dependency_reason']=reason;row['record']=rec
        else:row['dependency_valid']=False
        slots.append(row)
    valid=[r for r in slots if r.get('valid') and r.get('dependency_valid')];valid.sort(key=lambda r:int(r['pointer']['sequence']),reverse=True)
    if not valid:return {'status':'HOLD','selected_sequence':None,'pointer_slots':slots,'store_state':{'segment_tail_bytes':segs['tail_bytes'],'checkpoint_tail_bytes':cps['tail_bytes'],'segment_tail_reason':segs['reason'],'checkpoint_tail_reason':cps['reason']}}
    s=valid[0];pointed={r['pointer']['checkpoint_sha256'] for r in slots if r.get('valid')};unpointed=[]
    for row in cps['records']:
        rec=row['record']
        if rec['checkpoint_sha256'] not in pointed and int(rec['sequence'])>int(s['pointer']['sequence']):
            fake={'sequence':rec['sequence'],'offset':row['offset'],'length':row['length'],'checkpoint_sha256':rec['checkpoint_sha256']};ok,reason,_=_validate_candidate(fake,cps,segs);unpointed.append({'sequence':rec['sequence'],'checkpoint_sha256':rec['checkpoint_sha256'],'valid':ok,'reason':reason})
    return {'schema':'axm.flowing-compute-checkpoint-transaction-recovery/v0.1','status':'RECOVERED_COMMITTED','selected_slot':s['slot'],'selected_sequence':int(s['pointer']['sequence']),'pointer':s['pointer'],'record':s['record'],'pointer_slots':slots,'unpointed_newer_checkpoints':unpointed,'store_state':{'segment_tail_bytes':segs['tail_bytes'],'checkpoint_tail_bytes':cps['tail_bytes'],'segment_tail_reason':segs['reason'],'checkpoint_tail_reason':cps['reason']},'truth':{'pointer_replace_is_checkpoint_commit_surface':True,'unpointed_checkpoint_not_current':True,'valid_prefix_survives_torn_newest_tail':True}}
def _append(path:Path,raw:bytes)->int:
    with path.open('ab') as f:start=f.tell();f.write(raw);_fsync(f);return start
def _inactive(selected:str|None,a:Path,b:Path)->Path:return b if selected=='A' else a
def commit(*,pointer_a:str|Path,pointer_b:str|Path,segment_store:str|Path,checkpoint_spine:str|Path,segment:dict[str,Any],anchor:dict[str,Any],fail_after:str|None=None)->dict[str,Any]:
    pa,pb,sg,cp=Path(pointer_a),Path(pointer_b),Path(segment_store),Path(checkpoint_spine);before=recover(pointer_a=pa,pointer_b=pb,segment_store=sg,checkpoint_spine=cp)
    parent=before.get('record');parent_ptr=before.get('pointer');selected=before.get('selected_slot')
    if parent is None:
        if int(segment['start_sequence'])!=1:raise ValueError('first checkpoint segment must start at generation 1')
        parent_off=parent_len=None
    else:
        if int(segment['start_sequence'])!=int(parent['sequence'])+1 or int(segment['start'])!=int(parent['spine_prefix_bytes']):raise ValueError('new segment does not extend committed checkpoint')
        parent_off=int(parent_ptr['offset']);parent_len=int(parent_ptr['length'])
    sobj=make_segment(segment);sraw=canonical(sobj);ssha=sha(sraw);segs=scan_segments(sg)
    if ssha not in segs['objects']:_append(sg,bytes.fromhex(ssha)+struct.pack('>I',len(sraw))+sraw)
    if fail_after=='segment':raise InjectedCrash('after segment')
    rec=make_record(sequence=segment['end_sequence'],spine_prefix_bytes=segment['end'],segment_sha256=ssha,anchor=anchor,parent=parent,parent_offset=parent_off,parent_len=parent_len);rraw=canonical(rec);frame=struct.pack('>I',len(rraw))+rraw;start=_append(cp,frame);ro=start+4;rl=len(rraw)
    if fail_after=='checkpoint':raise InjectedCrash('after checkpoint')
    target=_inactive(selected,pa,pb);praw=serialize_pointer(rec['sequence'],ro,rl,rec['checkpoint_sha256']);tmp=target.with_name(target.name+'.tmp')
    with tmp.open('wb') as f:f.write(praw);_fsync(f)
    if fail_after=='pointer_temp':raise InjectedCrash('after pointer temp')
    os.replace(tmp,target);_fsync_dir(target.parent)
    if fail_after=='pointer_commit':raise InjectedCrash('after pointer commit')
    after=recover(pointer_a=pa,pointer_b=pb,segment_store=sg,checkpoint_spine=cp)
    return {'before_sequence':before.get('selected_sequence'),'after_sequence':after.get('selected_sequence'),'target_slot':target.name,'pointer_bytes':len(praw),'truth':{'segment_before_checkpoint_record':True,'checkpoint_record_before_pointer':True,'pointer_replace_is_commit':True}}
