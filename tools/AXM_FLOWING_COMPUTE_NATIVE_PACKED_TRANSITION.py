from __future__ import annotations
import hashlib,json
from pathlib import Path
from typing import Any
from AXM_FLOWING_COMPUTE_NATIVE_PACKED_STATE import parse_native,serialize_native_with_identity,canon

DELTA_SCHEMA='axm.execution-graph.semantic-delta/v0.1'
RECEIPT_SCHEMA='axm.flowing-compute-native-packed-transition/v0.1'

def h(v:Any)->str: return hashlib.sha256(v if isinstance(v,(bytes,bytearray)) else canon(v)).hexdigest()
def file_sha(path:str|Path)->str:
    hh=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): hh.update(b)
    return hh.hexdigest()
def _get(block:bytearray,i:int)->bytes: return bytes(block[i*32:(i+1)*32])
def _set(block:bytearray,i:int,value:bytes): block[i*32:(i+1)*32]=value

def _validate_delta(delta):
    if delta.get('schema')!=DELTA_SCHEMA: raise ValueError('unsupported delta schema')
    stored=delta.get('delta_sha256'); body=dict(delta); body.pop('delta_sha256',None)
    if h(body)!=stored: raise ValueError('delta integrity mismatch')
    if delta.get('topology_change') is not False: raise ValueError('HOLD: topology change requires rebuild')

def _local_hash(header,parsed,c:int)->bytes:
    rows=[]
    for i in sorted(header['component_edge_indices'][str(c)]):
        rows.append([header['edge_ids'][i],_get(parsed['edge_hashes'],i).hex()])
    return hashlib.sha256(canon(rows)).digest()
def _signature(header,parsed,c:int)->bytes:
    payload={'component_members':header['component_members'][c],
      'local_edge_contract_sha256':_get(parsed['local_hashes'],c).hex(),
      'predecessor_signatures':[_get(parsed['signatures'],int(p)).hex() for p in sorted(header['predecessors'][str(c)])]}
    return hashlib.sha256(canon(payload)).digest()

def transition_native(*, packed_path:str|Path, delta:dict[str,Any], current_source_path:str|Path, mode:str, rehash_current_source:bool=True)->tuple[bytes,dict[str,Any]]:
    if mode not in ('incremental','global'): raise ValueError('mode must be incremental or global')
    _validate_delta(delta)
    parsed=parse_native(Path(packed_path).read_bytes(),validate_semantic=True); header=parsed['header']
    if header['source_sha256']!=delta['from_source_sha256']: raise ValueError('delta does not start from packed generation')
    if rehash_current_source and file_sha(current_source_path)!=delta['to_source_sha256']: raise ValueError('current source content does not match delta target generation')
    changed=set()
    for change in delta['changes']:
        eid=change['edge_id']; i=parsed['edge_index'].get(eid)
        if i is None: raise ValueError('delta edge not retained: '+eid)
        before=_get(parsed['edge_hashes'],i).hex()
        if before!=change['before_edge_sha256']: raise ValueError('delta before-edge mismatch')
        after=change['after_edge']
        if h(after)!=change['after_edge_sha256']: raise ValueError('delta after-edge mismatch')
        if after.get('id')!=eid or after.get('wiring_status')!='wired_candidate': raise ValueError('HOLD: edge identity/wiring change')
        topo=hashlib.sha256(canon([after.get('from'),after.get('to'),after.get('wiring_status')])).digest()
        if topo!=_get(parsed['edge_topology_hashes'],i): raise ValueError('HOLD: edge topology changed')
        _set(parsed['edge_hashes'],i,bytes.fromhex(change['after_edge_sha256']))
        changed.add(int(parsed['edge_component_indices'][i]))
    for c in changed: _set(parsed['local_hashes'],c,_local_hash(header,parsed,c))
    affected=set(changed); stack=list(changed)
    while stack:
        c=stack.pop()
        for d in header['successors'][str(c)]:
            d=int(d)
            if d not in affected: affected.add(d); stack.append(d)
    recompute=set(range(header['component_count'])) if mode=='global' else affected
    for c in header['topological_order']:
        c=int(c)
        if c in recompute: _set(parsed['signatures'],c,_signature(header,parsed,c))
    out,semantic=serialize_native_with_identity(parsed,source_sha256=delta['to_source_sha256'])
    receipt={'schema':RECEIPT_SCHEMA,'from_source_sha256':delta['from_source_sha256'],'to_source_sha256':delta['to_source_sha256'],
      'delta_sha256':delta['delta_sha256'],'mode':mode,'changed_components':len(changed),'affected_components':len(affected),
      'total_components':header['component_count'],'recomputed_components':len(recompute),
      'result_native_semantic_sha256':semantic,'result_artifact_sha256':hashlib.sha256(out).hexdigest(),
      'rehash_current_source':rehash_current_source,'truth':{'no_full_json_hash_maps_materialized_in_transition':True,'json_equivalence_requires_external_evidence':True}}
    receipt['receipt_sha256']=h(receipt)
    return out,receipt
