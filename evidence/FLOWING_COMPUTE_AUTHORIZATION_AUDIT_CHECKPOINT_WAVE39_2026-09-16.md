# Flowing Compute Wave 39 — Sparse Authorization Audit Checkpoint

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST AUTHORIZATION-AUDIT SCALING EVIDENCE`

## Question

Wave 38 made fast carried authorization recovery O(1)-like for current receipt discovery, but full audit still walks old receipt history. Can a non-authoritative receipt-history checkpoint bound audited recovery while preserving full-from-zero audit?

## Fixture

Synthetic-but-format-valid append-only authorization receipt store:

- receipt objects: **10,000**;
- store bytes: **6,977,672**;
- checkpoint receipt: **9,216**;
- tail receipts after checkpoint: **784**.

The scaling fixture validates receipt integrity + parent receipt linkage. It is not 10,000 organic AXM authorization events.

## Results

Median CPU:

- full receipt-chain audit: **~127.07 ms**;
- carried checkpoint + tail audit: **~8.64 ms**;
- audited checkpoint (rehash old prefix + tail audit): **~12.92 ms**.

Relative to full audit:

- carried checkpoint: **~93.20% less CPU / 14.70x yield**;
- audited checkpoint: **~89.84% less CPU / 9.84x yield**.

## Corruption controls

Historical mutation inside the checkpointed prefix:

- carried checkpoint: intentionally still passes;
- audited checkpoint: detects prefix hash mismatch;
- full audit: detects invalid historical receipt.

Recent-tail corruption:

- carried checkpoint: detects;
- audited checkpoint: detects.

Tampered checkpoint metadata is rejected before use.

## Negative result / debt

Checkpoint creation currently performs a full receipt-history audit plus prefix SHA. This moves the linear work to checkpoint admission if done repeatedly.

That design is **not promoted** as the long-term writer path.

## Truth boundary

- checkpoint is audit acceleration metadata, not checkpoint/state authority;
- carried mode reuses prior verification and does not rediscover old-prefix corruption;
- audited mode re-establishes byte identity of the old prefix;
- one host/runtime/filesystem;
- CPU time is not joules;
- no claim of compute/energy from nothing.

## Next gate

Build the authorization audit segment proof live while receipts are committed, so checkpoint creation does not reread history.
