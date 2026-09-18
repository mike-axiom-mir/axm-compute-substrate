# Flowing Compute Wave 83 — Four-Root Drop Gate + Concurrent Retention CAS

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST AUTHORIZATION-GATE / CONCURRENT-POINTER EVIDENCE`

## Question

Wave 82 made rollback-root removal explicit and predecessor-bound, but its drop receipt intentionally did **not** establish authorization. It also left concurrent writers unresolved. Wave 83 asks two narrower questions:

1. Can a rollback-root drop be refused unless an explicit four-root evaluation receipt is bound to the exact predecessor, checkpoint, and drop receipt?
2. Can two writers starting from the same current retention generation race without both gaining current-pointer authority?

## Exact prior state / provenance

Wave 83 deliberately starts the current-pointer test from the exact Wave 81 retention body because Wave 82's G1 root drop was explicitly a **test-only generation**, not a canonical promotion:

- predecessor retention SHA-256: `53d91b18e1a12eb27bd503bcfa70b4cd74add598ceaef522c88d7c075fdee4d4`
- older rollback checkpoint: `a28948258187a3e43e3b7841d71494e065894bacb79e70493df459aa47514799`
- later retained checkpoint: `43a63855b44b5a4983abc4cde38633550a6b36dc64c615c49bc924eeb63b0826`
- exact Wave 82 drop-receipt SHA-256 reused: `9a60bbfb8302bbdc4e06eb39fd7898366b5fc1ef3963978dd857b845946b31a0`

No monolith artifact was reread in Wave 83. The Wave 79 11,255,808-byte audit remains prior evidence only; this wave studies retention authorization mechanics and pointer concurrency.

## Reusable contract

`tools/AXM_FLOWING_COMPUTE_RETENTION_AUTH_CAS.py` extends the Wave 82 retention model with:

- an explicit `root-evaluation` receipt covering **Truth**, **Agency / non-domination**, **Continuity**, and **Wisdom before speed**;
- exact binding from that receipt to predecessor retention identity, drop-receipt identity, checkpoint identity, and next retention sequence;
- nested evidence hashes that must still match their embedded facts even if the outer receipt is rehashed;
- an authorized-retention candidate format where every removed rollback root needs both its drop receipt and its root-evaluation receipt;
- a content-addressed staging store where candidate evidence may exist without being current;
- a single-host POSIX compare-and-swap pointer using `flock`, fsynced temporary writes, and atomic `os.replace`.

The four-root receipt is intentionally marked **test-only**. It proves that the mechanical gate was traversed with explicit evidence identities. It does **not** prove actor identity, cryptographic signer identity, external authorization, or that the test PASS judgments are canonical AXM root judgments.

## Positive result

Two different sequence-1 candidates were built from the same exact predecessor:

- DROP candidate: `4078169dce33c5816c7dd1073eaff5920bcfb07284a023726322e67970378dd1`
- KEEP candidate: `0f918393dc9d4dfb33fe150bbdca9bd4ecbdca8fab0317becdf94fb9296b1721`
- test-only four-root evaluation receipt: `14702460c18e02f50ab09d45b420d4d3188960bde588cc89fad06211bf8fa4ee`

The DROP candidate could not be constructed without an ALLOW result across all four explicit root entries. The KEEP candidate requested no root removal and therefore did not receive a fake drop authorization.

A staged candidate had **zero current-state authority** until the mutable retention pointer moved to its exact content hash.

In **40 true same-host two-process races**, both writers began with the same predecessor expectation. Every race produced exactly:

- **1 `COMMITTED` writer**;
- **1 `CONFLICT` writer**.

Observed scheduling produced 2 DROP wins and 38 KEEP wins in this run. This distribution is **not** a fairness claim; the useful result is only that both candidate types did win at least once and no race produced two current winners.

The losing candidate and its evidence remained present in the content-addressed store but gained no pointer authority merely by existing.

## Negative / crash controls

The Wave 83 self-test passed **17/17** positive/adversarial controls. It rejected:

- a root drop with no root-evaluation receipt;
- a `HOLD` from even one of the four root entries;
- a root-evaluation receipt rebound to the wrong drop receipt even after recomputing its outer hash;
- outer root-evaluation tampering;
- an embedded root fact rewritten without its matching nested evidence identity;
- retention-pointer tampering.

A simulated crash after the new pointer body was written and fsynced to a temporary file but **before atomic replacement** left the exact predecessor current. The staged candidate remained evidence only. Normal retry could then commit it.

Sequential stale-writer controls also passed in both directions: if DROP committed first, KEEP conflicted; if KEEP committed first, DROP conflicted. The mechanism does not grant special CAS priority to the more destructive proposal.

## Important counterexample found — ABA

Wave 83 also found a real boundary that must remain visible.

The current CAS compares the **retention content identity**. If some separate rollback mechanism later restores the pointer to the exact same predecessor body, an old writer that was prepared before the intervening state change cannot tell that history advanced and returned.

A direct control reproduced this:

1. start at Wave 81 retention `53d91b...`;
2. commit the DROP candidate;
3. simulate restoration of the exact same Wave 81 pointer body;
4. retry an old KEEP writer still expecting `53d91b...`;
5. that stale writer **commits successfully**.

This is the classic ABA problem. It does not invalidate the same-generation one-winner result above, but it means content identity alone is insufficient once rollback can legitimately return to an older body.

## Cost

Across **100** synthetic local successful CAS commits, median measured **process CPU time** was about **250.643 microseconds** on this host.

This number is deliberately narrow:

- it is a synthetic infrastructure benchmark, not a monolith workload;
- process CPU time excludes time spent blocked waiting for filesystem I/O and is therefore **not end-to-end commit latency**;
- it is not an energy measurement and CPU time is not joules.

## Truth boundary

- Four-root PASS rows in this wave are **test fixtures**, not canonical AXM constitutional determinations.
- Hashes prove content identity/integrity under this contract; they do not establish who evaluated the roots or whether that evaluator was legitimate.
- `flock + os.replace` is a single-host POSIX mechanism, not distributed consensus and not a claim about NFS or multi-host behavior.
- No garbage collection ran in Wave 83.
- No fresh monolith audit ran in Wave 83.
- The observed race win ratio is scheduler noise, not a fairness guarantee.
- The ABA counterexample is preserved rather than hidden.
- No canonical merge, canon rewrite, or automatic promotion occurred.
- No physical-energy or over-unity claim is made.

## Next gate

**Wave 84: ABA-safe retention pointer epochs.** Add a monotonic pointer-generation / commit-epoch identity that never rewinds when an older retention body is selected. CAS must compare the exact pointer epoch as well as the retention object, so a stale writer prepared before `A -> B -> A` cannot commit after the return to A. Test explicit rollback-to-old-content, process crashes, concurrent writers across rollback, and recovery without making rollback itself impossible.

A later gate still remains for evaluator provenance: Wave 83 proves an explicit four-root mechanical gate, not independent evaluator legitimacy.
