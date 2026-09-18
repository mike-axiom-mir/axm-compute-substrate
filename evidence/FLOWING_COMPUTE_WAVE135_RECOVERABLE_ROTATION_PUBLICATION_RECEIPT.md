# Flowing Compute Wave 135 — Recoverable Rotation Publication Receipt

Date: 2026-09-18
Status: EXPERIMENTAL / NON-CANON / builder lane only / no automatic merge

## Continuity and provenance

Wave 135 continues directly from Wave 134 evidence head `0f326221584e45723e8a9855f4d8fad5635711ac` and its exact green implementation source `20abcb846a48709dba4ba345380a1782f3fa83c8`. It does not rewrite Wave 132, Wave 133, or Wave 134 evidence.

The concrete predecessor counterexample is preserved from independent verifier PR #59, `Verifier: Wave 134 rotation retains historical private-key temp copies`.

Verifier exact successful testing identity:

- challenged Wave 134 evidence head: `0f326221584e45723e8a9855f4d8fad5635711ac`
- verifier tested head: `12e96da5486c4bf5372feb2cc7bcac75478655e4`
- workflow run: `35328632211`
- job: `105547531871`
- artifact: `10539743946`
- artifact SHA-256: `36b87d111c3e060370b58dab4ba6e355c8ba23d0550d14be09ee8ff04dc3663c`

The verifier demonstrated a real Wave-134 boundary failure: the full Wave-132 rotation path still used the older random temporary-file publication for the live `response_private.pem`. A real SIGKILL after a complete private key had been written and fsynced but before `os.replace` could leave a complete authority-owned mode-0600 historical private-key temp. Repeating that cut created additional complete copies. Three cuts retained three complete copies of the same 1704-byte successor RSA private key, and later clean rotations could advance to sequence 2 while those historical secret copies remained. No worker read of the authority directory, key forgery, or stale-authority acceptance was required. That remains a real predecessor counterexample.

## Wave 135 exact source

Exact tested implementation source:

`03cfcd0ceab3884796c28ed5d25fa8cc0f3b2c71`

Commit message: `Wave 135: recover current-key rotation publication`

New reusable source identities:

- `tools/AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ROTATION_PUBLICATION_RECOVERY.py`
  - blob `88a67b9fec7b519bb68a3d530ba3e7a051c7478d`
- `tools/AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ROTATION_PUBLICATION_RECOVERY_SELFTEST.py`
  - blob `2f5f0be94f09851de395bddf6c3b6ff5f523d40b`
- `.github/workflows/wave135-recoverable-rotation-publication.yml`
  - blob `3e5465bd08924df40f2ad32944d2e6b1e8c9555e`

Wave 135 deliberately does not rewrite the predecessor implementation. It wraps the post-pending current-key publication boundary with deterministic, content-bound staging and strict recovery rules while reusing the existing authorized rotation protocol.

## What changed

For the already-durable Wave-132 pending transaction, Wave 135 now routes selected current publication targets through exact-intent recovery:

- live authority response private key;
- live authority response public key;
- witness verifier/public key;
- witness binding;
- final rotation state;
- generated public-generation file through the Wave-134 exact writer.

A new stage name is deterministically bound to target name, mode, length, and SHA-256 of the intended bytes. Repeated crashes therefore reuse one exact staging identity instead of creating one new historical private-key temp per attempt.

Legacy random `target.tmp-*` files are adopted or deduplicated only when they are regular files owned by the exact authority UID, have the exact required mode, and contain the complete intended bytes already proven by the durable pending transaction. New deterministic stage files are accepted only at the expected content-bound path and only when their bytes are an exact prefix of the intended content. Wrong bytes, foreign ownership, wrong mode, unrelated stages, or ambiguous residue fail closed and remain visible rather than being guessed away.

## Exact CI evidence

Wave 135 workflow run: `35331690980`

- job: `105557242695`
- exact head: `03cfcd0ceab3884796c28ed5d25fa8cc0f3b2c71`
- artifact: `10541800334`
- artifact name: `wave135-recoverable-rotation-publication`
- artifact size: 5905 bytes
- artifact SHA-256: `17aab78aa34287b540f2ab0751dbe0c490762b6c7f07627dc9f8ae955d559f76`
- runner: Ubuntu 24.04.5 / Linux 6.17.0-1022-azure
- Python: 3.12.14
- OpenSSL: 3.0.13
- worker UID: 1001
- authority UID: 23001

Unchanged Wave 134 regression:

- 12/12 normal
- 12/12 under `python -O`

Wave 135 focused suite:

- 5/5 normal
- 5/5 under `python -O`

## Positive and negative cases retained

1. **PR #59 historical-secret amplification reproduced, then repaired.** Three predecessor random private-key temps were deliberately produced by three real SIGKILL cuts. All three contained the same intended successor-key bytes. Wave 135 resumed the exact already-authorized rotation to sequence 1, removed the exact historical helpers, then completed another authorized rotation to sequence 2 with no private-key publication residue remaining.

2. **Repeated-crash growth bounded.** Ten real SIGKILLs at `post_close_pre_replace` left exactly one deterministic private-key stage after every cut. All ten cuts reused the same stage pathname. Exact recovery then completed sequence 1; retry was idempotent and left no publication residue.

3. **Wrong bytes fail closed.** A content-bound private-key stage whose bytes were changed was rejected with `wave135-stage-temp-mismatch` and retained for inspection.

4. **Foreign owner fails closed.** An exact staged private key whose ownership was changed to worker UID 1001 was rejected with `wave135-candidate-owner-mismatch` and retained for inspection.

5. **Normal authorized lineage still works.** Two clean successive rotations reached sequence 1 then sequence 2, and final validation remained green with no current private-key publication residue.

Generated JSON reports and runner output remain CI artifact ballast, not repository history. Reusable code, self-test, workflow, and this concise receipt are preserved in the lane.

## Truth boundary

This is a same-host Linux/process/filesystem result for the **post-pending current-key publication boundary** challenged by verifier PR #59. It demonstrates bounded exact recovery/deduplication for the tested authority-owned historical `response_private.pem` temps and deterministic current-key stages.

It does **not** yet prove:

- crash-safe creation of the pending rotation transaction itself, especially `pending_private.pem` and its metadata;
- crash safety inside append-style authority or witness lineage updates;
- cleanup crash cuts after an otherwise valid rotation;
- validation-to-service inode/path identity against later substitution;
- Linux user-namespace UID alias safety;
- uniqueness of copied genuine keys across namespaces or hosts;
- resistance to root/kernel compromise or an attacker already operating as the authority UID;
- whole-domain rollback resistance;
- hardware-backed non-exportable key custody;
- provider independence or physical finality.

No real AXM/monolith performance workload and no synthetic scaling workload were run in Wave 135 because this was a correctness/key-custody gate. Therefore this receipt makes **no new performance, speed, energy, retained-compute, incremental-compute, dormant-compute, throughput, or scaling claim**.

## Next gate

Extend exact-intent recovery through the remaining rotation transaction rather than jumping ahead:

1. attack creation/publication of the pending transaction, especially `pending_private.pem` and pending metadata, with internal SIGKILL cuts;
2. attack append-style authority and witness lineage writes, including partial append/fsync boundaries;
3. attack cleanup/removal boundaries so a crash cannot create ambiguous stale secret or metadata residue;
4. repeat important cuts at 1/10/100 scale and require bounded residue rather than assuming one successful retry is enough;
5. preserve hostile wrong-byte, foreign-owner, stale-generation, and unrelated leftover counterexamples as fail-closed cases.

Only after the complete on-host authorized rotation transaction has an exact crash/recovery story should the larger uniqueness gate resume: copy the genuinely current authority identity, lineage, and real private key into another Linux namespace and preferably another host, then let both authentic copies try to authorize different successors. If both can create independently valid divergent chains, keep that counterexample; signatures prove identity, not uniqueness.

No merge, auto-merge, or CANON promotion is authorized by this receipt.
