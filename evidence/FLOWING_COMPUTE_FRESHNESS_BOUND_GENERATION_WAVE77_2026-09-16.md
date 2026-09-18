# Flowing Compute Wave 77 — Atomic Generation + Verification Freshness

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST COMMIT EVIDENCE`

Wave 77 binds verification-freshness state to the same atomic pointer that selects the current generation.

Observed:

- before G1 commit: current G0, mesh/capability audit ages both **0**;
- crash before pointer move: G0 and both ages remain 0;
- commit G1 with carried reuse: G1 and both audit ages become **1** together;
- audited G1 alternative: both audit ages commit as **0**.

A freshness-state tamper was made while recomputing the outer pointer hash. The nested freshness-state hash still rejected it.

This prevents a split state where a generation advances but its verification-freshness evidence remains on a different sequence. Freshness remains evidence and never grants commit authority itself.
