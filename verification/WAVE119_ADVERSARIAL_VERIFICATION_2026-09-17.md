# Wave 119 independent adversarial verification — orphan rotation prepare retention

Date: 2026-09-17  
Lane: `verifier/wave119-orphan-rotation-prepare-retention`  
Draft PR: #44  
Status: verifier-only, unmerged, non-CANON. Do not auto-merge.

## Exact builder state challenged

- newest Wave 119 evidence head at verification start: `b39e89fa8e0e64df543ab8a593429e47fbc3a530`
- exact Wave 119 tested source: `c96d679d7cb03935c821bbdff4ab3e1a19c99018`
- exact Wave 119 tool blob: `28c8c85b3377289b69d742990556e5429fca487f`
- builder evidence CI: run `35261332504`, job `105337519571`, artifact `10514504266`, SHA-256 `1bb51aac958737905b642246fff759841ea7c8e8924ceceea92ced95d5b85e98`

## What survives

Wave 119's direct recovery result survives its unchanged self-test in this independent lane:

- Wave 119 self-test normal Python: **16/16 PASS**
- Wave 119 self-test `python -O`: **16/16 PASS**

This verifier does not contradict the bounded claims that exact root/root+envelope bootstrap prefixes can resume, or that the exact lower-committed rotation/provenance crash can recover and activate the accepted successor under the tested contract.

No speed, energy, retained/incremental/dormant-compute win, OS-process isolation, device durability, network/provider independence, or physical power-loss claim is inferred.

## New reproduced hidden cost

Verdict:

`FAIL_FAILED_ROTATION_PREPARES_ACCUMULATE_UNREFERENCED_ROOT_AND_ENVELOPE_STATE`

The rotation prepare path persists a candidate rotated outcome root and its app envelope **before** calling the lower Wave-114 prepare. The verifier injects a lower prepare exception at that boundary. Each failed attempt uses a fresh legitimate successor credential and a fresh valid target user-state SHA.

Across **16 failed attempts**, in both normal Python and `python -O`:

- each failed attempt added exactly **1 outcome root**;
- each failed attempt added exactly **1 envelope**;
- lower transition count changed by **0**;
- lower binding count changed by **0**;
- authority remained `AUTHORITATIVE_QUORUM_3_OF_3_MODELED` after every failure;
- total retained orphan growth was **16 roots + 16 envelopes**;
- canonical compact JSON size of those 32 retained bodies was **13,616 bytes**, exactly **851 bytes per failed attempt** in this fixture;
- after all orphan residue existed, a normal clean rotation prepare still succeeded.

The result therefore isolates upper-layer retained-state accumulation rather than a lower prepared transaction or authority takeover. The orphan objects are not referenced by the accepted checkpoint lineage, so normal authority ignores them while they remain resident in the retained stores.

This is a structural retention/accounting result, not a wall-clock or energy benchmark. It demonstrates linear storage amplification for this injected lower-failure boundary inside the current in-memory model; it does not claim filesystem/database byte cost or real crash durability.

## Exact independent CI

Verifier run: `35263785310`  
Job: `105345738955`  
Conclusion: success

The job completed all required steps:

1. unchanged Wave 119 self-test normal — success;
2. unchanged Wave 119 self-test optimized — success;
3. adversarial retention reproducer normal — success / failure reproduced;
4. adversarial retention reproducer optimized — success / failure reproduced;
5. exact source identity — success;
6. evidence upload — success.

Artifact: `10516156028` (`verifier-wave119-orphan-rotation-prepare-retention`)  
Artifact SHA-256: `43651d4c13f131495aa76c388dd1839d5a434f18c7f4f29f2e00425172dcf1c6`

The artifact contains the two unchanged builder reports, both adversarial JSON reports, exact verifier head, and source digests.

## Severity / truth boundary

Not reproduced:

- stale or older authority becoming authoritative;
- hash collision or credential forgery;
- transition/binding semantic substitution;
- benchmark unfairness or timing/energy claim;
- failure of Wave 119's exact recovery cases.

Reproduced:

- failed/aborted rotation prepare can consume retained root/envelope state before lower acceptance;
- repeated unique failures accumulate linearly with no rollback/cleanup in the public prepare path;
- current authority and later clean preparation can remain healthy, making the retained cost easy to overlook.

## Next adversarial gate

Make rotation prepare transactional across the **candidate root -> envelope -> lower prepare** boundary. Either stage candidate root/envelope outside retained canonical stores until lower prepare succeeds, or roll back only newly-created unreferenced objects on failure while never deleting pre-existing shared/content-addressed objects.

Then attack:

- failure after root write but before envelope;
- failure after envelope but before lower prepare;
- lower prepare exception before any lower write;
- lower prepare exception after partial lower write;
- duplicate retries with the same candidate successor versus fresh successors;
- cleanup when another valid object already references the same root/envelope;
- crash/restart between every write boundary;
- retained byte/object growth at 1, 10, 100, and 1,000 failed attempts before any efficiency or long-lived retained-state claim is broadened.

Only after ownership/reference-safe cleanup is defined should orphan collection be automatic; recovery evidence must never be garbage-collected merely because it is not on the current accepted lineage.
