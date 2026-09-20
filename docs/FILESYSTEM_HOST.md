# Durable Filesystem Host v0.1

Status: **experimental / local-host adapter / not CANON**

`src/fs-host.js` gives the neutral in-memory runtime one concrete Linux/POSIX-style durable host.

It does **not** change the Neutral Compute behavioral contract. It implements one physical storage strategy behind it.

## Layout

```text
HOST/
  CURRENT.json
  objects/
    artifact/
      <artifact-sha256>.blob
    runtime/
      <runtime-object-sha256>.blob
```

Artifact and runtime objects are immutable and content-addressed.

`CURRENT.json` is the only mutable authority pointer.

## Commit path

For a staged generation:

1. clone/import the current neutral runtime;
2. logically commit the stage in that isolated candidate;
3. verify every updated artifact body against the staged artifact reference;
4. write any new artifact objects;
5. fsync each object file;
6. atomically rename each completed immutable object into its content-addressed name;
7. fsync the object directory;
8. serialize the complete sealed candidate runtime as canonical JSON;
9. persist/fsync its content-addressed runtime object;
10. write/fsync a new temporary `CURRENT` pointer;
11. atomically rename the pointer over `CURRENT.json`;
12. fsync the host directory.

Only step 11 changes which generation recovery considers current.

Pre-pointer objects may remain after a crash. They are preserved orphan evidence/cache, not authority.

## Recovery

Recovery:

1. reads only `CURRENT.json`;
2. verifies its pointer digest;
3. reads the exact content-addressed runtime object named by the pointer;
4. verifies its raw bytes and sealed Neutral Compute runtime;
5. requires the runtime current-generation identity to equal the pointer;
6. verifies every artifact referenced by the current generation exists and matches its content hash.

It never selects "the newest looking" orphan runtime or artifact.

## Crash test boundary

The v0.1 suite launches a separate Node process and uses real `SIGKILL` at these boundaries:

- after updated artifacts are durable;
- after the new runtime object is durable;
- after temporary pointer fsync;
- after atomic pointer rename;
- after parent-directory fsync.

Expected recovery:

- every kill **before pointer rename** -> old complete generation;
- every kill **after pointer rename** -> new complete generation.

This is a process-crash/filesystem visibility test on GitHub's Linux filesystem. It is **not** a physical power-loss, disk-controller, filesystem-journal or hardware-failure proof.

## Why the whole runtime is stored in v0.1

This first adapter writes one sealed runtime snapshot per committed generation. That is intentionally simple and makes recovery easy to audit.

It is not the final compact storage design. The research lane already contains base/history/head and content-addressed overlay experiments. Those should be introduced only when the durable host has a measured need; correctness comes first.

## Provenance

### UC atomic writer pattern

Inspected donor:

- repository: `mike-axiom-mir/axm-universal-creation`
- file: `src/axm_uc/atomic.py`
- observed before this adapter was built on 2026-09-20

Reusable pattern:

`temporary file -> flush -> fsync(file) -> os.replace(target)`

The neutral JavaScript host independently implements that pattern and additionally fsyncs the containing directory after publication.

No UC domain/state code is copied.

### Flowing Compute research

The crash-boundary architecture also distills the earlier experimental PR #2 work around:

- immutable objects before pointer movement;
- pointer movement as visibility boundary;
- preserving unpointed objects;
- restart validation rather than assuming a completed write;
- old-or-new, never half-current goals.

The huge research implementation is not imported.

## Truth boundary

This adapter does not prove:

- distributed or multi-host atomicity;
- physical finality;
- immunity to root/kernel/filesystem corruption;
- automatic garbage collection of orphan objects;
- efficient long-history storage;
- that referenced artifact semantics are correct;
- any speed, RAM, storage-amplification or energy improvement.

It proves only the behavior actually exercised by its durable-host tests.
