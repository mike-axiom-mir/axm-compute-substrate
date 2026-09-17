# Wave 90 adversarial verification — evaluator replacement lineage gap

Date: 2026-09-16
Verifier lane: independent / draft / non-canon
Builder head tested: `e9007c6c298f62d73def373c4c2bb299325ba7f0`
Primary Wave 90 tool: `tools/AXM_FLOWING_COMPUTE_EVALUATOR_PROVENANCE.py`

## Result

**FAIL — Wave 90 does not mechanically enforce the claimed predecessor-bound lineage for a replaced evaluator record.**

Wave 90's intended control works: an evaluator replacement can carry the exact prior evaluator SHA in `predecessor_evaluator_sha256`, and the registry/transition path accepts it.

However, the reusable validators do not require that relationship. A replacement evaluator with the same evaluator ID but a changed evaluator body can carry:

- `predecessor_evaluator_sha256 = None`; or
- an unrelated syntactically valid 64-hex digest;

and still pass `validate_registry()` plus `validate_registry_transition()` for a registry whose transition is classified as `REPLACE`.

The exact public API can then fully commit that malformed replacement registry through all three modeled registry witnesses. `registry_view_status()` reports `CONSISTENT`, and `make_authorization()` / `validate_authorization()` can return `ALLOW` from the now-current registry.

This counterexample does **not** rely on Wave 90's already-disclosed gap where a merely stored/prepared registry can authorize before becoming current. In this verifier case, the malformed replacement registry is first made the runtime's fully current witnessed registry.

## Why it happens

`validate_evaluator()` validates `predecessor_evaluator_sha256` only if it is present, and then only as a 64-hex-shaped value. It does not resolve that predecessor or compare it with the evaluator record being replaced.

`make_registry_transition()` / `validate_registry_transition()` detect replacement by observing that an evaluator ID maps to a different evaluator SHA, but they do not require the target evaluator body's `predecessor_evaluator_sha256` to equal the old registry entry's evaluator SHA.

So registry lineage is predecessor-bound, while evaluator-record replacement lineage is presently fixture-conventional rather than validator-enforced.

## Exact reproducer

`verification/wave90_evaluator_replacement_lineage_repro.py`

The reproducer imports the committed Wave 90 module directly and asserts:

1. correctly linked replacement control passes;
2. missing evaluator predecessor replacement passes registry validation;
3. missing evaluator predecessor replacement passes transition validation;
4. the normal three-witness registry handoff commits it as current;
5. current registry status becomes `CONSISTENT`;
6. authorization from that current registry returns `ALLOW`;
7. a replacement pointing at an unrelated 64-hex predecessor also passes transition validation.

Expected terminal verdict:

`FAIL_REPLACEMENT_EVALUATOR_PREDECESSOR_NOT_ENFORCED`

## Bounded survival

Wave 90 still materially improves several narrower properties:

- root rows must match the evaluator ID currently assigned to that root in the selected registry;
- row evaluator/tool/source digests must match the selected evaluator record;
- missing evaluator or registry bodies fail closed;
- stale rows cannot simply be rebound across a registry replacement by changing only the outer registry identity;
- registry witness disagreement remains HOLD in the modeled full witness set;
- the report correctly keeps moral/canonical evaluator legitimacy outside the mechanical claim.

The failure is narrower: **the system can say a registry performed an evaluator REPLACE without proving that the new evaluator record descends from the exact evaluator record that registry transition replaced.**

## Benchmark / provenance boundary

No new compute-efficiency claim is made here. Wave 90 itself labels its timing as synthetic single-host evaluator-registry/authorization bookkeeping rather than retained/incremental/dormant-state savings. This verifier did not reinterpret that benchmark.

No fresh monolith audit was required to reproduce this semantic validator gap.

## Next adversarial gate

Before or alongside current-registry authority binding, replacement validation should resolve both old and target evaluator bodies and require, for every replaced evaluator ID:

`target_evaluator.predecessor_evaluator_sha256 == old_registry.evaluator_entries[evaluator_id]`

For unchanged evaluator IDs, identity should remain exact; for ADD, predecessor semantics should be explicit; for REMOVE, no target evaluator body exists. Recovery and authorization should invoke the same semantic validator rather than relying on constructor behavior.

Then attack:

- missing replacement predecessor;
- unrelated predecessor digest;
- predecessor pointing to a real but wrong historical evaluator;
- multi-step replacement skipping an intermediate evaluator generation;
- replacement registry committed correctly but evaluator predecessor body garbage-collected/missing;
- concurrent competing replacements of the same evaluator ID.

Keep this lane draft/unmerged. It is verification evidence, not merge or canon authority.
