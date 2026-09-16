# Independent adversarial verification — Wave 86 witness-set identity boundary

Date: 2026-09-16  
Builder head examined: `be5e066b6a6d7aa9c1fa99fca0c540ee3cd1dca0`  
Status: **BOUNDED SURVIVAL + CONFIGURATION/COMMIT BYPASS COUNTEREXAMPLE**

This verifier lane changes no builder files, performs no merge/canon action, and does not treat a verifier result as constitutional authority.

## What survives

The narrow Wave 86 result is meaningful **when the caller keeps passing the same complete witness set**:

- three equal witness heads can be checked against the primary;
- primary-only or partial witness rewind is detected when the surviving newer witness remains in the supplied set;
- valid 2-vs-1 and newest-looking disagreement fail closed rather than becoming a majority/newest-wins rule;
- unanimous one-epoch-ahead witness state can identify the tested interrupted pointer move;
- the all-modeled-domain rollback limitation is stated honestly;
- the benchmark is correctly scoped as same-host JSON/hash/fsync process CPU, not a compute-efficiency or energy result.

## New primary counterexample — configured witness membership is not part of the retained contract

Wave 86 describes three required witness ledgers, but `paths` is trusted caller input on every `witness_status()` and `multi_anchor_cas()` call. The primary pointer, anchor records, and a persistent manifest do not bind the exact required witness IDs/paths/count.

`initialize()` checks only that the *initial* supplied mapping has at least two distinct raw paths. Later `witness_status()` accepts any non-empty supplied set, and `multi_anchor_cas()` delegates to that status without re-enforcing the initialization membership/count.

The preserved reproducer uses the same failure shape already present in the Wave 86 self-test:

1. initialize the normal three witnesses A/B/C at genesis;
2. advance all three through epoch 2;
3. restore the primary and witnesses A/B to genesis while leaving C at epoch 2;
4. with the original A/B/C set, `witness_status()` correctly returns `WITNESS_DIVERGENCE_HOLD`;
5. call `witness_status()` again with only rewound witness A in the mapping;
6. it returns `CONSISTENT` with `witness_count == 1`;
7. call the actual `multi_anchor_cas()` with that one-witness mapping;
8. it returns `COMMITTED` and publishes a new pointer while omitted witness C still preserves the newer conflicting history;
9. supplying the original A/B/C set again exposes divergence, but the reduced-set commit has already occurred.

No SHA-256 collision, anchor rewrite, witness corruption, or fake majority is required. The surviving newer witness is bypassed by removing it from the caller-supplied configuration.

## Why this matters

This is an authority/configuration boundary, not a cryptographic break. Wave 86 proves disagreement handling only relative to **the witness set the caller chooses for that call**. It does not yet prove that the caller is using the same witness set that established prior history.

That weakens two broad readings of the current write-up:

- “three required witness ledgers” is an experiment fixture/default, not an enforced persistent invariant;
- “no witness is silently promoted to canonical authority” is not true if a later caller can shrink the set to one matching witness and commit through it.

The core multi-witness detection algorithm can still be useful after membership identity is bound explicitly.

## Reproducer

`verification/wave86_witness_set_identity_repro.py`

The script imports the actual Wave 86/Wave 84 APIs, creates the three-witness history, reproduces the builder's partial-rewind disagreement, then demonstrates status acceptance and an actual commit after shrinking the supplied mapping to one rewound witness.

## Additional inherited boundaries not re-counted as new findings

- Wave 86 imports the Wave 85 anchor contract; prior verifier work already showed that anchor-history continuity needs cross-binding to the prior anchor's exact pointer history.
- `initialize()` still delegates into the earlier initialization path before all witness preconditions are fully established; prior verifier work already covered fail-after-mutation/reinitialization behavior.
- multiple directories on one host remain modeled software failure domains, not independent physical witnesses.

## Benchmark / provenance check

No fresh monolith audit or retained-compute benchmark was run here. Wave 86's published ~1.1–1.18 ms median is explicitly infrastructure process-CPU timing over local temporary stores and should remain labeled that way. This verifier does not independently reproduce that timing.

## Next adversarial gate

Before partial-fanout auto-repair, bind one exact **witness-set identity** into the persistent contract:

- stable witness IDs + expected count + membership digest;
- reject shrink, substitution, duplicate/aliased logical witnesses, or unknown additions unless an explicit membership-change transition is itself evidenced;
- bind the same membership identity into the planned Wave 87 commit-set;
- on restart, verify every required witness from that bound set before allowing recovery or a new commit.

Then attack membership rotation, one witness replacement by a copied old ledger, path aliasing/symlink identity, add/remove transitions, partial membership-change crashes, and a commit-set that is valid under one membership generation but replayed under another.
