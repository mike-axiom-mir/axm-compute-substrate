from __future__ import annotations
import hashlib,json,struct,zlib
from pathlib import Path
from typing import Any
from AXM_FLOWING_COMPUTE_NATIVE_PACKED_STATE import parse_native,canon
from AXM_FLOWING_COMPUTE_NATIVE_OVERLAY import parse_overlay,shahex
from AXM_FLOWING_COMPUTE_PROVEN_OVERLAY import CHECKPOINT_SCHEMA,validate_hashed
from AXM_FLOWING_COMPUTE_PROOF_MANIFEST import validate_manifest

BLOCK_MAGIC=b'AXHB21\x00\x01';ROOT_MAGIC=b'AXHR21\x00\x01'
BLOCK_SCHEMA='axm.flowing-compute-cas-head-block/v0.1';ROOT_SCHEMA='axm.flowing-compute-cas-head-root/v0.1'
WAKE_SCHEMA='axm.flowing-compute-cas-head-wake/v0.1';TAG=b'AXM-HISTORY20\x00'
CATEGORY_CODE={'edge':1,'local':2,'signature':3};CODE_CATEGORY={v:k for k,v in CATEGORY_CODE.items()}
PAGE_WIDTH={'edge':512,'local':64,'signature':16}

def sh(raw:bytes)->bytes:return hashlib.sha256(raw).digest()
def digest(v:Any)->str:return hashlib.sha256(canon(v)).hexdigest()
def history_start(base_sha:str)->str:return hashlib.sha256(TAG+bytes.fromhex(base_sha)).hexdigest()
def history_next(root:str,overlay_sha:str)->str:return hashlib.sha256(bytes.fromhex(root)+bytes.fromhex(overlay_sha)).hexdigest()

def _serialize_block(category:str,page_id:int,entries:dict[int,bytes])->bytes:
    if category not in CATEGORY_CODE:raise ValueError('bad block category')
    width=PAGE_WIDTH[category]; lo=page_id*width; hi=lo+width
    for i,v in entries.items():
        if not (lo<=i<hi) or len(v)!=32:raise ValueError('block entry out of page/value contract')
    h={'schema':BLOCK_SCHEMA,'category':category,'page_id':page_id,'page_width':width,'entry_count':len(entries)}
    hb=zlib.compress(canon(h),6)
    records=b''.join(struct.pack('>I',i)+v for i,v in sorted(entries.items()))
    prefix=BLOCK_MAGIC+struct.pack('>II',len(hb),len(entries))+hb+records
    return prefix+sh(prefix)

def parse_block(raw:bytes)->dict[str,Any]:
    if len(raw)<len(BLOCK_MAGIC)+8+32 or raw[:len(BLOCK_MAGIC)]!=BLOCK_MAGIC:raise ValueError('bad cas block magic')
    body,stored=raw[:-32],raw[-32:]
    if sh(body)!=stored:raise ValueError('cas block integrity mismatch')
    off=len(BLOCK_MAGIC);hlen,n=struct.unpack('>II',body[off:off+8]);off+=8
    h=json.loads(zlib.decompress(body[off:off+hlen]));off+=hlen
    if h.get('schema')!=BLOCK_SCHEMA or h.get('entry_count')!=n:raise ValueError('cas block header mismatch')
    cat=h.get('category');page=int(h.get('page_id'));width=PAGE_WIDTH.get(cat)
    if width is None or int(h.get('page_width'))!=width:raise ValueError('cas block page contract mismatch')
    entries={}
    for _ in range(n):
        i=struct.unpack('>I',body[off:off+4])[0];off+=4;v=body[off:off+32];off+=32
        if not (page*width<=i<(page+1)*width):raise ValueError('cas block index outside page')
        entries[i]=v
    if off!=len(body):raise ValueError('cas block trailing bytes')
    return {'header':h,'entries':entries,'artifact_sha256':shahex(raw)}

def _serialize_root(header:dict[str,Any],refs:dict[tuple[str,int],dict[str,Any]])->bytes:
    h=dict(header);h['block_ref_count']=len(refs);h['page_widths']=PAGE_WIDTH
    hb=zlib.compress(canon(h),6)
    records=[]
    for (cat,page),ref in sorted(refs.items(),key=lambda x:(CATEGORY_CODE[x[0][0]],x[0][1])):
        records.append(struct.pack('>BIH',CATEGORY_CODE[cat],page,int(ref['entry_count']))+bytes.fromhex(ref['sha256']))
    prefix=ROOT_MAGIC+struct.pack('>II',len(hb),len(refs))+hb+b''.join(records)
    return prefix+sh(prefix)

def parse_root(raw:bytes)->dict[str,Any]:
    if len(raw)<len(ROOT_MAGIC)+8+32 or raw[:len(ROOT_MAGIC)]!=ROOT_MAGIC:raise ValueError('bad cas root magic')
    body,stored=raw[:-32],raw[-32:]
    if sh(body)!=stored:raise ValueError('cas root integrity mismatch')
    off=len(ROOT_MAGIC);hlen,n=struct.unpack('>II',body[off:off+8]);off+=8
    h=json.loads(zlib.decompress(body[off:off+hlen]));off+=hlen
    if h.get('schema')!=ROOT_SCHEMA or h.get('block_ref_count')!=n or h.get('page_widths')!=PAGE_WIDTH:raise ValueError('cas root header mismatch')
    refs={}
    for _ in range(n):
        code,page,count=struct.unpack('>BIH',body[off:off+7]);off+=7;sha=body[off:off+32].hex();off+=32
        cat=CODE_CATEGORY.get(code)
        if cat is None:raise ValueError('unknown cas block category')
        refs[(cat,page)]={'sha256':sha,'entry_count':count}
    if off!=len(body):raise ValueError('cas root trailing bytes')
    return {'header':h,'refs':refs,'artifact_sha256':shahex(raw)}

def _cas_path(store:Path,sha:str)->Path:return Path(store)/f'{sha}.axhb'
def _store_block(store:Path,raw:bytes)->tuple[str,bool]:
    store=Path(store);store.mkdir(parents=True,exist_ok=True);sha=shahex(raw);p=_cas_path(store,sha)
    if p.exists():
        if p.read_bytes()!=raw:raise ValueError('content-address collision or store corruption')
        return sha,False
    p.write_bytes(raw);return sha,True

def _load_block(store:Path,ref:dict[str,Any])->dict[str,Any]:
    raw=_cas_path(Path(store),ref['sha256']).read_bytes();b=parse_block(raw)
    if b['artifact_sha256']!=ref['sha256'] or len(b['entries'])!=int(ref['entry_count']):raise ValueError('cas block ref mismatch')
    return b

def _entries_from_root(root:dict[str,Any],store:Path)->dict[str,dict[int,bytes]]:
    out={'edge':{},'local':{},'signature':{}}
    for (cat,page),ref in root['refs'].items():out[cat].update(_load_block(store,ref)['entries'])
    return out

def root_from_overrides(*,header:dict[str,Any],edge:dict[int,bytes],local:dict[int,bytes],signature:dict[int,bytes],store:Path)->tuple[bytes,dict[str,Any]]:
    refs={};new_bytes=0;new_blocks=0;reused_blocks=0
    for cat,data in [('edge',edge),('local',local),('signature',signature)]:
        pages={}
        w=PAGE_WIDTH[cat]
        for i,v in data.items():pages.setdefault(i//w,{})[i]=v
        for page,entries in pages.items():
            raw=_serialize_block(cat,page,entries);sha,created=_store_block(store,raw)
            refs[(cat,page)]={'sha256':sha,'entry_count':len(entries)}
            if created:new_blocks+=1;new_bytes+=len(raw)
            else:reused_blocks+=1
    root_raw=_serialize_root(header,refs)
    return root_raw,{'new_block_bytes':new_bytes,'new_blocks':new_blocks,'reused_blocks':reused_blocks,'root_bytes':len(root_raw),'total_new_bytes':new_bytes+len(root_raw),'block_refs':len(refs)}

def update_root(previous_root_raw:bytes,new_overlay_raw:bytes,new_manifest:dict[str,Any],store:Path)->tuple[bytes,dict[str,Any]]:
    validate_manifest(new_manifest);root=parse_root(previous_root_raw);h=dict(root['header']);expected=int(h['overlay_count'])+1
    if len(new_manifest['entries'])!=expected:raise ValueError('manifest depth does not match cas head update')
    ov=parse_overlay(new_overlay_raw);oh=ov['header'];entry=new_manifest['entries'][-1]
    if ov['artifact_sha256']!=entry['overlay_artifact_sha256']:raise ValueError('overlay not attested by manifest')
    prev_tip=h['overlay_chain_tip_sha256'] or h['base_artifact_sha256']
    if oh['previous_artifact_sha256']!=prev_tip:raise ValueError('overlay does not extend cas root tip')
    if oh['parent_native_semantic_sha256']!=h['final_native_semantic_sha256'] or oh['from_source_sha256']!=h['final_source_sha256']:raise ValueError('overlay does not extend cas root generation')
    refs=dict(root['refs']);new_bytes=0;new_blocks=0;reused_blocks=0;touched=[]
    updates={'edge':ov['edge_updates'],'local':ov['local_updates'],'signature':ov['signature_updates']}
    for cat,pairs in updates.items():
        by_page={};w=PAGE_WIDTH[cat]
        for i,v in pairs:by_page.setdefault(i//w,[]).append((i,v))
        for page,changes in by_page.items():
            ref=refs.get((cat,page));entries=_load_block(store,ref)['entries'] if ref else {}
            entries=dict(entries)
            for i,v in changes:entries[i]=v
            raw=_serialize_block(cat,page,entries);sha,created=_store_block(store,raw)
            refs[(cat,page)]={'sha256':sha,'entry_count':len(entries)};touched.append((cat,page))
            if created:new_blocks+=1;new_bytes+=len(raw)
            else:reused_blocks+=1
    h.update({'overlay_count':expected,'overlay_chain_tip_sha256':ov['artifact_sha256'],'history_chain_root_sha256':history_next(h['history_chain_root_sha256'],ov['artifact_sha256']),'proof_manifest_sha256':new_manifest['manifest_sha256'],'final_source_sha256':oh['to_source_sha256'],'final_native_semantic_sha256':oh['target_native_semantic_sha256']})
    out=_serialize_root(h,refs)
    return out,{'new_block_bytes':new_bytes,'new_blocks':new_blocks,'reused_blocks':reused_blocks,'root_bytes':len(out),'total_new_bytes':new_bytes+len(out),'block_refs':len(refs),'touched_pages':[f'{a}:{b}' for a,b in touched]}

def wake_root(base_raw:bytes,base_proof:dict[str,Any],root_raw:bytes,store:Path)->tuple[dict[str,Any],dict[str,Any]]:
    validate_hashed(base_proof,CHECKPOINT_SCHEMA,'proof_sha256');root=parse_root(root_raw);h=root['header'];base=parse_native(base_raw,validate_semantic=False);bh=base['header'];base_sha=shahex(base_raw)
    if base_sha!=base_proof['artifact_sha256'] or base_sha!=h['base_artifact_sha256']:raise ValueError('cas root base artifact mismatch')
    if bh['source_sha256']!=base_proof['source_sha256'] or bh['native_semantic_sha256']!=base_proof['native_semantic_sha256']:raise ValueError('cas root base proof mismatch')
    entries=_entries_from_root(root,Path(store))
    view={'base':base,'header':dict(bh),'edge_overrides':entries['edge'],'local_overrides':entries['local'],'signature_overrides':entries['signature']}
    view['header']['source_sha256']=h['final_source_sha256'];view['header']['legacy_json_state_sha256']=None;view['header']['native_semantic_sha256']=h['final_native_semantic_sha256']
    receipt={'schema':WAKE_SCHEMA,'root_artifact_sha256':root['artifact_sha256'],'base_artifact_sha256':base_sha,'overlay_count':h['overlay_count'],'block_refs':len(root['refs']),'history_chain_root_sha256':h['history_chain_root_sha256'],'overlay_chain_tip_sha256':h['overlay_chain_tip_sha256'],'final_source_sha256':h['final_source_sha256'],'final_native_semantic_sha256':h['final_native_semantic_sha256'],'runtime_history_replayed':False,'runtime_recomputed_effective_semantic':False,'semantic_identity_reused_from_proven_root':True,'truth':{'cas_blocks_content_addressed':True,'unchanged_blocks_reused_by_hash':True,'full_overlay_history_preserved_separately':True,'full_revalidation_remains_available':True}}
    receipt['receipt_sha256']=digest(receipt);return view,receipt

def initial_header_from_head20(head20:dict[str,Any])->dict[str,Any]:
    h=head20['header']
    return {'schema':ROOT_SCHEMA,'base_artifact_sha256':h['base_artifact_sha256'],'base_source_sha256':h['base_source_sha256'],'base_native_semantic_sha256':h['base_native_semantic_sha256'],'overlay_count':h['overlay_count'],'overlay_chain_tip_sha256':h['overlay_chain_tip_sha256'],'history_chain_root_sha256':h['history_chain_root_sha256'],'proof_manifest_sha256':h['proof_manifest_sha256'],'final_source_sha256':h['final_source_sha256'],'final_native_semantic_sha256':h['final_native_semantic_sha256'],'history_preserved_elsewhere':True,'semantic_identity_carried_from_creation_proof':True,'current_head_blocks_content_addressed':True}
