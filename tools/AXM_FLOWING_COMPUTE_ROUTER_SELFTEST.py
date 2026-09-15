from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from AXM_FLOWING_COMPUTE_ROUTER import load_calibration,decide
cal=load_calibration(ROOT/'calibration'/'execution-graph-signature-propagation.v0.1.json')
low=decide(cal,affected_components=22,mutated_source_components=1)
near=decide(cal,affected_components=121,mutated_source_components=76)
full=decide(cal,affected_components=127,mutated_source_components=82)
assert low['decision']=='incremental' and low['confidence']=='clear'
assert near['decision']=='global' and near['confidence']=='uncertain'
assert full['decision']=='global'
assert low['predicted_incremental_cpu_ns'] < low['predicted_global_cpu_ns']
assert full['predicted_incremental_cpu_ns'] > full['predicted_global_cpu_ns']
print('AXM Flowing Compute Router self-test passed 5 checks.')
