from __future__ import annotations
import hashlib,json,struct,zlib
from pathlib import Path
from typing import Any
from AXM_FLOWING_COMPUTE_NATIVE_PACKED_STATE import parse_native,_semantic_hash,serialize_native_with_identity

MAGIC=b'AXOV17\x00\x01'
SCHEMA='axm.flowing-compute-native-overlay/v0.1'

def canon(v:Any)->bytes:return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def shahex(raw:bytes)->str:return hashlib.sha256(raw).hexdigest()
def shab(raw:bytes)->bytes:return hashlib.sha256(raw).digest()
def _get(block,i):return bytes(block[i*32:(i+1)*32])
def _set(block,i,v):block[i*32:(i+1)*32]=v

def _same_structure(a,b):
 keys=['edge_ids','component_members','component_edge_indices','predecessors','successors','topological_order','counts','edge_count','component_count']
 return all(a['header'][k]==b['header'][k] for k in keys) and bytes(a['edge_topology_hashes'])==bytes(b['edge_topology_hashes'])

def build_overlay_from_parsed(a:dict[str,Any],b:dict[str,Any],*,delta_sha256:str,previous_artifact_sha256:str)->bytes:
 if not _same_structure(a,b):raise ValueError('HOLD: overlay requires identical structural topology')
 def diffs(x,y,count):return [(i,_get(y,i)) for i in range(count) if _get(x,i)!=_get(y,i)]
 edge=diffs(a['edge_hashes'],b['edge_hashes'],a['header']['edge_count'])
 local=diffs(a['local_hashes'],b['local_hashes'],a['header']['component_count'])
 sig=diffs(a['signatures'],b['signatures'],a['header']['component_count'])
 header={'schema':SCHEMA,'from_source_sha256':a['header']['source_sha256'],'to_source_sha256':b['header']['source_sha256'],
  'parent_native_semantic_sha256':a['header']['native_semantic_sha256'],'target_native_semantic_sha256':b['header']['native_semantic_sha256'],
  'delta_sha256':delta_sha256,'previous_artifact_sha256':previous_artifact_sha256,'edge_updates':len(edge),'local_updates':len(local),'signature_updates':len(sig)}
 hb=zlib.compress(canon(header),6)
 records=b''.join(struct.pack('>I',i)+v for i,v in edge)+b''.join(struct.pack('>H',i)+v for i,v in local)+b''.join(struct.pack('>H',i)+v for i,v in sig)
 prefix=MAGIC+struct.pack('>IIII',len(hb),len(edge),len(local),len(sig))+hb+records
 return prefix+shab(prefix)

def build_overlay(from_raw:bytes,to_raw:bytes,*,delta_sha256:str,previous_artifact_sha256:str)->bytes:
 return build_overlay_from_parsed(parse_native(from_raw,validate_semantic=True),parse_native(to_raw,validate_semantic=True),delta_sha256=delta_sha256,previous_artifact_sha256=previous_artifact_sha256)

def build_overlay_from_update_sets(a:dict[str,Any],b:dict[str,Any],*,delta_sha256:str,previous_artifact_sha256:str,edge_indices:set[int]|list[int],local_indices:set[int]|list[int],signature_indices:set[int]|list[int])->bytes:
 if not _same_structure(a,b):raise ValueError('HOLD: overlay requires identical structural topology')
 edge=[(i,_get(b['edge_hashes'],i)) for i in sorted(set(edge_indices)) if _get(a['edge_hashes'],i)!=_get(b['edge_hashes'],i)]
 local=[(i,_get(b['local_hashes'],i)) for i in sorted(set(local_indices)) if _get(a['local_hashes'],i)!=_get(b['local_hashes'],i)]
 sig=[(i,_get(b['signatures'],i)) for i in sorted(set(signature_indices)) if _get(a['signatures'],i)!=_get(b['signatures'],i)]
 header={'schema':SCHEMA,'from_source_sha256':a['header']['source_sha256'],'to_source_sha256':b['header']['source_sha256'],'parent_native_semantic_sha256':a['header']['native_semantic_sha256'],'target_native_semantic_sha256':b['header']['native_semantic_sha256'],'delta_sha256':delta_sha256,'previous_artifact_sha256':previous_artifact_sha256,'edge_updates':len(edge),'local_updates':len(local),'signature_updates':len(sig)}
 hb=zlib.compress(canon(header),6)
 records=b''.join(struct.pack('>I',i)+v for i,v in edge)+b''.join(struct.pack('>H',i)+v for i,v in local)+b''.join(struct.pack('>H',i)+v for i,v in sig)
 prefix=MAGIC+struct.pack('>IIII',len(hb),len(edge),len(local),len(sig))+hb+records
 return prefix+shab(prefix)

def parse_overlay(raw:bytes)->dict[str,Any]:
 if len(raw)<len(MAGIC)+16+32 or raw[:len(MAGIC)]!=MAGIC:raise ValueError('bad overlay magic')
 body,stored=raw[:-32],raw[-32:]
 if shab(body)!=stored:raise ValueError('overlay integrity mismatch')
 off=len(MAGIC);hlen,ne,nl,ns=struct.unpack('>IIII',body[off:off+16]);off+=16
 header=json.loads(zlib.decompress(body[off:off+hlen]));off+=hlen
 if header.get('schema')!=SCHEMA or [header.get('edge_updates'),header.get('local_updates'),header.get('signature_updates')]!=[ne,nl,ns]:raise ValueError('overlay header mismatch')
 edge=[];local=[];sig=[]
 for _ in range(ne):i=struct.unpack('>I',body[off:off+4])[0];off+=4;edge.append((i,body[off:off+32]));off+=32
 for _ in range(nl):i=struct.unpack('>H',body[off:off+2])[0];off+=2;local.append((i,body[off:off+32]));off+=32
 for _ in range(ns):i=struct.unpack('>H',body[off:off+2])[0];off+=2;sig.append((i,body[off:off+32]));off+=32
 if off!=len(body):raise ValueError('overlay trailing bytes')
 return {'header':header,'edge_updates':edge,'local_updates':local,'signature_updates':sig,'artifact_sha256':shahex(raw)}

def wake_chain(base_raw:bytes,overlay_raws:list[bytes])->tuple[dict[str,Any],dict[str,Any]]:
 p=parse_native(base_raw,validate_semantic=True);h=p['header'];prev_art=shahex(base_raw);current_sem=h['native_semantic_sha256'];current_source=h['source_sha256']
 applied=[]
 for raw in overlay_raws:
  ov=parse_overlay(raw);oh=ov['header']
  if oh['previous_artifact_sha256']!=prev_art:raise ValueError('overlay artifact chain mismatch')
  if oh['parent_native_semantic_sha256']!=current_sem:raise ValueError('overlay semantic parent mismatch')
  if oh['from_source_sha256']!=current_source:raise ValueError('overlay source parent mismatch')
  for i,v in ov['edge_updates']:
   if i>=h['edge_count']:raise ValueError('overlay edge index out of range')
   _set(p['edge_hashes'],i,v)
  for i,v in ov['local_updates']:
   if i>=h['component_count']:raise ValueError('overlay local index out of range')
   _set(p['local_hashes'],i,v)
  for i,v in ov['signature_updates']:
   if i>=h['component_count']:raise ValueError('overlay signature index out of range')
   _set(p['signatures'],i,v)
  current_source=oh['to_source_sha256'];current_sem=oh['target_native_semantic_sha256'];h['source_sha256']=current_source;h['legacy_json_state_sha256']=None;h['native_semantic_sha256']=current_sem
  prev_art=ov['artifact_sha256'];applied.append(prev_art)
 blobs=bytes(p['edge_hashes'])+bytes(p['edge_topology_hashes'])+bytes(p['local_hashes'])+bytes(p['signatures'])
 actual=_semantic_hash(h,blobs)
 if actual!=current_sem:raise ValueError('overlay chain final semantic mismatch')
 return p,{'schema':'axm.flowing-compute-overlay-wake-receipt/v0.1','base_artifact_sha256':shahex(base_raw),'overlay_count':len(overlay_raws),'final_overlay_sha256':prev_art if overlay_raws else None,'final_source_sha256':current_source,'final_native_semantic_sha256':current_sem,'final_semantic_verified':True,'overlay_artifact_chain':applied}

def compact_chain(base_raw:bytes,overlay_raws:list[bytes])->bytes:
 p,_=wake_chain(base_raw,overlay_raws);return serialize_native_with_identity(p,source_sha256=p['header']['source_sha256'])[0]
