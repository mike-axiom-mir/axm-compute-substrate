from __future__ import annotations
import hashlib,json,pathlib,sys
W=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(W))
from AXM_FLOWING_COMPUTE_NATIVE_PACKED_STATE import parse_native,to_json_state
from AXM_FLOWING_COMPUTE_NATIVE_OVERLAY import wake_chain,compact_chain
from AXM_FLOWING_COMPUTE_OVERLAY_COMPACTION import load_calibration,decide
checks=0
def ok(v,msg):
 global checks
 assert v,msg;checks+=1
base=(W/'G0.native.axds').read_bytes(); ovs=[(W/f'G{i}_to_G{i+1}.axov').read_bytes() for i in range(6)]
p,r=wake_chain(base,ovs); target=parse_native((W/'G6.native.axds').read_bytes())['header']['native_semantic_sha256'];ok(r['final_native_semantic_sha256']==target,'six-overlay semantic equality')
ok(to_json_state(compact_chain(base,ovs))['state_sha256']==to_json_state((W/'G6.native.axds').read_bytes())['state_sha256'],'compaction semantic equality')
bad=bytearray(ovs[0]);bad[-40]^=1
try:wake_chain(base,[bytes(bad)]);raise AssertionError('tamper accepted')
except ValueError:checks+=1
try:wake_chain(base,[ovs[1],ovs[0]]);raise AssertionError('reorder accepted')
except ValueError:checks+=1
cal=load_calibration(W/'overlay-compaction-calibration.v0.1.json')
ok(decide(cal,depth=1,expected_wakes_before_next_update=1)['decision']=='append_overlay','depth1 one wake appends')
ok(decide(cal,depth=1,expected_wakes_before_next_update=3)['decision']=='compact_snapshot','depth1 three wakes compact')
ok(decide(cal,depth=48,expected_wakes_before_next_update=1)['decision']=='compact_snapshot','depth48 one wake compact')
try:decide(cal,depth=7,expected_wakes_before_next_update=1);raise AssertionError('unmeasured depth accepted')
except ValueError:checks+=1
print(f'Native overlay self-test passed {checks} checks.')
