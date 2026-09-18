from __future__ import annotations
import hashlib, json, struct, zlib
from pathlib import Path
from typing import Any

MAGIC=b'AXDS16\x00\x01'
SCHEMA='axm.flowing-compute-native-packed-state/v0.1'
SEMANTIC_TAG=b'AXM-NATIVE-PACKED-SEMANTICS-v0.1\x00'


def canon(v:Any)->bytes:
    return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')

def sha(raw:bytes)->bytes:
    return hashlib.sha256(raw).digest()

def _semantic_header(header:dict[str,Any])->dict[str,Any]:
    out=dict(header); out.pop('native_semantic_sha256',None); return out

def _semantic_hash(header:dict[str,Any], blobs:bytes)->str:
    return hashlib.sha256(SEMANTIC_TAG+canon(_semantic_header(header))+blobs).hexdigest()

def _blocks_from_json(state:dict[str,Any]):
    edge_ids=sorted(state['edge_hashes'])
    comps=sorted(int(k) for k in state['local_hashes'])
    edge_index={eid:i for i,eid in enumerate(edge_ids)}
    comp_indices={str(c):[edge_index[eid] for eid in state['component_edges'][str(c)]] for c in comps}
    edge_component=[None]*len(edge_ids)
    for c,indices in comp_indices.items():
        for i in indices: edge_component[i]=int(c)
    if any(v is None for v in edge_component): raise ValueError('edge without component')
    header={
      'schema':SCHEMA,'source_sha256':state['source_sha256'],'edge_ids':edge_ids,
      'component_members':state['component_members'],'component_edge_indices':comp_indices,
      'predecessors':state['predecessors'],'successors':state['successors'],
      'topological_order':state['topological_order'],'counts':state['counts'],
      'edge_count':len(edge_ids),'component_count':len(comps),
      'legacy_json_state_sha256':state.get('state_sha256')
    }
    blobs=(b''.join(bytes.fromhex(state['edge_hashes'][eid]) for eid in edge_ids)+
           b''.join(bytes.fromhex(state['edge_topology_hashes'][eid]) for eid in edge_ids)+
           b''.join(bytes.fromhex(state['local_hashes'][str(c)]) for c in comps)+
           b''.join(bytes.fromhex(state['signatures'][str(c)]) for c in comps))
    header['native_semantic_sha256']=_semantic_hash(header,blobs)
    return header,blobs

def pack_json_state(state:dict[str,Any])->bytes:
    header,blobs=_blocks_from_json(state)
    hb=zlib.compress(canon(header),6)
    prefix=MAGIC+struct.pack('>III',len(hb),header['edge_count'],header['component_count'])+hb+blobs
    return prefix+sha(prefix)

def parse_native(raw:bytes, *, validate_semantic:bool=True)->dict[str,Any]:
    minlen=len(MAGIC)+12+32
    if len(raw)<minlen or raw[:len(MAGIC)]!=MAGIC: raise ValueError('bad native packed magic')
    body,stored=raw[:-32],raw[-32:]
    if sha(body)!=stored: raise ValueError('native packed container integrity mismatch')
    off=len(MAGIC); hlen,edge_count,comp_count=struct.unpack('>III',body[off:off+12]); off+=12
    header=json.loads(zlib.decompress(body[off:off+hlen])); off+=hlen
    if header.get('schema')!=SCHEMA or header.get('edge_count')!=edge_count or header.get('component_count')!=comp_count:
        raise ValueError('native packed header mismatch')
    need=edge_count*64+comp_count*64
    if len(body)-off!=need: raise ValueError('native packed blob length mismatch')
    blobs=body[off:]
    if validate_semantic and _semantic_hash(header,blobs)!=header.get('native_semantic_sha256'):
        raise ValueError('native packed semantic identity mismatch')
    ebytes=edge_count*32; cbytes=comp_count*32
    edge_index={eid:i for i,eid in enumerate(header['edge_ids'])}
    edge_component=[None]*edge_count
    for c,indices in header['component_edge_indices'].items():
        for i in indices: edge_component[int(i)]=int(c)
    if any(v is None for v in edge_component): raise ValueError('edge without component')
    return {
      'header':header,'edge_index':edge_index,'edge_component_indices':edge_component,
      'edge_hashes':bytearray(blobs[0:ebytes]),
      'edge_topology_hashes':bytearray(blobs[ebytes:ebytes*2]),
      'local_hashes':bytearray(blobs[ebytes*2:ebytes*2+cbytes]),
      'signatures':bytearray(blobs[ebytes*2+cbytes:ebytes*2+cbytes*2]),
    }

def serialize_native_with_identity(parsed:dict[str,Any], *, source_sha256:str|None=None)->tuple[bytes,str]:
    header=dict(parsed['header'])
    if source_sha256 is not None: header['source_sha256']=source_sha256
    blobs=bytes(parsed['edge_hashes'])+bytes(parsed['edge_topology_hashes'])+bytes(parsed['local_hashes'])+bytes(parsed['signatures'])
    header['legacy_json_state_sha256']=None
    semantic=_semantic_hash(header,blobs)
    header['native_semantic_sha256']=semantic
    hb=zlib.compress(canon(header),6)
    prefix=MAGIC+struct.pack('>III',len(hb),header['edge_count'],header['component_count'])+hb+blobs
    return prefix+sha(prefix),semantic

def serialize_native(parsed:dict[str,Any], *, source_sha256:str|None=None)->bytes:
    return serialize_native_with_identity(parsed,source_sha256=source_sha256)[0]

def to_json_state(raw:bytes)->dict[str,Any]:
    p=parse_native(raw,validate_semantic=True); h=p['header']; edge_ids=h['edge_ids']; ec=h['edge_count']; cc=h['component_count']
    def get(block:bytearray,i:int)->str: return bytes(block[i*32:(i+1)*32]).hex()
    component_edges={str(c):[edge_ids[i] for i in h['component_edge_indices'][str(c)]] for c in range(cc)}
    state={'schema':'axm.execution-graph.dormant-signature-state/v0.1','source_sha256':h['source_sha256'],
      'component_members':h['component_members'],'component_edges':component_edges,
      'edge_hashes':{eid:get(p['edge_hashes'],i) for i,eid in enumerate(edge_ids)},
      'edge_topology_hashes':{eid:get(p['edge_topology_hashes'],i) for i,eid in enumerate(edge_ids)},
      'local_hashes':{str(c):get(p['local_hashes'],c) for c in range(cc)},
      'signatures':{str(c):get(p['signatures'],c) for c in range(cc)},
      'predecessors':h['predecessors'],'successors':h['successors'],'topological_order':h['topological_order'],'counts':h['counts']}
    state['state_sha256']=hashlib.sha256(canon(state)).hexdigest()
    return state

def write_native(path:str|Path,state:dict[str,Any])->Path:
    p=Path(path); p.write_bytes(pack_json_state(state)); return p
