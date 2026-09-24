from __future__ import annotations
from typing import Any

def calibration_decision(*, routing_decision:dict[str,Any], enabled:bool, remaining_shadow_budget:int)->dict[str,Any]:
    if remaining_shadow_budget < 0: raise ValueError('remaining_shadow_budget must be non-negative')
    confidence=routing_decision.get('confidence')
    if not enabled:
        return {'shadow_measure_both_routes':False,'reason':'calibration_disabled','budget_after':remaining_shadow_budget}
    if remaining_shadow_budget == 0:
        return {'shadow_measure_both_routes':False,'reason':'shadow_budget_exhausted','budget_after':0}
    if confidence != 'uncertain':
        return {'shadow_measure_both_routes':False,'reason':'prediction_clear','budget_after':remaining_shadow_budget}
    return {'shadow_measure_both_routes':True,'reason':'uncertain_prediction_with_explicit_budget','budget_after':remaining_shadow_budget-1}
