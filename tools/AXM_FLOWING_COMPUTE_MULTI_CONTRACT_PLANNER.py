from __future__ import annotations
from pathlib import Path
from typing import Any
from AXM_FLOWING_COMPUTE_CONTRACT_DEPENDENCY_ROUTER import load_registry as load_deps,route as dependency_route
from AXM_FLOWING_COMPUTE_POLICY_ABI_V03 import decide as policy_decide
from AXM_FLOWING_COMPUTE_SNAPSHOT_IDENTITY_POLICY import decide as snapshot_decide
GRAPH='axm.execution-graph.component-propagated-signatures/v0.1'
SNAP='axm.snapshot.file-identity/v0.1'
MESH='axm.framestate.dormant-mesh/v0.1'
CAP='axm.execution-fabric.capability-index/v0.1'

def plan(*,dependency_registry_path:str|Path,policy_registry_path:str|Path,mutation_sources:list[str],policy_context:dict[str,dict[str,Any]])->dict[str,Any]:
    dr=dependency_route(load_deps(dependency_registry_path),mutation_sources)
    if dr['status']!='ROUTED':return {'status':dr['status'],'dependency_route':dr}
    actions={}
    for cid in dr['reuse_contracts']:
        actions[cid]={'action':'reuse_exact_current_artifact','reason':'no declared source selector matched in this registry version'}
    for cid in dr['affected_contracts']:
        ctx=policy_context.get(cid)
        if ctx is None:return {'status':'HOLD_MISSING_POLICY_CONTEXT','contract_id':cid,'dependency_route':dr,'partial_actions':actions}
        if cid==SNAP:
            need={'changed_paths_known','path_topology_changed','artifact_available'}
            if set(ctx)!=need:return {'status':'HOLD_POLICY_CONTEXT_SHAPE','contract_id':cid,'expected':sorted(need),'got':sorted(ctx),'dependency_route':dr,'partial_actions':actions}
            d=snapshot_decide(**ctx);actions[cid]={'action':d['decision'],'policy':d}
        else:
            try:d=policy_decide(policy_registry_path,contract_id=cid,features=ctx)
            except Exception as e:return {'status':'HOLD_POLICY_DECISION','contract_id':cid,'reason':str(e),'dependency_route':dr,'partial_actions':actions}
            actions[cid]={'action':d['decision'],'policy':d}
    return {'status':'PLANNED','mutation_sources':mutation_sources,'dependency_route':dr,'actions':actions,'truth':{'dependency_affect_does_not_invent_policy_features':True,'contract_local_policy_decides_execution':True,'reuse_requires_exact_current_artifact_validation_later':True}}
