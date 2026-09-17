# Independent adversarial verification — Wave 107 multi-epoch partial loss

Status: **FAIL (bounded history-completeness claim); verifier-only draft evidence; no merge / no CANON promotion**

## Provenance

- repository: `mike-axiom-mir/axm-compute-substrate`
- newest builder head examined: `22289521483fe8e171f6c9016f0bd0b10e54a235`
- builder exact tested-source commit: `9e4edc8c484d32f9210804dc25ca61fadf7aa835`
- Wave 107 tool blob: `7aeb0e6f6018d1708b5fe89a4fdbf8e024398deb`
- Wave 107 self-test blob: `66d676685b23fd5cbcc5ac8f06a0ec5e383fd295`
- builder receipt: Wave 106 regression `36/36`, Wave 107 normal `22/22`, Wave 107 `python -O` `22/22`
- verifier PR: `#32`
- verifier CI run: `35193912823`
- verifier normal job: `105112535591`
- verifier optimized job: `105112535372`

The verifier CI reran the unchanged Wave 107 builder self-test successfully in normal Python. The independent reproducer succeeded in both normal Python and `python -O`. Both severity-bound steps also succeeded, which mechanically confirms that neither tested full-authority call returned an `AUTHORITATIVE...` verdict in this counterexample.

## What survived

The exact verifier-PR-#31 repair survives. At retained depth 1, deleting the only authority-link body while its checkpoint/use evidence remains is classified `INCOMPLETE_OR_CORRUPT`, and Wave 107 still fails closed for the original missing signer-use attack.

The builder's truth boundary is also honest about performance: Wave 107 reports no fresh AXM/monolith workload and makes no new performance, energy, network, retained/incremental/dormant-compute, process, device, or provider-independence claim. No benchmark-overclaim failure was found in this wave.

## Counterexample

Advance normally through two accepted authority epochs. Then delete **exactly one retained body**: the epoch-2 `L[authority_sha]` authority-link body.

Preserve all of the following unchanged:

- the epoch-2 signed checkpoint body in `C`;
- the epoch-2 signer-use body in `U`;
- the older valid epoch-1 authority link;
- the Wave-106 bootstrap-lineage store;
- certificate store and certificate-witness domain;
- remote services;
- binding store;
- runtime pointer for the primary attack.

Wave 107 classifies this attacked retained history as `VALID`, not `INCOMPLETE_OR_CORRUPT`.

The reason is structural. `retained_authority_history_state()` verifies every **surviving `L` row**, but once at least one link remains and all surviving links resolve, extra `C/U` rows are explicitly tolerated. At depth 1, losing the sole link leaves `L` empty and `C/U` non-empty, so loss is detected. At depth 2, losing the newest link leaves the older epoch-1 link resolvable, so the newer checkpoint/use rows become tolerated orphan evidence and the same kind of single-body loss is classified `VALID`.

Preserved verifier verdict:

`FAIL_MULTIEPOCH_AUTHORITY_LINK_LOSS_CLASSIFIED_VALID`

## Bounded severity

This reproducer does **not** demonstrate stale authority acceptance. With the current epoch-2 runtime pointer, the lower authority path remains non-authoritative because the current link is missing. With the runtime pointer rolled back to epoch 1 while the newer certificate/remote state remains intact, the lower authority path also remains non-authoritative. The verifier CI explicitly fails if either path becomes `AUTHORITATIVE...`, and both normal and optimized severity-bound steps passed.

So the narrow result is:

- the broad Wave 107 statement that loss of one authority-link body is mechanically caught by the bootstrap partial-evidence guard is false for multi-epoch retained history;
- the exact PR #31 repair still survives;
- the existing lower certificate/remote/lineage layers still stop this particular mutation from becoming accepted stale authority.

## Hidden-cost / retained-state note

Wave 107 now scans every retained authority-link row and calls `resolve()` for each guard evaluation. That establishes at least linear work in retained `L` depth before considering the cost inside each `resolve()`. This is not a benchmark failure because Wave 107 makes no performance claim, but it should be measured before extrapolating the guard to long-lived retained histories.

## Next adversarial gate

Before treating process separation as evidence that the history contract itself is settled, define a committed-history completeness invariant across **multiple epochs**. A practical repair needs to distinguish legitimate prepared-but-uncommitted orphan `C/U` rows from a missing committed authority-link suffix. Options include a durable committed-authority manifest/high-water mark, an append-only committed-head ledger, or an equivalent certificate-backed commitment that says which authority-link identities must exist.

Then attack at retained depths 2, 8, and larger:

- delete newest committed `L` only;
- delete newest `L+C`, `L+U`, and `L+C+U` suffixes;
- delete a middle committed authority link;
- retain legitimate prepared-only checkpoint/use leftovers;
- crash before local commit and after local commit;
- roll runtime to an older valid prefix while newer external witnesses remain;
- corrupt or truncate the committed-history marker itself.

Only after the multi-epoch prefix/suffix semantics are explicit should the same contract be moved into separate OS processes for kill/restart and cloned-disk testing.
