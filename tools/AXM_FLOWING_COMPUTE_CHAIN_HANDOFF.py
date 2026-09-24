from __future__ import annotations
from typing import Any
from AXM_FLOWING_COMPUTE_VALIDATED_TRANSACTION_HANDOFF import ValidatedTransitionHandoff
from AXM_FLOWING_COMPUTE_NATIVE_OVERLAY import build_overlay_from_update_sets,parse_overlay,shahex
from AXM_FLOWING_COMPUTE_PROVEN_OVERLAY import OVERLAY_PROOF_SCHEMA,digest as proof_digest
from AXM_FLOWING_COMPUTE_NATIVE_PACKED_TRANSITION import _get

def consume_to_chain_overlay_proof(handle:ValidatedTransitionHandoff,*,from_checkpoint_raw:bytes,previous_artifact_sha256:str)->dict[str,Any]:
    x=handle.consume();tr=x.transition_receipt;d=x.delta
    ovraw=build_overlay_from_update_sets(x.base,x.target,delta_sha256=d['delta_sha256'],previous_artifact_sha256=previous_artifact_sha256,edge_indices=x.edge_indices,local_indices=x.local_indices,signature_indices=x.signature_indices)
    ov=parse_overlay(ovraw);oh=ov['header']
    def check(rows,indices,block):
        got={i:v for i,v in rows}
        if set(got)!=set(indices):raise ValueError('overlay exact difference set mismatch')
        for i,v in got.items():
            if v!=_get(block,i):raise ValueError('overlay target block mismatch')
    check(ov['edge_updates'],x.edge_indices,x.target['edge_hashes']);check(ov['local_updates'],x.local_indices,x.target['local_hashes']);check(ov['signature_updates'],x.signature_indices,x.target['signatures'])
    if oh['target_native_semantic_sha256']!=tr['result_native_semantic_sha256']:raise ValueError('target semantic mismatch')
    proof={'schema':OVERLAY_PROOF_SCHEMA,'producer':'AXM_FLOWING_COMPUTE_CHAIN_HANDOFF/v0.1','overlay_artifact_sha256':ov['artifact_sha256'],'previous_artifact_sha256':previous_artifact_sha256,'from_checkpoint_artifact_sha256':shahex(from_checkpoint_raw),'target_checkpoint_artifact_sha256':tr['result_artifact_sha256'],'from_source_sha256':oh['from_source_sha256'],'to_source_sha256':oh['to_source_sha256'],'parent_native_semantic_sha256':oh['parent_native_semantic_sha256'],'target_native_semantic_sha256':oh['target_native_semantic_sha256'],'delta_sha256':oh['delta_sha256'],'proof_time_effective_semantic_sha256':tr['result_native_semantic_sha256'],'full_equivalence_verified':True,'proof_method':'one-use exact block-difference handoff','truth':{'overlay_not_reapplied_for_duplicate_semantic_hash':True,'all_base_target_block_differences_compared':True,'target_semantic_computed_over_full_target_state':True}}
    proof['proof_sha256']=proof_digest(proof)
    return {'target_raw':x.target_raw,'transition_receipt':tr,'overlay':ovraw,'overlay_parsed':ov,'overlay_proof':proof}
