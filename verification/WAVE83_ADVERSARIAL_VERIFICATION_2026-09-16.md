# Independent Adversarial Verification — Wave 83

Date: 2026-09-16  
Builder head examined: `4374c259fdd7ccbafe9309b1b5ba1476e253aced`  
Status: `VERIFIER-ONLY / DRAFT / NOT CANON / NO AUTO-MERGE`

## Scope

This verifier challenged the newest Wave 83 four-root retention gate + single-host CAS result rather than extending the builder. The known ABA counterexample is already preserved by Wave 83 and is not counted as a new finding here.

Source reviewed:

- `tools/AXM_FLOWING_COMPUTE_RETENTION_AUTH_CAS.py`
- `tools/AXM_FLOWING_COMPUTE_RETENTION_GC_MODEL.py`
- `evidence/FLOWING_COMPUTE_RETENTION_AUTH_CAS_WAVE83_2026-09-16.md`

The narrow same-predecessor CAS claim is structurally credible: under one shared lock file, the current pointer is reread while holding `flock`; the first replacement changes the retention hash, so the second writer expecting the old hash conflicts. Wave 83 also correctly bounds this to one host/POSIX and preserves the ABA failure.

## New primary counterexample — pointer may commit a corrupted staged candidate

`cas_commit()` validates the **caller-supplied in-memory candidate**, then asks only:

```python
if not store.has(candidate['retention_sha256']):
    raise ValueError(...)
```

It does not reload the staged candidate body by that content hash and verify that the object currently stored at `<hash>.json` is still the same candidate before moving the current pointer.

Counterexample:

1. Build and stage a valid KEEP candidate.
2. Replace the staged candidate file with `{"corrupted": true}` while leaving the filename/hash path unchanged.
3. Call `cas_commit()` with the original valid in-memory candidate.
4. `validate_authorized_retention()` passes on the in-memory candidate; `store.has(hash)` is still true.
5. CAS returns `COMMITTED` and the pointer now names the candidate hash.
6. Reloading the body at that hash yields the corrupted object and fails retention validation.

I replayed the exact published control flow locally and preserved an executable in-repo reproducer that imports the actual Wave 83 module: `verification/wave83_staging_integrity_boundary_repro.py`.

This is a referential-integrity / staging TOCTOU boundary, not a SHA-256 break. The pointer can become current while its required retention object is no longer recoverable from the content-addressed store under the claimed hash.

## New secondary counterexample — arbitrary rollback-root injection

Both `make_authorized_retention()` and `validate_authorized_retention()` derive evidence requirements only from:

```python
removed = roots(pred) - set(new_roots)
```

They do not reject `new_roots - roots(pred)` and do not require existence/reachability evidence for newly introduced rollback roots.

Therefore a candidate can retain the two real predecessor roots **plus an arbitrary 64-character fake checkpoint**, with empty drop/evaluation maps. No root was removed, so the four-root drop gate is never invoked. The candidate validates, can be staged, and can win CAS.

This does not mean adding future checkpoints must be forbidden. It means checkpoint introduction currently has no proof contract in Wave 83: a retention generation can grant current-state membership to a checkpoint identity that has not been shown to exist, recover, or own any receipt reachability mapping.

## Durability boundary worth keeping visible

`ObjectStore.put()` fsyncs the newly created object file but does not fsync the object-store directory after creating the directory entry. Wave 83's pointer replacement does fsync the pointer directory. On filesystems where crash durability of a newly created filename requires a directory fsync, the evidence object and pointer do not yet have a demonstrated power-loss ordering guarantee. This is a portability/durability boundary, not a reproduced data-loss claim on this host.

## What survived

- The four-root mechanical gate does reject missing/HOLD evidence for an actual root **removal** under the current supplied predecessor/evidence objects.
- The same-predecessor `flock` + pointer-hash CAS shape supports the bounded one-winner result.
- Candidate staging alone does not grant pointer authority.
- Wave 83 accurately labels root PASS rows as test fixtures, not canonical judgments or actor authentication.
- The known ABA failure is honestly preserved by the builder.

## Benchmark boundary

The reported ~250.643 microseconds is already correctly scoped by Wave 83 as process CPU time for synthetic local commits, not end-to-end fsync latency, energy, or a monolith workload. I found no reason to widen that claim.

## Next adversarial gate

Wave 84's epoch work should also close the two new boundaries:

1. before pointer movement, reload the staged candidate by hash and validate the exact stored bytes/object identity used for recovery; ideally bind the pointer move to an immutable staged object that cannot be swapped between validation and commit;
2. distinguish **retaining existing roots** from **introducing new checkpoint roots**. New roots need explicit checkpoint-existence/recovery/reachability evidence, not an accidental pass because no old root was removed;
3. make crash durability ordering explicit for object-store creation + pointer publication;
4. then attack epoch rollback, stale writers across A→B→A, candidate replacement between verify/publish, and concurrent introduction/removal of checkpoint roots.

No builder code was rewritten. No merge/canon promotion is requested by this verifier lane.
