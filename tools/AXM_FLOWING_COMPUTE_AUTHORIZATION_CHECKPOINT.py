from __future__ import annotations
import hashlib,json,struct
from pathlib import Path
from typing import Any
from AXM_FLOWING_COMPUTE_AUTHORIZATION_RECEIPTS import STORE_MAGIC,validate_receipt,canonical,digest
SCHEMA='axm.flowing-compute-authorization-audit-checkpoint/v0.1'
def sha_file_prefix(path:str|Path,n:int)->str:
 h=hashlib.sha256();left=int(n)
 with Path(path).open('rb') as f:
  while left:
   b=f.read(min(1024*1024,left))
   if not b:raise ValueError('receipt store shorter than checkpoint prefix')
   h.update(b);left-=len(b)
 return h.hexdigest()
def scan_receipts(path:str|Path, *, start_offset:int|None=None, parent_receipt_sha256:str|None=None, stop_body_offset:int|None=None)->dict[str,Any]:
 p=Path(path);size=p.stat().st_size;off=len(STORE_MAGIC) if start_offset is None else int(start_offset);prev=parent_receipt_sha256;rows=[];reason=None
 with p.open('rb') as f:
  f.seek(off)
  while off<size:
   start=off
   if off+36>size:reason='incomplete_receipt_header';break
   hdr=f.read(36)
   if len(hdr)<36:reason='incomplete_receipt_header';break
   h=hdr[:32].hex();ln=struct.unpack('>I',hdr[32:])[0];bo=off+36;body=f.read(ln)
   if len(body)!=ln:reason='incomplete_receipt_object';break
   try:r=json.loads(body);validate_receipt(r)
   except Exception:reason='receipt_object_invalid';break
   if r['receipt_sha256']!=h:reason='receipt_content_address_mismatch';break
   if r.get('parent_receipt_sha256')!=prev:reason='receipt_parent_chain_mismatch';break
   row={'frame_start':start,'offset':bo,'length':ln,'receipt_sha256':h,'receipt':r};rows.append(row);prev=h;off=bo+ln
   if stop_body_offset is not None and bo==int(stop_body_offset):break
 return {'passed':reason is None,'records':rows,'last_receipt_sha256':prev,'valid_prefix_bytes':off,'tail_bytes':size-off,'reason':reason,'scanned_bytes':off-(len(STORE_MAGIC) if start_offset is None else int(start_offset))}
def full_audit(path:str|Path)->dict[str,Any]:return scan_receipts(path)
def create_checkpoint(path:str|Path, *, receipt_count:int)->dict[str,Any]:
 scan=full_audit(path)
 if not scan['passed']:raise ValueError('cannot checkpoint invalid receipt history')
 if receipt_count<1 or receipt_count>len(scan['records']):raise ValueError('receipt_count outside valid history')
 row=scan['records'][receipt_count-1];prefix=int(row['offset'])+int(row['length'])
 cp={'schema':SCHEMA,'receipt_count':int(receipt_count),'prefix_bytes':prefix,'prefix_sha256':sha_file_prefix(path,prefix),'anchor':{'receipt_sha256':row['receipt_sha256'],'receipt_offset':row['offset'],'receipt_len':row['length'],'receipt':row['receipt']},'truth':{'checkpoint_not_authority':True,'carried_mode_reuses_prior_audit':True,'audited_mode_rehashes_old_prefix':True,'full_audit_remains_available':True,'checkpoint_creation_currently_full_scans':True}}
 cp['checkpoint_sha256']=digest(cp);return cp
def validate_checkpoint(cp:dict[str,Any])->None:
 if cp.get('schema')!=SCHEMA:raise ValueError('bad authorization checkpoint schema')
 stored=cp.get('checkpoint_sha256');body=dict(cp);body.pop('checkpoint_sha256',None)
 if digest(body)!=stored:raise ValueError('authorization checkpoint integrity mismatch')
 a=cp['anchor'];validate_receipt(a['receipt'])
 if a['receipt']['receipt_sha256']!=a['receipt_sha256']:raise ValueError('authorization checkpoint anchor mismatch')
 if int(a['receipt_offset'])+int(a['receipt_len'])!=int(cp['prefix_bytes']):raise ValueError('authorization checkpoint prefix mismatch')
def checkpointed_audit(path:str|Path,cp:dict[str,Any],*,audit_prefix:bool=False)->dict[str,Any]:
 validate_checkpoint(cp)
 if audit_prefix and sha_file_prefix(path,int(cp['prefix_bytes']))!=cp['prefix_sha256']:
  return {'passed':False,'mode':'checkpoint_audited','reason':'checkpoint_prefix_hash_mismatch','checkpoint_receipt_count':cp['receipt_count']}
 tail=scan_receipts(path,start_offset=int(cp['prefix_bytes']),parent_receipt_sha256=cp['anchor']['receipt_sha256'])
 return {'passed':tail['passed'],'mode':'checkpoint_audited' if audit_prefix else 'checkpoint_carried','reason':tail['reason'],'checkpoint_receipt_count':cp['receipt_count'],'tail_receipts':len(tail['records']),'tail_scanned_bytes':tail['scanned_bytes'],'last_receipt_sha256':tail['last_receipt_sha256']}
