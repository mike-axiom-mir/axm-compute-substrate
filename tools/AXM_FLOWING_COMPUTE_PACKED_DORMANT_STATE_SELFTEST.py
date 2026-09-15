import hashlib
from AXM_FLOWING_COMPUTE_PACKED_DORMANT_STATE import *
s={'schema':'axm.execution-graph.dormant-signature-state/v0.1','source_sha256':'a'*64,'component_members':[['a'],['b']],'component_edges':{'0':['e1'],'1':['e2']},'edge_hashes':{'e1':'1'*64,'e2':'2'*64},'edge_topology_hashes':{'e1':'3'*64,'e2':'4'*64},'local_hashes':{'0':'5'*64,'1':'6'*64},'signatures':{'0':'7'*64,'1':'8'*64},'predecessors':{'0':[],'1':[0]},'successors':{'0':[1],'1':[]},'topological_order':[0,1],'counts':{'active_edges':2,'active_nodes':2,'components':2}}
s['state_sha256']=hashlib.sha256(canon(s)).hexdigest(); raw=pack_state(s); got=unpack_state(raw); assert got==s; checks=2
bad=bytearray(raw); bad[-40]^=1
try: unpack_state(bytes(bad)); raise AssertionError
except ValueError: checks+=1
print(f'Packed dormant state self-test passed {checks} checks.')
