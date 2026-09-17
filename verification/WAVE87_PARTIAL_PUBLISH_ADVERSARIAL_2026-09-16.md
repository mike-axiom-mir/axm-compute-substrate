# Independent Verifier — Wave 87 partial publish via reduced runtime witness map

Date: 2026-09-16  
Verdict: **FAIL — primary publication can occur after only 1/3 declared witnesses advance**  
Builder base: `0fcd0cfddd0463b3e89c2f6f2b6e86e1f42bd51f` (`chatgpt/lane-001-platform-extract`)  
Verifier lane: `chatgpt/verifier-wave87-partial-publish-20260916`

This is independent verifier evidence only. It does not modify builder code, grant canon authority, or request an automatic merge.

## Claim challenged

Wave 87 correctly strengthens recovery by binding an exact ordered `witness_ids` list into each content-addressed commit-set and by requiring recovery to compare the configured witness set with that list. The evidence also states that repair revalidates all witness records against the same commit-set before moving the primary pointer.

The adversarial question was whether **every publication path**, not only recovery, enforces that exact declared witness membership before primary publication.

## Source-level gap

`commit_prepared()` validates the commit-set, then computes `ordered = sorted(witnesses)` from the **runtime map supplied by the caller**. It appends only those supplied witnesses and then unconditionally loads and publishes the target pointer.

It does not require:

- `sorted(witnesses) == commit_set['witness_ids']`;
- the minimum declared witness count at commit time; or
- a final re-read proving every witness named by the commit-set reached the exact target before `primary.commit(target)`.

This is notably weaker than the Wave 87 recovery path, which does compare `cs['witness_ids']` with the configured IDs and, during repair, re-reads every witness before moving the primary.

## Exact API reproduction

`verification/wave87_commit_prepared_membership_counterexample.py` uses the published Wave 87 module without changing it.

Two cases start from the same normal three-witness genesis and prepare a normal three-witness commit-set naming:

`witness-a, witness-b, witness-c`

### Control — intended one-witness crash

Call `commit_prepared()` with the full three-witness map and `crash_after_witness_count=1`.

Observed on GitHub Actions:

- helper result: `CRASH_DURING_WITNESS_FANOUT`;
- witness epochs: `A=1, B=0, C=0`;
- primary epoch: **0**;
- full recovery status: `PARTIAL_COMMIT_SET_RECOVERABLE`.

This is the intended Wave 87 crash behavior.

### Counterexample — reduced runtime map

Use the exact same kind of three-witness commit-set, but call `commit_prepared()` with a runtime map containing only `witness-a`.

Observed on GitHub Actions:

- commit-set still declares `A, B, C`;
- runtime map given to `commit_prepared()` contains only `A`;
- witness epochs after the call: `A=1, B=0, C=0` — physically the same 1/3 fan-out shape as the control;
- helper result: **`COMMITTED`**;
- primary epoch: **1**;
- recovery using the full declared witness set: **`NO_RECOVERABLE_COMMIT_SET_HOLD`**.

So the primary can move from epoch 0 to epoch 1 even though two witnesses explicitly named by the commit-set never advanced. The resulting published state is then rejected by the full recovery validator.

The exact reproducer assertions passed in GitHub Actions run `35089413515`, job `104771898109` on Ubuntu 24.04. The emitted verdict was:

`FAIL_PARTIAL_PUBLISH_VIA_REDUCED_RUNTIME_WITNESS_MAP`

## Why this matters

This does not break hashing and it does not falsify the bounded recovery logic when the full correct witness map is supplied. It does falsify a stronger interpretation that the Wave 87 commit-set itself guarantees exact witness fan-out before publication across the exported API.

The commit-set contains the right membership evidence, but `commit_prepared()` currently does not enforce that evidence at its irreversible publication boundary.

This is also distinct from the Wave 86 / early Wave 87 steady-state omission bug. The final steady-state validator now detects a missing member. The failure here happens **before** steady state: a reduced runtime map can make the primary move first, leaving the system in a state that the correct full validator subsequently holds.

## Benchmark / efficiency boundary

No compute-efficiency or energy claim was tested here. Wave 87's own orchestration timings remain scoped to local JSON/hash/fsync bookkeeping. This verifier result is an authority/atomicity failure, not a performance result.

## Next adversarial gate

Before treating Wave 87 publication as exact-membership atomic, require the commit path itself to fail **before mutation** unless the runtime witness IDs exactly equal the commit-set witness IDs. After fan-out, re-read and validate every declared witness against the exact commit-set immediately before primary publication, just as the recovery path does.

Then challenge Wave 88 membership reconfiguration with:

1. crash during add/remove/replace handoff;
2. reduced or aliased runtime maps at every commit entry point;
3. an old commit-set replayed under a newer membership generation;
4. one witness omitted after final fan-out but before primary publication;
5. concurrency between membership reconfiguration and a normal retention transition.

Until that gate is closed, Wave 87 is best described as **bounded recoverability under a correct/full runtime witness map**, not a self-enforcing exact-membership commit protocol.
