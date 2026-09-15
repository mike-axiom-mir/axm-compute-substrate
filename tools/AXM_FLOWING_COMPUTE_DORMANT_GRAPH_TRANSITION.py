from __future__ import annotations
import hashlib, json
from collections import deque
from pathlib import Path
from typing import Any

STATE_SCHEMA='axm.execution-graph.dormant-signature-state/v0.1'
DELTA_SCHEMA='axm.execution-graph.semantic-delta/v0.1'
TRANSITION_SCHEMA='axm.flowing-compute-dormant-transition-receipt/v0.1'

def canon(v:Any)->bytes:
    return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')
def h(v:Any)->str:
    return hashlib.sha256(v if isinstance(v,(bytes,bytearray)) else canon(v)).hexdigest()
def file_sha(path:str|Path)->str:
    hh=hashlib.sha256()
    with Path(path).open('rb') as f:
        while True:
            b=f.read(1024*1024)
            if not b: break
            hh.update(b)
    return hh.hexdigest()

def _graph_from_rows(edge_rows:list[dict[str,Any]]):
    edges=[dict(e) for e in edge_rows if e.get('wiring_status')=='wired_candidate']
    nodes=sorted({e['from'] for e in edges}|{e['to'] for e in edges})
    adj={n:[] for n in nodes}
    for e in edges: adj[e['from']].append(e['to'])
    idx={}; low={}; stack=[]; on=set(); comps=[]; counter=[0]
    def strong(v):
        idx[v]=low[v]=counter[0]; counter[0]+=1; stack.append(v); on.add(v)
        for w in adj[v]:
            if w not in idx:
                strong(w); low[v]=min(low[v],low[w])
            elif w in on: low[v]=min(low[v],idx[w])
        if low[v]==idx[v]:
            c=[]
            while True:
                w=stack.pop(); on.remove(w); c.append(w)
                if w==v: break
            comps.append(sorted(c))
    for n in nodes:
        if n not in idx: strong(n)
    comp_of={n:i for i,c in enumerate(comps) for n in c}
    cadj={i:set() for i in range(len(comps))}; pred={i:set() for i in range(len(comps))}; comp_edge_ids={i:[] for i in range(len(comps))}
    edge_by_id={e['id']:e for e in edges}
    for e in edges:
        a,b=comp_of[e['from']],comp_of[e['to']]
        comp_edge_ids[a].append(e['id'])
        if a!=b: cadj[a].add(b); pred[b].add(a)
    indeg={i:len(pred[i]) for i in range(len(comps))}; q=deque(sorted(i for i,v in indeg.items() if v==0)); topo=[]
    while q:
        c=q.popleft(); topo.append(c)
        for d in sorted(cadj[c]):
            indeg[d]-=1
            if indeg[d]==0:q.append(d)
    if len(topo)!=len(comps): raise ValueError('condensation graph is not acyclic')
    return edges,nodes,comps,comp_of,cadj,pred,topo,comp_edge_ids,edge_by_id

def _local_hash(comp_id:int, comp_edge_ids:dict[int,list[str]], edge_hashes:dict[str,str])->str:
    return h([[eid,edge_hashes[eid]] for eid in sorted(comp_edge_ids[comp_id])])

def _signature(comp_id:int, comps:list[list[str]], pred:dict[int,set[int]], local:dict[int,str], sig:dict[int,str])->str:
    return h({'component_members':comps[comp_id],'local_edge_contract_sha256':local[comp_id], 'predecessor_signatures':[sig[p] for p in sorted(pred[comp_id])]})

def build_state(graph:dict[str,Any], source_sha256:str)->dict[str,Any]:
    edges,nodes,comps,comp_of,cadj,pred,topo,comp_edge_ids,edge_by_id=_graph_from_rows(graph['edges'])
    edge_hashes={eid:h(edge_by_id[eid]) for eid in sorted(edge_by_id)}
    local={c:_local_hash(c,comp_edge_ids,edge_hashes) for c in range(len(comps))}
    sig={}
    for c in topo: sig[c]=_signature(c,comps,pred,local,sig)
    state={
      'schema':STATE_SCHEMA,'source_sha256':source_sha256,
      'component_members':comps,
      'component_edges':{str(k):sorted(v) for k,v in comp_edge_ids.items()},
      'edge_hashes':edge_hashes,
      'edge_topology_hashes':{eid:h([edge_by_id[eid]['from'],edge_by_id[eid]['to'],edge_by_id[eid].get('wiring_status')]) for eid in sorted(edge_by_id)},
      'local_hashes':{str(k):v for k,v in local.items()},
      'signatures':{str(k):v for k,v in sig.items()},
      'predecessors':{str(k):sorted(v) for k,v in pred.items()},
      'successors':{str(k):sorted(v) for k,v in cadj.items()},
      'topological_order':topo,
      'counts':{'active_edges':len(edges),'active_nodes':len(nodes),'components':len(comps)},
    }
    state['state_sha256']=h(state)
    return state

def validate_state(state:dict[str,Any])->None:
    if state.get('schema')!=STATE_SCHEMA: raise ValueError('unsupported dormant graph state')
    stored=state.get('state_sha256'); body=dict(state); body.pop('state_sha256',None)
    if h(body)!=stored: raise ValueError('dormant graph state integrity mismatch')

def make_delta(*, old_state:dict[str,Any], new_source_path:str|Path, changed_edges:list[dict[str,Any]])->dict[str,Any]:
    validate_state(old_state)
    new_sha=file_sha(new_source_path)
    changes=[]
    for edge in changed_edges:
        eid=edge['id']; before=old_state['edge_hashes'].get(eid)
        if not before: raise ValueError('delta edge is not retained: '+eid)
        changes.append({'edge_id':eid,'before_edge_sha256':before,'after_edge':edge,'after_edge_sha256':h(edge)})
    value={'schema':DELTA_SCHEMA,'from_source_sha256':old_state['source_sha256'],'to_source_sha256':new_sha,'topology_change':False,'changes':changes}
    value['delta_sha256']=h(value)
    return value

def validate_delta(delta:dict[str,Any])->None:
    if delta.get('schema')!=DELTA_SCHEMA: raise ValueError('unsupported delta schema')
    stored=delta.get('delta_sha256'); body=dict(delta); body.pop('delta_sha256',None)
    if h(body)!=stored: raise ValueError('delta integrity mismatch')
    if delta.get('topology_change') is not False: raise ValueError('HOLD: topology change requires rebuild')

def _runtime(state):
    comps=state['component_members']; comp_edge_ids={int(k):list(v) for k,v in state['component_edges'].items()}; edge_hashes=dict(state['edge_hashes']); edge_topology_hashes=dict(state['edge_topology_hashes']); local={int(k):v for k,v in state['local_hashes'].items()}; sig={int(k):v for k,v in state['signatures'].items()}; pred={int(k):set(v) for k,v in state['predecessors'].items()}; succ={int(k):set(v) for k,v in state['successors'].items()}; topo=list(state['topological_order']); edge_to_comp={eid:c for c,eids in comp_edge_ids.items() for eid in eids}
    return comps,comp_edge_ids,edge_hashes,edge_topology_hashes,local,sig,pred,succ,topo,edge_to_comp

def prepare_transition(*, old_state:dict[str,Any], delta:dict[str,Any], current_source_path:str|Path, rehash_current_source:bool=True)->dict[str,Any]:
    validate_state(old_state); validate_delta(delta)
    if old_state['source_sha256']!=delta['from_source_sha256']: raise ValueError('delta does not start from dormant state generation')
    if rehash_current_source and file_sha(current_source_path)!=delta['to_source_sha256']: raise ValueError('current source content does not match delta target generation')
    comps,comp_edge_ids,edge_hashes,edge_topology_hashes,local,sig,pred,succ,topo,edge_to_comp=_runtime(old_state)
    changed_components=set()
    for change in delta['changes']:
        eid=change['edge_id']
        if edge_hashes.get(eid)!=change['before_edge_sha256']: raise ValueError('delta before-edge mismatch')
        after=change['after_edge']
        if h(after)!=change['after_edge_sha256']: raise ValueError('delta after-edge integrity mismatch')
        if after.get('id')!=eid or after.get('wiring_status')!='wired_candidate': raise ValueError('HOLD: edge identity/wiring change requires rebuild')
        if h([after.get('from'),after.get('to'),after.get('wiring_status')]) != edge_topology_hashes[eid]: raise ValueError('HOLD: edge topology changed')
        c=edge_to_comp[eid]; edge_hashes[eid]=change['after_edge_sha256']; changed_components.add(c)
    for c in changed_components: local[c]=_local_hash(c,comp_edge_ids,edge_hashes)
    affected=set(changed_components); stack=list(changed_components)
    while stack:
        c=stack.pop()
        for d in succ[c]:
            if d not in affected: affected.add(d); stack.append(d)
    return {'old_state':old_state,'delta':delta,'comps':comps,'comp_edge_ids':comp_edge_ids,'edge_hashes':edge_hashes,'edge_topology_hashes':edge_topology_hashes,'local':local,'sig':sig,'pred':pred,'succ':succ,'topo':topo,'changed_components':changed_components,'affected':affected,'rehash_current_source':rehash_current_source}

def propagate_transition(prepared:dict[str,Any], mode:str)->dict[str,Any]:
    if mode not in ('incremental','global'): raise ValueError('mode must be incremental or global')
    comps=prepared['comps']; local=prepared['local']; sig=dict(prepared['sig']); pred=prepared['pred']; topo=prepared['topo']; affected=prepared['affected']; recompute=set(topo) if mode=='global' else set(affected)
    for c in topo:
        if c in recompute: sig[c]=_signature(c,comps,pred,local,sig)
    return {'mode':mode,'signatures':sig,'recompute':recompute}

def finalize_transition(prepared:dict[str,Any], propagated:dict[str,Any])->tuple[dict[str,Any],dict[str,Any]]:
    old_state=prepared['old_state']; delta=prepared['delta']; comps=prepared['comps']; comp_edge_ids=prepared['comp_edge_ids']; edge_hashes=prepared['edge_hashes']; edge_topology_hashes=prepared['edge_topology_hashes']; local=prepared['local']; sig=propagated['signatures']; pred=prepared['pred']; succ=prepared['succ']; topo=prepared['topo']; changed_components=prepared['changed_components']; affected=prepared['affected']; recompute=propagated['recompute']; mode=propagated['mode']
    new_state={'schema':STATE_SCHEMA,'source_sha256':delta['to_source_sha256'],'component_members':comps,'component_edges':{str(k):sorted(v) for k,v in comp_edge_ids.items()},'edge_hashes':edge_hashes,'edge_topology_hashes':edge_topology_hashes,'local_hashes':{str(k):v for k,v in local.items()},'signatures':{str(k):v for k,v in sig.items()},'predecessors':{str(k):sorted(v) for k,v in pred.items()},'successors':{str(k):sorted(v) for k,v in succ.items()},'topological_order':topo,'counts':dict(old_state['counts'])}
    new_state['state_sha256']=h(new_state)
    receipt={'schema':TRANSITION_SCHEMA,'from_source_sha256':delta['from_source_sha256'],'to_source_sha256':delta['to_source_sha256'],'delta_sha256':delta['delta_sha256'],'mode':mode,'rehash_current_source':prepared['rehash_current_source'],'changed_components':len(changed_components),'affected_components':len(affected),'total_components':len(comps),'recomputed_components':len(recompute),'result_state_sha256':new_state['state_sha256'],'equivalence_required':True}
    receipt['receipt_sha256']=h(receipt); return new_state,receipt

def finish_transition(prepared:dict[str,Any], mode:str)->tuple[dict[str,Any],dict[str,Any]]:
    return finalize_transition(prepared,propagate_transition(prepared,mode))

def transition(*, old_state:dict[str,Any], delta:dict[str,Any], current_source_path:str|Path, mode:str, rehash_current_source:bool=True)->tuple[dict[str,Any],dict[str,Any]]:
    return finish_transition(prepare_transition(old_state=old_state,delta=delta,current_source_path=current_source_path,rehash_current_source=rehash_current_source),mode)
