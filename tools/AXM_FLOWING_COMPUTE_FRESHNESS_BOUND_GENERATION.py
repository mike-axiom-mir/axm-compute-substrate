from __future__ import annotations
import hashlib,json,os
from pathlib import Path
from typing import Any
from AXM_FLOWING_COMPUTE_VERIFICATION_FRESHNESS import validate as validate_freshness
SCHEMA='axm.flowing-compute-freshness-bound-generation/v0.1'
def canon(v:Any)->bytes:return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def digest(v:Any)->str:return hashlib.sha256(canon(v)).hexdigest()
def make_pointer(*,sequence:int,generation_sha256:str,freshness:dict[str,dict[str,Any]])->dict[str,Any]:
    for s in freshness.values():validate_freshness(s)
    body={'schema':SCHEMA,'sequence':int(sequence),'generation_sha256':generation_sha256,'freshness':freshness,'truth':{'generation_and_verification_freshness_share_one_commit_boundary':True}}
    body['pointer_sha256']=digest(body);return body
def validate_pointer(p:dict[str,Any])->None:
    if p.get('schema')!=SCHEMA:raise ValueError('unsupported freshness-bound pointer schema')
    stored=p.get('pointer_sha256');b=dict(p);b.pop('pointer_sha256',None)
    if digest(b)!=stored:raise ValueError('freshness-bound pointer integrity mismatch')
    if int(p['sequence'])<0:raise ValueError('invalid sequence')
    for s in p.get('freshness',{}).values():
        validate_freshness(s)
        if int(s['current_sequence'])!=int(p['sequence']):raise ValueError('freshness sequence does not match generation')
def atomic_write(path:str|Path,pointer:dict[str,Any])->None:
    validate_pointer(pointer);path=Path(path);tmp=path.with_name(path.name+'.tmp')
    with tmp.open('wb') as f:f.write(canon(pointer)+b'\n');f.flush();os.fsync(f.fileno())
    os.replace(tmp,path);fd=os.open(str(path.parent),os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)
def read(path:str|Path)->dict[str,Any]:
    p=json.loads(Path(path).read_text());validate_pointer(p);return p
