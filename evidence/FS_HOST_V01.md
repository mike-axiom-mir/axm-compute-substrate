# Neutral Compute Filesystem Host v0.1 — process-crash durability receipt

Date: 2026-09-20  
Status: **EXPERIMENTAL / NON-CANON / PR #64**

## Purpose

Add the first durable host adapter around the neutral runtime.

The neutral core intentionally defines only a logical generation commit. This adapter supplies a Linux/Node filesystem implementation with:

- immutable content-addressed artifact objects;
- immutable runtime snapshots;
- fsynced temporary CURRENT pointer;
- atomic rename of CURRENT;
- parent-directory fsync;
- fresh-process recovery;
- fail-closed pointer/runtime/artifact verification;
- stale-caller rejection against the recovered durable CURRENT generation.

## Exact tested source

Tested head before this evidence note:

`0258690da0b572d8a2f402f5517a9d40ffed57b0`

GitHub Actions:

- workflow: `neutral-core`
- run: `35485492214`
- job: `106010970660`
- conclusion: **SUCCESS**

Results:

- `npm test`: **20/20 PASS**
- `npm run crash-matrix`: PASS
- `npm run conformance`: **8/8 behavioral vectors PASS**
- canonical JSON identity primitive: PASS
- raw-byte identity primitive: PASS

## Real process-kill crash matrix

The crash harness starts a real child process, waits until the child has reached the requested durable boundary, then kills it externally with **SIGKILL**. The harness requires exit status **137**.

Observed recovery:

| crash boundary | recovered sequence | result |
| --- | ---: | --- |
| after updated artifact objects are durable | 0 | old generation |
| after candidate runtime object is durable | 0 | old generation |
| after CURRENT temp file fsync, before rename | 0 | old generation |
| after CURRENT atomic rename | 1 | new generation |
| after CURRENT directory fsync | 1 | new generation |

No tested boundary exposed a mixed generation.

The runtime-object-before-pointer case also verifies that an orphan candidate runtime object remains visible on disk but **does not promote itself**.

The temp-pointer-before-rename case preserves the abandoned pending pointer file as evidence while recovery still follows the old CURRENT pointer.

## Additional negative controls

The suite also verifies:

- wrong updated artifact bytes fail before CURRENT moves;
- tampered CURRENT pointer fails closed rather than scanning for/promoting the newest runtime object;
- missing current artifact fails recovery;
- stale caller state cannot steer the host after another durable commit.

## Storage/authority order

The tested commit order is:

```text
updated artifact objects
        ↓ fsync + directory fsync
candidate runtime object
        ↓ fsync + directory fsync
CURRENT temp pointer
        ↓ fsync
atomic rename -> CURRENT.json
        ↓
parent directory fsync
```

Only `CURRENT.json` selects the current runtime/generation. Immutable objects that exist without a selected CURRENT pointer are evidence/candidates, not authority.

## Truth boundary

This is **process-crash / SIGKILL evidence on GitHub's Linux runner**, plus use of normal fsync+rename durability primitives.

It is **not a literal power-loss test**. CI did not cut machine power, remove a block device, simulate controller write-cache loss, or verify a specific filesystem's guarantees under sudden hardware failure.

Therefore the result establishes:

- old-or-new visibility across the tested process-death boundaries;
- not physical power-cut finality.

A later power-loss/VM-block-device test can strengthen that boundary without rewriting this receipt.
