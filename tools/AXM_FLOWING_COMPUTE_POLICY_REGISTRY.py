from __future__ import annotations
import json
from pathlib import Path
from typing import Any

REGISTRY_SCHEMA='axm.flowing-compute-policy-registry/v0.1'
PROFILE_SCHEMA='axm.flowing-compute-policy-profile/v0.1'

def load_json(path: str|Path)->dict[str,Any]: return json.loads(Path(path).read_text())

def load_registry(path: str|Path)->dict[str,Any]:
    value=load_json(path)
    if value.get('schema')!=REGISTRY_SCHEMA: raise ValueError('unsupported policy registry schema')
    if not isinstance(value.get('profiles'),dict) or not value['profiles']: raise ValueError('policy registry requires profiles')
    return value

def select_profile(registry:dict[str,Any], contract_id:str)->dict[str,Any]:
    try:return registry['profiles'][contract_id]
    except KeyError: raise ValueError(f'no Flowing Compute policy profile for state contract: {contract_id}')

def decide_retained_work_fraction(profile:dict[str,Any], *, affected_work_units:float,total_work_units:float)->dict[str,Any]:
    affected=float(affected_work_units); total=float(total_work_units)
    if total<=0 or affected<0 or affected>total: raise ValueError('invalid retained-work accounting')
    avoidable=(total-affected)/total*100.0
    decision='incremental' if affected<total else 'global'
    band=float(profile.get('uncertainty_band_percent',0.0))
    return {
      'profile_id':profile['profile_id'],'state_contract':profile['state_contract'],'model_kind':'retained_work_fraction',
      'affected_work_units':affected,'total_work_units':total,'predicted_avoidable_work_percent':avoidable,
      'decision':decision,'confidence':'uncertain' if avoidable<=band else 'clear','uncertainty_band_percent':band,
      'truth':{'decision_is_prediction_not_proof':True,'equivalent_output_still_required':True,'contract_specific':True}
    }

def route(profile:dict[str,Any], **features)->dict[str,Any]:
    kind=profile.get('model_kind')
    if kind is None and 'incremental_cost_model' in profile and 'global_cost_model' in profile:
        kind='linear_component_cost'
    if kind=='retained_work_fraction': return decide_retained_work_fraction(profile,affected_work_units=features['affected_work_units'],total_work_units=features['total_work_units'])
    if kind=='linear_component_cost':
        inc=profile['incremental_cost_model']; glob=profile['global_cost_model']; a=float(features['affected_components']); m=float(features['mutated_source_components'])
        pi=float(inc['intercept'])+float(inc['per_affected_component'])*a+float(inc['per_mutated_source'])*m
        pg=float(glob['intercept'])+float(glob['per_mutated_source'])*m
        adv=(pg-pi)/pg*100.0; band=float(profile.get('uncertainty_band_percent',0.0))
        return {'state_contract':profile['state_contract'],'model_kind':kind,'decision':'incremental' if pi<pg else 'global','confidence':'uncertain' if abs(adv)<=band else 'clear','predicted_incremental_advantage_percent':adv,'truth':{'decision_is_prediction_not_proof':True,'equivalent_output_still_required':True,'contract_specific':True}}
    raise ValueError(f'unsupported Flowing Compute policy model: {kind}')
