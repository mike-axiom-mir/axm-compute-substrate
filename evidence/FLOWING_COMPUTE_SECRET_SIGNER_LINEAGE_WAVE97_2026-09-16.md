# Flowing Compute Wave 97 — secret-seeded checkpoint signer lineage

Date: 2026-09-16  
Lane: `chatgpt/lane-001-platform-extract`  
Status: experimental research only; append-only evidence; no merge/CANON authority.

## Exact source / provenance identity

Wave 97 continues from exact Wave 96 builder head `f9599f45f8fc3d4f028157eab28b89e3b7962395`, Wave 96 tool blob `ab7a57af1f5259e893aaa14c6f17f40a064cc801`, and Wave 96 report blob `f55152574d076a56a710a9f4f3bcae0295ddeb0c`.

It incorporates independent verifier PR #21 at exact head `2933d68ab47577aa4afd52392ba10d832c1d7e11`, evidence blob `ea58ded87d0d91471898054e8772438ee100d1fc`. That verifier showed that Wave 96's Lamport "private" preimages were reproducible from public source labels and that a checkpoint could become authoritative while naming nonexistent successor signer bodies.

Wave 97 reusable tool: `tools/AXM_FLOWING_COMPUTE_SECRET_SIGNER_LINEAGE.py`, blob `f5ca09a21e64ec390c15e5825751d0d6977d023d`, introduced by commit `2db578d97de978c978dddcfbb56639872af32d68`.

Machine-readable report: `evidence/FLOWING_COMPUTE_SECRET_SIGNER_LINEAGE_WAVE97_REPORT.json`, blob `9e5fcdba8c6dbac9916c2fefd2c05f78e34ed31b`, introduced by commit `75f81093812c507a8a6b2e9f3d326717e2289be2`.

No verifier branch was merged or rewritten.

## What changed

Checkpoint Lamport preimages are now derived from a fresh 32-byte secret generated with Python `secrets.token_bytes(32)`. Public root/generation/index/bit metadata is domain-separated but no longer sufficient to regenerate the preimage. The secret seed lives only in a separate private signer store; the content-addressed public-key body contains only hashes and lineage metadata.

Checkpoint acceptance now resolves every successor signer body before authority can move. Each successor must exist under its exact content address, name the correct AXM root, advance exactly one signer generation, point to the exact current signer as predecessor, and remain unique across the four roots. Missing or malformed future signer state therefore fails now rather than poisoning the next checkpoint.

One-time signer consumption is no longer represented only by an in-memory `used` set. Each checkpoint has a content-addressed `signer-use/v1` batch bound to its exact checkpoint and signer set. The use batch is predecessor-chained and included in a content-addressed authority link. The authority link is what the three local witnesses converge on. Deleting committed use state makes current authority fail closed.

A signer is also reserved to the exact prepared checkpoint in the private store before another normal sibling prepare is allowed. This is a local crash/retry aid, not a claim of hardware-enforced anti-exfiltration.

## Positive and negative controls

Two exact-source local runs completed with **25/25 controls passing** each: one normal Python run and one `python -O` run.

Controls include the exact Wave 96 public-label regeneration recipe failing against the new secret-seeded keys; missing successor bodies rejected before authority; wrong successor generation rejected; already-prepared signers refusing a second normal prepare; public verification still succeeding after spent private seeds are erased; partial three-witness fan-out remaining non-authoritative; exact checkpoint/use/predecessor rotation across two checkpoint generations; missing use evidence blocking commit; committed use-evidence deletion making authority `HOLD`; direct old-authority replay rejection; and a surviving modeled external anchor detecting local rollback.

The all-current-key compromise is deliberately preserved as a **passing counterexample control** rather than hidden: if an attacker has copies of all four current private signer seeds before authoritative publication, the attacker can construct a different fully valid checkpoint and win first publication in this model. Secret-seeded signatures prove possession of modeled signing material, not that the signer was uncompromised or morally/canonically correct.

## Synthetic timing boundary

Wave 97 does **not** read a fresh AXM/monolith workload. The newest evidence forced a cryptographic/authority repair before stronger remote-witness work, so the measured work is explicitly synthetic single-host checkpoint bookkeeping.

Normal five-round run: checkpoint prepare median `78,462.516 µs` process CPU; public verification plus use-chain validation median `29,842.027 µs`.

Optimized-Python five-round repeat: checkpoint prepare median `50,827.118 µs` process CPU; public verification plus use-chain validation median `18,748.875 µs`.

The spread is visible rather than averaged away. These timings include Python Lamport key/signature work, are not remote latency or joule measurements, and are not evidence that retained, incremental, or dormant compute wins. Lamport OTS is intentionally a simple test model, not a performance or production-cryptography recommendation.

## Truth boundary / what still fails

- Compromise of all four current private signer seeds before authoritative publication can still mint a valid competing checkpoint and win the first-publish race in this model.
- Rolling back local authority state and the modeled external anchor together still produces an internally self-consistent old world.
- The external anchor remains a separately supplied in-model state domain, not a physically independent device, monotonic hardware counter, timestamp authority, or separately credentialed remote service.
- Crash-atomic durable persistence of private signer reservation, authority witness fan-out, and external publication is not proven across real filesystems/devices.
- Random secret seeds and valid signatures establish only modeled key possession. They do not prove evaluator legitimacy, root correctness, human consent, identity, or canonical AXM authority.
- No fresh monolith workload, compute-efficiency, energy, retained-state, incremental-state, or dormant-state win is claimed.

## Next gate — Wave 98

Move the checkpoint authority/consumption head into a **genuinely independent monotonic failure domain**, preferably two independent remote/device witnesses rather than another same-process list. Then attack remote credential compromise, stale-anchor replay, network partition, conflicting witness histories, partial publication, one witness unavailable, and recovery after reconnect.

Keep the all-current-signer compromise counterexample visible. A remote witness can improve rollback/equivocation detection; it must not be described as distributed consensus, signer legitimacy, or solved anti-rollback unless the actual failure domains and credentials justify that claim.
