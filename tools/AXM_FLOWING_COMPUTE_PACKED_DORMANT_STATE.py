from __future__ import annotations
import hashlib,json,struct,zlib
from pathlib import Path
from typing import Any
MAGIC=b'AXDS14\x00\x01'
SCHEMA='axm.flowing-compute-packed-dormant-state/v0.1'
def canon(v:Any)->bytes: return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def sha(raw:bytes)->bytes: return hashlib.sha256(raw).digest()
def pack_state(state:dict[str,Any])->bytes:
    edge_ids=sorted(state['edge_hashes']); comps=sorted(int(k) for k in state['local_hashes']); edge_index={eid:i for i,eid in enumerate(edge_ids)}
    header={'schema':SCHEMA,'source_sha256':state['source_sha256'],'semantic_state_sha256':state['state_sha256'],'edge_ids':edge_ids,'component_members':state['component_members'],'component_edge_indices':{str(k):[edge_index[eid] for eid in state['component_edges'][str(k)]] for k in comps},'predecessors':state['predecessors'],'successors':state['successors'],'topological_order':state['topological_order'],'counts':state['counts'],'edge_count':len(edge_ids),'component_count':len(comps)}
    hb=zlib.compress(canon(header),6)
    blobs=b''.join(bytes.fromhex(state['edge_hashes'][eid]) for eid in edge_ids)+b''.join(bytes.fromhex(state['edge_topology_hashes'][eid]) for eid in edge_ids)+b''.join(bytes.fromhex(state['local_hashes'][str(c)]) for c in comps)+b''.join(bytes.fromhex(state['signatures'][str(c)]) for c in comps)
    prefix=MAGIC+struct.pack('>III',len(hb),len(edge_ids),len(comps))+hb+blobs
    return prefix+sha(prefix)
def unpack_state(raw:bytes, *, verify_semantic_hash:bool=True)->dict[str,Any]:
    if len(raw)<len(MAGIC)+12+32 or raw[:len(MAGIC)]!=MAGIC: raise ValueError('bad packed dormant magic')
    body,stored=raw[:-32],raw[-32:]
    if sha(body)!=stored: raise ValueError('packed dormant container integrity mismatch')
    off=len(MAGIC); hlen,edge_count,comp_count=struct.unpack('>III',body[off:off+12]); off+=12; header=json.loads(zlib.decompress(body[off:off+hlen])); off+=hlen
    if header.get('schema')!=SCHEMA or header.get('edge_count')!=edge_count or header.get('component_count')!=comp_count: raise ValueError('packed dormant header mismatch')
    need=(edge_count*32*2)+(comp_count*32*2)
    if len(body)-off!=need: raise ValueError('packed dormant blob length mismatch')
    def take(n):
        nonlocal off; out=body[off:off+n]; off+=n; return out
    edge_ids=header['edge_ids']; edge_hashes={eid:take(32).hex() for eid in edge_ids}; topology={eid:take(32).hex() for eid in edge_ids}; local={str(c):take(32).hex() for c in range(comp_count)}; signatures={str(c):take(32).hex() for c in range(comp_count)}; component_edges={str(c):[edge_ids[i] for i in header['component_edge_indices'][str(c)]] for c in range(comp_count)}
    state={'schema':'axm.execution-graph.dormant-signature-state/v0.1','source_sha256':header['source_sha256'],'component_members':header['component_members'],'component_edges':component_edges,'edge_hashes':edge_hashes,'edge_topology_hashes':topology,'local_hashes':local,'signatures':signatures,'predecessors':header['predecessors'],'successors':header['successors'],'topological_order':header['topological_order'],'counts':header['counts']}
    semantic=hashlib.sha256(canon(state)).hexdigest(); expected=header['semantic_state_sha256']
    if verify_semantic_hash and semantic!=expected: raise ValueError('packed dormant semantic state mismatch')
    state['state_sha256']=expected; return state
def write_packed(path:str|Path,state:dict[str,Any])->Path:
    p=Path(path); p.write_bytes(pack_state(state)); return p
