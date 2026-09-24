# Flowing Compute Wave 18 — Identity Routing: Flat SHA, Lazy Overlays, and Merkle Locality

Date: 2026-09-15  
Status: `EXPERIMENTAL SINGLE-HOST RUNTIME + SYNTHETIC SCALING EVIDENCE`

## Question

Wave 17 showed that native overlays make generation writes/history much cheaper, but long overlay chains wake more slowly because current wake replays patches and then proves the final state with a flat semantic hash over the whole effective body.

Wave 18 asks whether that final proof can become more local without losing deterministic identity.

## Negative result 1 — naive lazy overlay wake

A lazy overlay view was tested that avoided eagerly copying/replaying every changed digest block into new arrays. Instead it built newest-value override maps and resolved effective blocks through the immutable base during final semantic hashing.

It was **slower than eager replay at every measured chain depth**. Representative operation CPU:

- depth 1: eager ~3.63 ms, lazy ~5.56 ms;
- depth 6: eager ~4.37 ms, lazy ~6.41 ms;
- depth 24: eager ~4.97 ms, lazy ~6.47 ms;
- depth 64: eager ~6.35 ms, lazy ~7.53 ms.

Root cause: the flat semantic proof still touches the entire effective body, and Python dictionary lookups for each block cost more than the eager block copies they replaced.

This design is **not promoted**.

## Merkle identity experiment

A grouped Merkle-style identity tree was built over the native packed state's digest leaves plus semantic header identity. The tree lets changed leaf groups and their ancestor path be rehashed while retaining unchanged subtree identities.

For the current ~261 KB native body, a 64-way tree needs only about 121 internal hashes (~3.9 KB), but the original real-transition implementation still lost to the existing flat semantic SHA in every transition or tied near the most-local cases.

Fanout tuning (8/16/32/64/128/256) did not make Merkle generally superior.

## Final fair real-transition control — byte-native sidecar

The first tree representation stored internal digests as hex strings, so each update converted the sidecar back into bytes. A final fair control retained a byte-native sidecar and benchmarked fanouts 16/32/64 over the six real G0→G6 transitions.

With fanout 16:

- G0→G1, 58 affected components: Merkle **12.2% slower** than flat SHA;
- G1→G2, 77 affected: **26.2% slower**;
- G2→G3, 68 affected: **16.1% slower**;
- G3→G4, 46 affected: **0.5% slower** (practical tie);
- G4→G5, 42 affected / one source-edge mutation: Merkle **3.4% faster**;
- G5→G6, 42 affected / reversible one-edge mutation: Merkle **4.9% faster**.

The fanout-16 sidecar is ~16 KB. Fanout 32 reduces it to ~7.8 KB but the two local wins shrink to ~2.9–3.8%.

So Merkle can win on the current body, but only by tens of microseconds on the most-local real changes. That is not enough end-to-end value to replace flat identity for the current runtime.

**Current decision: keep flat semantic SHA as the default identity contract for this ~261 KB body. Merkle remains experimental / optional.**

## Synthetic scaling — clearly not production evidence

Two synthetic studies were run to understand when the economics may change.

### Fixed-local mutation while state grows

With roughly the same ~85 changed leaves while duplicating the digest-state body:

- ~240 KB: incremental Merkle was ~16% slower than flat hashing;
- ~479 KB: ~34% faster;
- ~959 KB: ~66% faster;
- ~1.9 MB: ~82% faster;
- ~3.8 MB: ~90% faster;
- ~7.7 MB: ~95% faster;
- ~15.3 MB: ~97% faster.

This suggests a size crossover for **fixed-locality** changes on this host/implementation, but does not prove a universal threshold.

### State size × locality surface

The more important synthetic result is that raw changed percentage is not enough; the number of touched Merkle groups dominates.

Examples:

- current-size ~240 KB, ~1% changed **clustered into 3/118 groups**: Merkle ~35% faster;
- same ~1% changed but distributed across **75/118 groups**: Merkle ~334% slower;
- ~3.8 MB, ~1% clustered into 20/1873 groups: Merkle ~83% faster;
- same ~1% distributed across 1198/1873 groups: Merkle ~401% slower;
- broad 10–100% distributed invalidation is dramatically worse than flat hashing at every synthetic size tested.

Therefore identity choice is a **state-size × locality / touched-group surface**, not simply "large state = Merkle".

## Interpretation

Wave 18 repeats the same pattern seen elsewhere in Flowing Compute:

- no one representation is universally best;
- locality determines whether retained structure pays;
- an optimization can lose when its bookkeeping surface approaches the whole state;
- evidence should select the identity strategy rather than hard-coding one fashionable data structure.

For the current real Execution Graph dormant body, flat SHA remains the simpler and generally faster default. Merkle becomes interesting when state is larger and mutations remain highly localized.

## Truth boundary

- real benchmarks are one host / one state contract;
- synthetic scaling duplicates digest blocks and is **not** an actual larger AXM body;
- synthetic changed blocks are identity-workload probes, not valid source-generation semantics;
- CPU time is not joules;
- OS/cache effects remain possible;
- no universal Merkle crossover size is claimed;
- the two small real Merkle wins are not promoted into a new default runtime policy.

## Next gate

Test a **proof-carrying / validated overlay handoff**: an overlay generation whose target semantic identity was proven when the patch was created can carry that evidence across process death. Measure whether wake can validate the immutable base + overlay artifact/hash chain and accept the previously proven target generation without re-hashing the entire effective state every wake. Periodic compaction/full revalidation remains a separate correctness checkpoint.
