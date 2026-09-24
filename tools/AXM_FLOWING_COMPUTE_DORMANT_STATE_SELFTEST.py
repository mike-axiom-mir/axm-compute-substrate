from __future__ import annotations
import copy, tempfile
from pathlib import Path
from AXM_FLOWING_COMPUTE_DORMANT_STATE import make_envelope, resume, sha256_file

checks=0
with tempfile.TemporaryDirectory() as td:
    root=Path(td); source=root/'source.json'; source.write_text('{"x":1}\n')
    env=make_envelope(source_path=source,state_payload={'answer':7},semantic_contract='test/v0.1',producer='selftest')
    source_sha=sha256_file(source)
    for mode in ('trusted_content_id','stat_token','rehash'):
        payload,receipt=resume(envelope=env,source_path=source,validation_mode=mode,trusted_source_sha256=source_sha if mode=='trusted_content_id' else None)
        assert payload=={'answer':7} and receipt['resume_allowed'] is True; checks+=1
    bad=copy.deepcopy(env); bad['state_payload']['answer']=8
    try: resume(envelope=bad,source_path=source,validation_mode='trusted_content_id',trusted_source_sha256=source_sha); raise AssertionError
    except ValueError: checks+=1
    try: resume(envelope=env,source_path=source,validation_mode='trusted_content_id',trusted_source_sha256='0'*64); raise AssertionError
    except ValueError: checks+=1
    source.write_text('{"x":2}\n')
    try: resume(envelope=env,source_path=source,validation_mode='rehash'); raise AssertionError
    except ValueError: checks+=1
    try: resume(envelope=env,source_path=source,validation_mode='stat_token'); raise AssertionError
    except ValueError: checks+=1
print(f'Dormant-state self-test passed {checks} checks.')
