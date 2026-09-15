from __future__ import annotations
import hashlib,json
from pathlib import Path
from typing import Any
from AXM_FLOWING_COMPUTE_PACKED_DORMANT_STATE import unpack_state
from AXM_FLOWING_COMPUTE_DORMANT_GRAPH_TRANSITION import validate_state
HANDLE_SCHEMA='axm.flowing-compute-validated-state-handoff/v0.1'
_TOKEN=object()
class ValidatedStateHandle:
    __slots__=('_state','_receipt','_used','_token')
    def __init__(self,state:dict[str,Any],receipt:dict[str,Any],token:object):
        if token is not _TOKEN: raise ValueError('validated state handles can only be minted by registered validators')
        self._state=state; self._receipt=receipt; self._used=False; self._token=token
    @property
    def receipt(self): return dict(self._receipt)
    def consume(self)->dict[str,Any]:
        if self._used: raise ValueError('validated state handle already consumed')
        self._used=True; return self._state

def _artifact_sha(raw:bytes)->str: return hashlib.sha256(raw).hexdigest()
def _receipt(*,validator_id:str,artifact_sha256:str,state:dict[str,Any])->dict[str,Any]:
    return {'schema':HANDLE_SCHEMA,'validator_id':validator_id,'artifact_sha256':artifact_sha256,'state_sha256':state['state_sha256'],'source_sha256':state['source_sha256'],'validation_passed':True,'truth':{'handle_is_process_local_one_use':True,'validator_proves_semantic_state_before_handoff':True,'not_a_malicious_in_process_security_boundary':True}}
def load_validated_json(path:str|Path)->ValidatedStateHandle:
    raw=Path(path).read_bytes(); state=json.loads(raw); validate_state(state); return ValidatedStateHandle(state,_receipt(validator_id='canonical-json-state/v0.1',artifact_sha256=_artifact_sha(raw),state=state),_TOKEN)
def load_validated_axds(path:str|Path)->ValidatedStateHandle:
    raw=Path(path).read_bytes(); state=unpack_state(raw,verify_semantic_hash=True); return ValidatedStateHandle(state,_receipt(validator_id='axds-packed-state/v0.1',artifact_sha256=_artifact_sha(raw),state=state),_TOKEN)
