from __future__ import annotations
import copy,json,tempfile
from pathlib import Path
from AXM_FLOWING_COMPUTE_DORMANT_GRAPH_TRANSITION import *
checks=0
with tempfile.TemporaryDirectory() as td:
    root=Path(td)
    base={'edges':[{'id':'e1','from':'a','to':'b','wiring_status':'wired_candidate','source_evidence_status':'old'},{'id':'e2','from':'b','to':'c','wiring_status':'wired_candidate','source_evidence_status':'old'},{'id':'e3','from':'x','to':'y','wiring_status':'wired_candidate','source_evidence_status':'old'}]}
    bp=root/'base.json'; bp.write_text(json.dumps(base,indent=2)); old=build_state(base,file_sha(bp)); validate_state(old); checks+=1
    new=copy.deepcopy(base); new['edges'][0]['source_evidence_status']='new'; np=root/'new.json'; np.write_text(json.dumps(new,indent=2))
    delta=make_delta(old_state=old,new_source_path=np,changed_edges=[new['edges'][0]]); validate_delta(delta); checks+=1
    inc,ri=transition(old_state=old,delta=delta,current_source_path=np,mode='incremental'); glob,rg=transition(old_state=old,delta=delta,current_source_path=np,mode='global'); cold=build_state(new,file_sha(np)); assert inc['state_sha256']==glob['state_sha256']==cold['state_sha256']; checks+=1
    assert ri['recomputed_components']<=rg['recomputed_components']; checks+=1
    bad=copy.deepcopy(delta); bad['changes'][0]['after_edge']['to']='z'; bad['changes'][0]['after_edge_sha256']=h(bad['changes'][0]['after_edge']); body=dict(bad); body.pop('delta_sha256'); bad['delta_sha256']=h(body)
    try: transition(old_state=old,delta=bad,current_source_path=np,mode='incremental',rehash_current_source=False); raise AssertionError
    except ValueError as e: assert 'topology' in str(e); checks+=1
    bad2=copy.deepcopy(old); bad2['signatures']['0']='0'*64
    try: validate_state(bad2); raise AssertionError
    except ValueError: checks+=1
    bad3=copy.deepcopy(delta); bad3['changes'][0]['before_edge_sha256']='0'*64; body=dict(bad3); body.pop('delta_sha256'); bad3['delta_sha256']=h(body)
    try: transition(old_state=old,delta=bad3,current_source_path=np,mode='incremental',rehash_current_source=False); raise AssertionError
    except ValueError: checks+=1
print(f'Dormant graph transition self-test passed {checks} checks.')
