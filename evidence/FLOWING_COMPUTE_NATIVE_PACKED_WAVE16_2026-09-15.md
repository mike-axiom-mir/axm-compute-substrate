# Flowing Compute Wave 16 — Native Packed Transition

Date: 2026-09-15  
Status: `EXPERIMENTAL SINGLE-HOST RUNTIME EVIDENCE`

## Question

Can the dormant Execution Graph state operate **directly in its packed representation** instead of unpacking into the full JSON-shaped edge/local/signature dictionaries before every transition?

## Contract

Wave 16 introduces a new native packed state body. It stores the same graph structure and digest evidence but keeps the large hash surfaces as raw 32-byte digest blocks. Transition code validates and edits those blocks directly. Full JSON-shaped state reconstruction is used only after the measured transition for equivalence evidence.

The native packed semantic identity is deterministic and separate from the old JSON serialization identity. Cold equivalence is still required: after conversion, the resulting JSON semantic state must equal a full cold rebuild exactly.

## Storage

- canonical JSON dormant state: **662,225 bytes**
- native packed dormant state: **261,598 bytes**
- reduction: **60.50%**

An early Wave-16 prototype redundantly stored both edge indexes and derivable component lookup data and was ~281 KB. That redundancy was removed before final measurement; the final body is ~261.6 KB.

## Robust fresh-process benchmark

11 alternating fresh-process trials per format/case. Every route rehashes the full changed source and materializes the next dormant artifact. Exact cold-rebuild semantic state equality passed.

### 58 / 127 affected components

- JSON persist: **20.101 ms CPU**
- AXDS v0.1 validate/unpack/update/repack: **19.527 ms**
- native packed direct: **9.175 ms**
- native saving vs JSON: **54.36%**
- useful-yield multiplier: **2.191x**

### 127 / 127 affected components

- JSON persist: **21.685 ms CPU**
- AXDS v0.1 validate/unpack/update/repack: **21.854 ms**
- native packed direct: **12.053 ms**
- native saving vs JSON: **44.42%**
- useful-yield multiplier: **1.799x**

Fresh-process wall time remains dominated by interpreter/process startup and does not show the same magnitude; no wall-time claim is promoted.

## Double-validation repair

The first native implementation re-parsed and semantically revalidated the newly created packed artifact just to read back the identity it had already minted. Removing that redundant second validation materially improved the measured path. The serializer now returns the semantic identity alongside the artifact.

## Phase decomposition

### 58 / 127

- load + packed semantic validation: **2.849 ms** (32.8%)
- full source SHA-256: **1.259 ms** (14.5%)
- apply delta/local hashes/closure: **0.495 ms** (5.7%)
- dependency propagation: **0.962 ms** (11.1%)
- serialize next packed generation: **2.943 ms** (33.9%)

### 127 / 127

- load + packed semantic validation: **2.865 ms** (25.2%)
- full source SHA-256: **1.246 ms** (11.0%)
- apply delta/local hashes/closure: **2.475 ms** (21.8%)
- dependency propagation: **1.327 ms** (11.7%)
- serialize next packed generation: **2.972 ms** (26.1%)

The dominant remaining costs are packed load/validation and rewriting the next full packed generation; propagation itself is no longer the main cost.

## Truth boundary

- one host and one state contract;
- CPU process time is not joules;
- OS page cache is not flushed;
- native packed identity is format-specific; JSON equivalence is checked externally;
- topology-changing deltas still HOLD/rebuild;
- the transition still decompresses structural header metadata into Python objects; it is not memory-mapped/native-machine execution;
- no claim of universal performance or compute/energy from nothing.

## Next gate

Avoid rewriting unchanged packed blocks every generation. Test a content-addressed **base + overlay/patch** dormant body, measure wake cost as overlays accumulate, and compact only when the overlay chain costs more than materializing a fresh base.
