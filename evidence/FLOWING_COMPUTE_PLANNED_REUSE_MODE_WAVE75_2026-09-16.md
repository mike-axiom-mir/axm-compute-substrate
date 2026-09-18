# Flowing Compute Wave 75 — Planned Reuse Verification Mode

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST PLAN/TRUST-MODE EVIDENCE`

## Question

Can unchanged-contract reuse declare its trust mode in the plan itself, so an executor cannot silently take the cheaper carried-proof path while the plan claims a fresh audit?

## Result

The G0→G1 four-contract generation was validated in two explicit reuse modes for the unchanged FrameState mesh and capability index. Changed graph/snapshot artifacts remained strongly validated in both modes.

- carried reuse validation median: **0.1117 ms CPU**;
- audited reuse validation median: **7.335 ms**;
- audit/carried multiplier: **65.6x**.

## Controls

All passed:

- plan says audited, execution receipt says carried -> rejected before artifact verification;
- out-of-band capability-artifact corruption remains invisible to carried mode by design;
- audited mode rereads the artifact and rejects the corruption.

## Interpretation

The generation evidence now distinguishes not only **update vs reuse**, but also **how reuse was verified**.

`carried_immutable_proof` and `audited_reuse` are different claims with different compute costs. The executor does not get to silently substitute one for the other.

## Truth boundary

- carried mode is prior-proof reuse, not fresh byte verification;
- audited mode spends compute to re-establish strong artifact byte identity;
- the audit interval/freshness policy is not yet chosen by this experiment;
- one host/runtime; CPU time is not joules;
- no claim of compute or energy from nothing.

## Next gate

Track explicit verification freshness/debt across repeated carried generations: last strong audit generation, carried generations since audit, and bytes protected only by carried proof. Any audit cadence must be explicit policy/configuration rather than silently invented by the executor.
