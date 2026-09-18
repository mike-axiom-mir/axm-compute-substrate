# Flowing Compute Wave 26 — Incremental Segmented Recovery Checkpoints

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST RECOVERY-CHECKPOINT EVIDENCE`

## Question

Wave 25 proved sparse recovery checkpoints can bound normal recovery, but checkpoint creation itself rescanned the full historical spine. Can checkpoint admission also become incremental without pretending a flat SHA-256 prefix digest can be extended from yesterday's final digest?

## Proof shape

Wave 26 changes the checkpoint identity from one flat prefix SHA into an ordered list of immutable segment proofs.

Each segment records:

- start/end byte offsets;
- start/end generation sequence;
- SHA-256 of exactly that segment's spine bytes.

The checkpoint carries a deterministic hash of the ordered segment descriptors plus the parsed target anchor generation.

Advancing a checkpoint:

1. validates the parent checkpoint object;
2. parses only generations appended after the parent anchor;
3. hashes only those new segment bytes;
4. appends one segment descriptor;
5. emits a new self-contained latest checkpoint.

No claim is made that SHA-256(prefix N+1) can be derived from SHA-256(prefix N). The proof contract was changed instead.

## 20,000-generation checkpoint chain

Bootstrap: generation 1,024. Then checkpoints advanced in 1,024-generation segments through generation 19,456.

Every new segment was **303,104 bytes / 1,024 generation records**.

Across all 18 incremental advances:

- incremental checkpoint update CPU: roughly **4.0–4.9 ms** median;
- old full-admission path on the same 20k spine: roughly **89.5–101.8 ms**;
- CPU reduction generally **~95–96%**.

Representative points:

| target generation | segments carried | incremental CPU | old full admission | saved |
|---:|---:|---:|---:|---:|
| 2,048 | 2 | 4.130 ms | 99.380 ms | 95.84% |
| 9,216 | 9 | 4.031 ms | 93.344 ms | 95.68% |
| 14,336 | 14 | 4.909 ms | 96.480 ms | 94.91% |
| 19,456 | 19 | 4.116 ms | 89.510 ms | 95.40% |

The latest checkpoint is **4,449 bytes** and carries 19 segment proofs.

## Recovery at generation 20,000

Latest checkpoint: generation 19,456; tail: 544 generation records.

- carried-proof recovery: **2.932 ms CPU**;
- audited-segment recovery: **7.161 ms**.

Audited mode hashes every prior segment byte but does not reparse thousands of old generation records.

## Controls

- corrupt latest checkpoint -> full authoritative fallback;
- historical byte mutation -> carried mode intentionally reuses prior proof; audited mode detects a segment-hash mismatch and falls back;
- latest recovery does **not** require old parent checkpoint files because the latest checkpoint embeds the complete ordered segment-proof list.

## Important remaining waste

Incremental admission still rereads/parses/hashes the newest 1,024 records after they were already created by the transactional writer. ~4 ms is bounded, but it is still rediscovery of work the live runtime just performed.

So Wave 26 is promoted as a bounded improvement, not the final checkpoint architecture.

## Truth boundary

- 20k spine growth is synthetic-but-valid under the actual generation-record contract;
- one host/runtime/filesystem;
- CPU time is not joules;
- carried proof assumes already-verified segment immutability;
- audited mode spends compute to re-establish byte identity of every segment;
- latest checkpoint is acceleration evidence, not state authority;
- bootstrap checkpoint admission is still a one-time full operation;
- no claim of compute/energy from nothing.

## Next gate

Build segment proofs *during* normal generation writes. A live accumulator should ingest each exact framed generation record as it is appended, seal a segment without rereading the spine, survive process restart using a bounded persisted accumulator/checkpoint boundary, and preserve a full-audit path. Measure per-generation accumulator overhead and segment-seal cost against Wave-26's ~4 ms post-hoc update.
