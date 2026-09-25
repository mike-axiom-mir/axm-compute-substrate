# Durable Filesystem History-Spine Host v0.2 — evidence receipt

Date: 2026-09-20  
Status: **EXPERIMENTAL / NON-CANON / PR #64**

## Why this pass happened

The v0.1 filesystem host writes a complete sealed Neutral Compute runtime object for every generation.

A measured 256-generation tiny-state probe showed that this preserved correctness but repeated all prior generation/receipt history inside every later runtime snapshot.

Exact v0.1 probe on GitHub Linux:

- sequence 0 runtime object: **994 bytes**
- sequence 128 latest runtime object: **154,525 bytes**
- sequence 128 cumulative runtime objects: **10,024,999 bytes**
- sequence 256 latest runtime object: **308,381 bytes**
- sequence 256 cumulative runtime objects: **39,727,911 bytes**
- cumulative/latest ratio at 256: **128.827×**

This is a claim about the tested v0.1 representation, not a universal application-storage law.

## v0.2 physical format

The new parallel host is implemented in `src/fs-spine-host.js`.

It stores:

- one immutable META registry/runtime descriptor;
- one immutable generation object per unique generation;
- one immutable receipt object per commit receipt;
- existing content-addressed artifact objects;
- one append-only, hash-chained `HISTORY.log`;
- one small mutable `CURRENT.json` authority pointer.

A history record may be durable without being current. CURRENT remains the only visibility/authority selector.

## Green tested source

First fully green implementation + exact logical-identity comparison head:

`a02308b14d6f3a411f506758d22a5592871ff399`

GitHub Actions:

- workflow run: `35489218310`
- job: `106021109068`
- conclusion: **SUCCESS**

The run passed:

- ordinary Neutral Compute unit tests including v0.1 + v0.2 host controls;
- v0.1 SIGKILL crash matrix;
- v0.2 **7/7 SIGKILL crash matrix**;
- Neutral Compute conformance: **8/8 behavioral cases + 2/2 identity primitives**;
- v0.1 256-generation storage-growth probe;
- v0.1 versus v0.2 256-generation storage comparison with exact logical runtime identity equality.

## v0.2 SIGKILL matrix

A separate worker process reached each named durable boundary and was then killed externally with real `SIGKILL`.

| Kill point | Expected current | Observed current |
| --- | ---: | ---: |
| after updated artifact objects | G0 | G0 |
| after generation object | G0 | G0 |
| after receipt object | G0 | G0 |
| after history append + fsync | G0 | G0 |
| after CURRENT temp fsync | G0 | G0 |
| after CURRENT atomic rename | G1 | G1 |
| after CURRENT directory fsync | G1 | G1 |

Result: **7/7 PASS**.

The `after_history_append` case additionally proves that a complete durable generation/history record may remain visible as **unpointed evidence** while recovery still selects G0.

It is not auto-promoted by append order, sequence number, filename or recency.

## Invalid-tail behavior

Unit tests additionally prove:

- a malformed uncommitted HISTORY suffix is reported as `invalid_tail`;
- an older CURRENT whose record is inside the valid prefix still recovers;
- the invalid suffix is not silently deleted;
- new commits HOLD while the invalid tail remains;
- a missing generation object that CURRENT depends on fails recovery;
- a tampered history record that CURRENT depends on fails recovery.

This is bounded prefix-tolerant recovery, not automatic repair.

## Exact storage comparison

Same test workload:

- one tiny contract;
- 256 sequential mutations;
- same Neutral Compute plans/routes;
- same logical generation and receipt semantics.

### Whole-runtime-snapshot v0.1

- total host file bytes: **39,565,698**
- final reconstructed logical runtime: **307,096 bytes**
- logical runtime SHA-256:  
  `445a5ee5d02a33e666af708521534f0fe2c324f1bc0465a987d65b8674818328`

### History-spine v0.2

- total host file bytes: **473,196**
- final reconstructed logical runtime: **307,096 bytes**
- logical runtime SHA-256:  
  `445a5ee5d02a33e666af708521534f0fe2c324f1bc0465a987d65b8674818328`
- HISTORY.log: **180,313 bytes**
- artifact objects: **257 / 3,231 bytes**
- generation objects: **257 / 174,588 bytes**
- receipt objects: **256 / 114,324 bytes**
- invalid history tail: **none**

Comparison:

- file bytes avoided: **39,092,502**
- **98.804% fewer logical file bytes**
- v0.1/v0.2 size ratio: **83.614×**

The comparison script refuses completion unless the two reconstructed logical runtimes have the exact same canonical SHA-256.

These are logical file-byte counts, not filesystem block allocation, SSD write amplification, energy use or universal performance measurements.

## Failed attempts preserved

### First v0.2 CI

Head: `8cf58686754eb613c462a892f41c40bdf50989b8`  
Run: `35489105922`

Result before the v0.2 tests could execute fully: **20/21 tests pass / 1 test parse failure**.

Cause: the new test file contained an incorrectly escaped regular-expression slash. This was a test-code syntax bug, not a host result.

The assertion was repaired; no storage behavior was relaxed.

### Second v0.2 CI

Head: `d66f3f5bcfd4d83b6862f4d5337a0ac56813e874`  
Run: `35489129524`

Result: **26/27 PASS**.

The host correctly failed closed when the generation object named by CURRENT was removed, but recovery surfaced only:

`CURRENT points beyond valid history prefix`

The negative test required the actual dependency failure to remain diagnosable.

Repair `af02b689e51213d8d252b7fa2ff3dab57afb0dc0` changed recovery diagnostics so CURRENT-dependent invalid prefixes report the retained underlying reason (for example, missing generation object).

The refusal boundary did not become weaker.

### Green run before exact-runtime strengthening

Head: `af02b689e51213d8d252b7fa2ff3dab57afb0dc0`  
Run: `35489155998`

All correctness/crash/storage tests passed and first measured the **98.804%** storage reduction.

Before preserving that as final evidence, the storage comparison was strengthened: equal reconstructed runtime byte length was replaced by **exact canonical runtime SHA-256 equality**.

The final green run named above (`35489218310`) passed that stronger check.

## Donor/research provenance

Before the history-spine implementation, the following AXM-owned Global State modules were inspected:

- `mike-axiom-mir/axm-global-state/src/durable-receipt-history.mjs`
- `src/compacted-receipt-history.mjs`
- `src/replay-checkpoint.mjs`

Reusable architectural lesson: history/checkpoint evidence should remain separable from current state, and gaps/conflicts must fail visibly.

No Global State authority schema or mutation implementation is copied.

The concrete base/history/head direction also descends from the earlier Flowing Compute experimental lane in PR #2. That large implementation remains research evidence and is not imported.

## Remaining weakness

v0.2 solves the measured **persistent byte amplification**.

It still reconstructs the in-memory runtime by scanning/verifying the valid history prefix. Therefore recovery work grows with history length.

The next justified optimization is not another storage format rewrite. It is to measure v0.2 recovery/commit scaling and, if material, add a sparse trusted/checkpoint index without weakening full-history audit or tail visibility.

## Truth boundary

This result establishes:

- tested process-crash old-or-new visibility;
- append-only history + current-pointer authority on GitHub Linux;
- exact logical runtime equivalence to v0.1 in the 256-generation fixture;
- dramatically lower logical file bytes for that fixture.

It does **not** establish:

- literal power-loss/controller-cache finality;
- arbitrary filesystem failure safety;
- hostile root/kernel resistance;
- distributed/multi-host consensus;
- constant-time recovery;
- safe automatic garbage collection/repair;
- universal storage ratios;
- CPU/energy improvement;
- semantic quality of the stored artifacts;
- merge or CANON authority.
