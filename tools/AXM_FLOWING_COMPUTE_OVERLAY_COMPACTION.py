from __future__ import annotations
import json
from pathlib import Path
from typing import Any

SCHEMA='axm.flowing-compute-overlay-compaction-calibration/v0.1'

def load_calibration(path:str|Path)->dict[str,Any]:
    value=json.loads(Path(path).read_text())
    if value.get('schema')!=SCHEMA: raise ValueError('unsupported overlay compaction calibration')
    depths={int(r['depth']):r for r in value.get('depths',[])}
    if len(depths)!=len(value.get('depths',[])): raise ValueError('duplicate calibration depth')
    value['_depths']=depths
    return value

def decide(calibration:dict[str,Any], *, depth:int, expected_wakes_before_next_update:float)->dict[str,Any]:
    if expected_wakes_before_next_update<0: raise ValueError('expected_wakes_before_next_update must be non-negative')
    row=calibration.get('_depths',{}).get(int(depth))
    if row is None: raise ValueError(f'HOLD: no measured compaction calibration for depth={depth}')
    full_emit=float(calibration['emit']['full_snapshot_cpu_ns'])
    overlay_emit=float(calibration['emit']['overlay_cpu_ns'])
    compact_wake=float(row['compact_wake_cpu_ns']); overlay_wake=float(row['overlay_wake_cpu_ns']); n=float(expected_wakes_before_next_update)
    overlay_total=overlay_emit+n*overlay_wake
    compact_total=full_emit+n*compact_wake
    penalty=overlay_wake-compact_wake
    break_even=None if penalty<=0 else (full_emit-overlay_emit)/penalty
    return {'schema':'axm.flowing-compute-overlay-compaction-decision/v0.1','depth':depth,'expected_wakes_before_next_update':n,'decision':'append_overlay' if overlay_total<compact_total else 'compact_snapshot','predicted_overlay_cpu_ns':overlay_total,'predicted_compact_cpu_ns':compact_total,'predicted_cpu_saved_by_decision_ns':abs(overlay_total-compact_total),'estimated_wake_break_even':break_even,'storage':{'base_plus_overlays_bytes':row['base_plus_overlays_bytes'],'compact_snapshot_bytes':row['compact_snapshot_bytes'],'history_full_snapshot_bytes':row['full_history_bytes']},'truth':{'cpu_only_planner':True,'future_wake_count_is_caller_assumption':True,'storage_bytes_are_reported_not_monetized':True,'compaction_checkpoint_does_not_require_history_deletion':True,'unmeasured_depth_is_hold':True}}
