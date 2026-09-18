# Flowing Compute Wave 57 — One-Use Persistent Merkle Delta Handoff

Date: 2026-09-16  
Status: `EXPERIMENTAL FILE-IDENTITY PERSISTENCE EVIDENCE`

## Negative precursor
Wave56 wrote only changed Merkle nodes but rehashed the whole 2.1 MB base tree and reapplied its just-created overlay as mandatory creation-time verification. It wrote 98.8-99.97% fewer bytes but was CPU-worse than rewriting the full tree. That implementation is not promoted.

## Repair
Wave57 carries the already-validated base identity, target root, and exact changed-node values through a one-use handoff. Overlay reapplication becomes an audit path outside the measured creation transaction instead of duplicate mandatory work.

## Fsynced persistence (5 alternating trials)
### 1 changed file
- full 2.1 MB tree persist: **3.114 ms CPU**
- 684-byte node overlay: **2.093 ms**
- **32.79% less / 1.49x**
- **99.97% fewer bytes**

### 10 files
- full: **3.459 ms**
- 4,068-byte overlay: **2.746 ms**
- **20.61% less / 1.26x**
- **99.81% fewer bytes**

### 100 files
- full: **7.061 ms**
- 24,804-byte overlay: **7.129 ms**
- CPU tie/noise (~0.96% slower overlay), but **98.82% fewer bytes**.

Persistent Merkle deltas therefore have two objectives: CPU and write amplification. Local updates win both; broader dirty-node sets may keep the storage win after the CPU win disappears.

Truth: base identity is carried from previously validated state; later full audit remains available. One host/filesystem/runtime; CPU is not joules; no compute/energy-from-nothing claim.
