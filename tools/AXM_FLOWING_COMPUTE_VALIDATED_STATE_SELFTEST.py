from __future__ import annotations
import tempfile,pathlib
from AXM_FLOWING_COMPUTE_VALIDATED_STATE import *
from AXM_FLOWING_COMPUTE_DORMANT_GRAPH_TRANSITION import *
checks=0
# The self-test expects a real canonical state and AXDS artifact supplied by the local probe harness.
def run(json_path:pathlib.Path,axds_path:pathlib.Path)->int:
    global checks
    j=load_validated_json(json_path); a=load_validated_axds(axds_path)
    assert j.receipt['state_sha256']==a.receipt['state_sha256']; checks+=1
    state=j.consume(); checks+=1
    try: j.consume(); raise AssertionError
    except ValueError: checks+=1
    try: ValidatedStateHandle(state,{},object()); raise AssertionError
    except ValueError: checks+=1
    raw=bytearray(axds_path.read_bytes()); raw[-40]^=1
    with tempfile.TemporaryDirectory() as td:
        p=pathlib.Path(td)/'bad.axds'; p.write_bytes(raw)
        try: load_validated_axds(p); raise AssertionError
        except ValueError: checks+=1
    return checks
if __name__=='__main__':
    import sys
    if len(sys.argv)!=3: raise SystemExit('Usage: python AXM_FLOWING_COMPUTE_VALIDATED_STATE_SELFTEST.py STATE.json STATE.axds')
    print(f'Validated state handoff self-test passed {run(pathlib.Path(sys.argv[1]),pathlib.Path(sys.argv[2]))} checks.')
