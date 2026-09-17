# Independent verifier — Wave 89 target-membership cross-binding

Date: 2026-09-16  
Builder base: `c8738cd6d427e79accc31d616615134b7ea8b7c8`  
Scope: verifier-only evidence; no builder rewrite, no merge/canon promotion.

## What was challenged

Wave 89 claims that one exact four-root authorization receipt is bound to the exact witness-membership reconfiguration before modeled witness fan-out, including exact predecessor/target membership identities, pointer identities, transition kind, and exact witness sets.

The narrow control survives: the constructor-produced fixture `A,B,C -> A,B,D` produces a matching authorization, commits, and leaves runtime witness IDs equal to the target membership body's IDs.

## Reproduced failure

`validate_reconfiguration()` validates the reconfiguration seal, schema, derived retained/added/removed sets, and epoch step. It does **not** resolve the target membership object named by `target_membership_sha256`, and therefore does not prove that `target_witness_ids` equals the witness IDs inside that exact membership body.

The verifier starts from the normal Wave 89 fixture, whose exact target membership body is `A,B,D`, then changes only the reconfiguration's declared target witness set to `A,B,E`, recalculates its derived set fields, and reseals the reconfiguration. The exact published validator accepts it.

Wave 89's own `test_root_evaluations()` and `make_authorization()` then produce a structurally valid four-root PASS authorization for that malformed cross-object state. `validate_authorization()` returns `ALLOW`, because it proves the authorization fields equal the reconfiguration fields, not that those fields agree with the referenced target membership object.

`apply_step()` returns `COMMITTED` and publishes:

- current membership SHA = the legitimate target membership object for `A,B,D`;
- current pointer SHA = the legitimate pointer bound to that membership SHA;
- runtime witness heads = `A,B,E` from the forged reconfiguration.

No SHA-256 collision, authorization-store corruption, missing root, wrong auth/reconfiguration binding, or unregistered evaluator assumption is required. This is a semantic cross-object binding failure: the authorization can be exact about two claims that contradict each other.

## Secondary recovery boundary

After the contradictory state is published, the verifier deletes the exact authorization receipt. `recover()` still returns `CONSISTENT_TARGET` immediately because its fast path checks only current pointer SHA + current membership SHA against the reconfiguration target. It does not resolve the authorization receipt or verify witness heads against the target membership body on that path.

This does not contradict the positive crash test in the Wave 89 report, where the primary remained on the predecessor during partial fan-out. It narrows the claim: "recovery requires the exact authorization" is true for that modeled predecessor-state partial-fanout case, not for every inconsistent state carrying the target primary identities.

## Bounded conclusion

Wave 89 materially improves exact **authorization-to-reconfiguration** binding, and its no-auth / wrong-auth controls remain useful. But it does not yet prove **authorization-to-referenced-state semantics**. A content-valid authorization may bless a reconfiguration whose target witness set contradicts the exact target membership object it names.

## Next adversarial gate

Use one shared semantic validator that resolves both predecessor and target membership objects plus both pointer objects before authorization, commit, and recovery. Require:

- predecessor membership SHA -> exact `old_witness_ids`;
- target membership SHA -> exact `target_witness_ids`;
- membership generation/predecessor/transition kind agreement;
- pointer -> exact membership SHA and predecessor pointer lineage;
- reconfiguration transition kind rederived from the resolved old/target membership sets;
- recovery `CONSISTENT_TARGET` only after target membership, witness heads/roles, exact authorization lineage, and current pointer all agree.

Then attack target-membership substitution, pointer/membership substitution, malformed transition kinds, post-commit missing authorization, and recovery from target-primary / partial-witness crash states.

Executable reproducer: `verification/wave89_target_membership_crossbind_counterexample.py`.
