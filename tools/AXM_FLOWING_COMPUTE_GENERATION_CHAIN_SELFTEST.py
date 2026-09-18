import copy
from AXM_FLOWING_COMPUTE_GENERATION_CHAIN import *
base='a'*64; s0='b'*64
rows=[{'from_source_sha256':base,'to_source_sha256':'c'*64,'from_state_sha256':s0,'to_state_sha256':'d'*64,'delta_sha256':'1'*64,'route':'incremental','equivalence_passed':True},{'from_source_sha256':'c'*64,'to_source_sha256':base,'from_state_sha256':'d'*64,'to_state_sha256':s0,'delta_sha256':'2'*64,'route':'incremental','equivalence_passed':True}]
c=make_chain(contract_id='test',initial_source_sha256=base,initial_state_sha256=s0,transitions=rows); validate_chain(c); checks=2
bad=copy.deepcopy(rows); bad[1]['from_state_sha256']='f'*64
try: make_chain(contract_id='test',initial_source_sha256=base,initial_state_sha256=s0,transitions=bad); raise AssertionError
except ValueError: checks+=1
bad=copy.deepcopy(rows); bad[1]['to_state_sha256']='e'*64
try: make_chain(contract_id='test',initial_source_sha256=base,initial_state_sha256=s0,transitions=bad); raise AssertionError
except ValueError: checks+=1
badc=copy.deepcopy(c); badc['final_state_sha256']='f'*64
try: validate_chain(badc); raise AssertionError
except ValueError: checks+=1
print(f'Generation chain self-test passed {checks} checks.')
