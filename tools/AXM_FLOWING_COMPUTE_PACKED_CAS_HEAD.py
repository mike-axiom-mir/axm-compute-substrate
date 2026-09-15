from __future__ import annotations
from pathlib import Path
from typing import Any
from AXM_FLOWING_COMPUTE_CAS_HEAD import (_serialize_block,parse_block,_serialize_root,parse_root,PAGE_WIDTH,history_next,initial_header_from_head20,digest,WAKE_SCHEMA)
from AXM_FLOWING_COMPUTE_NATIVE_PACKED_STATE import parse_native
from AXM_FLOWING_COMPUTE_NATIVE_OVERLAY import parse_overlay,shahex
from AXM_FLOWING_COMPUTE_PROVEN_OVERLAY import CHECKPOINT_SCHEMA,validate_hashed
from AXM_FLOWING_COMPUTE_PROOF_MANIFEST import validate_manifest
from AXM_FLOWING_COMPUTE_CAS_PACK import PackedCAS

def _load(store:PackedCAS,ref:dict[str,Any])->dict[str,Any]:
    b=parse_block(store.get(ref['sha256']))
    if b['artifact_sha256']!=ref['sha256'] or len(b['entries'])!=int(ref['entry_count']):raise ValueError('packed CAS block ref mismatch')
    return b

def root_from_overrides(*,header:dict[str,Any],edge:dict[int,bytes],local:dict[int,bytes],signature:dict[int,bytes],store:PackedCAS)->tuple[bytes,dict[str,Any]]:
    refs={};new_payload=0;pack_append=0;new_blocks=0;reused=0
    for cat,data in [('edge',edge),('local',local),('signature',signature)]:
        pages={};w=PAGE_WIDTH[cat]
        for i,v in data.items():pages.setdefault(i//w,{})[i]=v
        for page,entries in pages.items():
            raw=_serialize_block(cat,page,entries);sha,created,written=store.add(raw);refs[(cat,page)]={'sha256':sha,'entry_count':len(entries)}
            if created:new_blocks+=1;new_payload+=len(raw);pack_append+=written
            else:reused+=1
    idxbytes=store.flush_index();root=_serialize_root(header,refs)
    return root,{'new_block_payload_bytes':new_payload,'pack_append_bytes':pack_append,'index_rewrite_bytes':idxbytes,'new_blocks':new_blocks,'reused_blocks':reused,'root_bytes':len(root),'total_persistent_write_bytes':pack_append+idxbytes+len(root),'block_refs':len(refs)}

def update_root(previous_root_raw:bytes,new_overlay_raw:bytes,new_manifest:dict[str,Any],store:PackedCAS)->tuple[bytes,dict[str,Any]]:
    validate_manifest(new_manifest);root=parse_root(previous_root_raw);h=dict(root['header']);expected=int(h['overlay_count'])+1
    if len(new_manifest['entries'])!=expected:raise ValueError('manifest depth mismatch')
    ov=parse_overlay(new_overlay_raw);oh=ov['header'];entry=new_manifest['entries'][-1]
    if ov['artifact_sha256']!=entry['overlay_artifact_sha256']:raise ValueError('overlay not attested')
    prev=h['overlay_chain_tip_sha256'] or h['base_artifact_sha256']
    if oh['previous_artifact_sha256']!=prev or oh['parent_native_semantic_sha256']!=h['final_native_semantic_sha256'] or oh['from_source_sha256']!=h['final_source_sha256']:raise ValueError('overlay does not extend packed CAS root')
    refs=dict(root['refs']);new_payload=0;pack_append=0;new_blocks=0;reused=0;touched=[]
    updates={'edge':ov['edge_updates'],'local':ov['local_updates'],'signature':ov['signature_updates']}
    for cat,pairs in updates.items():
        by={};w=PAGE_WIDTH[cat]
        for i,v in pairs:by.setdefault(i//w,[]).append((i,v))
        for page,changes in by.items():
            ref=refs.get((cat,page));entries=dict(_load(store,ref)['entries']) if ref else {}
            for i,v in changes:entries[i]=v
            raw=_serialize_block(cat,page,entries);sha,created,written=store.add(raw);refs[(cat,page)]={'sha256':sha,'entry_count':len(entries)};touched.append((cat,page))
            if created:new_blocks+=1;new_payload+=len(raw);pack_append+=written
            else:reused+=1
    idxbytes=store.flush_index();h.update({'overlay_count':expected,'overlay_chain_tip_sha256':ov['artifact_sha256'],'history_chain_root_sha256':history_next(h['history_chain_root_sha256'],ov['artifact_sha256']),'proof_manifest_sha256':new_manifest['manifest_sha256'],'final_source_sha256':oh['to_source_sha256'],'final_native_semantic_sha256':oh['target_native_semantic_sha256']})
    out=_serialize_root(h,refs)
    return out,{'new_block_payload_bytes':new_payload,'pack_append_bytes':pack_append,'index_rewrite_bytes':idxbytes,'new_blocks':new_blocks,'reused_blocks':reused,'root_bytes':len(out),'total_persistent_write_bytes':pack_append+idxbytes+len(out),'block_refs':len(refs),'touched_pages':[f'{a}:{b}' for a,b in touched]}

def wake_root(base_raw:bytes,base_proof:dict[str,Any],root_raw:bytes,store:PackedCAS)->tuple[dict[str,Any],dict[str,Any]]:
    validate_hashed(base_proof,CHECKPOINT_SCHEMA,'proof_sha256');root=parse_root(root_raw);h=root['header'];base=parse_native(base_raw,validate_semantic=False);bh=base['header'];base_sha=shahex(base_raw)
    if base_sha!=base_proof['artifact_sha256'] or base_sha!=h['base_artifact_sha256']:raise ValueError('packed root base mismatch')
    if bh['source_sha256']!=base_proof['source_sha256'] or bh['native_semantic_sha256']!=base_proof['native_semantic_sha256']:raise ValueError('packed root base proof mismatch')
    entries={'edge':{},'local':{},'signature':{}}
    for (cat,page),ref in root['refs'].items():entries[cat].update(_load(store,ref)['entries'])
    view={'base':base,'header':dict(bh),'edge_overrides':entries['edge'],'local_overrides':entries['local'],'signature_overrides':entries['signature']};view['header']['source_sha256']=h['final_source_sha256'];view['header']['legacy_json_state_sha256']=None;view['header']['native_semantic_sha256']=h['final_native_semantic_sha256']
    receipt={'schema':WAKE_SCHEMA,'root_artifact_sha256':root['artifact_sha256'],'base_artifact_sha256':base_sha,'overlay_count':h['overlay_count'],'block_refs':len(root['refs']),'history_chain_root_sha256':h['history_chain_root_sha256'],'overlay_chain_tip_sha256':h['overlay_chain_tip_sha256'],'final_source_sha256':h['final_source_sha256'],'final_native_semantic_sha256':h['final_native_semantic_sha256'],'runtime_history_replayed':False,'runtime_recomputed_effective_semantic':False,'semantic_identity_reused_from_proven_root':True,'truth':{'blocks_stored_in_single_append_only_pack':True,'unchanged_blocks_reused_by_hash':True,'full_overlay_history_preserved_separately':True}}
    receipt['receipt_sha256']=digest(receipt);return view,receipt

class ResidentPackedCASHead:
    """Runtime-resident current head. Wake/import is separate from per-generation update cost."""
    def __init__(self, root_raw:bytes, store:PackedCAS):
        root=parse_root(root_raw);self.header=dict(root['header']);self.refs=dict(root['refs']);self.store=store;self.pages={}
        for key,ref in self.refs.items():self.pages[key]=dict(_load(store,ref)['entries'])
        self.root_raw=root_raw
    def apply_overlay(self,new_overlay_raw:bytes,new_manifest:dict[str,Any])->tuple[bytes,dict[str,Any]]:
        validate_manifest(new_manifest);h=self.header;expected=int(h['overlay_count'])+1
        if len(new_manifest['entries'])!=expected:raise ValueError('manifest depth mismatch')
        ov=parse_overlay(new_overlay_raw);oh=ov['header'];entry=new_manifest['entries'][-1]
        if ov['artifact_sha256']!=entry['overlay_artifact_sha256']:raise ValueError('overlay not attested')
        prev=h['overlay_chain_tip_sha256'] or h['base_artifact_sha256']
        if oh['previous_artifact_sha256']!=prev or oh['parent_native_semantic_sha256']!=h['final_native_semantic_sha256'] or oh['from_source_sha256']!=h['final_source_sha256']:raise ValueError('overlay does not extend resident CAS head')
        new_payload=0;pack_append=0;new_blocks=0;reused=0;touched=[]
        updates={'edge':ov['edge_updates'],'local':ov['local_updates'],'signature':ov['signature_updates']}
        for cat,pairs in updates.items():
            by={};w=PAGE_WIDTH[cat]
            for i,v in pairs:by.setdefault(i//w,[]).append((i,v))
            for page,changes in by.items():
                key=(cat,page);entries=self.pages.setdefault(key,{})
                for i,v in changes:entries[i]=v
                raw=_serialize_block(cat,page,entries);sha,created,written=self.store.add(raw);self.refs[key]={'sha256':sha,'entry_count':len(entries)};touched.append(key)
                if created:new_blocks+=1;new_payload+=len(raw);pack_append+=written
                else:reused+=1
        idxbytes=self.store.flush_index();h.update({'overlay_count':expected,'overlay_chain_tip_sha256':ov['artifact_sha256'],'history_chain_root_sha256':history_next(h['history_chain_root_sha256'],ov['artifact_sha256']),'proof_manifest_sha256':new_manifest['manifest_sha256'],'final_source_sha256':oh['to_source_sha256'],'final_native_semantic_sha256':oh['target_native_semantic_sha256']})
        self.root_raw=_serialize_root(h,self.refs)
        return self.root_raw,{'new_block_payload_bytes':new_payload,'pack_append_bytes':pack_append,'index_rewrite_bytes':idxbytes,'new_blocks':new_blocks,'reused_blocks':reused,'root_bytes':len(self.root_raw),'total_persistent_write_bytes':pack_append+idxbytes+len(self.root_raw),'block_refs':len(self.refs),'touched_pages':[f'{a}:{b}' for a,b in touched]}
