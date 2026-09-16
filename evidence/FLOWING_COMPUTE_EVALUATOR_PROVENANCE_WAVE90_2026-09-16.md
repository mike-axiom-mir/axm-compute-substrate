# Flowing Compute Wave 90 — Evaluator Provenance Registry / Lineage

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST PROVENANCE / REGISTRY EVIDENCE`

## Question

Wave 89 proved that one exact four-root authorization receipt could be bound to one exact witness-membership reconfiguration, but it also preserved the larger failure that a self-minted structurally valid PASS could satisfy the gate. Wave 90 asks whether each root evaluation can be forced to resolve through explicit content-addressed evaluator provenance and explicit evaluator-registry lineage instead of anonymous/self-asserted rows.

This is a provenance/lineage experiment. It does **not** prove that a registered evaluator is morally legitimate or that its root judgments are canonical AXM authority.

## Exact prior identity / provenance

No fresh monolith audit ran in this wave.

Wave 89 reusable source:

- commit: `22182ef762be05835d912ae48da40c6043fb81dc`
- Git blob: `71b62f37911a5c2c53a32ddf2a29bf5610833181`
- file SHA-256: `eef82f3db83954d97f15b4f7bda53cc01b75d63c0f289c9a94b4b2eff00d8066`

Wave 90 reusable tool:

- path: `tools/AXM_FLOWING_COMPUTE_EVALUATOR_PROVENANCE.py`
- tool commit: `57435f3f21b017b6a532a39c31e0a8a58ca70182`
- Git blob: `35f756d023fcbfa1e24fff94a2dcf87b29d8962e`
- file SHA-256: `35355bb17ab069cf1de5d32168e2bf8153bf489eda30b27057e82ccab9743679`

Machine-readable report:

- path: `evidence/FLOWING_COMPUTE_EVALUATOR_PROVENANCE_WAVE90_REPORT.json`
- report commit: `f84a962ffc403e7e2b803dc2009c37ba3c43513f`
- Git blob: `9812c56e1430b02edae65bb5e79256c0203e5fdf`

The exact committed Wave 90 tool bytes were reconstructed locally from the committed source and verified against the Git blob identity before execution; the executed file SHA-256 is the value above.

## Reusable contract added

Wave 90 adds content-addressed evaluator records containing:

- stable evaluator ID;
- exact root scope;
- exact evaluation-tool SHA-256;
- exact evaluation-source SHA-256;
- predecessor evaluator record for replacements;
- explicit test-only / truth-boundary markers.

A content-addressed evaluator registry then binds:

- registry generation;
- predecessor registry identity;
- evaluator-ID -> evaluator-record identities;
- exactly four root assignments;
- ADD / REMOVE / REPLACE / MIXED lineage.

Each root evaluation must now bind the exact current registry identity it was made against plus the exact evaluator record, tool digest and source digest. Anonymous or unregistered evaluator rows fail closed inside the validator.

## Positive result

Two independent executions passed **32/32 controls each**.

The probe demonstrated:

- exact registered evaluator provenance can satisfy the four-root structural gate;
- an unregistered self-minted evaluator row is rejected;
- wrong evaluator-record, tool or source digests are rejected;
- missing evaluator bodies and corrupt registry bodies fail closed;
- evaluator ADD, REMOVE and REPLACE have explicit predecessor-bound lineage;
- a replaced evaluator record carries its exact predecessor evaluator identity;
- stale evaluations from the old registry cannot be rebound to the replacement registry;
- root HOLD and FAIL semantics still block membership authorization after provenance checks;
- a prepared registry target does not by itself move the modeled current-registry pointer.

## Registry disagreement / recovery result

The modeled registry has three required witness views.

- all three on the exact current registry -> `CONSISTENT`;
- 2-vs-1 split -> `HOLD`;
- one newer-looking witness -> `HOLD`;
- missing required witness -> `HOLD`;
- competing target histories -> `HOLD`;
- there is no majority vote and no newest-wins rule.

A partial exact registry handoff can be completed only through the exact predecessor-bound transition. The test advanced one witness, observed disagreement, then recovered the lagging witnesses through the same exact transition and committed the target registry.

## Important counterexample kept visible

Wave 90 closes the Wave 89 **anonymous evaluator** hole one layer further, but it exposes a more precise authority gap.

The current authorization validator resolves the registry identity named inside the authorization receipt from the content-addressed registry store. It does **not yet require that registry identity to equal the runtime's currently committed registry pointer**.

The test therefore preserves this counterexample: a self-minted evaluator can be placed into a structurally valid successor registry object and a structurally valid authorization can be produced from that stored registry even though that registry was not first made the current committed runtime registry in the test path.

So `stored / structurally valid registry` and `currently authoritative registry` are still separable. This is a real failure boundary, not a solved result.

Even after that mechanical hole is closed, explicit registry admission plus exact hashes still will not by itself prove moral legitimacy or canonical AXM authority.

## Cost

This benchmark is explicitly **synthetic single-host evaluator-registry / authorization bookkeeping**. It is not a monolith workload and it is not a compute-efficiency result.

For 100 rounds per independent run, validating the replacement registry, constructing an exact four-root authorization, resolving evaluator provenance, and validating the authorization measured:

- run 1 median process CPU: **1316.1315 microseconds**;
- run 2 median process CPU: **1229.092 microseconds**.

These are process CPU timings only. They are not wall-clock distributed latency, joules, or evidence that retained/incremental/dormant state saves compute.

## Truth boundary

- no fresh monolith audit;
- no retained/incremental/dormant-state performance claim;
- no energy claim;
- no distributed-consensus claim;
- all evaluator/root identities in this probe are test-only structural evidence;
- evaluator registration does not prove moral legitimacy;
- registry lineage does not create canonical AXM judgment;
- content-addressed storage does not equal current-state authority;
- no automatic merge and no silent canon rewrite;
- all registry/witness storage remains single-host modeled state.

## Next gate

**Wave 91: bind authorization to the exact current committed evaluator-registry authority.**

The validator should require the authorization's registry identity to equal the runtime current-registry pointer *and* require the required registry witnesses to be consistent at that identity before any root evaluation can authorize a membership change. A merely stored/prepared successor registry must have zero authorization authority. During registry handoff, the predecessor registry remains authoritative until the target is fully committed; new/target evaluators must not authorize their own admission before that commit. Competing registry/admission histories must remain `HOLD`, not vote or pick newest.

After that mechanical gate, actor/admission legitimacy remains a separate unsolved layer rather than being silently declared solved.
