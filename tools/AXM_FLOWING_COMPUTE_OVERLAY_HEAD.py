from __future__ import annotations
import hashlib,json,struct,zlib
from typing import Any
from AXM_FLOWING_COMPUTE_NATIVE_PACKED_STATE import parse_native,canon
from AXM_FLOWING_COMPUTE_NATIVE_OVERLAY import parse_overlay,shahex
from AXM_FLOWING_COMPUTE_PROVEN_OVERLAY import CHECKPOINT_SCHEMA,validate_hashed
from AXM_FLOWING_COMPUTE_PROOF_MANIFEST import validate_manifest,wake_proven_manifest

MAGIC=b'AXHD20\x00\x01';SCHEMA='axm.flowing-compute-overlay-head/v0.1';WAKE_SCHEMA='axm.flowing-compute-overlay-head-wake/v0.1';TAG=b'AXM-HISTORY20\x00'
def sh(raw:bytes)->bytes:return hashlib.sha256(raw).digest()
def digest(v:Any)->str:return hashlib.sha256(canon(v)).hexdigest()
def history_start(base_sha:str)->str:return hashlib.sha256(TAG+bytes.fromhex(base_sha)).hexdigest()
def history_next(root:str,overlay_sha:str)->str:return hashlib.sha256(bytes.fromhex(root)+bytes.fromhex(overlay_sha)).hexdigest()

def _serialize(header:dict[str,Any],edge:dict[int,bytes],local:dict[int,bytes],sig:dict[int,bytes])->bytes:
 h=dict(header);h['edge_override_count']=len(edge);h['local_override_count']=len(local);h['signature_override_count']=len(sig)
 hb=zlib.compress(canon(h),6);records=b''.join(struct.pack('>I',i)+v for i,v in sorted(edge.items()))+b''.join(struct.pack('>H',i)+v for i,v in sorted(local.items()))+b''.join(struct.pack('>H',i)+v for i,v in sorted(sig.items()))
 prefix=MAGIC+struct.pack('>IIII',len(hb),len(edge),len(local),len(sig))+hb+records
 return prefix+sh(prefix)

def parse_head(raw:bytes)->dict[str,Any]:
 if len(raw)<len(MAGIC)+16+32 or raw[:len(MAGIC)]!=MAGIC:raise ValueError('bad overlay head magic')
 body,stored=raw[:-32],raw[-32:]
 if sh(body)!=stored:raise ValueError('overlay head integrity mismatch')
 off=len(MAGIC);hlen,ne,nl,ns=struct.unpack('>IIII',body[off:off+16]);off+=16
 h=json.loads(zlib.decompress(body[off:off+hlen]));off+=hlen
 if h.get('schema')!=SCHEMA or [h.get('edge_override_count'),h.get('local_override_count'),h.get('signature_override_count')]!=[ne,nl,ns]:raise ValueError('overlay head header mismatch')
 edge={};local={};sig={}
 for _ in range(ne):i=struct.unpack('>I',body[off:off+4])[0];off+=4;edge[i]=body[off:off+32];off+=32
 for _ in range(nl):i=struct.unpack('>H',body[off:off+2])[0];off+=2;local[i]=body[off:off+32];off+=32
 for _ in range(ns):i=struct.unpack('>H',body[off:off+2])[0];off+=2;sig[i]=body[off:off+32];off+=32
 if off!=len(body):raise ValueError('overlay head trailing bytes')
 return {'header':h,'edge_overrides':edge,'local_overrides':local,'signature_overrides':sig,'artifact_sha256':shahex(raw)}

def manifest_prefix(manifest:dict[str,Any],depth:int)->dict[str,Any]:
 validate_manifest(manifest)
 if depth<0 or depth>len(manifest['entries']):raise ValueError('invalid manifest prefix depth')
 body={k:v for k,v in manifest.items() if k!='manifest_sha256'};body['entries']=list(manifest['entries'][:depth]);body['manifest_sha256']=digest(body);return body

def build_head(base_raw:bytes,overlay_raws:list[bytes],manifest:dict[str,Any])->bytes:
 validate_manifest(manifest)
 if len(overlay_raws)!=len(manifest['entries']):raise ValueError('head build requires exact manifest depth')
 view,receipt=wake_proven_manifest(base_raw,overlay_raws,manifest);base_sha=shahex(base_raw);root=history_start(base_sha);tip=base_sha
 for raw in overlay_raws:
  ov=parse_overlay(raw);tip=ov['artifact_sha256'];root=history_next(root,tip)
 h={'schema':SCHEMA,'base_artifact_sha256':base_sha,'base_source_sha256':view['base']['header']['source_sha256'],'base_native_semantic_sha256':view['base']['header']['native_semantic_sha256'],'overlay_count':len(overlay_raws),'overlay_chain_tip_sha256':tip if overlay_raws else None,'history_chain_root_sha256':root,'proof_manifest_sha256':manifest['manifest_sha256'],'final_source_sha256':receipt['final_source_sha256'],'final_native_semantic_sha256':receipt['final_native_semantic_sha256'],'history_preserved_elsewhere':True,'semantic_identity_carried_from_creation_proof':True}
 return _serialize(h,view['edge_overrides'],view['local_overrides'],view['signature_overrides'])

def update_head(previous_head_raw:bytes,new_overlay_raw:bytes,new_manifest:dict[str,Any])->bytes:
 validate_manifest(new_manifest);head=parse_head(previous_head_raw);h=dict(head['header']);expected_depth=int(h['overlay_count'])+1
 if len(new_manifest['entries'])!=expected_depth:raise ValueError('manifest depth does not match head update')
 ov=parse_overlay(new_overlay_raw);oh=ov['header'];entry=new_manifest['entries'][-1]
 if ov['artifact_sha256']!=entry['overlay_artifact_sha256']:raise ValueError('new overlay not attested by manifest')
 previous_tip=h['overlay_chain_tip_sha256'] or h['base_artifact_sha256']
 if oh['previous_artifact_sha256']!=previous_tip:raise ValueError('overlay does not extend head tip')
 if oh['parent_native_semantic_sha256']!=h['final_native_semantic_sha256'] or oh['from_source_sha256']!=h['final_source_sha256']:raise ValueError('overlay does not extend head semantic/source generation')
 edge=dict(head['edge_overrides']);local=dict(head['local_overrides']);sig=dict(head['signature_overrides'])
 for i,v in ov['edge_updates']:edge[i]=v
 for i,v in ov['local_updates']:local[i]=v
 for i,v in ov['signature_updates']:sig[i]=v
 h.update({'overlay_count':expected_depth,'overlay_chain_tip_sha256':ov['artifact_sha256'],'history_chain_root_sha256':history_next(h['history_chain_root_sha256'],ov['artifact_sha256']),'proof_manifest_sha256':new_manifest['manifest_sha256'],'final_source_sha256':oh['to_source_sha256'],'final_native_semantic_sha256':oh['target_native_semantic_sha256']})
 return _serialize(h,edge,local,sig)

def wake_head(base_raw:bytes,base_proof:dict[str,Any],head_raw:bytes)->tuple[dict[str,Any],dict[str,Any]]:
 validate_hashed(base_proof,CHECKPOINT_SCHEMA,'proof_sha256');head=parse_head(head_raw);h=head['header'];base=parse_native(base_raw,validate_semantic=False);bh=base['header'];base_sha=shahex(base_raw)
 if base_sha!=base_proof['artifact_sha256'] or base_sha!=h['base_artifact_sha256']:raise ValueError('head base artifact mismatch')
 if bh['source_sha256']!=base_proof['source_sha256'] or bh['native_semantic_sha256']!=base_proof['native_semantic_sha256']:raise ValueError('base proof mismatch')
 if h['base_source_sha256']!=bh['source_sha256'] or h['base_native_semantic_sha256']!=bh['native_semantic_sha256']:raise ValueError('head base semantic mismatch')
 view={'base':base,'header':dict(bh),'edge_overrides':head['edge_overrides'],'local_overrides':head['local_overrides'],'signature_overrides':head['signature_overrides']};view['header']['source_sha256']=h['final_source_sha256'];view['header']['legacy_json_state_sha256']=None;view['header']['native_semantic_sha256']=h['final_native_semantic_sha256']
 receipt={'schema':WAKE_SCHEMA,'head_artifact_sha256':head['artifact_sha256'],'base_artifact_sha256':base_sha,'overlay_count':h['overlay_count'],'history_chain_root_sha256':h['history_chain_root_sha256'],'overlay_chain_tip_sha256':h['overlay_chain_tip_sha256'],'final_source_sha256':h['final_source_sha256'],'final_native_semantic_sha256':h['final_native_semantic_sha256'],'runtime_history_replayed':False,'runtime_recomputed_effective_semantic':False,'semantic_identity_reused_from_proven_head':True,'truth':{'head_is_derived_index_not_full_history':True,'full_overlay_history_preserved_separately':True,'fast_wake_does_not_reaudit_omitted_history':True,'full_revalidation_remains_available':True}}
 receipt['receipt_sha256']=digest(receipt);return view,receipt
