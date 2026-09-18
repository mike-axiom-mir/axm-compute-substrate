from __future__ import annotations
import hashlib, json
from typing import Any

SCHEMA='axm.flowing-compute-routed-receipt/v0.1'

def canonical(value:Any)->bytes:
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')

def digest(value:Any)->str:
    return hashlib.sha256(canonical(value)).hexdigest()

def build_routed_receipt(*, base_receipt:dict[str,Any], routing_decision:dict[str,Any], profile_generation_sha256:str, actual_route:str, actual_cpu_ns:float, actual_global_cpu_ns:float|None=None, actual_incremental_cpu_ns:float|None=None, ledger_entry_sha256:str|None=None, calibration_mode:bool=False)->dict[str,Any]:
    if base_receipt.get('equivalence',{}).get('passed') is not True:
        raise ValueError('base receipt lacks equivalent-output proof')
    contract_id=str(routing_decision.get('contract_id') or '')
    profile_id=str(routing_decision.get('profile_id') or '')
    predicted_route=str(routing_decision.get('decision') or '')
    if not contract_id or not profile_id: raise ValueError('routing decision lacks contract/profile identity')
    if predicted_route not in ('global','incremental'): raise ValueError('invalid predicted route')
    if actual_route not in ('global','incremental'): raise ValueError('invalid actual route')
    if float(actual_cpu_ns)<=0: raise ValueError('actual_cpu_ns must be positive')
    if not profile_generation_sha256: raise ValueError('profile generation identity required')
    both=actual_global_cpu_ns is not None and actual_incremental_cpu_ns is not None
    winner=correct=regret=None
    if both:
        g=float(actual_global_cpu_ns); i=float(actual_incremental_cpu_ns)
        if g<=0 or i<=0: raise ValueError('counterfactual CPU values must be positive')
        winner='incremental' if i<g else 'global'; correct=predicted_route==winner
        chosen=g if predicted_route=='global' else i; regret=(chosen-min(g,i))/min(g,i)*100.0
    elif calibration_mode:
        raise ValueError('calibration mode requires both route measurements')
    routed={'schema':SCHEMA,'base_receipt_sha256':base_receipt.get('receipt_sha256') or digest(base_receipt),'equivalence':base_receipt['equivalence'],'source_set_sha256':base_receipt.get('source_identity',{}).get('set_sha256'),'routing':{'contract_id':contract_id,'profile_id':profile_id,'profile_generation_sha256':profile_generation_sha256,'features':routing_decision.get('features',{}),'predicted_route':predicted_route,'confidence':routing_decision.get('confidence'),'predicted_global_cpu_ns':routing_decision.get('predicted_global_cpu_ns'),'predicted_incremental_cpu_ns':routing_decision.get('predicted_incremental_cpu_ns'),'uncertainty_band_percent':routing_decision.get('uncertainty_band_percent')},'execution':{'actual_route':actual_route,'actual_cpu_ns':float(actual_cpu_ns),'calibration_mode':bool(calibration_mode),'actual_global_cpu_ns':float(actual_global_cpu_ns) if actual_global_cpu_ns is not None else None,'actual_incremental_cpu_ns':float(actual_incremental_cpu_ns) if actual_incremental_cpu_ns is not None else None,'actual_winner':winner,'prediction_correct':correct,'regret_percent':regret},'learning':{'ledger_entry_sha256':ledger_entry_sha256,'observation_eligible':bool(both and base_receipt['equivalence']['passed']),'auto_promotion_allowed':False},'truth':{'policy_prediction_is_not_execution_proof':True,'equivalent_output_is_required':True,'counterfactual_regret_only_available_when_both_routes_measured':True,'unknown_or_mismatched_contract_must_hold':True,'observations_do_not_rewrite_current_profile':True}}
    routed['routed_receipt_sha256']=digest(routed)
    return routed

def calibration_observation(routed:dict[str,Any])->dict[str,Any]:
    if routed.get('schema')!=SCHEMA: raise ValueError('unsupported routed receipt schema')
    e=routed.get('execution',{})
    if e.get('actual_global_cpu_ns') is None or e.get('actual_incremental_cpu_ns') is None:
        raise ValueError('routed receipt lacks both route measurements')
    return {'contract_id':routed['routing']['contract_id'],'profile_id':routed['routing']['profile_id'],'profile_generation_sha256':routed['routing']['profile_generation_sha256'],'features':routed['routing']['features'],'predicted_route':routed['routing']['predicted_route'],'actual_global_cpu_ns':e['actual_global_cpu_ns'],'actual_incremental_cpu_ns':e['actual_incremental_cpu_ns'],'equivalence_passed':routed['equivalence']['passed'],'output_sha256':routed['equivalence'].get('output_sha256'),'source_set_sha256':routed.get('source_set_sha256'),'routed_receipt_sha256':routed['routed_receipt_sha256']}
