# Durable Filesystem Host v0.1 — evidence receipt

Date: 2026-09-20  
Status: **EXPERIMENTAL / NON-CANON / PR #64**

## Tested source

First fully green durable-host source head:

`55bcf8de82215daa1fb4550310aa2080254d85a5`

Green GitHub Actions:

- run: `35484307060`
- job: `106007700664`
- platform: Linux / GitHub Actions
- ordinary unit tests: **18/18 PASS**
- Neutral Compute conformance: **8/8 behavioral cases PASS + 2/2 hash primitives**
- standalone durable SIGKILL matrix: **5/5 PASS**

The later standalone-matrix harness refactor and evidence files preserve the same storage implementation and crash boundaries; final head is reverified separately.

## Crash matrix

The matrix launches a separate worker process, pauses at an exact storage boundary, then an external shell process sends real `SIGKILL` to that worker.

| Kill point | Expected recovery | Observed recovery |
| --- | ---: | ---: |
| after updated artifact objects are durable | G0 | G0 |
| after new runtime object is durable | G0 | G0 |
| after temporary CURRENT pointer fsync | G0 | G0 |
| after atomic CURRENT rename | G1 | G1 |
| after host-directory fsync | G1 | G1 |

All cases passed.

The pre-pointer runtime-object case also verified that the new candidate runtime object remains physically present as an orphan while recovery still selects G0. The pre-rename pointer case preserves its pending pointer file as visible non-authoritative evidence.

## Additional fail-closed controls

Unit tests verify:

- a clean durable commit survives fresh-process recovery;
- wrong updated artifact bytes are rejected before `CURRENT` moves;
- a tampered `CURRENT` pointer is rejected rather than selecting the newest-looking object;
- a missing artifact referenced by the current generation makes recovery fail closed.

## Failed attempts retained

### First red run — crash hook accidentally active for clean writes

Early durable-host CI repeatedly reported the entire `test/fs-host.test.js` process as SIGKILLed.

The important root cause was eventually isolated in the adapter:

```text
writeImmutable(... crashAt=null, crashLabel=null)
crashIf(label=null, requested=null)
```

The crash helper treated `null === null` as a requested crash and killed the supposedly clean worker.

This was a real test-hook implementation bug, not a storage atomicity result.

Repair `55bcf8de82215daa1fb4550310aa2080254d85a5` changed crash injection to be explicitly opt-in:

```text
no requested crash OR no named boundary -> return
```

The actual storage ordering was not relaxed.

### Harness isolation attempts

Before the null/null bug was found, the tests also tried isolating Node test-runner environment variables and moving SIGKILL control outside the worker. Those attempts remain in history.

The final shape is intentionally cleaner:

- normal storage invariants run under `node --test`;
- hard-kill recovery runs as the standalone `npm run crash-matrix` CI step.

This prevents intentional child death from being confused with a unit-test process failure.

## Storage authority boundary

The v0.1 host uses:

```text
immutable content-addressed artifact objects
immutable content-addressed sealed runtime snapshots
                     +
            one mutable CURRENT pointer
```

New objects may exist before commit. They have no authority until the atomic `CURRENT` rename names their runtime generation.

Recovery never scans for "latest" files and never promotes orphan objects.

## Truth boundary

This proves the tested process-crash behavior on the GitHub Linux filesystem.

It does **not** prove:

- physical power-loss behavior;
- drive/controller cache durability;
- arbitrary filesystem/journal failure;
- hostile root/kernel resistance;
- distributed/multi-host atomicity;
- orphan garbage collection;
- compact long-history storage;
- performance, RAM, write-amplification or energy improvement.

The host currently stores one sealed runtime snapshot per generation for simplicity. The older base/history/head research may optimize that later only when measured need justifies the extra machinery.
