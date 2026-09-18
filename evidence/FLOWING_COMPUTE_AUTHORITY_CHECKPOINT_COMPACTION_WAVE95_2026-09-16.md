# Flowing Compute Wave 95 — authority-bound checkpoint compaction

Date: 2026-09-16  
Lane: `chatgpt/lane-001-platform-extract`  
Status: experimental research only; append-only evidence; no merge/canon authority.

## Source identity

Wave 95 continues directly from builder Wave 94 head `340fd44141b40493b0ddd7a51fd653ada9ddf9b8`, tool `tools/AXM_FLOWING_COMPUTE_EVIDENCE_CLOSURE_SIGNER_KEYS.py`, blob `4b086ac98331a63e21292d3f11e65b3868c9204c`.

It also incorporates independent verifier PR #19 at head `50212ef804bf9a545f930af55584ba7ff1d4fc75`, evidence blob `af5669da6f9c16a471ff45d6ae7b17429c36a8d1`, workflow run `35133408523`, finding `FAIL_ATTESTATION_AND_KEY_STATE_PREDECESSOR_BODIES_CAN_DANGLE_AND_HISTORY_CAN_EXTEND`.

No verifier branch is merged or rewritten by this wave.

## What changed

Wave 94 walked retained history, active attestation, and signer-key lineage, but PR #19 showed that the explicit predecessor chains of `att-state/v1` and `key-state/v1` could still dangle.

Wave 95 makes all five visible authority-history families explicit before compaction: history objects, attestation-state snapshots, signer-key-state snapshots, per-root attestation chains, and per-root key lineage. Before a checkpoint can exist, all five must close to genesis with exact content-address key/body identity. The PR #19 deletion attack now makes current authority `HOLD`, prevents another transition, and prevents checkpoint creation.

A checkpoint binds the exact live authority tuple, registry generation, all four attestation heads, all four key heads, and a digest/count manifest of the verified pre-cut closure. All three required checkpoint witnesses must converge on that exact checkpoint identity before it becomes authoritative. Partial or competing checkpoint fan-out stays non-authoritative.

After a committed checkpoint, pre-cut bodies are intentionally allowed to be pruned. Validation uses the checkpoint as the explicit historical cut and still requires exact post-cut closure back to that cut. This is deliberate compaction, not silent dangling history.

## Positive and negative controls

Two exact runs completed with **29/29 controls passing** each.

Important controls include:

- PR #19 dangling predecessor `att-state` + `key-state` attack now returns `HOLD`;
- no extension or checkpoint creation is permitted over that missing state;
- exact checkpoint base tuple and archive digest are bound;
- 1/3 checkpoint witness fan-out is non-authoritative and recoverable;
- after checkpoint commit, pre-cut history/state/key-state/attestation/key ancestry can be pruned and authority remains valid;
- a retired pre-cut HMAC secret can be destroyed after the cut and authority still remains valid;
- normal post-cut transition remains possible;
- missing current post-cut state returns `HOLD`;
- checkpoint witness disagreement and competing checkpoint identity return `HOLD`;
- a rehashed checkpoint with altered archive digest fails its root endorsements;
- deleting the checkpoint-signing head secret returns `HOLD` in this symmetric test model;
- whole-domain rollback remains an explicit surviving counterexample.

The cut used in the exact run bound an archive manifest containing 3 history objects, 3 attestation-state snapshots, 3 key-state snapshots, 8 attestations, and 5 key records. Compaction pruned 2 old history bodies, 2 old attestation-state bodies, 2 old key-state bodies, all 8 pre-cut attestation bodies, 1 retired key record, and 1 retired secret while retaining the live cut tuple and active key heads.

## Synthetic scaling probe

This section is **synthetic single-host process-CPU validation scaling**, not a fresh AXM/monolith workload and not evidence that retained/incremental/dormant compute generally wins.

| retained depth | full closure median CPU | checkpointed median CPU | checkpoint/full ratio |
|---:|---:|---:|---:|
| 1 | 671.768 µs | 534.041 µs | 0.7950 |
| 4 | 1923.154 µs | 567.002 µs | 0.2948 |
| 16 | 6881.953 µs | 583.401 µs | 0.0848 |
| 64 | 26686.981 µs | 612.131 µs | 0.0229 |

Full closure cost grows with retained depth in this model. Checkpointed validation is bounded by live post-cut depth, but checkpoint **creation** itself performs the full closure plus four root endorsements. There is no claim that checkpointing is free or universally profitable.

## Truth boundary / what still fails

- No fresh monolith workload was read this wave and no compute-efficiency, energy, or physical claim is made.
- The signatures are HMAC-SHA256 **test-model** endorsements. They show modeled possession of a symmetric secret, not identity, legitimacy, moral correctness, or canonical AXM authority.
- Compaction permits destruction of retired **pre-cut** secrets, but the secret of each key that endorsed the checkpoint is still needed to verify that checkpoint in this model.
- If runtime state, all witnesses, the checkpoint store, and surviving secrets are rolled back together, the old world remains internally self-consistent. Wave 95 does not solve whole-domain rollback.
- Pre-cut evidence becomes non-required only after exact full closure and exact checkpoint witness commit; before that, missing predecessor bodies fail closed.

## Next gate

Move the checkpoint anti-rollback fact into a genuinely separate failure domain, then test rollback of live state plus local checkpoint state against a surviving external checkpoint witness. In parallel, replace the HMAC-only signer model with a public-verification experiment so retired private signing material can be destroyed without making old checkpoints unverifiable.

Do not call either step distributed consensus or canonical legitimacy unless separately demonstrated.
