# Flowing Compute Wave 89 — Membership-Change Authorization Bound to Exact Reconfiguration

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST AUTHORIZATION / RECOVERY EVIDENCE`

## Question

Wave 88 made witness membership explicit content-addressed state, so an ADD/REMOVE/REPLACE can no longer be hidden in caller configuration. Wave 89 asks whether **membership mutation and crash recovery can be mechanically blocked unless one exact four-root authorization receipt is bound to the exact reconfiguration**.

This is an authorization-structure experiment, not a claim that the machine has solved who is legitimately entitled to evaluate AXM's four roots.

## Exact prior identity / provenance

No fresh monolith audit ran in this wave. The reusable tool binds the exact Wave 88 implementation source:

- Wave 88 tool commit: `76ed78a64825a5c71ff2017ef9383d389b878192`
- Wave 88 tool blob: `efabee7b9c9724e1bd23f37cfc909cc9ed54cf1a`
- Wave 89 tool commit: `22182ef762be05835d912ae48da40c6043fb81dc`
- Wave 89 tool blob: `71b62f37911a5c2c53a32ddf2a29bf5610833181`
- Wave 89 tool file SHA-256: `eef82f3db83954d97f15b4f7bda53cc01b75d63c0f289c9a94b4b2eff00d8066`
- report commit: `cf8f7d352488c990bb4cbf1f0c95e86c329b9608`
- report blob: `5f3c7b6c7d68c7f9fbbf508a85bb273e6a203c14`
- report file SHA-256: `873d897e70855620484a6b1f9c6df65f870c3eea52ae7b13e037c0599473082d`

## Reusable contract

`tools/AXM_FLOWING_COMPUTE_WITNESS_MEMBERSHIP_AUTH.py` adds a content-addressed authorization receipt that binds all of the following at once:

- predecessor membership identity and epoch;
- target membership identity and epoch;
- predecessor and target pointer identities;
- exact reconfiguration identity;
- transition kind;
- exact old / target / retained / added / removed witness sets;
- exactly four test-only root evaluations: Truth, Agency / non-domination, Continuity, and Wisdom before speed.

A prepared reconfiguration object and a prepared authorization receipt have **zero current-state authority by mere existence**. Before any modeled witness fan-out occurs, the authorization must be present, content-valid, exact-binding-valid, and all four evaluations must be PASS.

## Positive result

The test path replaces membership `A,B,C -> A,B,D`.

- no authorization -> `AUTHORIZATION_REQUIRED_HOLD` before any witness mutation;
- exact authorization -> replacement commits to the exact target membership;
- removed witness `C` has zero current-state authority after commit;
- a partial authorized fan-out can be recovered only while the exact authorization receipt is still available;
- deleting that receipt after the simulated crash freezes recovery;
- restoring the exact content-addressed receipt allows recovery to finish.

Two independent executions passed **27/27 controls each**.

## Negative controls / failures kept visible

The gate rejected:

- a root `HOLD`;
- a root `FAIL`;
- a missing root;
- an extra pseudo-root;
- wrong predecessor membership;
- wrong target membership;
- wrong predecessor pointer;
- wrong target pointer;
- wrong reconfiguration identity;
- wrong witness-set binding;
- wrong transition kind;
- nested root evidence tampering;
- top-level receipt tampering;
- reuse of a valid receipt on a different reconfiguration from the same predecessor;
- a corrupt authorization body stored under the original content-address key.

## Important counterexample — evaluator legitimacy remains unsolved

Wave 89 deliberately preserves a failure of the *larger* authorization problem: a party that can mint a completely self-consistent, rehashed structural PASS receipt can satisfy this mechanical gate. The hashes prove exact content and binding; they do **not** prove who evaluated the roots, whether that evaluator is legitimate, or whether the PASS should become canonical AXM judgment.

So the result is narrower and useful: **wrong or missing authorization evidence cannot silently authorize a different membership change inside this model.** It is not proof of legitimate evaluator identity.

## Cost

The benchmark is explicitly **synthetic single-host authorization bookkeeping**, not a monolith workload and not evidence of compute savings.

Each round constructs the small modeled membership/reconfiguration objects, creates four structural evaluation rows, seals one authorization receipt, and validates it.

- final run 1 median process CPU: **95.1615 microseconds** over 100 rounds;
- final run 2 median process CPU: **94.31 microseconds** over 100 rounds.

These values are process CPU timing only. They are not wall-clock distributed latency, not joules, and not a compute-efficiency claim.

## Truth boundary

- no fresh monolith audit;
- no retained/incremental/dormant-state performance claim;
- no energy claim;
- no distributed-consensus claim;
- no actor/evaluator identity proof;
- no claim that test-only root PASS rows are canonical AXM judgments;
- no automatic merge and no silent canon rewrite;
- all modeled witness/evidence storage remains single-host test state.

Machine-readable evidence:

- `evidence/FLOWING_COMPUTE_WITNESS_MEMBERSHIP_AUTH_WAVE89_REPORT.json`

## Next gate

**Wave 90: evaluator provenance becomes explicit state.** The current receipt proves that four evaluation rows were bound correctly, but a self-minted structurally valid PASS remains possible. Add a content-addressed evaluator registry / lineage so every root evaluation must name an exact registered evaluator identity plus exact evaluation-tool/source digest, and evaluator add/remove/replace is itself an explicit predecessor-bound handoff. Unregistered evaluators must fail closed; registry disagreement must HOLD rather than vote or pick newest. Preserve the deeper boundary that registry membership and cryptographic/source identity still do not magically prove moral legitimacy of the evaluator; they only make provenance and authorized lineage mechanically inspectable.
