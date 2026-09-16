# Flowing Compute Wave 50 — FrameState Dormant-Asset Compile Break-Even

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST ROUTING EVIDENCE`

Dormant mesh compile setup includes full source SHA-256, native OBJ parse, canonical parsed-mesh serialization, zlib compression, checksummed container construction, and durable temp write/fsync.

Median over 31 trials:
- setup CPU: **~6.87 ms**;
- dormant artifact: **15,137 bytes**.

Wave-49 single-frame fresh-process medians:
- cold: ~24.66 ms CPU;
- dormant: ~20.69 ms;
- saving: ~3.97 ms/start.

Independent 18-worker data implies ~4.10 ms/start saving.

Measured CPU break-even: **about 2 future fresh workers**.

Policy:
- dormant artifact already exists -> use dormant path;
- expected 1 fresh worker -> cold parse;
- expected >=2 compatible fresh workers -> compile dormant artifact;
- long-lived single-process rendering is a different contract and is not forced through this worker-start rule.

Truth: expected future workers are an input/estimate, not a fact; CPU-only; hardware joules unavailable; no universal compile-everything rule.
