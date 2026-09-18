# Flowing Compute Wave 55 — Dense Snapshot Identity Plane + Byte-Surface Routing

Date: 2026-09-16  
Status: `EXPERIMENTAL REAL-MONOLITH IDENTITY-ROUTING EVIDENCE`

Wave54 reconstructed ~65k Python hash-node objects on each fresh update. Wave55 keeps the 2.1 MB tree as one dense bytearray and mutates 32-byte slices directly.

11-trial fresh-process retained update medians:
- 1 file: **2.026 ms** (~78% less than Wave54; ~655x faster than full audit)
- 10 files: **2.530 ms** (~74% less; ~522x vs full)
- 100 files: **5.868 ms** (~58% less; ~230x vs full)

Exact roots remain equal to cold audit.

## Count is not enough
Ten tiny changed files: ~2.53 ms retained verification.

Ten largest files total ~125.12 MB: ~**85.42 ms**. Same path count, ~34x different CPU. The large-file case still saved ~93.71% / 15.89x vs full snapshot audit.

## Changed-byte cost surface
Routing calibration over verified baseline bytes (cost-only; not organic semantic mutations):
- ~25% bytes, 14 paths: **97.10 ms**, ~92.93% less / 14.14x vs full
- ~50% bytes, 128 paths: **197.87 ms**, ~85.59% / 6.94x
- ~75% bytes, 1,168 paths: **326.25 ms**, ~76.24% / 4.21x
- ~100% nonzero bytes, 24,939 paths: **1177.66 ms**, still ~14.24% less / 1.17x than reconstructing ordering/tree from zero.

Thus routing needs changed-byte surface and dirty-node surface, not just changed-file count. Even a full content rehash can benefit from retained path/order/index structure while topology remains unchanged.

Truth: the percentage sweep is routing-cost calibration; exact semantic-mutation equality was separately established for 1/10/100 files. Path topology changes remain outside v0.1. CPU is not joules; no compute/energy-from-nothing claim.
