# Flowing Compute Wave 54 — Snapshot File-Identity Merkle Plane

Date: 2026-09-16  
Status: `EXPERIMENTAL REAL-MONOLITH FILE-IDENTITY EVIDENCE`

A deterministic Merkle identity tree was compiled from the fresh actual-ZIP receipt:
- files: 24,965
- leaf capacity: 32,768
- tree artifact: 2,097,136 bytes
- path->leaf SQLite index: 7,954,432 bytes
- compile-from-receipt CPU: ~121.57 ms.

Leaves bind path + byte count + content SHA-256. Wave54 v0.1 preserves a fixed path set.

Full ~558 MB audit and retained Merkle update produced exact identical roots for the real Wave-53 target generations.

Fresh-process medians (3 trials):
- 1 changed file: **1327.66 ms cold -> 9.206 ms Merkle** (**99.31% less / 144.2x**), 15 internal nodes touched.
- 10 files: **1320.34 -> 9.677 ms** (**99.27% / 136.4x**), 100 nodes.
- 100 files: **1350.62 -> 13.912 ms** (**98.97% / 97.1x**), 586 nodes.

Important contrast: Merkle identity was not promoted on the earlier ~261 KB Execution Graph body because flat SHA was usually faster. It wins here because the identity contract spans 24,965 paths / ~558 MB with local changes.

Truth: fixed path topology only; add/delete/rename must HOLD or use a topology-aware successor. One host/filesystem/runtime; CPU is not joules; no compute/energy-from-nothing claim.
