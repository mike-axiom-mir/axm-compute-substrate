# Flowing Compute Wave 133 — Rotation Bootstrap Recovery Receipt

Status: **EXPERIMENTAL / NON-CANON**. Existing lane: `chatgpt/lane-001-platform-extract`, PR #2. This receipt does not authorize merge, auto-merge, or CANON promotion.

## Why this wave exists

Wave 132 added predecessor-authorized response-signing-key rotation, but its rotation-metadata bootstrap had an existence-only boundary: once `response_rotation/` existed, bootstrap returned as if genesis metadata were complete. A real process death after creating that directory, or after only part of its genesis files were durable, could therefore strand an otherwise exact legitimate Wave-131 authority. The predecessor control is retained in the Wave-133 self-test: a directory-only Wave-132 bootstrap returns nonzero, while Wave 133 can recover the exact genesis and continue the same authorized rotation.

## Wave 133 change

Wave 133 adds a narrow recovery layer without changing Wave 131 or Wave 132. It creates an exact `bootstrap.json` intent bound to the already-validated Wave-131 manifest/readiness bytes, anchor credential identity, witness credential identity/root, genesis response public key, and deterministic sequence-zero rotation state. It writes deterministic genesis artifacts with **write-or-exact-match** semantics and publishes `bootstrap.ready.json` last.

Recovery is permitted only before rotation evolution. Missing deterministic genesis artifacts may be resumed; existing artifacts must byte-match the exact expected bytes. A mismatched intent is retained and rejected rather than rewritten. An unexpected pending rotation transaction before readiness is rejected. If the bootstrap-ready receipt disappears after signed rotation evolution exists, the implementation refuses to silently recreate genesis. Rolling the mutable rotation state back to sequence zero while signed lineage remains newer also fails closed.

Because Wave 131 intentionally rejects unknown anchor artifacts, the first Wave-133 candidate exposed an integration problem: the recovery path called the strict Wave-131 validator after `response_rotation/` already existed. The repaired Wave-133 adapter preserves Wave-131's exact credential, keypair, readiness, UID-boundary, ledger, and source/provenance checks while allowing **only the known `response_rotation/` directory name** as an extra anchor artifact; nothing inside that directory is trusted by the adapter and its contents are separately validated by Wave 133.

## Real kill/recovery coverage

The Wave-133 test sends real `SIGKILL` after each named bootstrap publication boundary:

- rotation directory creation;
- bootstrap intent publication;
- genesis response-public-key publication;
- authority lineage genesis publication;
- witness lineage genesis publication;
- sequence-zero state publication;
- bootstrap-ready publication.

Each exact restart completed the same authorized rotation to sequence 1, and the next exact retry was idempotent. The bootstrap intent and ready receipt remained stable after recovery and no pending rotation-transaction files remained.

Negative cases retained in the same suite:

- mismatched bootstrap intent fails closed without rewriting it;
- unexpected pre-ready rotation transaction fails closed;
- bootstrap-ready receipt loss after rotation evolution fails closed;
- mutable rotation-state rollback against newer signed lineage fails closed.

## Exact evidence

Green exact tested source: `1a6867e4ee1ddeb8010cf1115da9efe5ac246f5f`.

GitHub Actions run `35321911044`, job `105526072539` completed successfully on Ubuntu 24.04 / Python 3.12.14 / OpenSSL 3.0.13.

Results:

- unchanged Wave 131: **15/15 normal + 15/15 under `python -O`**;
- unchanged Wave 132: **14/14 normal + 14/14 under `python -O`**;
- Wave 133: **12/12 normal + 12/12 under `python -O`**.

Artifact `10537661871`, `wave133-rotation-bootstrap-recovery`, size 11,772 bytes, SHA-256 `5c352f73994f1137a2241d6757ed2e37bb30377e7ca6fd4f7f4bfbcf1b33f14b`. The artifact contains the six concise JSON reports plus exact tested-head/parent and source/workflow blob identities. Generated CI reports are not committed as repository ballast.

## Failed attempt retained

The first Wave-133 CI run is intentionally part of the evidence trail:

- source: `4766e10d67f8486974a2d4abd157c40d6f0debfb`;
- run: `35321422956`;
- job: `105524553347`;
- unchanged Wave 131 and Wave 132 regressions passed before the new Wave-133 step failed;
- exact failure: `RuntimeError:wave131-unexpected-anchor-artifact:response_rotation`.

That failure was in the new Wave-133 integration logic, not evidence that the predecessor was safe. The repair changed the Wave-133 validation adapter only; it did not weaken or rewrite Wave 131 or Wave 132. The successful rerun still contains the predecessor control proving the Wave-132 directory-only bootstrap remains stuck while Wave 133 recovers it.

## Truth boundary

This wave proves only the tested same-host deterministic rotation-bootstrap recovery around named post-publication `SIGKILL` points. It does **not** prove safety for a kill inside an atomic-write implementation, root/kernel compromise, an attacker already controlling the authority UID, user-namespace/container UID aliasing, copied genuine private keys in another namespace/host, whole-domain rollback, hardware-backed/non-exportable custody, provider independence, or physical finality.

The unchanged Wave-131 regression also continues to carry its fresh verifier boundary from PR #55: the user-namespace UID-alias attack was environment-blocked in CI, so that boundary is neither falsified nor proven safe.

No real AXM/monolith performance workload and no synthetic scaling workload were run in Wave 133 because this was a correctness/recovery gate. Therefore this receipt makes **no new speed, energy, retained-compute, incremental-compute, dormant-compute, throughput, or scaling claim**.

## Next gate

Move the genuine-clone fight across the kernel/host boundary. Copy the **current authentic authority identity, real response private key, bootstrap receipt, and rotation lineage** into a separate Linux network/user namespace and, when available, a second host. Let both authentic copies attempt different successor rotations against the same logical witness lineage. Test stale/current clone restart, reconnects, verifier rollback, mixed Wave-131/132/133 downgrade paths, and coordinated whole-domain rollback.

If two genuine copies can produce individually valid divergent successor chains, preserve that counterexample. Signatures prove identity; they do not by themselves prove uniqueness. Any next architecture would then need an independently retained uniqueness/rotation authority rather than silently declaring the signed clone problem solved.
