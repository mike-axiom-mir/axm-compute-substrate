from __future__ import annotations
import hashlib,json
from typing import Any
from AXM_FLOWING_COMPUTE_NATIVE_PACKED_STATE import parse_native,_semantic_hash,canon
from AXM_FLOWING_COMPUTE_NATIVE_OVERLAY import parse_overlay,shahex,_get,_set

CHECKPOINT_SCHEMA='axm.flowing-compute-validated-checkpoint-proof/v0.1'
OVERLAY_PROOF_SCHEMA='axm.flowing-compute-overlay-generation-proof/v0.1'
WAKE_SCHEMA='axm.flowing-compute-proven-overlay-wake/v0.1'

def digest(v:Any)->str:return hashlib.sha256(canon(v)).hexdigest()
def _with_hash(body:dict[str,Any],field:str)->dict[str,Any]:
 out=dict(body);out[field]=digest(body);return out
def validate_hashed(value:dict[str,Any],schema:str,field:str)->None:
 if value.get('schema')!=schema:raise ValueError('unsupported proof schema')
 stored=value.get(field);body=dict(value);body.pop(field,None)
 if not stored or digest(body)!=stored:raise ValueError('proof integrity mismatch')

def prove_checkpoint(raw:bytes, *, producer:str='AXM_FLOWING_COMPUTE_PROVEN_OVERLAY/v0.1')->dict[str,Any]:
 parsed=parse_native(raw,validate_semantic=True);h=parsed['header']
 return _with_hash({'schema':CHECKPOINT_SCHEMA,'producer':producer,'artifact_sha256':shahex(raw),'source_sha256':h['source_sha256'],'native_semantic_sha256':h['native_semantic_sha256'],'semantic_recomputed_at_proof_creation':True},'proof_sha256')

def _apply_overlay_to_checkpoint(from_parsed:dict[str,Any],ov:dict[str,Any])->str:
 p={k:v for k,v in from_parsed.items()};p['header']=dict(from_parsed['header'])
 for name in ('edge_hashes','edge_topology_hashes','local_hashes','signatures'):p[name]=bytearray(from_parsed[name])
 h=p['header'];oh=ov['header']
 for i,v in ov['edge_updates']:_set(p['edge_hashes'],i,v)
 for i,v in ov['local_updates']:_set(p['local_hashes'],i,v)
 for i,v in ov['signature_updates']:_set(p['signatures'],i,v)
 h['source_sha256']=oh['to_source_sha256'];h['legacy_json_state_sha256']=None;h['native_semantic_sha256']=oh['target_native_semantic_sha256']
 blobs=bytes(p['edge_hashes'])+bytes(p['edge_topology_hashes'])+bytes(p['local_hashes'])+bytes(p['signatures'])
 return _semantic_hash(h,blobs)

def prove_overlay(*, from_checkpoint_raw:bytes, overlay_raw:bytes, target_checkpoint_raw:bytes, producer:str='AXM_FLOWING_COMPUTE_PROVEN_OVERLAY/v0.1')->dict[str,Any]:
 a=parse_native(from_checkpoint_raw,validate_semantic=True);b=parse_native(target_checkpoint_raw,validate_semantic=True);ov=parse_overlay(overlay_raw);oh=ov['header'];ah=a['header'];bh=b['header']
 if oh['parent_native_semantic_sha256']!=ah['native_semantic_sha256'] or oh['from_source_sha256']!=ah['source_sha256']:raise ValueError('overlay parent does not match proof checkpoint')
 if oh['target_native_semantic_sha256']!=bh['native_semantic_sha256'] or oh['to_source_sha256']!=bh['source_sha256']:raise ValueError('overlay target does not match target checkpoint')
 actual=_apply_overlay_to_checkpoint(a,ov)
 if actual!=bh['native_semantic_sha256']:raise ValueError('overlay proof-time semantic equivalence failed')
 body={'schema':OVERLAY_PROOF_SCHEMA,'producer':producer,'overlay_artifact_sha256':ov['artifact_sha256'],'previous_artifact_sha256':oh['previous_artifact_sha256'],'from_checkpoint_artifact_sha256':shahex(from_checkpoint_raw),'target_checkpoint_artifact_sha256':shahex(target_checkpoint_raw),'from_source_sha256':oh['from_source_sha256'],'to_source_sha256':oh['to_source_sha256'],'parent_native_semantic_sha256':oh['parent_native_semantic_sha256'],'target_native_semantic_sha256':oh['target_native_semantic_sha256'],'delta_sha256':oh['delta_sha256'],'proof_time_effective_semantic_sha256':actual,'full_equivalence_verified':True}
 return _with_hash(body,'proof_sha256')

class ProvenOverlayView:
 __slots__=('base','header','edge_overrides','local_overrides','signature_overrides','overlay_count','final_overlay_sha256')
 def __init__(self,base,header,edge,local,sig,count,final):self.base=base;self.header=header;self.edge_overrides=edge;self.local_overrides=local;self.signature_overrides=sig;self.overlay_count=count;self.final_overlay_sha256=final
 def edge_hash(self,i:int)->bytes:return self.edge_overrides.get(i,_get(self.base['edge_hashes'],i))
 def topology_hash(self,i:int)->bytes:return _get(self.base['edge_topology_hashes'],i)
 def local_hash(self,i:int)->bytes:return self.local_overrides.get(i,_get(self.base['local_hashes'],i))
 def signature(self,i:int)->bytes:return self.signature_overrides.get(i,_get(self.base['signatures'],i))

def wake_proven(base_raw:bytes,base_proof:dict[str,Any],overlay_raws:list[bytes],proofs:list[dict[str,Any]])->tuple[ProvenOverlayView,dict[str,Any]]:
 if len(overlay_raws)!=len(proofs):raise ValueError('overlay/proof count mismatch')
 validate_hashed(base_proof,CHECKPOINT_SCHEMA,'proof_sha256')
 base=parse_native(base_raw,validate_semantic=False);h=dict(base['header'])
 if shahex(base_raw)!=base_proof['artifact_sha256'] or h['source_sha256']!=base_proof['source_sha256'] or h['native_semantic_sha256']!=base_proof['native_semantic_sha256']:raise ValueError('base checkpoint proof mismatch')
 prev_art=base_proof['artifact_sha256'];current_sem=base_proof['native_semantic_sha256'];current_source=base_proof['source_sha256'];edge={};local={};sig={};chain=[]
 for raw,proof in zip(overlay_raws,proofs):
  validate_hashed(proof,OVERLAY_PROOF_SCHEMA,'proof_sha256');ov=parse_overlay(raw);oh=ov['header']
  if proof.get('full_equivalence_verified') is not True:raise ValueError('overlay proof lacks full equivalence')
  if ov['artifact_sha256']!=proof['overlay_artifact_sha256']:raise ValueError('overlay artifact proof mismatch')
  if oh['previous_artifact_sha256']!=prev_art or proof['previous_artifact_sha256']!=prev_art:raise ValueError('overlay artifact chain mismatch')
  if oh['parent_native_semantic_sha256']!=current_sem or proof['parent_native_semantic_sha256']!=current_sem:raise ValueError('overlay semantic parent mismatch')
  if oh['from_source_sha256']!=current_source or proof['from_source_sha256']!=current_source:raise ValueError('overlay source parent mismatch')
  for i,v in ov['edge_updates']:
   if i>=h['edge_count']:raise ValueError('overlay edge index out of range')
   edge[i]=v
  for i,v in ov['local_updates']:
   if i>=h['component_count']:raise ValueError('overlay local index out of range')
   local[i]=v
  for i,v in ov['signature_updates']:
   if i>=h['component_count']:raise ValueError('overlay signature index out of range')
   sig[i]=v
  current_source=oh['to_source_sha256'];current_sem=oh['target_native_semantic_sha256'];prev_art=ov['artifact_sha256'];chain.append(prev_art)
  if proof['to_source_sha256']!=current_source or proof['target_native_semantic_sha256']!=current_sem or proof['proof_time_effective_semantic_sha256']!=current_sem:raise ValueError('overlay target proof mismatch')
 h['source_sha256']=current_source;h['legacy_json_state_sha256']=None;h['native_semantic_sha256']=current_sem
 view=ProvenOverlayView(base,h,edge,local,sig,len(overlay_raws),prev_art if overlay_raws else None)
 receipt={'schema':WAKE_SCHEMA,'base_artifact_sha256':base_proof['artifact_sha256'],'overlay_count':len(overlay_raws),'final_overlay_sha256':prev_art if overlay_raws else None,'final_source_sha256':current_source,'final_native_semantic_sha256':current_sem,'semantic_identity_reused_from_creation_proof':True,'runtime_recomputed_effective_semantic':False,'unique_edge_overrides':len(edge),'unique_local_overrides':len(local),'unique_signature_overrides':len(sig),'overlay_artifact_chain':chain,'truth':{'integrity_and_chain_rechecked_at_wake':True,'semantic_equivalence_was_computed_at_proof_creation':True,'proof_is_content_integrity_not_external_authentication':True,'full_revalidation_remains_available':True}}
 receipt['receipt_sha256']=digest(receipt);return view,receipt
