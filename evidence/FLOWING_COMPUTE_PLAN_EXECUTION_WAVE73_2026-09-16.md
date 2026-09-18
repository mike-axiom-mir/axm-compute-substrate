# Flowing Compute Wave 73 — Plan-Executed Multi-Contract Generation

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST EXECUTION-PROVENANCE EVIDENCE`

## Question

Wave 72 bound an explanatory plan to a generation. Can the generation also preserve evidence of **which executor actually ran for every contract**, and reject a generation when plan, execution receipt, and artifact reality disagree?

## Real G0→G1 execution

Mutation source: `monolith:EXECUTION_GRAPH.json`.

Actions actually executed:

- Execution Graph -> `incremental` using `validated_transition_handoff/v0.1`;
- snapshot identity -> `fixed_dense_merkle` using `snapshot_merkle_handoff/v0.1`;
- FrameState dormant mesh -> `reuse_exact_current_artifact`;
- Execution-Fabric capability index -> `reuse_exact_current_artifact`.

Content identities:

- plan receipt: `d4334385512128e63fbff40dcc4f6bf70618558c30e0ae68e08349c114a78e14`;
- execution receipt: `2a11f34bf588b6a85e14ddf7d67210566f768ad42709b6405d56adf7cb2ee0f2`;
- generation: `88d4d617478a9362b5cd7529349e4881ae6a73db356510629de7a488b2cb5a50`.

Measured CPU on this run:

- graph executor: **12.687 ms**;
- snapshot executor: **3.934 ms**;
- dormant-mesh reuse audit: **3.340 ms**;
- capability-index reuse audit: **20.758 ms**.

The unchanged capability-index audit was the most expensive per-contract execution step because this prototype rereads/hashes the full ~11.25 MB sleeping artifact.

## Controls

All passed:

- all referenced artifacts validated;
- an execution receipt that falsely claimed a different graph action was rejected even though the produced graph artifact remained correct;
- an execution receipt missing one contract row was rejected;
- changing a generation artifact ref while leaving the execution receipt intact was rejected.

## Interpretation

The state chain now distinguishes:

1. **plan** — what should execute and why;
2. **execution receipt** — what executor says it actually did;
3. **artifact reality** — what exact content identities were produced/reused.

All three must agree. Execution evidence does not gain commit authority merely by existing.

## Truth boundary

- one host/runtime;
- CPU time is not joules;
- execution receipts are content-addressed evidence, not external authentication;
- the executor registry is still experimental and currently covers the measured four-contract body;
- correct final bytes do not prove truthful provenance by themselves;
- no claim of compute or energy from nothing.

## Next gate

Split unchanged-contract reuse into explicit trust modes. `carried immutable proof` should reuse prior verified artifact identity without rehashing large sleeping artifacts on every generation; `audited reuse` should reread/rehash the bytes. The mode must be visible in the execution receipt, and tampering must be rediscovered by audited mode.
