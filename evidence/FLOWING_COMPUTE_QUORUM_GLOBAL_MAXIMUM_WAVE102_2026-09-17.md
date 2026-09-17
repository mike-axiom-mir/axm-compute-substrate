# Flowing Compute — Wave 102 quorum-global maximum

Status: **experimental, unmerged, no CANON promotion**. Lane: `chatgpt/lane-001-platform-extract` / PR #2.

## Why Wave 102 changed direction

Independent verifier PR #26 found a narrower rollback failure after Wave 101. Epoch 2 could become authoritative on remote A+B while C remained at epoch 1. If the local current pointer and only B were later restored to epoch 1, A still retained `[1,2]` and the newer local authority/checkpoint bodies still existed, but Wave 101 counted stale B plus lagging C as a fresh 2-of-3 quorum for epoch 1. Per-witness monotonic history therefore was not yet a quorum-global remembered maximum.

Exact predecessor/provenance: Wave 101 builder head `08bed3007e118fdcc2499c873da85ed9355c96d2`; tool blob `9283b748aefcc1914eb763748674ee83a5ec3b15`; self-test blob `4bddbd849319b7475ac399dd96cd72ceb498545a`; verifier PR #26 head `c0c5b718b1ad77f4685045e290d6c7021f4786ca`; verifier evidence blob `4ce07288e73d9a288c026a771f598585c698c090`; reproducer blob `2d5fc38bd07ebe3c172f02496b41b7c7a469a6f0`.

## What changed

Wave 102 adds an append-only, content-addressed, predecessor-linked **quorum certificate maximum**. The maximum advances only after the exact local authority is present on the registered 2-of-3 remote quorum and an explicit certificate is appended. A certificate binds the authority epoch/SHA, checkpoint SHA, registry SHA, exact sealed supporting remote records, certificate sequence, and predecessor certificate SHA.

This keeps an important distinction: **newer seen is not the same as newer accepted by quorum**. A record visible only on one witness does not gain finality. But after a newer authority actually reaches quorum and is certified, an older local world cannot become authoritative merely because two stale/lagging witnesses happen to match it. The exact PR #26 attack now returns `HOLD_QUORUM_GLOBAL_MAXIMUM_AHEAD`, including when the intact newer witness is temporarily unavailable.

Reusable tools are `tools/AXM_FLOWING_COMPUTE_QUORUM_GLOBAL_MAXIMUM.py` and `tools/AXM_FLOWING_COMPUTE_QUORUM_GLOBAL_MAXIMUM_SELFTEST.py`. Protocol commit: `ffb77dd75501b941fcce8fe81ee842927a35ecca`; protocol blob: `8bd23cf3db02ba90161f4a7c38f36dca3f3b2733`. Final tested self-test commit/head: `8760b37bdd0a554f87d6f7f8eaaecc7be8ad11f5`; final self-test blob: `cc53bd23732acc31e8b85f0998187fba979c8a89`.

## Verification and failure evidence

The first CI run is intentionally preserved. Wave 101 regression passed 27/27, while Wave 102 reported 32/33 because the `same_sequence_sibling_certificate_rejected` **negative test was constructed incorrectly**: changing its authority SHA made support-binding verification reject the object before the intended duplicate-sequence gate. Nothing was rewritten. Append-only repair commit `8760b37...` changed the test to an individually valid resealed sibling with the same sequence so the intended store-level conflict was actually exercised.

Final CI run `35172195500` on exact head `8760b37bdd0a554f87d6f7f8eaaecc7be8ad11f5` passed. Normal Python: Wave 101 regression **27/27**, Wave 102 **33/33**. `python -O`: Wave 101 regression **27/27**, Wave 102 **33/33**. Negative controls cover the exact PR #26 rollback, newer-witness outage after certification, mutable certificate-head rewind, missing predecessor, certificate-body tamper, support-record tamper, same-sequence sibling conflict, and the intentionally permitted case where a one-witness newer state never reached quorum.

Synthetic authority bookkeeping medians were about **59.2–62.8 ms CPU** on one CI runner and **107.1–118.5 ms CPU** under `python -O` on another CI runner across retained depths 1/4/8. These are explicitly **synthetic single-process protocol timings**, and the different hosted runners make them unsuitable as a normal-vs-optimized performance comparison. They are not AXM/monolith workload, network, energy, retained-compute, incremental-compute, or dormant-compute evidence.

## Counterexamples kept alive

All three remote witnesses and the quorum-certificate store are still Python state in one process. Rolling local runtime, the certificate store, and enough modeled witness stores back together can still reconstruct an internally valid old world. The certificate store is not independently authenticated: hashes detect mutation/broken lineage in retained objects, but wholesale malicious replacement of the modeled store is not independently detectable here. Remote credentials remain symmetric test tokens, quorum support is integrity evidence rather than independent public-key service attestation, and two compromised current remote credentials remain inside the modeled 2-of-3 attack/availability surface. Mechanical quorum chronology also says nothing about moral/root judgment correctness, consent, evaluator legitimacy, or CANON authority.

## Next gate

**Wave 103: real OS-process separation.** Move the quorum-certified maximum plus repaired registry/authority chronology across at least three separate OS processes with separate durable stores and separately held credentials. Attack kill/restart, stale durable-store restoration, partition/reconnect, partial publication before versus after quorum certification, certificate-store rollback, credential rotation, one-process quarantine, two-process compromise, and recovery with one certificate witness unavailable. Even a successful Wave 103 will count only as process-level separation evidence, not physical/provider independence.
