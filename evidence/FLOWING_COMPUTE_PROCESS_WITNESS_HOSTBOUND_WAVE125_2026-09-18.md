# AXM Flowing Compute — Wave 125 host-bound process witness identity

Status: **GREEN inside the bounded same-host claim; experimental / unmerged / NON-CANON.**

Builder lane: `chatgpt/lane-001-platform-extract`  
Parent evidence head: `27ccee01297feaa9dac169a00d6af456979f606b`  
Exact CI-tested Wave 125 source: `d9b9621bd26f6bf981bfd0f8b51881aaf3f0c886`  
Independent trigger: verifier PR #49, evidence head `45f082097f415151879a9aadb33553118f4a80d3`, executable tested head `8a64415d9d2e93dc405e254fb2bc04be5841093e`.

## What failed in Wave 124

Verifier PR #49 copied a live valid Wave 124 witness store after one authenticated HOLD prefix. The copy kept the exact root, HMAC credential fingerprint and byte-identical ledger prefix, but its copied `serve.lock` was a different inode. Two unchanged Wave 124 servers could therefore be live concurrently. For the exact same authority/transition, the original accepted stable COMMIT while the clone accepted stable REJECT. Both terminal records occupied the same sequence and predecessor and both separate ledgers independently remained valid.

Wave 125 reproduces this prerequisite first; it is not erased from the test history.

## Wave 125 repair

Wave 125 keeps the Wave 124 per-store `flock`, then adds two independent same-host protections:

1. a Linux abstract UNIX-socket lease keyed by the exact witness credential fingerprint, outside the copyable witness directory, so two cooperating Wave 125 processes cannot serve one copied credential identity concurrently in the same Linux network namespace;
2. an external host-local high-water pin keyed by the credential fingerprint, containing the exact root hash plus the highest accepted ledger sequence and record SHA. A stale cloned store is rejected after the live process exits if its ledger is behind the retained host pin.

The server also opens the accepted witness directory and performs ledger access through the open directory handle. Before non-stop requests it verifies that the caller-visible path still names the same device/inode. Renaming/replacing the live witness path therefore fails closed instead of silently redirecting later reads/writes into a clone.

A lagging host pin may advance only when a fully verified witness ledger is an exact extension of the already pinned prefix. This preserves the real crash window where the ledger was fsynced and the process died before publishing the host pin.

## Positive and negative evidence

Exact CI run `35293032557`, job `105439762899`, conclusion **success**.

- unchanged Wave 124 regression: **13/13 normal + 13/13 under `python -O`**;
- Wave 125 adversarial suite: **11/11 normal + 11/11 under `python -O`**;
- PR #49 cloned-store fork is reproduced against unchanged Wave 124 before testing the repair;
- a live byte-identical clone is rejected by credential identity even though it has a different directory/lock inode;
- normal stable COMMIT advances the external high-water pin;
- live directory rename/swap makes the established server fail closed with path-identity mismatch, while the replacement clone is still unable to serve;
- after the original exits, a stale clone is rejected because the host pin is newer;
- the exact current store restarts and remains authoritative;
- an up-to-date byte-identical clone can take over only after the existing credential lease is released;
- real `SIGKILL` after ledger fsync but before host-pin publication recovers the exact valid ledger extension, advances the pin, leaves the local client at `HOLD_WITNESS_AHEAD`, and then allows exact local receipt recovery to authority;
- host-pin corruption fails closed and is not silently rewritten.

## Preserved failed run

The first exact-source Wave 125 run `35292893987` / job `105439352425` is intentionally retained. It reported **10/11** Wave 125 controls green. The sole red control already contained the expected `witness-credential-already-live-on-host` rejection, but the test helper killed that correctly failing child immediately after its error marker appeared, producing return code `-9` before the child could exit with code `2`.

Artifact `10526407948`, SHA-256 `080eadc9394f6bd92983f5b353df33911ff62feba2e2b85c68c051d80c55791c`, preserves that false-negative run. The Wave 125 implementation was not changed for the rerun. A small wrapper changed only the verifier wait to match the proven Wave 124 helper: after an expected error marker, allow up to one second for clean child exit before SIGKILL fallback.

## Exact-source receipt

Green artifact: `10527122724` (`wave125-report`)  
Green artifact SHA-256: `4388d40ce0d4354ce93d030421973f68fbf54c63548a800b126f5ba513ccb547`

Exact blobs in the green artifact source-identity record:

- `tools/AXM_FLOWING_COMPUTE_PROCESS_WITNESS_HOSTBOUND.py` — `9a07d4b61bf071d144cee10ac297d35de968f3f3`
- `tools/AXM_FLOWING_COMPUTE_PROCESS_WITNESS_HOSTBOUND_SELFTEST.py` — `c177cd6bb0858b13a5c82f2e079a232d7b6bb993`
- `tools/AXM_FLOWING_COMPUTE_PROCESS_WITNESS_HOSTBOUND_SELFTEST_FIXED.py` — `a30503ecfeb27962b4bdf7549fd08d4c770fc498`
- `.github/workflows/wave125-host-bound-process-witness.yml` — `518858e99beb74bfb6c4452fe98ec08b888ed371`
- predecessor Wave 124 tool — `d8ececaab8aedd3ca9543b36c5e90d9130d19905`
- predecessor Wave 124 self-test — `c2a916feebb3026a434cd0f25eb777efb0729bd4`
- Wave 123 base process witness — `2e87f9416d8ec0d9d04b46e842ac2d7a1a9e0f08`

Generated JSON reports remain in the CI artifact and are not committed as repository ballast.

## Counterexample kept alive

The suite deliberately rolls back **both the witness store and the external host pin together** to an older genuine empty prefix after a newer COMMIT had been authoritative. That older world can serve again. Wave 125 therefore does **not** establish physical finality, host-independent monotonicity, provider independence, or safety against rollback/replacement of the entire claimed trust domain.

The first host-pin creation is also a bootstrap boundary. Wave 125 does not retroactively reconcile a pre-existing Wave 124 fork, and a Wave 124/mixed-version server can bypass the new protocol. The abstract credential lease is scoped to one Linux network namespace. Another namespace/host with the copied credential is outside the result.

No real AXM/monolith performance workload and no synthetic scaling workload were run in this correctness wave. No speed, energy, retained-compute, incremental-compute or dormant-compute result is claimed.

## Next gate

Move the uniqueness/monotonicity boundary one layer outward before advancing process-boundary referee rotation:

- clone the exact witness into a separate Linux network namespace or second host where the abstract-socket lease no longer collides;
- independently retain the high-water pin outside the cloneable witness host and attack witness rollback while that pin stays newer;
- attack host-pin namespace rename/replacement, pin rollback/corruption, mixed-version downgrade, and hard kill after pin fsync but before reply;
- preserve the whole-domain rollback as a counterexample until an actually independent trust domain defeats it.

Only after copied credential identity cannot produce two divergent histories across the claimed host/device boundary should old-root-authorized witness/referee rotation be promoted further.

No merge, auto-merge or CANON promotion is authorized by this evidence.
