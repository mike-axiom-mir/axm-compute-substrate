# Flowing Compute Wave 134 — recoverable atomic bootstrap publication receipt

Status: **experimental / NON-CANON / no automatic merge**.

This receipt preserves the exact Wave 134 correctness/security result in the ongoing `chatgpt/lane-001-platform-extract` research lane. It does not promote the result to CANON and does not replace earlier receipts or counterexamples.

## Provenance carried forward

Wave 133 evidence head: `be2bf60d834a4feab9e7a49f166c92a7e464684c`  
Wave 133 exact green implementation source: `1a6867e4ee1ddeb8010cf1115da9efe5ac246f5f`

Independent verifier PR #58 (`verifier/wave133-atomic-temp-kill-recovery`) widened the crash cut *inside* the shared atomic-write helper. Its CI-tested verifier head was `73e8b105ce2e04b66f4305e5861e77b245f1b83c`; run `35323372319`, job `105529487432`, artifact `10538438742`, artifact SHA-256 `0172b66828877ec78687bef4b083b2d23090b1f38aad825074f0ccd1dc8a05da`.

The verifier established a genuine Wave 133 counterexample: `_atomic_write` used random same-directory `target.tmp-PID-random` staging. A real SIGKILL after the temp was fully written and fsynced but before `os.replace` could leave an authority-owned temp. For bootstrap intent that leftover could make exact retry fail the strict pre-ready allowlist; at the witness-lineage target a retry could succeed while leaving the orphan temp behind. Therefore Wave 133's recovery statement did **not** cover kills inside the atomic helper.

## Wave 134 change

Wave 134 adds `tools/AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ATOMIC_RECOVERY.py` plus an adversarial self-test and exact-source CI workflow.

The reusable writer uses a deterministic, content-bound same-directory stage name derived from target name, mode, length, and intended-byte SHA-256. A current Wave-134 stage can be resumed only when it is authority-owned, has the exact expected mode, and its bytes are an exact prefix of the caller's already-known intended bytes. A legacy Wave-133 random `.tmp-*` may be adopted only when authority ownership/mode match and its **complete bytes exactly equal** the intended bytes. Wrong bytes, foreign ownership, or an unrelated deterministic stage fail closed and are retained for inspection. Successful publication ends with `os.replace` followed by parent-directory fsync.

The new fault harness cuts with real SIGKILL at six internal publication positions: temp creation, partial write, full write before fsync, after fsync before close, after close before replace, and after replace before directory fsync. It also keeps the exact PR-58-style legacy-temp predecessor control, exercises the same placement at witness-lineage bootstrap publication, tests multiple exact legacy temps, wrong-byte legacy temps, wrong deterministic-stage bytes, and an exact-byte foreign-owner lookalike.

## Failed Wave 134 attempt retained

Initial candidate/source `d07c02f09315883c828efc98c1636fef333f778a`, workflow run `35326600260`, job `105540978879`, was **red** after unchanged Wave 133 regressions passed.

The first implementation always re-ran the Wave-131 genesis validator and re-derived bootstrap expectations from the *current* response public key. After a legitimate Wave-132 rotation, that current key is intentionally different from the frozen genesis key, so an exact retry failed with `ValueError:wave133-wave131-readiness-receipt-mismatch`.

This was a real Wave-134 implementation bug, not a verifier-only problem. It was repaired by preserving Wave 133's post-readiness trust rule: once `bootstrap.ready.json` is durable, validate the frozen bootstrap receipt directly and do not reinterpret a legitimately rotated current key as genesis. Post-readiness helper residue is still scanned by stable target-name prefixes and fails closed rather than being silently accepted.

## Exact successful source and CI evidence

Exact tested Wave 134 source: `20abcb846a48709dba4ba345380a1782f3fa83c8`  
Workflow run: `35326922695`  
Job: `105542005667`  
Artifact: `10538724219` (`wave134-recoverable-atomic-bootstrap`)  
Artifact SHA-256: `736c3855cb38ede65ee2fd7f4ed5590e47d51cc26451bd1910b333ab2aa3488d`

On Ubuntu 24.04 / Python 3.12.14 the exact source passed:

- unchanged Wave 133 regression: **12/12 normal + 12/12 under `python -O`**;
- Wave 134 recoverable atomic bootstrap: **12/12 normal + 12/12 under `python -O`**.

Observed positive cases include exact recovery of the verifier-PR-58 fsynced legacy temp without manual deletion, exact/idempotent recovery after every new internal SIGKILL cut, witness-lineage temp recovery with no silent orphan, and safe deduplication of multiple identical authority-owned legacy temps.

Observed negative cases include wrong-byte legacy temp rejection with the evidence retained, non-prefix deterministic-stage rejection with the evidence retained, and exact-byte foreign-owner lookalike rejection with the evidence retained.

Generated JSON reports and CI identity files remain in the workflow artifact rather than being committed as repository ballast.

## Truth boundary

Wave 134 proves only the tested same-host Linux/process/filesystem bootstrap-publication recovery boundary. It does **not** yet prove:

- the same internal atomic-cut recovery across the full Wave-132 rotation transaction (`pending`, predecessor certificate, successor key, authority/witness lineage, key/verifier/binding/state publication);
- validation-to-service inode/path stability against live substitution;
- user-namespace UID alias safety;
- uniqueness of copied genuine response keys across namespaces or hosts;
- resistance to root/kernel or authority-UID compromise;
- coordinated rollback of the whole trust domain;
- hardware-backed non-exportable custody, provider independence, or physical finality.

No real AXM/monolith performance benchmark and no synthetic scaling benchmark were run in Wave 134 because this was a correctness/recovery gate. There is therefore **no new speed, energy, retained-compute, incremental-compute, dormant-compute, throughput, or scaling claim**.

## Next gate

Apply the same exact-intent recovery discipline to the **entire rotation transaction**, not only bootstrap genesis: place internal SIGKILL cuts around pending-transaction publication, predecessor certificate, successor-key staging, both signed lineage publications, authority key swap, witness verifier/binding publication, and final state. Keep wrong-byte, foreign-owner, stale/ambiguous helper residue, and rollback cases as permanent negatives.

After the rotation transaction itself survives those cuts, return to the larger genuine-clone gate: copied current authority identity + real private key in another Linux namespace/host competing to authorize divergent successors. A valid signature proves which key signed something; it still does not prove only one copy of that key exists.
