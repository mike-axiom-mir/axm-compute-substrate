from __future__ import annotations
import json
from pathlib import Path
from typing import Any

SCHEMA = 'axm.flowing-compute-routing-calibration/v0.1'

def load_calibration(path: str | Path) -> dict[str, Any]:
    value=json.loads(Path(path).read_text())
    if value.get('schema') != SCHEMA: raise ValueError('unsupported routing calibration schema')
    for key in ('incremental_cost_model','global_cost_model','uncertainty_band_percent','state_contract'):
        if key not in value: raise ValueError(f'missing calibration field: {key}')
    return value

def decide(calibration: dict[str, Any], *, affected_components: int, mutated_source_components: int) -> dict[str, Any]:
    if affected_components < 0 or mutated_source_components < 0: raise ValueError('structural counts must be non-negative')
    inc=calibration['incremental_cost_model']; glob=calibration['global_cost_model']
    predicted_incremental=(float(inc['intercept']) + float(inc['per_affected_component'])*affected_components + float(inc['per_mutated_source'])*mutated_source_components)
    predicted_global=(float(glob['intercept']) + float(glob['per_mutated_source'])*mutated_source_components)
    if predicted_global <= 0 or predicted_incremental <= 0: raise ValueError('calibration predicted non-positive CPU cost')
    advantage=(predicted_global-predicted_incremental)/predicted_global*100.0
    band=float(calibration['uncertainty_band_percent'])
    return {
      'state_contract':calibration['state_contract'],
      'affected_components':affected_components,
      'mutated_source_components':mutated_source_components,
      'predicted_incremental_cpu_ns':predicted_incremental,
      'predicted_global_cpu_ns':predicted_global,
      'predicted_incremental_advantage_percent':advantage,
      'decision':'incremental' if predicted_incremental < predicted_global else 'global',
      'confidence':'uncertain' if abs(advantage) <= band else 'clear',
      'uncertainty_band_percent':band,
      'truth':{
        'decision_is_prediction_not_proof':True,
        'output_equivalence_must_be_enforced_by_execution_contract':True,
        'calibration_is_contract_specific':True,
      },
    }
