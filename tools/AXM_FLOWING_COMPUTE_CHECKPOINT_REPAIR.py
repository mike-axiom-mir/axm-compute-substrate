from __future__ import annotations
import os
from pathlib import Path
from typing import Any
from AXM_FLOWING_COMPUTE_CHECKPOINT_TRANSACTION import recover,scan_segments,scan_checkpoint_spine

def _truncate(path:Path,n:int)->None:
    with path.open('r+b') as f:f.truncate(int(n));f.flush();os.fsync(f.fileno())

def repair_invalid_tails(*,pointer_a:str|Path,pointer_b:str|Path,segment_store:str|Path,checkpoint_spine:str|Path,dry_run:bool=True)->dict[str,Any]:
    before=recover(pointer_a=pointer_a,pointer_b=pointer_b,segment_store=segment_store,checkpoint_spine=checkpoint_spine)
    ss=scan_segments(segment_store);cs=scan_checkpoint_spine(checkpoint_spine);actions=[]
    for name,path,scan in [('segment_store',Path(segment_store),ss),('checkpoint_spine',Path(checkpoint_spine),cs)]:
        tail=int(scan['tail_bytes']);valid=int(scan['valid_prefix_bytes'])
        if tail>0:
            actions.append({'store':name,'truncate_from_bytes':path.stat().st_size,'truncate_to_bytes':valid,'removed_tail_bytes':tail,'scanner_reason':scan['reason']})
            if not dry_run:_truncate(path,valid)
    after=before if dry_run else recover(pointer_a=pointer_a,pointer_b=pointer_b,segment_store=segment_store,checkpoint_spine=checkpoint_spine)
    if not dry_run and before.get('selected_sequence')!=after.get('selected_sequence'):raise RuntimeError('repair changed committed checkpoint selection')
    return {'schema':'axm.flowing-compute-checkpoint-tail-repair/v0.1','dry_run':bool(dry_run),'selected_sequence_before':before.get('selected_sequence'),'selected_sequence_after':after.get('selected_sequence'),'unpointed_before':before.get('unpointed_newer_checkpoints',[]),'unpointed_after':after.get('unpointed_newer_checkpoints',[]) if not dry_run else before.get('unpointed_newer_checkpoints',[]),'actions':actions,'truth':{'only_scanner_proven_invalid_suffix_bytes_are_truncated':True,'valid_unpointed_checkpoint_records_are_not_gc_targets':True,'dependency_invalid_but_structurally_valid_history_is_not_silently_deleted':True,'repair_must_not_change_committed_pointer_selection':True}}
