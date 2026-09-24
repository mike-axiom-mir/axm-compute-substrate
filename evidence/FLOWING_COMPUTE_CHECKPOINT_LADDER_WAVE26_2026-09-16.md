# Flowing Compute Wave 26 — Incremental Checkpoint Ladder

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST RECOVERY-SCALING EVIDENCE`

## Question

Wave 25 showed that one sparse checkpoint can bound normal recovery, but creating that checkpoint by rescanning history merely moves the linear work to the checkpoint writer. It also makes historical rollback older than the one checkpoint fall back to byte-zero recovery.

Can AXM maintain a **ladder of chained, non-authoritative checkpoints** where each new checkpoint validates only the newly appended segment, and recovery selects the newest valid checkpoint not newer than the committed pointer target?

## Contract

Wave 26 adds `AXM_FLOWING_COMPUTE_CHECKPOINT_LADDER.py`.

Each checkpoint records its generation/anchor, segment start/end offsets, SHA-256 of only the newly admitted segment, parent checkpoint SHA-256, and a rolling checkpoint-chain root. The root checkpoint is established from the first real valid generation record discovered by the existing scanner; byte offset zero is not assumed to be a generation frame.

Checkpoints remain acceleration metadata. The dual committed pointer slots remain current-state authority.

Two modes remain separate:

- `carried_proof`: validate checkpoint artifacts/hash chain and reuse prior segment verification;
- `audited`: rehash every checkpoint segment before using the ladder.

A corrupt latest checkpoint in carried mode can fall back to the newest earlier valid checkpoint and parse forward. Audited mode treats a broken checkpoint proof chain as a reason to use full authoritative recovery.

## Checkpoint creation cost

Interval: 1,024 generations.

| history | target | parent | old full admission | incremental child | CPU saved | yield |
|---:|---:|---:|---:|---:|---:|---:|
| 5,000 | 4,096 | 3,072 | ~21.91 ms | ~4.00 ms | 81.74% | 5.48x |
| 10,000 | 9,216 | 8,192 | ~47.12 ms | ~3.96 ms | 91.59% | 11.89x |
| 20,000 | 19,456 | 18,432 | ~94.82 ms | ~3.87 ms | 95.92% | 24.53x |

This removes Wave 25's measured checkpoint-admission regression where repeated checkpoint creation itself became linear in total retained history.

## Historical rollback repair

The first Wave-26 implementation selected the correct checkpoint for rollback but then parsed from that checkpoint all the way to the end of the 20,000-generation spine. That defeated bounded rollback.

The repaired implementation reads committed pointer slots first, groups them by the checkpoint needed to validate them, and scans only through the largest committed pointer target required for that checkpoint group. The failed first implementation is not counted as a success.

## Recovery measurements after repair

20,000-generation spine; checkpoint interval 1,024.

### Current pointer = generation 20,000

- full authoritative median: **93.49 ms CPU** (7 samples);
- carried ladder, checkpoint 19,456: **3.874 ms** (15 samples);
- audited ladder: **7.826 ms** (10 samples).

Versus full recovery, carried saved **95.86% CPU / 24.14x yield** and audited saved **91.63% / 11.95x**.

### Historical rollback pointer = generation 5,000

The ladder selects checkpoint 4,096 and stops parsing at the committed rollback target.

- old full recovery median: **2.940 s CPU** (3 samples);
- carried ladder: **4.940 ms** (15 samples);
- audited ladder: **9.167 ms** (10 samples).

This is **fast committed-state recovery**, not a like-for-like replacement for complete historical audit. The old full path also walks/validates the roughly 15,000 later generations as newer unpointed history, while targeted ladder recovery intentionally stops once it has enough evidence to validate the committed rollback pointer. Full later-history audit remains separate.

## Controls

Passed:

- current 20,000 -> checkpoint 19,456 -> recover 20,000;
- audited current -> recover 20,000;
- rollback 5,000 -> checkpoint 4,096 -> recover 5,000;
- rollback 1,000, before ladder root -> full fallback;
- corrupt newest checkpoint in carried mode -> use last valid earlier checkpoint 18,432 and parse forward;
- same corruption in audited mode -> full authoritative fallback.

## Truth boundary

- long histories are synthetic extensions using the real generation record/recovery contract, not 20,000 organic AXM edits;
- CPU process time is not direct energy measurement;
- checkpoint ladder is non-authoritative;
- carried proof reuses previously established segment verification;
- audited mode rehashes checkpoint segments but remains one-host/filesystem evidence;
- fast historical rollback does not perform a complete audit of later generations;
- corrupt/missing acceleration metadata must fall back rather than move canonical state;
- hashes provide content identity/integrity, not external authentication;
- no claim of compute/energy from nothing.

## Next gate

Wave 27 removes the remaining checkpoint-creation rediscovery: build each segment proof live while generations are committed, using metadata the transactional writer already owns. The proof accumulator must survive restart, remain tiny enough to travel in the dual pointer, and later audit to the exact same segment root.
