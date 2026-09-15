# Flowing Compute Wave 11 — Dormant State Across Process Death

Date: 2026-09-15  
Status: `EXPERIMENTAL SINGLE-HOST RUNTIME EVIDENCE`

## Question

Does the measured retained-state advantage survive when the producing process is gone, or is it only an in-RAM cache effect?

Wave 11 uses the real 39,055,991-byte AXM `EXECUTION_FABRIC.json` source and derives its summary state once, serializes that state, starts fresh Python processes, and compares routes that must return the exact same canonical summary output.

## Source

- source bytes: **39,055,991**
- source SHA-256: `2f8f5f306b6790b3e8a4d58b2c00fd60eb5c18a3c4f6b40424000e26aa87ef6e`
- useful derived summary payload: **677 bytes**
- compact generic dormant envelope during benchmark: about **1.4 KB**

The state is a derived summary, not a lossless compression of the 39 MB source.

## Four fresh-process routes

Each measurement launches a new Python process.

1. `cold_parse` — read and JSON-parse the 39 MB source, then derive `summary`.
2. `trusted_content_id` — load the tiny dormant envelope and rely on an externally established immutable source-generation SHA-256.
3. `stat_token` — load the tiny state and check source byte-size + mtime generation token.
4. `rehash` — load the tiny state **and reread/hash every byte of the 39 MB source** before allowing resume.

Mode 2 is appropriate only when a parent package/cartridge/runtime has already established immutable content identity. Mode 3 is a freshness mechanism, not cryptographic identity. Mode 4 is the intentionally expensive integrity control.

## Independent stripped-probe runs

### Run 1 — median operation CPU

- cold parse: **170.70 ms**
- trusted state: **0.163 ms** — **99.90% less CPU**
- stat state: **0.177 ms** — **99.90% less CPU**
- full rehash + state: **26.77 ms** — **84.32% less CPU / 6.38× yield**

Fresh-process total wall-time improvement versus cold parse:

- trusted: **40.68%**
- stat: **40.49%**
- rehash: **35.63%**

### Run 2 — median operation CPU

- cold parse: **166.98 ms**
- trusted state: **0.165 ms** — **99.90% less CPU**
- stat state: **0.181 ms** — **99.89% less CPU**
- full rehash + state: **25.11 ms** — **84.96% less CPU / 6.65×**

Fresh-process total wall-time improvement versus cold parse:

- trusted: **37.07%**
- stat: **39.20%**
- rehash: **34.28%**

The first cold run visibly warmed the OS page cache; the second run was stable. Page cache was deliberately not flushed because the research target here is repeated compute/reconstruction cost, not storage-device cold-read benchmarking.

## Generic dormant-state contract control

Wave 11 then repeated the benchmark using the reusable `AXM_FLOWING_COMPUTE_DORMANT_STATE.py` envelope validator rather than the stripped benchmark format.

Seven alternating-order fresh-process trials:

- cold parse: **188.71 ms CPU**
- trusted content identity: **0.131 ms** — **99.93% less CPU / 1445× operation yield**
- stat generation check: **0.152 ms** — **99.92% less CPU / 1242×**
- full 39 MB source rehash: **25.20 ms** — **86.64% less CPU / 7.49×**

One-time compile/setup cost for this run: **193.0 ms CPU**.

Using operation CPU accounting, each retained route paid back its one-time compile cost by approximately the **second restart**. Exact canonical output hash equivalence passed for all modes and trials.

## Reusable primitive

Wave 11 adds:

- `tools/AXM_FLOWING_COMPUTE_DORMANT_STATE.py`
- `tools/AXM_FLOWING_COMPUTE_DORMANT_STATE_SELFTEST.py`
- `schemas/dormant-state-envelope.v0.1.schema.json`
- `schemas/dormant-state-resume-receipt.v0.1.schema.json`

The generic tool supports three explicit source-validation modes and records which one was used in the resume receipt.

Self-test: **7 checks PASS**, including payload tamper rejection, wrong trusted generation rejection, source rehash mismatch rejection, and stat-token change rejection.

## What this establishes

For this one real AXM derived-state contract on this host:

> useful computational structure can be serialized, the process can terminate, and a later fresh process can resume from the small derived state while retaining a large compute-yield advantage over rebuilding the same derived answer from the full JSON source.

Even when every source byte is reread and cryptographically hashed on resume, avoiding full JSON parse/reconstruction remained materially cheaper in these measurements.

## Truth boundary

- The 677-byte state does not contain the full 39 MB Execution Fabric.
- Not every workload has a compact sufficient derived state.
- Trusted content-ID mode cannot be used honestly unless source generation identity was established elsewhere.
- `stat_token` can miss adversarial same-size/same-mtime modification and is not a substitute for content identity.
- OS page cache was not cleared.
- Fresh-process total wall time contains interpreter/process startup noise.
- Process CPU time is not joules.
- This is one host and one source snapshot.
- No compute or energy is created from nothing.

## Next gate

Test a dormant state that is **partially invalidated after restart**: load the prior serialized generation, change a small source region, update only the affected retained-state closure, and compare that path against fresh global reconstruction. This combines Wave 5 incremental propagation with Wave 11 process-independent persistence.
