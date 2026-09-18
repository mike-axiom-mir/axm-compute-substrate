from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from AXM_FLOWING_COMPUTE_POLICY_REGISTRY import *
reg=load_registry(ROOT/'calibration/policy-registry.v0.1.json')
# FrameState profile: partial retained work stays incremental; full invalidation goes global.
ref=select_profile(reg,'framestate-frame-manifest'); frame=load_json(ROOT/ref['profile_path'])
a=route(frame,affected_work_units=46,total_work_units=80); b=route(frame,affected_work_units=80,total_work_units=80)
assert a['decision']=='incremental' and a['confidence']=='clear'
assert b['decision']=='global' and b['confidence']=='uncertain'
# Execution-graph profile remains independently calibrated and routable.
gref=select_profile(reg,'execution-graph-signature-propagation'); graph=load_json(ROOT/gref['profile_path'])
g1=route(graph,affected_components=22,mutated_source_components=1); g2=route(graph,affected_components=127,mutated_source_components=82)
assert g1['decision']=='incremental'
assert g2['decision']=='global'
# Unknown contracts fail closed rather than borrowing a random profile.
try: select_profile(reg,'unknown-contract'); raise AssertionError('unknown contract accepted')
except ValueError: pass
print('AXM Flowing Compute policy registry self-test passed 7 checks.')
