from __future__ import annotations
import hashlib
from pathlib import Path
from typing import Any
from AXM_FLOWING_COMPUTE_NATIVE_PACKED_STATE import parse_native,serialize_native_with_identity,canon
from AXM_FLOWING_COMPUTE_NATIVE_PACKED_TRANSITION import _validate_delta,_local_hash,_signature,_get,_set,file_sha
from AXM_FLOWING_COMPUTE_NATIVE_OVERLAY import build_overlay_from_update_sets,parse_overlay,shahex
from AXM_FLOWING_COMPUTE_PROVEN_OVERLAY import OVERLAY_PROOF_SCHEMA,digest as proof_digest
from AXM_FLOWING_COMPUTE_PROOF_MANIFEST import build_manifest
from AXM_FLOWING_COMPUTE_OVERLAY_HEAD import _serialize as serialize_head,history_start,history_next

class ValidatedTransitionHandoff:
    __slots__=('base','target','target_raw','transition_receipt','edge_indices','local_indices','signature_indices','delta','_used')
    def __init__(self,**kw):
        for k,v in kw.items():setattr(self,k,v)
        self._used=False
    def consume(self):
        if self._used:raise ValueError('validated transition handoff already consumed')
        self._used=True;return self

def h(v:Any)->str:return hashlib.sha256(v if isinstance(v,(bytes,bytearray)) else canon(v)).hexdigest()
def _copy_parsed(p):
    out={k:v for k,v in p.items()};out['header']=dict(p['header'])
    for n in ('edge_hashes','edge_topology_hashes','local_hashes','signatures'):out[n]=bytearray(p[n])
    out['edge_index']=dict(p['edge_index']);out['edge_component_indices']=list(p['edge_component_indices']);return out

def transition_handoff(*,base_raw:bytes,delta:dict[str,Any],current_source_path:str|Path,mode:str,rehash_current_source:bool=True)->ValidatedTransitionHandoff:
    if mode not in ('incremental','global'):raise ValueError('mode must be incremental or global')
    _validate_delta(delta);base=parse_native(base_raw,validate_semantic=True);target=_copy_parsed(base);header=target['header']
    if header['source_sha256']!=delta['from_source_sha256']:raise ValueError('delta does not start from base generation')
    if rehash_current_source and file_sha(current_source_path)!=delta['to_source_sha256']:raise ValueError('source generation mismatch')
    changed=set()
    for change in delta['changes']:
        eid=change['edge_id'];i=target['edge_index'].get(eid)
        if i is None:raise ValueError('delta edge not retained')
        if _get(target['edge_hashes'],i).hex()!=change['before_edge_sha256']:raise ValueError('delta before mismatch')
        after=change['after_edge']
        if h(after)!=change['after_edge_sha256']:raise ValueError('delta after mismatch')
        topo=hashlib.sha256(canon([after.get('from'),after.get('to'),after.get('wiring_status')])).digest()
        if topo!=_get(target['edge_topology_hashes'],i):raise ValueError('HOLD topology change')
        _set(target['edge_hashes'],i,bytes.fromhex(change['after_edge_sha256']));changed.add(int(target['edge_component_indices'][i]))
    for c in changed:_set(target['local_hashes'],c,_local_hash(header,target,c))
    affected=set(changed);stack=list(changed)
    while stack:
        c=stack.pop()
        for d in header['successors'][str(c)]:
            d=int(d)
            if d not in affected:affected.add(d);stack.append(d)
    recompute=set(range(header['component_count'])) if mode=='global' else affected
    for c in header['topological_order']:
        c=int(c)
        if c in recompute:_set(target['signatures'],c,_signature(header,target,c))
    out,semantic=serialize_native_with_identity(target,source_sha256=delta['to_source_sha256'])
    target['header']['source_sha256']=delta['to_source_sha256'];target['header']['legacy_json_state_sha256']=None;target['header']['native_semantic_sha256']=semantic
    ec=header['edge_count'];cc=header['component_count']
    exact_edge={i for i in range(ec) if _get(base['edge_hashes'],i)!=_get(target['edge_hashes'],i)}
    exact_local={i for i in range(cc) if _get(base['local_hashes'],i)!=_get(target['local_hashes'],i)}
    exact_sig={i for i in range(cc) if _get(base['signatures'],i)!=_get(target['signatures'],i)}
    receipt={'schema':'axm.flowing-compute-validated-transition-handoff/v0.1','mode':mode,'from_source_sha256':delta['from_source_sha256'],'to_source_sha256':delta['to_source_sha256'],'delta_sha256':delta['delta_sha256'],'changed_components':len(changed),'affected_components':len(affected),'recomputed_components':len(recompute),'result_native_semantic_sha256':semantic,'result_artifact_sha256':shahex(out),'exact_edge_differences':len(exact_edge),'exact_local_differences':len(exact_local),'exact_signature_differences':len(exact_sig),'truth':{'base_parsed_once':True,'target_semantic_computed_over_full_target_state':True,'handoff_one_use':True}}
    receipt['receipt_sha256']=h(receipt)
    return ValidatedTransitionHandoff(base=base,target=target,target_raw=out,transition_receipt=receipt,edge_indices=exact_edge,local_indices=exact_local,signature_indices=exact_sig,delta=delta)

def consume_to_overlay_proof_head(handle:ValidatedTransitionHandoff,*,base_raw:bytes,base_proof:dict[str,Any])->dict[str,Any]:
    x=handle.consume();base_sha=shahex(base_raw);tr=x.transition_receipt;d=x.delta
    overlay=build_overlay_from_update_sets(x.base,x.target,delta_sha256=d['delta_sha256'],previous_artifact_sha256=base_sha,edge_indices=x.edge_indices,local_indices=x.local_indices,signature_indices=x.signature_indices)
    ov=parse_overlay(overlay);oh=ov['header']
    def check(rows,indices,block):
        got={i:v for i,v in rows}
        if set(got)!=set(indices):raise ValueError('overlay exact difference set mismatch')
        for i,v in got.items():
            if v!=_get(block,i):raise ValueError('overlay target block mismatch')
    check(ov['edge_updates'],x.edge_indices,x.target['edge_hashes']);check(ov['local_updates'],x.local_indices,x.target['local_hashes']);check(ov['signature_updates'],x.signature_indices,x.target['signatures'])
    if oh['target_native_semantic_sha256']!=tr['result_native_semantic_sha256'] or oh['to_source_sha256']!=tr['to_source_sha256']:raise ValueError('overlay target identity mismatch')
    proof={'schema':OVERLAY_PROOF_SCHEMA,'producer':'AXM_FLOWING_COMPUTE_VALIDATED_TRANSACTION_HANDOFF/v0.1','overlay_artifact_sha256':ov['artifact_sha256'],'previous_artifact_sha256':oh['previous_artifact_sha256'],'from_checkpoint_artifact_sha256':base_sha,'target_checkpoint_artifact_sha256':tr['result_artifact_sha256'],'from_source_sha256':oh['from_source_sha256'],'to_source_sha256':oh['to_source_sha256'],'parent_native_semantic_sha256':oh['parent_native_semantic_sha256'],'target_native_semantic_sha256':oh['target_native_semantic_sha256'],'delta_sha256':oh['delta_sha256'],'proof_time_effective_semantic_sha256':tr['result_native_semantic_sha256'],'full_equivalence_verified':True,'proof_method':'exact transition-handoff block-difference coverage + full target semantic identity','truth':{'overlay_not_reapplied_for_duplicate_semantic_hash':True,'all_base_target_block_differences_compared':True,'target_semantic_was_computed_over_full_target_state':True}}
    proof['proof_sha256']=proof_digest(proof)
    manifest=build_manifest(base_proof,[proof])
    edge={i:v for i,v in ov['edge_updates']};local={i:v for i,v in ov['local_updates']};sig={i:v for i,v in ov['signature_updates']}
    hh={'schema':'axm.flowing-compute-overlay-head/v0.1','base_artifact_sha256':base_sha,'base_source_sha256':x.base['header']['source_sha256'],'base_native_semantic_sha256':x.base['header']['native_semantic_sha256'],'overlay_count':1,'overlay_chain_tip_sha256':ov['artifact_sha256'],'history_chain_root_sha256':history_next(history_start(base_sha),ov['artifact_sha256']),'proof_manifest_sha256':manifest['manifest_sha256'],'final_source_sha256':oh['to_source_sha256'],'final_native_semantic_sha256':oh['target_native_semantic_sha256'],'history_preserved_elsewhere':True,'semantic_identity_carried_from_creation_proof':True}
    head=serialize_head(hh,edge,local,sig)
    return {'target_raw':x.target_raw,'transition_receipt':tr,'overlay':overlay,'overlay_proof':proof,'manifest':manifest,'head':head}
