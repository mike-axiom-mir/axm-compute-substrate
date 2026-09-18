# Flowing Compute Wave 96 — replay-safe public checkpoints and modeled external rollback anchor

Date: 2026-09-16  
Lane: `chatgpt/lane-001-platform-extract`  
Status: experimental research only; append-only evidence; no merge/canon authority.

## Exact source / provenance identity

Wave 96 continues from builder Wave 95 head `42bf7230f2537fe7229983769b9130f9c58c2393`, Wave 95 tool blob `5e38d8ad23dc9c659d774127beb95a745b08a151`, and Wave 95 evidence blob `b202f5724dc340119e656189718ea64f0a9feb71`.

It incorporates independent verifier PR #20 at head `bbe9bbccbc5c9241c4391c609ec36deef99df1fa`, workflow run `35139830377`. That verifier reproduced two important Wave 95 boundaries: an older valid checkpoint could be replayed after a newer checkpoint, and compaction was one-shot because the next checkpoint constructor still required intentionally pruned pre-cut history. It also identified that Wave 95 checkpoint construction walked full closure twice.

Final Wave 96 reusable tool: `tools/AXM_FLOWING_COMPUTE_PUBLIC_CHECKPOINT_ANCHOR.py`, blob `ab7a57af1f5259e893aaa14c6f17f40a064cc801`, final tool-fix commit `610bab19c7fadf0a3c2519ca602589539bee9976`.

Machine-readable report: `evidence/FLOWING_COMPUTE_PUBLIC_CHECKPOINT_ANCHOR_WAVE96_REPORT.json`, blob `f55152574d076a56a710a9f4f3bcae0295ddeb0c`, report commit `545fc1a8da63b6e77411b371816e41cf77e9c5fb`.

No verifier branch was merged or rewritten.

## What changed

Checkpoint publication is now predecessor-bound and monotonic. Every checkpoint names the exact predecessor checkpoint and next epoch. Local checkpoint witnesses and the modeled external anchor reject an older valid checkpoint after a newer checkpoint has committed, so the PR #20 replay path returns `PREDECESSOR_HOLD` / `EPOCH_HOLD` instead of becoming current again.

Checkpointing is now repeatable after compaction. The constructor validates only the exact post-cut segment back to the currently committed checkpoint; it no longer asks for intentionally pruned evidence before that cut. The exact test sequence successfully committed checkpoint 1, advanced state, committed checkpoint 2, pruned the checkpoint-1-to-2 segment, advanced again, then created and committed checkpoint 3.

The Wave 95 double traversal was removed on this path. Each checkpoint preparation records one closure traversal and constructs its segment manifest from that same traversal rather than walking the history again.

Checkpoint endorsements moved from the Wave 95 symmetric-HMAC-only checkpoint model to a deliberately limited public-verification experiment: deterministic Lamport one-time SHA-256 signatures. Each checkpoint commits the exact public signer identities for the current checkpoint and the exact successor public keys for the next checkpoint. Reusing a one-time signer is rejected. Once a checkpoint is signed, its private Lamport material can be erased while the checkpoint remains verifiable from public material.

A modeled append-only `external-anchor/v1` domain was added. Local authority after a checkpoint requires the latest external anchor to name the same checkpoint. Rolling local runtime/checkpoint state back from checkpoint 3 to checkpoint 2 while the external anchor remains at checkpoint 3 returns `HOLD_EXTERNAL_AHEAD`.

## Positive and negative controls

Two final exact-source runs completed with **32/32 controls passing** each: one normal Python run and one `python -O` run.

Controls include partial checkpoint fan-out staying non-authoritative; exact predecessor/epoch binding; signer rotation binding; old-checkpoint replay rejection locally and at the external-anchor boundary; re-checkpointing after prior compaction; continuation after compaction; public verification after checkpoint private signing material is erased; altered Lamport signature rejection; wrong signer-generation rejection; local rollback detection while the modeled external anchor survives; and preservation of the whole-domain rollback counterexample.

During this wave an implementation weakness was caught before final evidence: the first draft used Python `assert` for content-hash/collision checks, which could disappear under optimized Python. The final tool replaces those with explicit exceptions, and the full 32-control run was repeated under `python -O` successfully. The earlier commit remains in repository history rather than being silently hidden.

## Synthetic timing boundary

This wave did **not** read a fresh monolith/AXM workload. Timings are synthetic single-host process-CPU costs for checkpoint construction/public verification only.

Normal run, five benchmark rounds: checkpoint construction median `12,532.475 µs`; public verification median `6,513.104 µs`.

Optimized-Python repeat, five benchmark rounds: checkpoint construction median `12,737.653 µs`; public verification median `6,013.840 µs`.

These numbers are not energy measurements, not distributed latency, and not evidence that retained, incremental, or dormant compute generally wins. The Lamport test model is intentionally bulky and is not presented as a performance recommendation.

## Truth boundary / what still fails

- The external anchor is only a separately supplied append-only state domain inside this experimental model. It is **not yet** a physically independent device, remote monotonic service, TPM, timestamp service, or distributed consensus system.
- If the local state and the modeled external anchor are rolled back together to checkpoint 2, the old world remains internally self-consistent. This counterexample is preserved explicitly.
- Lamport OTS proves only modeled possession of one-time private material. It does not prove identity, evaluator legitimacy, moral/root correctness, or canonical AXM authority.
- The older state-transition attestation layer still uses the Wave 95-style HMAC test model. Wave 96 changes checkpoint verification, not every authority-signing layer.
- No fresh monolith workload or compute-efficiency, energy, retained-state, incremental-state, or dormant-state win is claimed.

## Next gate

Move the external checkpoint anchor into a **physically independent monotonic failure domain** (or two independent remote witnesses) and attack credentialed remote rewrite, witness/network partition, conflicting remote histories, stale-anchor replay, and recovery with one external witness unavailable. Only after that should the remaining HMAC state-attestation layer be migrated toward public verification, while preserving the same rollback and transition semantics.

Do not call the current modeled external anchor distributed consensus or solved anti-rollback.
