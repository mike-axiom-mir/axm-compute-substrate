# AXM Flowing Compute Wave 136 — Rotation Transaction Recovery Receipt

Status: **EXPERIMENTAL / NON-CANON / unmerged**

This receipt records the tested continuation from Wave 135. It does not rewrite prior evidence and does not authorize merge or CANON promotion.

## Source / provenance identity

- Wave 135 evidence head inherited by this wave: `e486f7fd1383115f020f2c6d047ee2c63d91c6d7`
- Wave 135 exact green implementation source: `03cfcd0ceab3884796c28ed5d25fa8cc0f3b2c71`
- Wave 136 exact tested source: `49d0bd8aa24a91036a85e1cd265985dfd97585b7`
- Tested parent: `f445d6d269566a3196d4ebbae94551a61e05fc21`
- Wave 135 tool blob: `88a67b9fec7b519bb68a3d530ba3e7a051c7478d`
- Wave 136 tool blob: `47fe034330c808b48ee39f64f70b07778b533372`
- Wave 136 self-test blob: `589934e3b476ee7f9e661558255e3a43df7d3c49`
- Wave 136 workflow blob: `c0c0a495bbdaa37f4652641c269fe8763176c7a6`

## What Wave 136 changes

Wave 135 made post-pending publication of the current private key recoverable but intentionally left the earlier pending-transaction creation, authority/witness lineage append, and later cleanup boundaries open. Wave 136 adds a bounded same-host recovery path for those three areas.

The pending private key is now written first through deterministic recoverable atomic staging. A **complete** authority-owned candidate is adopted exactly after restart. A partial/invalid private-key or certificate stage may be abandoned only while `pending.json` does not exist and signed lineage/current trust pointers still prove the predecessor generation. That is explicitly **not** a claim that an incomplete cryptographic candidate can be reconstructed byte-for-byte; it is a pre-commit candidate that never became durable transaction identity.

`pending.json` is published last and freezes the pending transaction identity. Authority and witness lineage append use recoverable whole-file replacement of the exact predecessor bytes plus the exact signed certificate rather than in-place append. After the final trust state proves the rotation current, pending files are removed one-by-one with directory fsync and cleanup can resume idempotently after a kill. Cleanup only accepts residue that exactly matches the already-committed rotation; conflicting residue fails closed and remains visible.

Reusable implementation and adversarial verification are kept in:

- `tools/AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ROTATION_TRANSACTION_RECOVERY.py`
- `tools/AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ROTATION_TRANSACTION_RECOVERY_SELFTEST.py`
- `.github/workflows/wave136-recoverable-rotation-transaction.yml`

Generated JSON reports remain CI-artifact ballast rather than repository source.

## Positive and negative evidence

GitHub Actions run `35336523082`, job `105572516825`, completed successfully on the exact tested source above.

Artifact:

- id: `10542563138`
- name: `wave136-recoverable-rotation-transaction`
- SHA-256 digest: `135828a564ffb5aa0fcadbe7eee9022505443e504fb1ab1b9035ec3e21ebce55`

Regression and new-wave results:

- unchanged Wave 135: **5/5 normal + 5/5 under `python -O`**
- Wave 136: **11/11 normal + 11/11 under `python -O`**

The Wave 136 suite includes:

- real `SIGKILL` during partial pending-private publication repeated **1, 10, and 100 times**; residue remained bounded to one authority-owned stage and the uncommitted partial candidate could be safely abandoned before a new candidate completed;
- real `SIGKILL` after a complete 1,704-byte pending private key was staged; restart preserved that exact candidate and it became the committed successor key;
- partial `pending.json` commit recovery to the same transaction;
- partial authority-lineage whole-file replacement recovery;
- partial witness-lineage whole-file replacement recovery;
- wrong-byte lineage stage rejection with the hostile residue retained (`wave135-stage-temp-mismatch`);
- real `SIGKILL` after each of four post-commit cleanup boundaries, followed by idempotent cleanup recovery;
- corrupt post-commit pending-private residue rejection, retained for inspection;
- two clean sequential rotations reaching one valid sequence-2 predecessor-signed lineage.

There was **no failed Wave 136 CI implementation run before the green exact-source run**. The negative cases above are deliberate counterexamples and fail-closed tests, not hidden failures.

## Truth boundary

This is a same-host Linux/process/filesystem recovery result. It does **not** prove:

- same-candidate recovery from an incomplete pre-commit private-key generation; that candidate is allowed to be abandoned only before transaction identity is committed;
- validation-to-service inode/path substitution safety;
- user-namespace UID alias safety;
- uniqueness of a genuinely copied current private key/authority on another namespace or host;
- resistance to root/kernel compromise or an attacker already running as the authority UID;
- whole-domain rollback resistance;
- hardware-backed non-exportable custody, provider independence, or physical finality.

No real AXM/monolith performance workload and no synthetic scaling workload were run in Wave 136 because this was a crash-consistency/correctness gate. Therefore Wave 136 makes **no new speed, energy, retained/incremental/dormant-compute, throughput, or scaling claim**.

## Next gate

First close the remaining hostile-local recovery edges around this transaction machinery: wrong owner, stale generation, unrelated/extra residue, and validation-to-service path/inode substitution at pending and lineage boundaries. Keep every hostile artifact visible on rejection.

Then resume the larger architectural test: copy the **genuinely current authority identity, rotation lineage, and real current private key** into another Linux namespace and preferably a second host, and let both authentic copies try to authorize different successors. If both can advance individually valid divergent chains, keep that counterexample. Signatures would then prove key possession but not uniqueness, and the next design must introduce an independently retained uniqueness/rotation authority rather than another local lock.
