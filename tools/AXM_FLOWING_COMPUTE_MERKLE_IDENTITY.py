from __future__ import annotations
import hashlib,json
from typing import Any
from AXM_FLOWING_COMPUTE_NATIVE_PACKED_STATE import _semantic_header,canon

SCHEMA='axm.flowing-compute-merkle-identity/v0.1';FANOUT=64;TAG=b'AXM-MERKLE18-v0.1\x00'
def sh(raw:bytes)->bytes:return hashlib.sha256(raw).digest()
def _get(block,i):return bytes(block[i*32:(i+1)*32])

def leaf_count(parsed)->int:
 h=parsed['header'];return 1+h['edge_count']*2+h['component_count']*2

def leaf_value(parsed,i:int)->bytes:
 h=parsed['header'];ec=h['edge_count'];cc=h['component_count']
 if i==0:return sh(canon(_semantic_header(h)))
 i-=1
 if i<ec:return _get(parsed['edge_hashes'],i)
 i-=ec
 if i<ec:return _get(parsed['edge_topology_hashes'],i)
 i-=ec
 if i<cc:return _get(parsed['local_hashes'],i)
 i-=cc
 if i<cc:return _get(parsed['signatures'],i)
 raise IndexError(i)

def _group_hash(level:int,group:int,items:list[tuple[int,bytes]])->bytes:
 raw=bytearray(TAG);raw.extend(level.to_bytes(2,'big'));raw.extend(group.to_bytes(4,'big'));raw.extend(len(items).to_bytes(2,'big'))
 for idx,val in items:raw.extend(idx.to_bytes(4,'big'));raw.extend(val)
 return sh(bytes(raw))

def build_tree(parsed,fanout:int=FANOUT)->dict[str,Any]:
 n=leaf_count(parsed);level=[]
 for start in range(0,n,fanout):
  g=start//fanout;level.append(_group_hash(0,g,[(i,leaf_value(parsed,i)) for i in range(start,min(n,start+fanout))]))
 levels=[level];lev=1
 while len(level)>1:
  nxt=[]
  for start in range(0,len(level),fanout):
   g=start//fanout;nxt.append(_group_hash(lev,g,[(i,level[i]) for i in range(start,min(len(level),start+fanout))]))
  levels.append(nxt);level=nxt;lev+=1
 return {'schema':SCHEMA,'fanout':fanout,'leaf_count':n,'levels':[[x.hex() for x in lv] for lv in levels],'root_sha256':levels[-1][0].hex(),'native_semantic_sha256':parsed['header']['native_semantic_sha256']}

def validate_tree(tree):
 if tree.get('schema')!=SCHEMA or int(tree.get('fanout',0))<2 or not tree.get('levels'):raise ValueError('invalid merkle identity tree')
 if tree['levels'][-1][0]!=tree.get('root_sha256'):raise ValueError('merkle root field mismatch')

def update_tree(tree:dict[str,Any],parsed_new,changed_leaf_indices:set[int]|list[int])->dict[str,Any]:
 validate_tree(tree);fanout=int(tree['fanout']);levels=[[bytes.fromhex(x) for x in lv] for lv in tree['levels']];n=int(tree['leaf_count'])
 changed={int(i) for i in changed_leaf_indices}
 if any(i<0 or i>=n for i in changed):raise ValueError('changed leaf out of range')
 groups={i//fanout for i in changed}
 for g in groups:
  start=g*fanout;levels[0][g]=_group_hash(0,g,[(i,leaf_value(parsed_new,i)) for i in range(start,min(n,start+fanout))])
 prev_groups=groups
 for lev in range(1,len(levels)):
  groups={g//fanout for g in prev_groups}
  for g in groups:
   start=g*fanout;levels[lev][g]=_group_hash(lev,g,[(i,levels[lev-1][i]) for i in range(start,min(len(levels[lev-1]),start+fanout))])
  prev_groups=groups
 return {'schema':SCHEMA,'fanout':fanout,'leaf_count':n,'levels':[[x.hex() for x in lv] for lv in levels],'root_sha256':levels[-1][0].hex(),'native_semantic_sha256':parsed_new['header']['native_semantic_sha256'],'changed_leaf_count':len(changed),'changed_level0_groups':len({i//fanout for i in changed})}

def changed_leaf_indices(parsed, *, edge_indices:set[int], local_indices:set[int], signature_indices:set[int], header_changed:bool=True)->set[int]:
 h=parsed['header'];ec=h['edge_count'];cc=h['component_count'];out=set()
 if header_changed:out.add(0)
 out|={1+i for i in edge_indices};out|={1+ec*2+i for i in local_indices};out|={1+ec*2+cc+i for i in signature_indices};return out
