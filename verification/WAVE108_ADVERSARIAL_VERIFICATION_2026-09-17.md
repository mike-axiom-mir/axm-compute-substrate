# Independent adversarial verification — Wave 108 marker-tail commit-status memory

Status: **verifier-only draft evidence; no merge / no CANON promotion**

## Exact target

- repository: `mike-axiom-mir/axm-compute-substrate`
- builder branch: `chatgpt/lane-001-platform-extract`
- newest builder head examined: `7573e1e97d026ed07065fcca46cc0d88a26e64b5`
- exact Wave 108 tested source commit: `7b9ec8548bde69df1d8971567aaf04abd0fa2e5c`
- Wave 108 tool blob: `629318c9645649a29d7a4d4c97f106a0ba958f6d`
- Wave 108 self-test blob: `aeac803084fc05e82c626bb830cee48146c710e2`
- builder exact-source CI: Wave 107 regression `22/22`, Wave 108 normal `27/27`, Wave 108 `python -O` `27/27`

## What survives

Wave 108 materially closes verifier PR #32's exact newest-link-loss case. Its paired commit/high-water ledgers name accepted authority links explicitly, so deleting a manifested committed `L` body while its marker remains is classified incomplete/corrupt and authority fails closed. The builder also preserves an honest truth boundary: depth 8/16 is correctness-only, and no new performance, energy, retained/incremental/dormant-compute, network, process, device, or provider result is claimed.

## New adversarial question

The two new marker chains are themselves the only Wave-108 memory distinguishing **committed** from **prepared-but-uncommitted** for an extra next-epoch authority link.

`committed_history_state()` computes `extras = L - committed_marker_shas`. An extra resolved link is accepted as prepared if it is exactly `max_manifested_epoch + 1` and the supplied runtime still points to the last manifested epoch. Therefore, after a real epoch 2 was accepted, if both Wave-108 marker tails are truncated from sequence 2 back to sequence 1 while the epoch-2 `L/C/U` bodies remain, rolling the runtime pointer back to epoch 1 makes the still-retained epoch-2 link satisfy the code's prepared-only shape.

That is a different attack from PR #32. PR #32 removed the newest `L` body while marker history did not yet exist. This challenge keeps the newer authority/checkpoint/use bodies and instead removes the two records that say that newer link had already committed.

## Exact reproducer

`verification/wave108_marker_tail_reclassification_repro.py`:

1. creates a normal Wave-108 world and adopts genesis;
2. advances normally through fully authoritative epochs 1 and 2;
3. preserves legitimate epoch-1 snapshots needed for stale-store restoration;
4. deletes only sequence-2 rows from `W108_COMMITTED_AUTHORITY_LEDGER` and `W108_COMMITTED_HIGH_WATER_LEDGER`;
5. keeps all epoch-2 local `L/C/U` bodies and the complete current Wave-105 binding store, including its epoch-2 binding body;
6. restores only the mutable local runtime pointer to epoch 1;
7. first checks the isolated semantic effect while all newer external state remains untouched;
8. then truncates only the local quorum-certificate tail to certificate 1, restores remote B+C to their legitimate epoch-1 snapshots while leaving remote A intact at `[1,2]`, and restores certificate-witness B+C disks to epoch 1 while leaving certificate-witness A's `[1,2]` disk intact but unavailable;
9. asks unchanged Wave 108 for committed-history status and final authority.

The intended distinction is narrow: this is **not** coordinated whole-world rollback. A newer local authority/checkpoint/use set remains physically retained, one remote remains fully newer, one registered certificate witness retains the newer certificate on disk, and the newer binding body remains retained.

## Expected interpretation

If unchanged Wave 108 reports the still-retained epoch-2 authority link in `prepared_authority_shas`, the marker tail has forgotten a real historical fact: that epoch 2 was previously committed. That is already a bounded commit-status/history-semantics failure.

If the partial stale quorum then makes epoch 1 authoritative, the stronger verdict is:

`FAIL_COMMITTED_MARKER_TAIL_TRUNCATION_RECLASSIFIES_ACCEPTED_EPOCH_AS_PREPARED_AND_PERMITS_STALE_QUORUM`

If lower certificate/witness/root layers still prevent stale authority, preserve the narrower verdict instead:

`FAIL_COMMITTED_MARKER_TAIL_TRUNCATION_FORGETS_COMMIT_STATUS_BOUNDED`

The read-only CI runs the unchanged Wave-108 builder self-test first and executes the reproducer in normal Python and `python -O`. This note must be updated with the observed verdict rather than assuming the stronger outcome.

## Benchmark / hidden-cost boundary

There is no new builder performance claim to falsify. The new Wave-108 guard linearizes both marker stores and then resolves every manifested authority link on every check, while Wave 107 also scans retained authority history underneath it. That establishes growing verification work with retained history depth, but no complexity or performance number is claimed here until it is measured fairly.

## Next gate

If the attack reproduces, committed-history memory needs a monotonic boundary that cannot be converted into “prepared” merely by truncating both local marker tails. Process separation alone is not sufficient if a stale process/store image can restore the same logical marker prefix.

The next repair should distinguish at least three states mechanically: never committed, prepared-only, and once-committed-but-history-now-incomplete. Then attack marker-tail truncation with newer `L/C/U` retained, one newer remote intact, one newer certificate-witness disk offline/online, crash recovery, and stale process restart. Keep coordinated whole-world rollback as a separate stronger unresolved boundary.
