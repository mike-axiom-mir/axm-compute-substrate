from __future__ import annotations
import json,pathlib,sys
W=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(W))
from AXM_FLOWING_COMPUTE_NATIVE_PACKED_STATE import pack_json_state,to_json_state,parse_native
from AXM_FLOWING_COMPUTE_NATIVE_PACKED_TRANSITION import transition_native
from AXM_FLOWING_COMPUTE_DORMANT_GRAPH_TRANSITION import build_state,file_sha
checks=0
def ok(x,msg):
 global checks
 assert x,msg;checks+=1
base=json.loads((W/'baseline.dormant-state.json').read_text()); raw=pack_json_state(base)
ok(to_json_state(raw)['state_sha256']==base['state_sha256'],'baseline semantic roundtrip')
bad=bytearray(raw);bad[-40]^=1
try: parse_native(bytes(bad)); raise AssertionError('tamper accepted')
except ValueError: checks+=1
for case in ['a058_m013','a127_m082']:
 d=json.loads((W/f'{case}.delta.json').read_text()); src=W/f'{case}.EXECUTION_GRAPH.json'
 (W/'_tmp.axds').write_bytes(raw); out,r=transition_native(packed_path=W/'_tmp.axds',delta=d,current_source_path=src,mode='incremental')
 cold=build_state(json.loads(src.read_text()),file_sha(src))
 ok(to_json_state(out)['state_sha256']==cold['state_sha256'],case+' cold equivalence')
 ok(r['result_native_semantic_sha256']==parse_native(out)['header']['native_semantic_sha256'],case+' native identity')
(W/'_tmp.axds').unlink(missing_ok=True)
print(f'Native packed state self-test passed {checks} checks.')
