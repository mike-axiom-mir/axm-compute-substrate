from __future__ import annotations
import hashlib,struct
from pathlib import Path
from typing import Any
PACK_MAGIC=b'AXCP21\x00\x01';INDEX_MAGIC=b'AXCI21\x00\x01';RECORD_MAGIC=b'B21\x00'

def shahex(raw:bytes)->str:return hashlib.sha256(raw).hexdigest()
def sh(raw:bytes)->bytes:return hashlib.sha256(raw).digest()

class PackedCAS:
    def __init__(self, pack_path:str|Path, index_path:str|Path, *, create:bool=False, keep_open:bool=True):
        self.pack_path=Path(pack_path);self.index_path=Path(index_path);self.keep_open=keep_open;self.index:dict[str,tuple[int,int]]={};self.dirty=False
        if create:
            self.pack_path.parent.mkdir(parents=True,exist_ok=True)
            self.pack_path.write_bytes(PACK_MAGIC)
            self._write_index()
        if not self.pack_path.is_file():raise FileNotFoundError(self.pack_path)
        if self.index_path.is_file():self._read_index()
        else:self._scan_pack();self._write_index()
        self._fh=self.pack_path.open('r+b') if keep_open else None
    def close(self):
        if self.dirty:self.flush_index()
        if self._fh is not None:self._fh.close();self._fh=None
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
    def _read_index(self):
        raw=self.index_path.read_bytes()
        if len(raw)<len(INDEX_MAGIC)+4+32 or not raw.startswith(INDEX_MAGIC):raise ValueError('bad CAS index magic')
        body,stored=raw[:-32],raw[-32:]
        if sh(body)!=stored:raise ValueError('CAS index integrity mismatch')
        off=len(INDEX_MAGIC);n=struct.unpack('>I',body[off:off+4])[0];off+=4;idx={}
        for _ in range(n):
            sha=body[off:off+32].hex();off+=32;pos,length=struct.unpack('>QI',body[off:off+12]);off+=12;idx[sha]=(pos,length)
        if off!=len(body):raise ValueError('CAS index trailing bytes')
        self.index=idx
    def _write_index(self)->int:
        records=b''.join(bytes.fromhex(sha)+struct.pack('>QI',pos,length) for sha,(pos,length) in sorted(self.index.items()))
        body=INDEX_MAGIC+struct.pack('>I',len(self.index))+records;raw=body+sh(body)
        self.index_path.write_bytes(raw);self.dirty=False;return len(raw)
    def flush_index(self)->int:return self._write_index() if self.dirty else 0
    def _scan_pack(self):
        raw=self.pack_path.read_bytes()
        if not raw.startswith(PACK_MAGIC):raise ValueError('bad CAS pack magic')
        off=len(PACK_MAGIC);idx={}
        while off<len(raw):
            if raw[off:off+len(RECORD_MAGIC)]!=RECORD_MAGIC:raise ValueError('CAS pack record magic mismatch')
            off+=len(RECORD_MAGIC);sha=raw[off:off+32].hex();off+=32;length=struct.unpack('>I',raw[off:off+4])[0];off+=4;pos=off;payload=raw[pos:pos+length];off+=length
            if shahex(payload)!=sha:raise ValueError('CAS pack payload hash mismatch')
            idx[sha]=(pos,length)
        self.index=idx
    def add(self,raw:bytes)->tuple[str,bool,int]:
        sha=shahex(raw)
        if sha in self.index:return sha,False,0
        record=RECORD_MAGIC+bytes.fromhex(sha)+struct.pack('>I',len(raw))+raw
        if self._fh is None:
            with self.pack_path.open('ab') as f: pos=f.tell()+len(RECORD_MAGIC)+32+4;f.write(record)
        else:
            self._fh.seek(0,2);start=self._fh.tell();self._fh.write(record);self._fh.flush();pos=start+len(RECORD_MAGIC)+32+4
        self.index[sha]=(pos,len(raw));self.dirty=True
        return sha,True,len(record)
    def get(self,sha:str)->bytes:
        pos,length=self.index[sha]
        if self._fh is None:
            with self.pack_path.open('rb') as f:f.seek(pos);raw=f.read(length)
        else:
            self._fh.seek(pos);raw=self._fh.read(length)
        if len(raw)!=length or shahex(raw)!=sha:raise ValueError('CAS packed block integrity mismatch')
        return raw
    @property
    def index_bytes(self)->int:return self.index_path.stat().st_size if self.index_path.exists() else 0
    @property
    def pack_bytes(self)->int:return self.pack_path.stat().st_size

class MemoryPackedCAS:
    """Read-only fresh-wake view: read tiny append-only pack once, slice by indexed offsets."""
    def __init__(self, pack_path:str|Path,index_path:str|Path):
        self.pack_path=Path(pack_path);self.index_path=Path(index_path);self.index={}
        rawidx=self.index_path.read_bytes()
        if len(rawidx)<len(INDEX_MAGIC)+4+32 or not rawidx.startswith(INDEX_MAGIC):raise ValueError('bad CAS index magic')
        body,stored=rawidx[:-32],rawidx[-32:]
        if sh(body)!=stored:raise ValueError('CAS index integrity mismatch')
        off=len(INDEX_MAGIC);n=struct.unpack('>I',body[off:off+4])[0];off+=4
        for _ in range(n):
            sha=body[off:off+32].hex();off+=32;pos,length=struct.unpack('>QI',body[off:off+12]);off+=12;self.index[sha]=(pos,length)
        if off!=len(body):raise ValueError('CAS index trailing bytes')
        self.pack=self.pack_path.read_bytes()
        if not self.pack.startswith(PACK_MAGIC):raise ValueError('bad CAS pack magic')
    def get(self,sha:str)->bytes:
        pos,length=self.index[sha];raw=self.pack[pos:pos+length]
        if len(raw)!=length or shahex(raw)!=sha:raise ValueError('memory CAS block integrity mismatch')
        return raw
