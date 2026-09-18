# Flowing Compute Wave 51 — Dormant Execution-Fabric Capability Truth Index

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST REAL-MONOLITH EVIDENCE`

## Source
`EXECUTION_FABRIC.json`: **39,055,991 bytes**, SHA-256 `2f8f5f306b6790b3e8a4d58b2c00fd60eb5c18a3c4f6b40424000e26aa87ef6e`, **23,705 endpoints**.

Wiring truth is preserved verbatim:
- callable: 22
- addressable_probe_hold: 210
- addressable: 252
- addressable_not_callable: 23,221

The dormant index stores a bounded exact projection for every endpoint. It does not upgrade callability.

## Artifact / exhaustive equality
SQLite-backed local index: **11,255,808 bytes**, ~71.18% smaller than the 39 MB source. Setup (full source SHA + parse + index build): **~724.54 ms CPU**.

All **23,705/23,705** endpoint projections matched the source exactly.

Activation-ticket decisions also matched source truth exactly:
- READY_VERIFIED_NATIVE_COMMAND: 22
- HOLD_PROBE_NOT_VERIFIED: 210
- HOLD_ADDRESSABLE_ONLY: 252
- HOLD_NOT_CALLABLE: 23,221

Tickets do not execute commands.

## Fresh-process operation CPU (5 trials)
One exact endpoint:
- cold parse+lookup: **161.37 ms**
- dormant lookup: **0.475 ms** -> **99.71% less / ~340x**
- dormant + full 39 MB source SHA recheck: **25.64 ms** -> **84.11% less / ~6.29x**

16 stratified endpoints: 168.65 ms -> 0.819 ms dormant; 25.83 ms audited.

128 deterministic endpoints: 168.93 ms -> 3.104 ms dormant; 27.93 ms audited.

Setup amortization:
- carried dormant: ~**5 fresh starts**;
- full-source-audited dormant: ~**6 fresh starts**.

If shipped/present, compile debt is already paid.

## Truth boundary
Lookup/ticket evidence is not command execution evidence; callable status is inherited from the source registry and was not independently re-probed here. SQLite is an experimental backend, not claimed final cartridge format. CPU is not joules; no compute/energy-from-nothing claim.
