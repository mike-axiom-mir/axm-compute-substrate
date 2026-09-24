from __future__ import annotations
import json
import tempfile
from pathlib import Path
from AXM_FLOWING_COMPUTE_RECEIPT import run_receipt, validate_receipt, make_retained_envelope, validate_retained_envelope, file_identity, source_set_identity

class Adapter:
    id='selftest'; title='Synthetic retained-state receipt selftest'; units=5
    setup_boundary_complete=True
    equivalence_contract='five identical integer answers'
    def __init__(self, source): self.source=source
    def source_files(self): return [(self.source,'input')]
    def inline_source_identity(self): return {'formula':'sum(range(1000))'}
    def cold(self): return [sum(range(1000)) for _ in range(self.units)]
    def setup(self): return sum(range(1000))
    def flow(self,state): return [state for _ in range(self.units)]
    def retained_state(self,state):
        raw=json.dumps(state).encode(); return {'logical_serialized_bytes':len(raw),'measurement':'exact-json-bytes'}
    def freshness_contract(self): return {'mode':'sha256-source-identity','checked_during_probe':True}

with tempfile.TemporaryDirectory() as td:
    p=Path(td)/'source.txt'; p.write_text('source-v1')
    receipt=run_receipt(Adapter(p), trials=2)
    validate_receipt(receipt)
    assert receipt['equivalence']['passed'] is True
    assert receipt['source_identity']['files'][0]['sha256']
    assert receipt['flowing']['retained_state']['logical_serialized_bytes'] > 0
    assert receipt['derived']['useful_yield_multiplier_vs_cold'] > 0
    assert isinstance(receipt['derived']['cpu_saved_percent_vs_cold'], float)
    sid=source_set_identity([file_identity(p,'input')], {'formula':'sum(range(1000))'})
    env=make_retained_envelope({'answer':499500},sid,'selftest','cached deterministic answer')
    assert validate_retained_envelope(env,sid)=={'answer':499500}
    p.write_text('source-v2')
    stale=source_set_identity([file_identity(p,'input')], {'formula':'sum(range(1000))'})
    try:
        validate_retained_envelope(env,stale)
        raise AssertionError('stale envelope was accepted')
    except ValueError as exc:
        assert 'stale' in str(exc)
    tampered=dict(env); tampered['state_payload']={'answer':1}
    try:
        validate_retained_envelope(tampered,sid)
        raise AssertionError('tampered envelope was accepted')
    except ValueError as exc:
        assert 'integrity' in str(exc)
    print('Flowing Compute Receipt self-test passed')
