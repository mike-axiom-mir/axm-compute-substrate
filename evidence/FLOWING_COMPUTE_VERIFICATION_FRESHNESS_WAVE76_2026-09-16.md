# Flowing Compute Wave 76 — Verification Freshness / Explicit Audit Debt

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST EVIDENCE`

Wave 76 tracks verification freshness without inventing an audit cadence.

After 100 carried generations with no hidden limit:

- capability index audit age: **100 generations**; current artifact bytes under carried proof: **11,255,808**; cumulative rehash work skipped: **1,125,580,800 bytes**;
- dormant mesh audit age: **100 generations**; artifact bytes under carried proof: **15,137**.

These values are compute/freshness accounting, not corruption probabilities or risk scores.

An explicit test-only limit of 10 carried generations caused generation 11 carried reuse to return `HOLD_AUDIT_REQUIRED`. Audited reuse at generation 11 reset audit age to zero; generation 12 carried then had age 1. With no configured limit the tracker reports debt but does not force a policy.

Bookkeeping median: **13.07 microseconds CPU/generation** on this host.

Controls passed: no-limit reporting, explicit-limit HOLD, audit reset, and artifact/proof identity changes cannot inherit old freshness state.

Truth boundary: the explicit limit is configuration, not a recommendation; carried count is not corruption probability; cumulative skipped bytes are compute accounting; CPU time is not joules.
