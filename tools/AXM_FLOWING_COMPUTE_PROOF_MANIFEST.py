from __future__ import annotations
import hashlib,json
from typing import Any
from AXM_FLOWING_COMPUTE_PROVEN_OVERLAY import CHECKPOINT_SCHEMA,OVERLAY_PROOF_SCHEMA,validate_hashed
from AXM_FLOWING_COMPUTE_NATIVE_OVERLAY import parse_overlay,shahex
from AXM_FLOWING_COMPUTE_NATIVE_PACKED_STATE import parse_native,canon

SCHEMA='axm.flowing-compute-overlay-proof-manifest/v0.1'
WAKE_SCHEMA='axm.flowing-compute-manifest-proven-overlay-wake/v0.1'
def digest(v:Any)->str:return hashlib.sha256(canon(v)).hexdigest()

def build_manifest(base_proof:dict[str,Any],proofs:list[dict[str,Any]])->dict[str,Any]:
 validate_hashed(base_proof,CHECKPOINT_SCHEMA,'proof_sha256');entries=[]
 for p in proofs:
  validate_hashed(p,OVERLAY_PROOF_SCHEMA,'proof_sha256')
  if p.get('full_equivalence_verified') is not True:raise ValueError('unverified overlay proof')
  entries.append({'overlay_artifact_sha256':p['overlay_artifact_sha256'],'target_checkpoint_artifact_sha256':p['target_checkpoint_artifact_sha256'],'proof_sha256':p['proof_sha256']})
 body={'schema':SCHEMA,'base':{'artifact_sha256':base_proof['artifact_sha256'],'source_sha256':base_proof['source_sha256'],'native_semantic_sha256':base_proof['native_semantic_sha256'],'proof_sha256':base_proof['proof_sha256']},'entries':entries,'verification_semantics':'each entry references a previously full-equivalence-verified overlay proof; overlay header retains parent/source/target/delta linkage','truth':{'manifest_compacts_verified_evidence':True,'manifest_does_not_create_new_semantic_proof':True,'external_authentication_not_provided':True}}
 body['manifest_sha256']=digest(body);return body

def validate_manifest(m:dict[str,Any])->None:
 if m.get('schema')!=SCHEMA:raise ValueError('unsupported proof manifest schema')
 stored=m.get('manifest_sha256');body=dict(m);body.pop('manifest_sha256',None)
 if digest(body)!=stored:raise ValueError('proof manifest integrity mismatch')

def wake_proven_manifest(base_raw:bytes,overlay_raws:list[bytes],manifest:dict[str,Any]):
 validate_manifest(manifest)
 if len(overlay_raws)>len(manifest.get('entries',[])):raise ValueError('proof manifest lacks overlay entries')
 base=parse_native(base_raw,validate_semantic=False);h=dict(base['header']);mb=manifest['base']
 if shahex(base_raw)!=mb['artifact_sha256'] or h['source_sha256']!=mb['source_sha256'] or h['native_semantic_sha256']!=mb['native_semantic_sha256']:raise ValueError('base manifest mismatch')
 prev_art=mb['artifact_sha256'];current_sem=mb['native_semantic_sha256'];current_source=mb['source_sha256'];edge={};local={};sig={};chain=[]
 for idx,raw in enumerate(overlay_raws):
  ov=parse_overlay(raw);oh=ov['header'];entry=manifest['entries'][idx]
  if ov['artifact_sha256']!=entry['overlay_artifact_sha256']:raise ValueError('overlay not attested by manifest')
  if oh['previous_artifact_sha256']!=prev_art:raise ValueError('overlay artifact chain mismatch')
  if oh['parent_native_semantic_sha256']!=current_sem:raise ValueError('overlay semantic parent mismatch')
  if oh['from_source_sha256']!=current_source:raise ValueError('overlay source parent mismatch')
  for i,v in ov['edge_updates']:
   if i>=h['edge_count']:raise ValueError('edge index out of range')
   edge[i]=v
  for i,v in ov['local_updates']:
   if i>=h['component_count']:raise ValueError('local index out of range')
   local[i]=v
  for i,v in ov['signature_updates']:
   if i>=h['component_count']:raise ValueError('signature index out of range')
   sig[i]=v
  current_source=oh['to_source_sha256'];current_sem=oh['target_native_semantic_sha256'];prev_art=ov['artifact_sha256'];chain.append(prev_art)
 h['source_sha256']=current_source;h['legacy_json_state_sha256']=None;h['native_semantic_sha256']=current_sem
 receipt={'schema':WAKE_SCHEMA,'proof_manifest_sha256':manifest['manifest_sha256'],'overlay_count':len(overlay_raws),'final_overlay_sha256':prev_art if overlay_raws else None,'final_source_sha256':current_source,'final_native_semantic_sha256':current_sem,'runtime_recomputed_effective_semantic':False,'semantic_identity_reused_from_creation_evidence':True,'unique_edge_overrides':len(edge),'unique_local_overrides':len(local),'unique_signature_overrides':len(sig),'overlay_artifact_chain':chain}
 receipt['receipt_sha256']=digest(receipt)
 return {'base':base,'header':h,'edge_overrides':edge,'local_overrides':local,'signature_overrides':sig},receipt
