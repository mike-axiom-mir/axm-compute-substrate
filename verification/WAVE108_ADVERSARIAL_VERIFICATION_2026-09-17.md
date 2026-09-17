# Independent adversarial verification — Wave 108 marker-tail commit-status memory

Status: **FAIL reproduced independently; verifier-only draft evidence; no merge / no CANON promotion**

## Exact target

- repository: `mike-axiom-mir/axm-compute-substrate`
- builder branch: `chatgpt/lane-001-platform-extract`
- newest builder head examined: `7573e1e97d026ed07065fcca46cc0d88a26e64b5`
- exact Wave 108 tested source commit: `7b9ec8548bde69df1d8971567aaf04abd0fa2e5c`
- Wave 108 tool blob: `629318c9645649a29d7a4d4c97f106a0ba958f6d`
- Wave 108 self-test blob: `aeac803084fc05e82c626bb830cee48146c710e2`
- builder exact-source CI: Wave 107 regression `22/22`, Wave 108 normal `27/27`, Wave 108 `python -O` `27/27`

## What survives

Wave 108 materially closes verifier PR #32's exact newest-link-loss case. Its paired commit/high-water ledgers name accepted authority links explicitly, so deleting a manifested committed `L` body while its marker remains is classified incomplete/corrupt and authority fails closed. The unchanged Wave-108 builder self-test also passed again inside this verifier lane before the normal-mode attack ran.

The builder preserves an honest truth boundary: depth 8/16 is correctness-only, and no new performance, energy, retained/incremental/dormant-compute, network, process, device, or provider result is claimed.

## New failure

The two new marker chains are themselves the only Wave-108 memory distinguishing **committed** from **prepared-but-uncommitted** for an extra next-epoch authority link.

`committed_history_state()` computes `extras = L - committed_marker_shas`. An extra resolved link is accepted as prepared if it is exactly `max_manifested_epoch + 1` and the supplied runtime still points to the last manifested epoch. After a real epoch 2 had already been accepted, truncating both Wave-108 marker tails from sequence 2 back to sequence 1 while retaining the epoch-2 `L/C/U` bodies and rolling the runtime pointer back to epoch 1 caused unchanged Wave 108 to classify that previously committed epoch-2 link as a legal prepared-only next epoch.

That lost commit-status memory combines with a partial stale quorum to make epoch 1 authoritative again.

Preserved verifier verdict:

`FAIL_COMMITTED_MARKER_TAIL_TRUNCATION_RECLASSIFIES_ACCEPTED_EPOCH_AS_PREPARED_AND_PERMITS_STALE_QUORUM`

## Exact reproduced attack

`verification/wave108_marker_tail_reclassification_repro.py`:

1. created a normal Wave-108 world and adopted genesis;
2. advanced normally through fully authoritative epochs 1 and 2;
3. preserved legitimate epoch-1 snapshots needed for stale-store restoration;
4. deleted only sequence-2 rows from `W108_COMMITTED_AUTHORITY_LEDGER` and `W108_COMMITTED_HIGH_WATER_LEDGER`;
5. kept all epoch-2 local `L/C/U` bodies and the complete current Wave-105 binding store, including its epoch-2 binding body;
6. restored only the mutable local runtime pointer to epoch 1;
7. with newer external evidence still intact, confirmed stale authority remained blocked while the Wave-108 history layer had already reclassified the epoch-2 link as prepared-only;
8. truncated only the local quorum-certificate tail to certificate 1;
9. restored remote B+C to their legitimate epoch-1 snapshots while leaving remote A intact at `[1,2]`;
10. restored certificate-witness B+C disks to certificate 1 while leaving the genuine registered cert-A disk at `[1,2]`, then made only cert-A unavailable;
11. unchanged Wave 108 classified the marker-truncated committed history `VALID`, treated the retained epoch-2 authority as prepared-only, and returned an `AUTHORITATIVE...` result for the stale epoch-1 world.

This is narrower than the builder's preserved coordinated whole-world rollback. The newer epoch-2 local authority/checkpoint/signer-use bodies remain physically retained; the newer Wave-105 binding body remains retained; remote A remains fully newer; and the genuine registered certificate witness A retains the newer certificate on disk. No hashes or credentials are forged.

## Independent CI

Read-only verifier workflow run: `35198901311` at verifier head `d2d5851a1bf3088d1d2c96af909777bc6ea2ed6f`.

- normal job `105128625588`: **PASS**
  - unchanged Wave-108 builder self-test: PASS
  - adversarial reproducer: PASS
  - explicit strong stale-authority verdict assertion: PASS
- `python -O` job `105128625455`: **PASS**
  - adversarial reproducer: PASS
  - explicit strong stale-authority verdict assertion: PASS

The CI gate requires the exact strong verdict above, requires final authority to begin with `AUTHORITATIVE`, and requires the marker-truncated committed-history state to equal `VALID`; a merely bounded history-classification failure would fail this verifier workflow.

## Why this is not PR #32 again

PR #32 removed the newest committed `L` body and showed Wave 107 could overlook that deletion. Wave 108 correctly repairs that exact case.

This attack leaves the newer `L/C/U` evidence intact. It instead removes the paired marker tail that says the link had crossed the commit boundary. The remaining epoch-2 authority object is then semantically downgraded from "once committed" to "prepared-only" solely because the local marker ledgers forgot their newest entries.

## Benchmark / hidden-cost boundary

There is no new builder performance claim to falsify in Wave 108. The guard linearizes both complete marker stores and then resolves every manifested authority link on each check, while the Wave-107 history guard also scans retained authority history beneath it. Verification work therefore grows with retained history by construction, but this verifier does **not** attach a performance number or claim a regression without a fair benchmark.

## Next adversarial gate

Committed status needs a monotonic durability boundary that cannot be converted back into `prepared-only` by restoring/truncating both local marker ledgers. Merely moving the same contract into OS processes is not enough if those processes can restart from stale disk prefixes.

The next repair should mechanically distinguish at least: never committed, prepared-only, once committed and complete, and once committed but evidence now incomplete. Then attack:

- both-marker-tail truncation while newer `L/C/U` remains;
- one newer remote intact plus a stale two-node remote quorum;
- one newer certificate-witness disk intact but unavailable, and then available/reconnecting;
- local certificate-tail truncation independently from marker-tail truncation;
- crash before/after each durable write;
- stale process restart and cloned disk restoration;
- marker durability located in a genuinely independent failure domain.

Keep coordinated whole-world rollback as the stronger unresolved boundary rather than using it to hide this narrower stale-authority counterexample.
