# Flowing Compute Wave 126 — separate monotonic anchor

Status: **experimental lane only / NON-CANON / unmerged**.

Wave 126 continues from Wave 125 and independent verifier PR #50. PR #50 demonstrated that Wave 125's high-water protection could be reopened by renaming the accepted `/tmp/axm-flowing-compute-wave125-host-v1-<uid>` namespace aside, creating a fresh empty namespace at the same pathname, releasing the live witness credential lease, and starting a genuine stale witness clone. The accepted newer witness store and its original sequence-2 pin remained intact; the stale clone nevertheless bootstrapped a fresh sequence-1 pin in the replacement namespace.

## Change

Wave 126 removes witness monotonicity from that mutable `/tmp` pathname.

A separate anchor OS process now owns:

- its own durable directory;
- its own credential and externally pinned exact credential fingerprint;
- a copy of the witness credential provisioned at anchor initialization;
- an append-only, fsync'd, HMAC-authenticated mirror of each accepted witness record;
- independent validation of the exact witness record chain before a suffix can advance the anchor;
- exact-prefix/idempotent reconciliation;
- fail-closed stale-witness handling when the anchor is newer;
- fail-closed fork handling when an already anchored position differs;
- a same-Linux-network-namespace kernel lease for concurrent clones of the exact anchor credential.

The witness does not silently create a replacement anchor. Startup requires the configured exact anchor fingerprint and a reachable anchor process.

Reusable implementation:

- `tools/AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ANCHORED.py`
- `tools/AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ANCHORED_SELFTEST.py`
- `.github/workflows/flowing-compute-wave126-anchor.yml`

## Exact-source result

CI-tested source: `b3713154cc1ca587b365ae3647578f791a750e48`

Run: `35296859034`  
Job: `105451094721`  
Conclusion: **success**

Artifact: `10528510743` (`flowing-compute-wave126-anchor-evidence`)  
Artifact SHA-256: `145969e6cb18e62794e6aa91025e7d73eec1536274ac40cca1e4fbae933fde6b`

Exact tested blobs:

- Wave 126 tool: `cf267f87aca1dd53e182f306697eb0e15c529769`
- Wave 126 self-test: `afbb5938b288a531998ef27fa192361bba5c430d`
- Wave 126 workflow: `edfa6fe8e56255bd37560da4a4ae130dd31ec055`

Regression and new-wave results:

- unchanged Wave 125: **11/11 PASS** normal Python;
- unchanged Wave 125: **11/11 PASS** under `python -O`;
- Wave 126: **12/12 PASS** normal Python;
- Wave 126: **12/12 PASS** under `python -O`.

## Positive and negative controls

The Wave 126 suite verifies that:

1. witness and anchor are separate live OS processes with distinct durable stores and an exact anchor identity pin;
2. a genuine HOLD prefix is independently mirrored into the anchor;
3. a genuine COMMIT reaches witness + anchor + local receipt and becomes authoritative;
4. replacing Wave 125's old `/tmp` host-pin namespace does **not** reopen a stale witness clone — the independent anchor remains at the newer sequence and startup fails with `anchor-ahead-of-witness-store`;
5. the current witness restarts against the same anchor after that namespace attack;
6. a wrong external anchor fingerprint fails closed;
7. an unavailable anchor cannot silently bootstrap or serve a witness;
8. a real `SIGKILL` after witness-ledger fsync but before anchor publication is recovered by exact suffix reconciliation, then exact local-receipt recovery returns authority;
9. a byte-identical live anchor clone is rejected in the same Linux network namespace;
10. a truncated/corrupt anchor ledger fails closed;
11. the whole-domain rollback counterexample remains visible: rolling back **both witness and anchor** to the same older genuine prefix can serve that older world again after the current processes release their leases;
12. restoring the untouched current witness + anchor restores the newer authoritative state.

## Preserved failure / truth boundary

Wave 126 does **not** establish physical, device, provider, or host-independent finality.

The new anchor is independent of Wave 125's mutable `/tmp` host-pin pathname, but it is still on the same Linux host/filesystem in this wave. Its exact fingerprint is an external configuration/pinning boundary. If the witness, anchor, and that external pin are all rolled back/replaced together, the older genuine world can still be served. The anchor's same-credential clone lease is scoped to one Linux network namespace, so a copied anchor in another network namespace or second host remains unproved.

The anchor stores a copy of the witness credential in order to validate the witness chain independently; compromise of either shared credential is outside this claim.

No real AXM/monolith performance workload and no synthetic scaling workload were run in Wave 126. Therefore there is **no new speed, energy, retained-compute, incremental-compute, or dormant-compute claim**.

## Next gate

Move the clone/uniqueness test across the current kernel namespace boundary:

- run an exact copied witness + anchor identity in a second Linux network namespace or second host where the abstract-socket leases cannot collide;
- require both competing witness clones to contact one independently pinned anchor and prove that only one exact chain extension can advance it;
- then attack a copied/rolled-back anchor itself in the second namespace/host;
- distinguish legitimate anchor migration/rotation from rollback without trusting only a mutable pathname;
- test mixed Wave 125/Wave 126 downgrade paths;
- retain the `SIGKILL` witness-ledger -> anchor publication recovery as a regression control.

Success there would still establish only the tested cross-namespace/host anchor boundary, not provider-independent or physical finality.
