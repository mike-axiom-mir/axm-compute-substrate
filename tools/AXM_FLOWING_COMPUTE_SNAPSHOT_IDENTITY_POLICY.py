from __future__ import annotations
from typing import Any

def decide(*,changed_paths_known:bool,path_topology_changed:bool,artifact_available:bool=True)->dict[str,Any]:
    if not changed_paths_known:
        return {'decision':'full_audit','reason':'changed_path_set_unknown','truth':{'incremental_requires_known_change_surface':True}}
    if not artifact_available:
        return {'decision':'compile_identity_artifacts_then_full_or_incremental','reason':'retained_identity_artifact_missing','truth':{'setup_cost_must_be_accounted':True}}
    if path_topology_changed:
        return {'decision':'bucket_identity','reason':'path_set_changed','truth':{'fixed_leaf_order_not_valid_under_path_topology_change':True}}
    return {'decision':'fixed_dense_merkle','reason':'content_change_with_stable_path_set','truth':{'uses_cheaper_measured_structure_for_stable_topology':True}}
