from __future__ import annotations
import hashlib,json,os,struct
from pathlib import Path
from typing import Any
MAGIC=b'AXCL66\x00\x01'
def canon(v:Any)->bytes:return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def dig(v:Any)->str:return hashlib.sha256(canon(v)).hexdigest()
def validate_pointer(p:dict[str,Any])->None:
 if p.get('schema')!='axm.flowing-compute-composite-lineage-pointer/v0.2':raise ValueError('bad lineage pointer schema')
 s=p.get('pointer_sha256');b=dict(p);b.pop('pointer_sha256',None)
 if not s or dig(b)!=s:raise ValueError('lineage pointer integrity mismatch')
def make_pointer(*,sequence:int,parent_pointer_sha256:str|None,graph:dict[str,Any],snapshot:dict[str,Any],branch_label:str='main')->dict[str,Any]:
 b={'schema':'axm.flowing-compute-composite-lineage-pointer/v0.2','sequence':int(sequence),'parent_pointer_sha256':parent_pointer_sha256,'branch_label':branch_label,'graph':graph,'snapshot':snapshot,'truth':{'parent_hash_defines_lineage_not_sequence_number':True}}
 b['pointer_sha256']=dig(b);return b
class Store:
 def __init__(self,path):
  self.path=Path(path)
  if not self.path.exists():self.path.write_bytes(MAGIC)
  self.objects={};self.scan()
 def scan(self):
  raw=self.path.read_bytes()
  if not raw.startswith(MAGIC):raise ValueError('bad lineage store magic')
  off=len(MAGIC);objs={}
  while off<len(raw):
   if off+36>len(raw):break
   hh=raw[off:off+32].hex();ln=struct.unpack('>I',raw[off+32:off+36])[0];bo=off+36;end=bo+ln
   if end>len(raw):break
   body=raw[bo:end];p=json.loads(body);validate_pointer(p)
   if p['pointer_sha256']!=hh:raise ValueError('lineage content-address mismatch')
   objs[hh]={'offset':bo,'length':ln,'pointer':p};off=end
  self.objects=objs;return objs
 def put(self,p):
  validate_pointer(p);raw=canon(p);hh=p['pointer_sha256']
  if hh in self.objects:return self.objects[hh]
  frame=bytes.fromhex(hh)+struct.pack('>I',len(raw))+raw
  with self.path.open('ab') as f:f.write(frame);f.flush();os.fsync(f.fileno())
  self.scan();return self.objects[hh]
 def get(self,hh):
  if hh not in self.objects:raise ValueError('lineage object missing')
  return self.objects[hh]['pointer']
def ref_bytes(hh,offset,length):
 b={'schema':'axm.flowing-compute-composite-current-ref/v0.1','pointer_sha256':hh,'offset':int(offset),'length':int(length)};b['ref_sha256']=dig(b);return canon(b)+b'\n'
def parse_ref(raw):
 r=json.loads(raw);s=r.get('ref_sha256');b=dict(r);b.pop('ref_sha256',None)
 if r.get('schema')!='axm.flowing-compute-composite-current-ref/v0.1' or dig(b)!=s:raise ValueError('bad current ref')
 return r
def atomic(path,raw):
 p=Path(path);tmp=p.with_name(p.name+'.tmp')
 with tmp.open('wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 os.replace(tmp,p);fd=os.open(str(p.parent),os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)
def current(store:Store,ref_path):
 r=parse_ref(Path(ref_path).read_bytes());o=store.objects.get(r['pointer_sha256'])
 if not o or o['offset']!=r['offset'] or o['length']!=r['length']:raise ValueError('current ref object mismatch')
 return o['pointer']
def rollback(*,store:Store,ref_path,target_sha256:str,execute:bool=True):
 cur=current(store,ref_path);cursor=cur;path=[]
 while cursor is not None:
  path.append(cursor['pointer_sha256'])
  if cursor['pointer_sha256']==target_sha256:break
  parent=cursor.get('parent_pointer_sha256');cursor=store.get(parent) if parent else None
 if not path or path[-1]!=target_sha256:return {'status':'HOLD_TARGET_NOT_ANCESTOR','current':cur['pointer_sha256'],'target':target_sha256}
 target=store.get(target_sha256)
 if not execute:return {'status':'ROLLBACK_READY','from_sequence':cur['sequence'],'to_sequence':target['sequence'],'path_depth':len(path)}
 o=store.objects[target_sha256];atomic(ref_path,ref_bytes(target_sha256,o['offset'],o['length']))
 after=current(store,ref_path)
 if after['pointer_sha256']!=target_sha256:raise RuntimeError('rollback commit failed')
 return {'status':'ROLLED_BACK_EXACT_ANCESTOR','from_sequence':cur['sequence'],'to_sequence':after['sequence'],'path_depth':len(path),'target_pointer_sha256':target_sha256}
def activate_descendant(*,store:Store,ref_path,target_sha256:str,execute:bool=True):
 cur=current(store,ref_path)
 try:target=store.get(target_sha256)
 except Exception:return {'status':'HOLD_TARGET_NOT_PRESERVED'}
 cursor=target;reverse_path=[]
 while cursor is not None:
  reverse_path.append(cursor['pointer_sha256'])
  if cursor['pointer_sha256']==cur['pointer_sha256']:break
  parent=cursor.get('parent_pointer_sha256');cursor=store.get(parent) if parent else None
 if not reverse_path or reverse_path[-1]!=cur['pointer_sha256']:
  return {'status':'HOLD_TARGET_NOT_DESCENDANT','current':cur['pointer_sha256'],'target':target_sha256}
 if target['pointer_sha256']==cur['pointer_sha256']:return {'status':'ALREADY_CURRENT','sequence':cur['sequence']}
 if not execute:return {'status':'DESCENDANT_ACTIVATION_READY','from_sequence':cur['sequence'],'to_sequence':target['sequence'],'path_depth':len(reverse_path)}
 o=store.objects[target_sha256];atomic(ref_path,ref_bytes(target_sha256,o['offset'],o['length']))
 after=current(store,ref_path)
 if after['pointer_sha256']!=target_sha256:raise RuntimeError('descendant activation failed')
 return {'status':'ACTIVATED_EXACT_DESCENDANT','from_sequence':cur['sequence'],'to_sequence':after['sequence'],'path_depth':len(reverse_path),'target_pointer_sha256':target_sha256}
