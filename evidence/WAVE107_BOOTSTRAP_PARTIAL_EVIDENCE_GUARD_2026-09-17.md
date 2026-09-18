# Wave 107 — fail-closed partial authority-evidence guard

Status: **experimental builder evidence; PASS on exact source; no merge / no CANON promotion**

## Why this wave happened

Independent verifier PR #31 found that Wave 106 could confuse **incomplete retained authority history** with **no retained authority history**. `_retained_authority_evidence()` caught any `resolve()` failure and silently continued. After a legitimate accepted epoch, deleting only the Wave-106 lineage store plus the signer-use body referenced by the retained authority link left the sealed authority link and signed checkpoint in place, but the scanner returned an empty history. A saved genesis runtime plus a fresh legitimate certificate-witness domain could then reopen bootstrap.

Verifier identity preserved exactly:

- verifier PR: `#31`
- verifier head: `06beba92c188879d65ebd970bbaaa529ca095660`
- evidence blob: `d0e6c230bc11f04811748d36b3400ca597c9ffc6`
- reproducer blob: `c3342d4561ba10ea8deaeb878ffead870edde252`
- Wave 106 builder head: `eb8ac4d23a3399af82885afc435dae6de0aa28b6`
- Wave 106 exact tested source: `652f3da1acd88e02f085cf1ace92c6bfb412e065`

## Smallest repair tested

Wave 107 adds a tri-state bootstrap history guard in front of the unchanged Wave-106 contract:

- `NONE`: no authority-facing retained rows exist;
- `VALID`: retained authority links fully resolve through their signed checkpoint + signer-use dependencies;
- `INCOMPLETE_OR_CORRUPT`: retained authority evidence exists, but any required part is missing, malformed, mismatched, or unresolvable.

The guard examines the retained `L` authority-link, `C` signed-checkpoint, and `U` signer-use stores. It no longer treats a failed authority-link resolution as absence. Bootstrap adoption raises instead of selecting a new root, and authority returns `HOLD_BOOTSTRAP_AUTHORITY_EVIDENCE_INCOMPLETE`.

This is additive. Wave 106 remains untouched.

## Positive and negative results

Exact-source CI run `35192037553`, job `105106546783`, tested commit `9e4edc8c484d32f9210804dc25ca61fadf7aa835`:

- unchanged Wave 106 regression: **36/36**
- Wave 107 normal Python: **22/22**
- Wave 107 `python -O`: **22/22**
- report artifact: `10484875188`
- artifact ZIP SHA-256: `e58316f9a19bd7def7a6edc86b199a2b18d71e0063b973150f90cb1a5eb394d7`
- report JSON SHA-256: `17acb3fad0d9b3df4297d2b86d402fc07372d41b2bc2a98dac59f998b3f6d652`

The self-test first reproduces verifier PR #31 against unchanged Wave 106:

`AUTHORITATIVE_GENESIS_MODELED`

The same partial-loss world under Wave 107 becomes:

`INCOMPLETE_OR_CORRUPT` → `HOLD_BOOTSTRAP_AUTHORITY_EVIDENCE_INCOMPLETE`

The new negative cases also delete one signed checkpoint body, delete the authority-link body while checkpoint/use evidence remains, tamper authority-link key/body identity, and corrupt an authority-store shape. All fail closed. Losing only the Wave-106 lineage store while complete authority history remains still uses the older specific Wave-106 history HOLD. Binding-lineage loss remains non-authoritative. Normal forward progress to epoch 2 remains authoritative.

## Failure / counterexample deliberately preserved

Wave 107 still does **not** make local history physically monotonic. If the entire retained authority state is rolled back or substituted with a genuine pre-adoption image, every local bootstrap/history fact disappears together and a fresh genesis can still look valid in this one-process model. The passing suite keeps that counterexample visible.

The existing safety-over-availability choice also remains: a prepared-but-uncommitted authority body can conservatively close bootstrap. Crash atomicity between the lower authority commit and Wave-106 closure persistence is still unsolved. Symmetric modeled credentials, fixed certificate-witness root limitations, and one-process failure domains are unchanged.

## Scope / truth boundary

This wave is a correctness/finality repair. It ran no fresh AXM/monolith workload and makes no new performance, energy, network, retained-compute, incremental-compute, dormant-compute, OS-process, device, or provider-independence claim.

## Next gate

Wave 108 should now perform the deferred real process-persistence experiment: place the repaired bootstrap + authority + certificate contract into at least three separate OS processes with separate durable stores and credentials, then attack kill/restart, stale/cloned disk restoration, saved-genesis restart, crash exactly between lower commit and closure persistence, one process offline plus one stale process, two-process rollback, partitions/reconnects, lineage/certificate-store loss, and simultaneous old/new process views.

Success there would establish only **process-level persistence evidence**. It would not yet prove physically monotonic storage or provider/device independence.
