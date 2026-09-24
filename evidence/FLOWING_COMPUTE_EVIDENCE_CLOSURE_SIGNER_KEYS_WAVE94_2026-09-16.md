# Flowing Compute Wave 94 — evidence closure + signer-key lineage

Date: 2026-09-16  
Lane: `chatgpt/lane-001-platform-extract` / PR #2  
Status: experimental evidence only; keep open/unmerged; no canon or automatic-merge authority.

## Exact predecessor / verifier provenance

Wave 94 continues from the exact Wave 93 builder head and consumes the newest independent Wave 93 verifier failure before extending the model.

- Wave 93 builder head: `24c3597089097d67b5f2972beb11d51a764bee12`
- Wave 93 tool: `tools/AXM_FLOWING_COMPUTE_TRANSITION_ATTESTATION_HISTORY.py`
- Wave 93 tool blob: `bd34149b4370973b56a2ab213ae9e1f1adc2ae0e`
- Wave 93 tool SHA-256: `4ab6553768a23dcbff16255763f92f89f00179eff1fde6915692fc17301522a3`
- Independent verifier PR #18 head: `9e58b601c39eabcb619b3cb6b784e7d2e95dffac`
- Verifier evidence: `verification/WAVE93_ADVERSARIAL_VERIFICATION_2026-09-16.md`
- Verifier evidence blob: `ba10e7b2bfee6eb22975d45b9eaa369d910099a7`
- Verifier finding: `FAIL_COMMITTED_HISTORY_CAN_EXTEND_OVER_MISSING_PREDECESSOR_BODIES`
- Verifier workflow run: `35127370580`

Wave 94 reusable artifacts are preserved as new append-only files:

- `tools/AXM_FLOWING_COMPUTE_EVIDENCE_CLOSURE_SIGNER_KEYS.py` — Git blob `4b086ac98331a63e21292d3f11e65b3868c9204c`
- `evidence/FLOWING_COMPUTE_EVIDENCE_CLOSURE_SIGNER_KEYS_WAVE94_REPORT.json` — Git blob `c51d46000f579814d3dfcb12daa1f5c342968045`

## What changed

The Wave 93 verifier showed that a current state could keep hashes of already-committed predecessor evidence, lose the actual predecessor history/attestation bodies, remain `AUTHORITATIVE`, and then extend that dangling chain with another normal commit. Wave 94 therefore makes retained evidence availability part of authority instead of treating a hash reference alone as sufficient.

For the retained horizon modeled here, authority now walks the full history chain back to genesis and verifies exact content-addressed key/body identity at every step. Each active root attestation head is also resolved and walked back to sequence 1. Missing immediate or older retained bodies fail closed before a new transition can extend the chain.

Wave 94 also adds explicit signer-key state. Every root has a current content-addressed signer-key record. Key replacement is predecessor-bound: the new key names the exact old key, and the rotation receipt for that transition must be authenticated by the predecessor key. The authority tuple becomes `(history, attestation state, signer-key state)` and all three modeled witnesses must agree on that exact tuple. Partial fan-out remains non-authoritative, while exact predecessor evidence can resume it.

The key-control mechanism is deliberately a **symmetric HMAC-SHA256 test model**. It demonstrates possession/control of fixture key material inside this experiment. It is not public-key identity, production key management, actor authentication, or proof that a root judgment is correct.

## Result

Two independent exact-source runs passed **31/31 controls each**.

Positive controls covered genesis authority, normal generation commits, predecessor-authenticated key rotation, use of the new current key after rotation, restoration of removed evidence, and exact three-witness partial recovery.

Negative/adversarial controls covered deletion of an already-committed immediate attestation body, deletion of an older attestation body, deletion of predecessor history bodies, missing signer-key lineage bodies, use of old key material after rotation, visible same-sequence equivocation, missing required witnesses, and attempts to extend over dangling retained evidence.

Synthetic single-host validation/bookkeeping medians over 100 rounds were **11662.811 us** and **10535.928 us** process CPU. These numbers are not wall-clock storage/network latency, joules, or a retained/incremental/dormant-state efficiency result.

## Preserved failures / truth boundary

Wave 94 intentionally keeps several failures visible:

- possession of the **current symmetric key** is enough to mint structurally valid test evidence; therefore this proves modeled key control only, not human/AI identity, canonical authority, or root correctness;
- same-sequence equivocation is detectable only when competing evidence is visible in the modeled store;
- rolling back the runtime plus **all** modeled evidence/key stores together can still recreate an internally valid old world;
- requiring complete retained closure means old evidence cannot be silently garbage-collected. There is no authority-bound compaction/checkpoint cut yet.

No fresh AXM/monolith workload was reread in Wave 94. No compute-efficiency, retained-state, incremental-state, dormant-state, energy, distributed-consensus, scaling, public-key-signature, actor-identity, canonical-root-judgment, or moral-legitimacy claim is made.

## Next gate — Wave 95

Make deliberate history/attestation compaction an **authority-bound checkpoint operation** instead of requiring every historical body forever. A checkpoint should explicitly bind the retained cut, exact live authority tuple, key lineage, and predecessor checkpoint, and garbage collection should be explainable by that checkpoint rather than by silent deletion.

Then attack stale checkpoint reuse, omitted pre-cut evidence, malicious cut points, key rotation across a compaction boundary, and rollback of both live state and checkpoint. After that, move anti-rollback witnessing into a genuinely separate failure domain and consider public-key signatures without conflating key identity with root correctness.
