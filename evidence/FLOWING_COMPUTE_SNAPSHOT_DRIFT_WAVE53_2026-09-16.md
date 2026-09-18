# Flowing Compute Wave 53 — Snapshot Receipt Drift + Retained File Identity

Date: 2026-09-16  
Status: `EXPERIMENTAL REAL-MONOLITH FILE-IDENTITY EVIDENCE`

The bundled `SNAPSHOT_FILE_RECEIPT.json` does **not** identify the final v0.4.30 ZIP.

Old receipt: 18,055 files / 472,349,811 bytes. Actual extracted ZIP: **24,965 files / 557,862,377 bytes**.

Comparison:
- 18,031 old paths still byte-identical;
- **24 old paths changed**;
- **6,910 new files** added;
- no old paths disappeared.

The stale receipt remains historical evidence and was not relabeled as current.

A fresh experimental receipt minted from the actual ZIP required ~**1.775 s CPU** to hash all 24,965 files. It proves file identity only.

Controlled working-copy mutations to 1 / 10 / 100 existing small JSON files were then verified two ways: full ~558 MB rehash, or retained prior file identities + hashing only the known changed paths. Exact target snapshot root/file-count/byte-count equality was required.

Fresh-process medians (3 trials):
- 1 file: **1495.95 ms -> 43.47 ms** retained (**97.09% less / 34.41x**)
- 10 files: **1432.23 -> 41.69 ms** (**97.09% / 34.36x**)
- 100 files: **1361.67 -> 42.84 ms** (**96.85% / 31.79x**)

The retained ~42 ms is dominated by loading/scanning the 24,965-entry identity table, motivating Wave 54.

Truth: known changed-path input is part of this v0.1 retained contract; file identity does not prove semantic correctness; controlled mutations are not canonical monolith edits; CPU is not joules; no compute/energy-from-nothing claim.
