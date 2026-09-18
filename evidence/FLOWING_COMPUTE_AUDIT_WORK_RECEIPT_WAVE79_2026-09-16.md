# Flowing Compute Wave 79 — Audit-Work Receipt Binding

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST REAL-MONOLITH-DERIVED EVIDENCE`

## Question

Can `audited_reuse` reset verification freshness only when the executor supplies evidence that the exact artifact bytes were actually read and matched the expected immutable identity?

Wave 78 made verification freshness independent per sleeping contract. Its remaining loophole was semantic: a caller could name `audited_reuse`, and the freshness transition itself had no direct proof that a full byte audit really occurred.

## Real workload

The positive case used the existing immutable capability-index artifact derived from the supplied AXM Connected Monolith execution fabric:

- contract: `axm.execution-fabric.capability-index/v0.1`
- capability-index artifact: **11,255,808 bytes**
- artifact SHA-256: `e676fafb2f825d946c10480ccd2184ab69daf9464ae77cf5703dfe59562644da`
- proof SHA-256: `0e90715689e43290371acc3d1608b58d179cd4c6e7bfc288b9bd41b718f353a2`
- source member: `AXM_Connected_Monolith_v0.4.30-WALMI-NATIVE-WIRING/EXECUTION_FABRIC.json`
- source member bytes: **39,055,991**
- source member SHA-256: `2f8f5f306b6790b3e8a4d58b2c00fd60eb5c18a3c4f6b40424000e26aa87ef6e`

The source member was streamed directly from the supplied monolith ZIP during the Wave 79 run. Its SHA-256 exactly matched the source identity already recorded by the capability proof.

## New contracts

### Audit-work receipt

`AXM_FLOWING_COMPUTE_AUDIT_WORK_RECEIPT.py` adds `axm.flowing-compute-audit-work-receipt/v0.1`.

Before reading the artifact, it derives a challenge over:

- exact contract identity;
- target generation sequence;
- predecessor freshness-state identity;
- artifact SHA-256 and byte length;
- proof SHA-256;
- explicit `audited_reuse` mode.

The audit then reads the complete artifact, hashes the bytes, counts the bytes/chunks read, and emits `AUDIT_PASS` only when the observed byte count and SHA-256 match the predecessor state exactly.

### Receipt-bound partial audit transition

`AXM_FLOWING_COMPUTE_RECEIPT_BOUND_PARTIAL_AUDIT.py` wraps the Wave 78 per-contract freshness transition without rewriting it.

For every contract planned as `audited_reuse`, a matching valid audit-work receipt is now mandatory. A carried contract is not allowed to carry an audit receipt because that would blur the evidence about what path actually happened.

If any receipt is missing/invalid, or if any other contract's freshness policy holds the generation, **no next freshness set is exposed**.

## Observed positive case

The real capability-index artifact was read completely:

- bytes read: **11,255,808 / 11,255,808**
- chunks read: **11** (1 MiB nominal chunk size)
- observed SHA-256: exact match
- audit receipt SHA-256: `fb65ba5ad5cc0f4c33a851957ccc42a4142c64a3d0815abb1a4f0886dbf4ecf2`
- measured audit CPU time: **8.543797 ms**
- measured audit wall time: **8.543712 ms**

At generation 1:

- capability index: `audited_reuse` + valid receipt -> audit age **0**;
- dormant FrameState mesh: `carried_immutable_proof` -> audit age **1**.

This closes the Wave 78 label-only reset loophole **inside this transition contract**: naming `audited_reuse` is no longer sufficient to reset freshness.

## Negative controls

All seven controls passed:

1. `audited_reuse` with no receipt -> `HOLD / AUDIT_RECEIPT_REQUIRED`.
2. A generation-1 receipt reused at generation 2 -> rejected as stale/sequence-mismatched.
3. `bytes_read` was reduced by one and the outer receipt digest was recomputed -> rejected for incomplete byte read.
4. A copy of the capability artifact had its final byte flipped -> the real audit returned `AUDIT_FAIL`; freshness could not reset.
5. A carried contract supplied with an audit receipt -> `HOLD / UNEXPECTED_AUDIT_RECEIPT`.
6. Capability audit valid, but another contract hit an explicit carry limit -> whole transition held and no partial freshness state was exposed.
7. Current supplied monolith `EXECUTION_FABRIC.json` -> streamed SHA exactly matched the capability proof source SHA.

The canonical immutable artifact was never mutated; corruption testing used a temporary copy.

## Truth boundary

- The receipt proves what this local tool run measured, not who ran it.
- `receipt_sha256` protects receipt integrity. It is **not** a secret-key signature, TPM quote, secure-enclave attestation, or remote proof of actor behavior.
- A forged actor with permission to fabricate both code and evidence is outside this receipt's trust boundary.
- The measured ~8.54 ms is one host/runtime observation, not a universal cost and not a joule/energy measurement.
- No audit cadence is recommended or silently introduced.
- `carried_immutable_proof` remains prior-proof reuse and can miss out-of-band corruption until a real audit occurs.
- No claim of compute or energy from nothing.

## Next gate

Bind the exact validated audit-receipt SHA map into the **atomic generation pointer** itself. A committed generation that says a contract's audit age reset to zero should also commit the exact receipt identity that justified that reset.

Negative controls for the next wave should reject: age-zero audited state with no receipt reference, a stale prior-generation receipt reference, a receipt attached to a carried contract, and crash/rollback states where generation/freshness/receipt references diverge.
