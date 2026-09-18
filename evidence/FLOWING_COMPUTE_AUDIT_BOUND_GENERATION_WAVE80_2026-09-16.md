# Flowing Compute Wave 80 — Audit Receipt IDs Bound Into the Atomic Generation Pointer

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST COMMIT/RECOVERY EVIDENCE`

## Question

Wave 79 made an `audited_reuse` freshness reset require a real audit-work receipt. The remaining gap was commit identity: could a generation persist audit age `0` without also persisting the exact receipt identity that justified that reset?

Wave 80 closes that gap at the atomic pointer layer.

## Real evidence reused

The positive case uses the exact real Wave 79 capability-index audit receipt:

- contract: `axm.execution-fabric.capability-index/v0.1`
- immutable capability artifact: **11,255,808 bytes**
- artifact SHA-256: `e676fafb2f825d946c10480ccd2184ab69daf9464ae77cf5703dfe59562644da`
- proof SHA-256: `0e90715689e43290371acc3d1608b58d179cd4c6e7bfc288b9bd41b718f353a2`
- predecessor freshness state SHA-256: `58959e3053fe81c2686894296e542859a3a6d86a5591dfddde19110786bc7a01`
- Wave 79 audit receipt SHA-256: `fb65ba5ad5cc0f4c33a851957ccc42a4142c64a3d0815abb1a4f0886dbf4ecf2`

Wave 79 had read and hashed all **11,255,808** artifact bytes before issuing that receipt. Wave 80 deliberately does **not** reread those bytes; this wave tests whether already-validated audit evidence survives commit/recovery with exact identity.

## New contract

`tools/AXM_FLOWING_COMPUTE_AUDIT_BOUND_GENERATION.py` adds `axm.flowing-compute-audit-bound-generation/v0.1`.

A committed pointer now binds, in one hashed/atomic body:

- generation sequence and generation identity;
- exact predecessor pointer SHA-256;
- complete per-contract verification-freshness states;
- per-contract verification modes;
- for every `audited_reuse` contract, a compact receipt reference containing the exact `receipt_sha256`, receipt generation sequence, and exact predecessor freshness-state SHA-256.

Pointer construction accepts the Wave 79 transition result, then **replays the freshness transition** from the predecessor and revalidates each full audit receipt before committing only its compact identity reference.

Carried reuse commits no fresh audit receipt.

## Positive case

Controlled generation G0 contained the real capability-index freshness identity above.

G1 used `audited_reuse`:

- resulting audit age: **0**
- predecessor pointer SHA-256: `97ba881dd417916e2e02e23b9f026bee1e1093896e7a809e09fb019ea2b0e3ad`
- committed Wave 80 pointer SHA-256: `1b93525216e04d20e4b5556f8ada44aeefcbb8168b33c9d01c723dfcc6117c58`
- committed audit receipt SHA-256: `fb65ba5ad5cc0f4c33a851957ccc42a4142c64a3d0815abb1a4f0886dbf4ecf2`

The full predecessor + receipt chain validated.

G2 then used `carried_immutable_proof`:

- resulting audit age: **1**
- predecessor pointer is exactly G1;
- committed fresh audit receipt count: **0**
- G2 pointer SHA-256: `99876d8d36348b3403cb162152adbd75d2d82c4dbe645c6b1151c1b14cbe694d`

This demonstrates that audit evidence is committed only on the generation where the strong audit actually happened; later carried generations preserve freshness history without fabricating a new receipt.

## Negative / recovery controls

All **8/8** controls passed:

1. audited age-zero state with no receipt reference -> rejected;
2. G1 receipt reference copied unchanged into G2 -> rejected as stale;
3. receipt reference attached to a carried contract -> rejected;
4. receipt predecessor-state SHA changed while recomputing the outer pointer hash -> chain validation rejected it;
5. receipt SHA changed to another syntactically valid SHA while recomputing the outer pointer hash -> chain validation rejected it because the exact receipt body was unavailable;
6. skipped/rollback predecessor supplied for G2 -> rejected;
7. G2 prepared but pointer move omitted -> persisted state remained complete G1;
8. atomic pointer move -> complete G2 appeared, with no mixed generation/freshness/receipt state.

## Cost

Over 2,000 local iterations, median CPU for `make audited Wave 80 pointer + validate predecessor/receipt/freshness chain` was **143.9 microseconds**.

That number excludes artifact-byte rereading. It measures commit/evidence bookkeeping only. The real byte-audit cost remains the separate Wave 79 observation.

## Truth boundary

- The Wave 79 receipt is real local audit evidence reused here; Wave 80 does not pretend to have reread the artifact.
- Receipt SHA-256 protects integrity, not actor identity or remote attestation.
- Controlled G0/G1/G2 generation SHA values in this test are deterministic test commit identities, not canonical monolith generation hashes.
- Pointer/receipt/freshness consistency is proven only within these software contracts and this host/runtime.
- CPU time is not joules.
- No audit cadence or corruption probability is inferred.
- No canonical branch merge or automatic canon promotion occurred.

## Next gate

Make recovery **receipt-store aware** across multiple audited generations: maintain a content-addressed append-only audit receipt store and prove that a restored pointer can resolve every committed receipt ID, while garbage collection may remove only receipts that are provably unreachable from retained rollback checkpoints.

Negative controls should include a missing receipt body after restart, wrong body under a correct-looking filename/key, deleting a receipt still reachable from a rollback checkpoint, and retaining an unreferenced receipt without granting it authority.
