# Flowing Compute Wave 38 — Carried vs Audited Authorization Recovery

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST AUTHORIZATION-RECOVERY EVIDENCE`

## Question

Wave 37 preserves append-only authorization receipts, but current recovery walks the whole receipt chain and scans the receipt store. Can fast boot reuse previously verified authorization history while full audit remains available as a separate, more expensive contract?

## Pointer change

Wave 38 pointer size: **132 bytes**.

In addition to checkpoint identity, it carries:

- current receipt body offset;
- current receipt body length;
- current receipt SHA-256.

This allows a fresh process to direct-read the exact current receipt without indexing the whole append-only receipt store.

## Trust modes

`carried`

- validate current checkpoint;
- direct-read current receipt by pointer offset/length/hash;
- validate current receipt + exact current intent;
- reuse the fact that the older receipt chain was previously verified.

`audited`

- validate current checkpoint;
- walk and validate the complete authorization receipt chain and its intents/checkpoints.

Neither mode changes checkpoint authority; they differ in how much old provenance they re-establish now.

## Real chain corruption control

Three real explicitly authorized commits were reused: 2,048 -> 3,072 -> 4,096.

The oldest 2,048 authorization receipt was corrupted while current pointer / current checkpoint remained intact.

Observed:

- carried mode: still recovered **4,096**;
- audited mode: `HOLD_NO_VALID_POINTER_FOR_AUTHORIZATION_MODE`.

This is intentional. Carried mode cannot claim it rediscovered historical corruption it did not re-read. Audited mode spends compute to do so.

## Physical receipt-discovery scaling

A synthetic-but-contract-valid append-only receipt store with **10,000** receipt objects was built in one batch write to avoid measuring fixture fsync cost.

- store size: **6,977,672 bytes**;
- full ReceiptStore parse/index CPU median: **~124.99 ms**;
- direct current-receipt read CPU median: **~0.0152 ms**;
- discovery CPU reduction: **~99.988%**;
- discovery yield: **~8,233x**.

This benchmark measures physical discovery/index cost, not semantic authorization audit of 10,000 real checkpoint transitions.

## Truth boundary

- carried authorization proof assumes previously verified immutable history remains valid;
- carried mode does not rediscover corruption in old receipts;
- audited mode is the re-establishment path;
- the 10k scaling body is synthetic receipt growth under the receipt format, not 10k organic AXM authorization events;
- hashes prove integrity/identity, not external authorization meaning;
- one host/runtime/filesystem;
- CPU time is not joules;
- no claim of compute/energy from nothing.

## Next gate

Make full authorization audit scalable too. Add segment/checkpoint proofs for authorization receipts so audit can verify bounded recent history plus previously audited immutable receipt segments, with an explicit full-from-zero audit still available.
