# Flowing Compute Wave 43 — Real Monolith End-to-End Durable State Transaction

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST REAL-MONOLITH EVIDENCE`

## Question

Do the newer dormant/head primitives still save compute when used together on the real AXM `EXECUTION_GRAPH.json`, including semantic proof creation, persistent writes, and an atomic current-pointer move?

## Real workloads

Source lineage: uploaded `AXM_Connected_Monolith_v0.4.30-WALMI-NATIVE-WIRING.zip` / preserved Wave-16 execution graph.

Two controlled semantic source generations were reused:

- `a058_m013`: 13 mutated source edges, 58 / 127 affected SCC components; route `incremental`.
- `a127_m082`: 82 mutated source edges, 127 / 127 affected SCC components; route `global`.

The preserved older `.native.axds` target artifacts use an earlier packed-metadata revision. Raw packed semantic hashes therefore differ from the current packed serializer. The stable equivalence contract is the reconstructed logical graph state hash; both current fast outputs exactly match cold rebuild logical state.

## Crash boundary

For both real mutations:

1. immutable overlay/proof/manifest/head artifacts were made durable;
2. crash injected before pointer replacement -> restart selected sequence 0 / old base;
3. atomic pointer replaced -> restart selected sequence 1 / new head.

Persisted transaction bytes:

- medium case: ~10.8 KB;
- global case: ~25.1 KB.

## First full durable implementation

9 alternating-order trials/case. Includes source rehash, packed transition, overlay creation, full overlay proof, head creation, durable writes/fsync and atomic pointer commit.

### 58 / 127
- cold rebuild + full packed snapshot: 47.46 ms CPU;
- flowing durable transaction: 32.98 ms;
- CPU saved: 30.52%;
- bytes: 261,948 -> 10,783 (95.88% fewer).

### 127 / 127
- cold: 48.94 ms CPU;
- flowing: 36.36 ms;
- CPU saved: 25.72%;
- bytes: 261,942 -> 25,129 (90.41% fewer).

## Fresh-process wake

9 fresh-process trials/case after committed transaction.

### 58 / 127
- cold graph rebuild: 43.86 ms CPU;
- lazy head wake: 5.03 ms (88.54% less);
- full logical-state materialization from head: 17.93 ms (59.12% less).

### 127 / 127
- cold: 43.87 ms;
- lazy head: 5.11 ms (88.36% less);
- full materialization: 17.96 ms (59.05% less).

Full materialization exactly matched the cold logical state hash.

## Truth boundary

- CPU process time is not joules;
- one host/runtime/filesystem;
- mutations are controlled real-graph semantic generations, not arbitrary topology changes;
- pointer crash test is software/process failure injection, not universal storage-hardware durability proof;
- packed-format revisions can have different packed semantic metadata while reconstructing identical logical state;
- no compute/energy-from-nothing claim.

## Next gate

Remove duplicate re-parse/re-proof work between transition -> overlay -> proof -> head without weakening exact difference/equivalence evidence.
