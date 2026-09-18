# Flowing Compute Wave 82 — Predecessor-Bound Retention + Crash-Safe GC

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST RETENTION / GC TRANSACTION EVIDENCE`

## Question

Wave 81 made audit receipts recoverable from explicit rollback checkpoints, but it also exposed a dangerous boundary: once retention policy drops a checkpoint, the receipt behind that checkpoint can become collectible. Wave 82 asks whether retention changes themselves can become append-only, predecessor-bound evidence, and whether garbage collection can fail safely across crashes and stale retention views.

## Exact prior state / provenance

Wave 82 starts from the exact published Wave 81 retention identity, reconstructed from its two known rollback checkpoint roots:

- Wave 81 retention SHA-256: `53d91b18e1a12eb27bd503bcfa70b4cd74add598ceaef522c88d7c075fdee4d4`
- older rollback checkpoint: `a28948258187a3e43e3b7841d71494e065894bacb79e70493df459aa47514799`
- retained later checkpoint: `43a63855b44b5a4983abc4cde38633550a6b36dc64c615c49bc924eeb63b0826`
- real prior Wave 79 monolith audit receipt behind the older checkpoint: `fb65ba5ad5cc0f4c33a851957ccc42a4142c64a3d0815abb1a4f0886dbf4ecf2`
- Wave 81 second audit receipt behind the later checkpoint: `27dc30ebd1172695c8873cb919efc59de9adde8a546533b64f6b7d6199c4ca1b`

The Wave 79 receipt remains real prior evidence for the **11,255,808-byte monolith-derived capability-index audit** established in Wave 79 and preserved through Wave 81. Wave 82 does **not** reread that artifact or revalidate receipt bodies; it tests retention/GC transaction semantics against their exact published identities.

## Reusable contract

`tools/AXM_FLOWING_COMPUTE_RETENTION_GC_MODEL.py` preserves the deterministic, non-destructive planner/validator for append-only retention generations, predecessor-bound drop receipts, receipt reachability, exact-inventory GC marks, stale-mark rejection, missing-evidence refusal, and crash-recovery decisions. The measured Wave 82 probe additionally exercised stage / sweep-commit / recovery against a temporary local filesystem; the repository model intentionally returns the permitted transition instead of deleting host files.

A drop receipt records explicit test intent. It is **not** actor authentication, constitutional/root approval, or authority merely because it exists.

## Positive result

A test-only G1 explicitly removed the older Wave 81 rollback root. That change was accepted only with a matching drop receipt tied to the exact Wave 81 predecessor:

- G1 retention SHA-256: `f9cb087d701268b4f7eb660161776f37d46d312f0e46c1fbc883c46a452d3eb5`
- G1 predecessor: `53d91b18e1a12eb27bd503bcfa70b4cd74add598ceaef522c88d7c075fdee4d4`
- drop receipt SHA-256: `9a60bbfb8302bbdc4e06eb39fd7898366b5fc1ef3963978dd857b845946b31a0`

Under G1, GC marked exactly the now-unreachable real Wave 79 receipt as the candidate and kept the Wave 81 second receipt reachable. A committed sweep then removed that candidate while preserving the still-retained receipt.

The probe also built G2, which re-added the old rollback checkpoint *before* collection. The old G1 GC mark immediately became stale and was rejected. After the receipt had genuinely been purged under G1, attempting to select G2 was refused because G2 would point at missing recovery evidence.

## Negative / crash controls

All **15/15** controls passed. Silent root removal, wrong-predecessor drop receipts, retention-body tamper, missing referenced drop receipts, stale receipt inventories, stale marks after a rollback root becomes reachable again, and skipped predecessor chains all failed closed. A crash before retention-pointer movement left Wave 81 current; a crash after staging but before sweep commit restored the staged receipt; and a crash after sweep commit completed the purge only under the exact retention generation that authorized it.

## Cost

Over **1000** local iterations, GC mark planning against exact current retention generation with two receipt-key envelopes had median CPU time of about **150.489 microseconds** on this host.

This benchmark excludes receipt-body revalidation and underlying artifact rereads. CPU time is not joules.

## Truth boundary

- Wave 82 uses exact prior Wave 81 / Wave 79 evidence identities but does not claim a fresh monolith audit.
- The small receipt files used by the Wave 82 transaction harness are receipt-key envelopes, not replacements for Wave 81 receipt-body validation.
- A hash proves content integrity under this local contract; it does not prove who authorized a rollback-root drop.
- The test-only root drop demonstrates mechanics, **not a recommendation to discard rollback history**.
- A GC win is not assumed: if evidence becomes reachable again before collection, the stale GC path loses authority and must stop.
- No canonical branch merge, canon rewrite, or automatic promotion occurred.
- No physical-energy or over-unity claim is made.

## Next gate

**Wave 83: drop authorization + concurrent-writer CAS.** Bind rollback-root drop intent to an explicit authorization/root-evaluation receipt, then make the current-retention pointer compare-and-swap against its exact predecessor so two writers cannot both successfully advance from the same retention generation. Test conflicting add/drop proposals, crash recovery, and make the losing writer preserve its evidence without gaining pointer authority.
