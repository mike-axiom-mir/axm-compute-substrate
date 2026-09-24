# Flowing Compute Wave 25 — Sparse Recovery Checkpoints

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST RECOVERY-SCALING EVIDENCE`

## Question

Wave 24 recovery scans the append-only generation spine from byte zero. Does recovery become a meaningful compute bill as history grows, and can a non-authoritative sparse checkpoint bound normal recovery while preserving a full authoritative fallback?

## Full authoritative scan scaling

Synthetic-but-valid generation spines were grown under the same Wave-22 record contract while reusing the same tiny state/table bodies.

| generations | spine bytes | full recovery CPU median |
|---:|---:|---:|
| 100 | 29,608 | 0.926 ms |
| 1,000 | 296,008 | 4.221 ms |
| 5,000 | 1,480,008 | 22.696 ms |
| 10,000 | 2,960,008 | 46.859 ms |
| 20,000 | 5,920,008 | 97.346 ms |

The current authoritative parser therefore grows approximately linearly with retained spine history.

## Sparse recovery checkpoint

A checkpoint records one previously verified generation anchor plus:

- the exact verified spine-prefix byte boundary;
- SHA-256 of that immutable prefix;
- the parsed anchor generation;
- its generation hash/offset/length.

It is explicitly **not authority**. Current state is still determined only by valid committed pointer slots whose dependency closure validates.

Two trust modes were measured:

- `carried_proof` — reuse the prior verification that the immutable prefix was valid; parse only the new tail;
- `audited` — rehash the checkpointed prefix first, then parse only the tail.

Checkpoint corruption, rollback behind the checkpoint, or an audited prefix mismatch falls back to the full authoritative path.

## Same-process scaling

| current gen | checkpoint gen | tail records | full CPU | carried CPU | audited CPU | carried saved | audited saved |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1,000 | 500 | 500 | 4.409 ms | 2.647 ms | 2.854 ms | 40.0% | 35.3% |
| 5,000 | 4,096 | 904 | 20.932 ms | 4.365 ms | 5.096 ms | 79.1% | 75.7% |
| 10,000 | 9,216 | 784 | 48.695 ms | 4.034 ms | 5.935 ms | 91.7% | 87.8% |
| 20,000 | 19,456 | 544 | 101.994 ms | 2.857 ms | 7.052 ms | 97.2% | 93.1% |

## Fresh-process control

A new Python process was launched for every recovery sample.

### 10,000 generations

- full authoritative: **54.179 ms CPU**;
- carried checkpoint: **4.978 ms** (**90.81% less**);
- audited checkpoint: **7.272 ms** (**86.58% less**).

### 20,000 generations

- full authoritative: **151.931 ms CPU**;
- carried checkpoint: **3.490 ms** (**97.70% less**);
- audited checkpoint: **8.301 ms** (**94.54% less**).

The checkpoint advantage therefore survives process death.

## Controls

- corrupt checkpoint file -> full fallback, committed state recovered;
- pointer rollback before checkpoint -> full fallback, older committed generation recovered;
- historical prefix mutation -> carried-proof mode intentionally does not rediscover it, while audited mode detects the prefix mismatch and falls back to the authoritative scanner;
- corrupt tail after current generation -> current committed generation remains recoverable and corrupt tail stays visible.

This preserves the trust distinction: carried proof is faster because it reuses previously established immutable-prefix evidence; audited mode spends additional compute to re-establish byte identity.

## Important negative result — checkpoint creation cost

The current `create_checkpoint()` deliberately creates its checkpoint through a full authoritative scan plus prefix SHA. That makes checkpoint admission expensive:

| current generations | checkpoint sequence | creation CPU median |
|---:|---:|---:|
| 1,000 | 500 | 3.903 ms |
| 5,000 | 4,096 | 20.542 ms |
| 10,000 | 9,216 | 44.813 ms |
| 20,000 | 19,456 | **95.282 ms** |

So simply creating a checkpoint every fixed interval by rescanning from byte zero would move the same linear waste from recovery to the write/checkpoint side. **That design is not promoted.**

## Truth boundary

- long spines are synthetic generation growth under the real record contract, not 20,000 distinct AXM product mutations;
- one host/runtime/filesystem;
- CPU time is not joules;
- carried-proof mode assumes the checkpointed prefix remains immutable after prior verification;
- audited mode verifies byte identity of the old prefix but still relies on SHA/content identity rather than external authentication;
- checkpoints are acceleration hints, never canonical state authority;
- current checkpoint creation is intentionally expensive and is a measured negative result;
- no claim of compute/energy from nothing.

## Next gate

Make checkpoint creation incremental too. A checkpoint generation should reuse the previous checkpoint's verified immutable prefix, validate/hash only the newly appended segment, and chain the new checkpoint proof to its parent. Full audit must remain available. Measure checkpoint-update cost versus full checkpoint admission and prove corrupt/missing parent checkpoints always fall back to the full authoritative scan.
