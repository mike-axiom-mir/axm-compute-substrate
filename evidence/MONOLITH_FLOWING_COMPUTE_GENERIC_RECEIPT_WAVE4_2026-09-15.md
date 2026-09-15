# Flowing Compute Generic Receipt — Wave 4

Status: `EXPERIMENTAL RUNTIME EVIDENCE`

## Goal

Replace workload-specific timing notes with one reusable receipt contract that can describe cold/rebuild execution and retained-state execution without assuming retained state must win.

The receipt names the source generation, requires equivalent output, separates setup from service cost, records retained-state size, declares freshness policy, and preserves raw trial timings.

## Contract implemented

Monolith copy instrumentation:

- `AXM_FLOWING_COMPUTE_RECEIPT.py`
- `AXM_FLOWING_COMPUTE_RECEIPT_SELFTEST.py`

Repository schemas:

- `flowing-compute-receipt.v0.1.schema.json`
- `retained-state-envelope.v0.1.schema.json`

The self-test deliberately allows positive, neutral, or negative results. A measurement tool is not allowed to assume its hypothesis is true.

## Real workload A — FrameState relay mesh

- units: **18 frames**
- trials: **3**
- exact ordered frame-digest equivalence: **PASS**
- cold median CPU: **702.38 ms**
- retained-state median CPU including setup: **562.32 ms**
- this short run: **19.94% less CPU / 1.249× yield**
- logical retained state after service: **102,936 bytes**

This 3-trial result is higher than the earlier, stronger multi-run evidence around 14–16%; do **not** replace the established range with this noisier ~20% point. It primarily demonstrates that the generic receipt reproduces the same direction with exact-output proof.

The OBJ has 1,216 source polygon face lines; FrameState triangulates them into 2,384 render faces.

Setup break-even is intentionally withheld because FrameState lazily parses mesh state during the first service call, so the current adapter cannot truthfully claim the setup boundary is complete.

## Real workload B — Execution Fabric status

- units: **4 status requests**
- trials: **3**
- exact canonical answer equivalence: **PASS**
- cold median CPU: **3.487 s**
- compact retained-state median CPU including setup: **0.899 s**
- CPU reduction: **74.22%**
- useful-yield multiplier: **3.879×**
- retained status payload: **848 bytes**
- estimated setup break-even: **request 2**

This independently reproduces the earlier Execution Fabric result through the generic contract rather than workload-specific accounting.

## Content-addressed retained-state envelope

The 848-byte status state was wrapped in an envelope bound to source-set SHA-256:

- source-set SHA-256: `68ee52d4e7fbe1bb8a1f7f8302157014db603d63716bfeda23f9a9848ea8713c`
- state payload bytes: **848**
- full envelope bytes: **1327**
- exact live status equivalence: **PASS**
- stale-source mismatch rejection contract: **PASS**
- payload-integrity rejection contract: **PASS**

The generic self-test also mutates a source file and confirms that an envelope tied to the previous source generation is rejected, then tampers with the payload and confirms integrity rejection.

## Important identity/freshness distinction

Strong SHA-256 identity is evidence of which source generation produced a state. Hashing a 39 MB source on every request would itself waste compute. Therefore the contract separates:

1. **strong source identity** — content hash for a named generation;
2. **freshness mechanism** — how a live system learns that generation changed;
3. **request service** — which should not blindly rehash/reparse the entire source when an immutable generation or trustworthy invalidation event is already known.

Production AXM should prefer immutable/content-addressed generations where possible, and explicit generation/invalidation events for mutable state.

## Truth boundary

- these remain single-host measurements;
- CPU time is not direct energy measurement;
- the receipt framework does not prove generalized compute savings;
- retained state can lose, and the contract records negative results;
- source identity does not make state semantically complete by itself;
- stale-state handling is part of correctness, not optional optimization;
- no claim of compute or energy from nothing.

## Next gate

Instrument a third kind of AXM workload whose state changes incrementally rather than remaining static. The important question becomes whether a retained-state body can update only the affected dependency closure while preserving equivalent outputs and honest invalidation receipts.
