from __future__ import annotations
import json
from pathlib import Path
from typing import Any

PROFILE_SCHEMA="axm.flowing-compute-policy-profile/v0.1"
REGISTRY_SCHEMA="axm.flowing-compute-policy-registry/v0.1"

def load_registry(path: str|Path)->dict[str,Any]:
    value=json.loads(Path(path).read_text())
    if value.get("schema")!=REGISTRY_SCHEMA: raise ValueError("unsupported policy registry schema")
    seen=set()
    for item in value.get("profiles",[]):
        cid=str(item.get("contract_id") or "")
        if not cid: raise ValueError("profile registration missing contract_id")
        if cid in seen: raise ValueError("duplicate policy profile contract_id: "+cid)
        seen.add(cid)
    return value

def load_profile(path: str|Path)->dict[str,Any]:
    value=json.loads(Path(path).read_text())
    if value.get("schema")!=PROFILE_SCHEMA: raise ValueError("unsupported policy profile schema")
    return value

def select_profile(registry:dict[str,Any], *, contract_id:str, base_dir:str|Path)->dict[str,Any]:
    matches=[x for x in registry.get("profiles",[]) if x.get("contract_id")==contract_id]
    if len(matches)!=1: raise ValueError("HOLD: no unique exact policy profile for contract_id="+contract_id)
    profile=load_profile(Path(base_dir)/matches[0]["profile_path"])
    if profile.get("contract_id")!=contract_id: raise ValueError("policy profile contract mismatch")
    return profile

def _cost(model:dict[str,Any], features:dict[str,float])->float:
    total=float(model.get("intercept",0.0))
    for name,value in features.items(): total += float(model.get(name,0.0))*float(value)
    return total

def decide(profile:dict[str,Any], *, contract_id:str, features:dict[str,float])->dict[str,Any]:
    if profile.get("contract_id")!=contract_id: raise ValueError("policy profile contract mismatch")
    required=list(profile.get("features") or [])
    missing=[x for x in required if x not in features]
    extra=[x for x in features if x not in required]
    if missing or extra: raise ValueError(f"feature contract mismatch missing={missing} extra={extra}")
    if any(float(features[x])<0 for x in required): raise ValueError("policy features must be non-negative")
    pg=_cost(profile["models"]["global_cpu_ns"],features); pi=_cost(profile["models"]["incremental_cpu_ns"],features)
    if pg<=0 or pi<=0: raise ValueError("policy predicted non-positive CPU")
    advantage=(pg-pi)/pg*100.0; band=float(profile.get("uncertainty_band_percent",0.0))
    return {"contract_id":contract_id,"profile_id":profile.get("profile_id"),"features":features,"decision":"incremental" if pi<pg else "global","confidence":"uncertain" if abs(advantage)<=band else "clear","predicted_global_cpu_ns":pg,"predicted_incremental_cpu_ns":pi,"predicted_incremental_advantage_percent":advantage,"uncertainty_band_percent":band,"truth":{"prediction_not_proof":True,"exact_output_contract_still_required":True,"profile_is_contract_specific":True}}
