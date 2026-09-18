# Flowing Compute Wave 132 — predecessor-authorized response-key rotation receipt

Status: **experimental / NON-CANON / no automatic merge**.

## Source identity

- Tested source commit: `60865699c2c2fe1f53860bcb5d0196860ee98086`
- Predecessor Wave-131 evidence head: `72b6cf04e8cbd1a8fc356bb47dca103fa1e39ffe`
- Wave-132 tool blob: `6839f537cccb31b913e3206980f8a2a99b81c3b9`
- Wave-132 self-test blob: `c9039853a0cfd70adb7070ea63d6ac1659369cb9`
- Wave-132 workflow blob: `f79076586bf333254923f3edf31bc362ccc576ef`
- GitHub Actions run: `35319161234`
- Job: `105517495685`
- Artifact: `10536726099`
- Artifact SHA-256: `d1f3ac73ecbff46736c7dc003dc6d3eb405faa50f16a5898beb3c4a0a65d2045`

## Result

Unchanged Wave 131 remained green at **15/15 normal + 15/15 under `python -O`**.

Wave 132 passed **14/14 normal + 14/14 under `python -O`**. The positive matrix killed the authority process with real `SIGKILL` after each named durable rotation boundary: pending transaction, authority lineage, witness lineage, successor public key, authority current key, witness current public key, witness binding, and final rotation state. Exact retry of the same rotation id resumed to one predecessor-authorized certificate and one successor identity; a second retry was idempotent. Two consecutive rotations also formed one exact predecessor-signed chain, and the rotated authority still served an authenticated endpoint verified through the newly authorized public key.

Negative controls stayed fail-closed: a different rotation id could not reinterpret a pending transaction; a tampered predecessor certificate did not advance; rolling the witness verifier back to the genesis key while the lineage stayed newer was detected; and modifying the witness-side lineage was detected. Pending private duplicates were removed only after both authority/witness current pointers and state agreed.

## What changed

Wave 131 had a safe, recoverable initialization path but no legitimate authenticated response-key rotation path. Directly replacing the response key or witness verifier would either break its readiness receipt or become an unaudited provisioning rewrite. Wave 132 adds a durable rotation transaction in which the old response private key signs the exact successor public key, rotation id, sequence, previous certificate hash, anchor identity, witness identity, and witness root before current trust pointers move. The authority and witness retain byte-exact copies of the signed certificate. Rotation also takes the existing same-host anchor-credential lifetime lease, preventing a live old signer from racing the writer within the tested Linux namespace.

## Truth boundary / retained counterexamples

This establishes only the tested same-host, dedicated-UID, predecessor-signed response-key rotation and named post-publication crash recovery. The Wave-131 initial verifier remains the bootstrap/rollback root. A crash during first creation of Wave-132 rotation metadata is not yet claimed crash-atomic. Root/kernel compromise, authority-UID compromise, copied genuine private keys in another network namespace or host, whole-domain rollback, hardware-backed non-exportable key custody, provider independence, and physical finality remain open.

No real AXM/monolith performance workload and no synthetic scaling workload were run in this wave. Therefore there is **no new speed, energy, retained/incremental/dormant-compute, throughput, or scaling claim**.

## Next gate

First close the Wave-132 rotation-bootstrap crash window: make genesis-public/lineage/state creation itself exactly recoverable or fail-closed without ambiguous partial metadata, including hard kills inside the first rotation setup. Then move the genuine-clone attack across the kernel boundary: copy a cryptographically genuine current authority identity and private key into a separate Linux network namespace / second host and test whether two authentic copies can produce divergent signed successor lineages. If they can, retain that counterexample and move uniqueness/rotation authority into an independently retained domain rather than treating signatures as uniqueness.
