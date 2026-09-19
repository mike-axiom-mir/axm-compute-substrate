# Wave 123 independent verifier evidence — overlapping witness instance

**VERIFIER ONLY / NON-CANON / DO NOT AUTO-MERGE**

This evidence belongs to the independent adversarial verification lane. It does not rewrite builder evidence, promote a result to CANON, or claim a broader physical/system guarantee than the experiment actually tested.

## Exact source boundary

- Builder evidence head: `fe431e64b3aee7840cff848395aef2e9af2847db`
- Builder tested source commit: `b594d1bac276c11f98ce6a6f558fb929ed0c30eb`
- Wave 123 witness tool blob: `2e87f9416d8ec0d9d04b46e842ac2d7a1a9e0f08`
- Verifier CI-tested head: `e905ac1937a6bb59b4a4591d96b60ed6ec916628`
- Verifier CI run: `35285936043`
- Verifier CI job: `105418137333`
- Artifact: `10524620838` (`wave123-overlapping-witness-verifier`)
- Artifact ZIP SHA-256: `3f1f64de3a8836588285e40f411f106abf18cd4616083732d051072e096afdaf`

## Builder controls independently rerun

The unchanged Wave 123 builder self-test passed:

- normal Python: **19/19 PASS**
- `python -O`: **19/19 PASS**

This preserves the bounded builder result: separate-process witness behavior, tested SIGKILL boundaries, pin mismatch handling, corruption/truncation failure, local rollback detection, and the builder's explicit whole-domain rollback counterexample all still behave as the Wave 123 suite says.

The builder truth boundary also remains important: same host/filesystem only; `fsync` is not physical power/device/controller/kernel finality; no network/provider independence, Byzantine consensus, performance, energy, or retained/incremental/dormant-compute claim.

## New counterexample

**Failure label:** `FAIL_OVERLAPPING_WITNESS_INSTANCES_ACCEPT_CONTRADICTORY_TERMINAL_OUTCOMES`

Wave 123 has no exclusive witness-store lifetime lease/lock. `serve()` removes an existing Unix-socket pathname before binding a replacement process. An already-established connection to the old process remains alive even after that pathname is unlinked and rebound. `decide()` separately performs load/verify -> terminal-conflict check -> choose next `(seq, prev_record_sha)` -> append, without cross-process serialization covering that whole transaction.

The verifier therefore:

1. creates the genuine Wave 123 witness identity;
2. seeds **20,000 valid authenticated retriable HOLD records** using the exact Wave 123 sealing code (12,548,894 ledger bytes) only to widen the ordinary load/verify window;
3. starts witness A and opens a live connection to it;
4. starts witness B against the **same witness directory and same configured socket path**;
5. races a stable `COMMIT` through the still-live connection to A against a stable `REJECT` through the replacement socket to B for the exact same `(authority_sha, transition_sha)`.

No credential, hash, signature, or prior record is forged or rewritten.

### Normal Python reproduction

Reproduced on attempt 1.

- old witness PID: `2276`
- replacement witness PID: `2277`
- both processes used the same genuine credential fingerprint
- authority SHA: `9eb55bb86efbaa9653b0274b5eaf788f35ea9c1e18c06080612c76a6f98319fb`
- transition SHA: `2f2c79e210ebc769a4bdb86ad22322b36eb303201e09b1a83b720befd68e9e7b`
- old process returned `ok: true` for `COMMIT`
- replacement returned `ok: true` for `REJECT`
- both returned sequence `20001`
- both used the same `prev_record_sha`: `c3ebe02cf86af450e528811d0d263072df3470757e3460ed88128a622f788b07`
- the returned records had different authenticated `record_sha` values
- both returned witness acknowledgements could be preserved as individually valid local receipts using the existing Wave 123 local receipt primitive
- subsequent full ledger validation failed closed with `ValueError:ledger-chain-position-mismatch`

### `python -O` reproduction

Reproduced on attempt 1 again.

- old witness PID: `2315`
- replacement witness PID: `2316`
- both terminal requests again returned `ok: true`
- exact same deterministic authority and transition identities were used
- both again chose sequence `20001` and the same predecessor, but produced different authenticated sibling records (`COMMIT` vs `REJECT`)
- subsequent validation again failed `ValueError:ledger-chain-position-mismatch`

## What failed vs what survived

**Failed:** the witness is not yet a single linearizable terminal-outcome authority across overlapping/restarted process instances. During the overlap window, two genuine processes holding the same genuine witness identity can each acknowledge mutually contradictory terminal outcomes for one exact authority/transition before later validation notices the damaged chain.

**Survived:** after the contradictory sibling records are present, later ledger validation fails closed. This verifier did **not** demonstrate stale authority being accepted after the corruption was detected. It demonstrated contradictory authenticated acknowledgements plus evidence-chain corruption / availability loss before that later fail-closed check.

The long HOLD prefix is not a benchmark baseline and does not establish a performance result. It only widens an existing check-then-append race using valid evidence. No speed, energy, retained-state efficiency, dormant-compute advantage, physical power-loss survival, or provider independence is inferred.

## Next adversarial gate

Make witness-store ownership exclusive and make terminal decision publication linearizable across process lifetimes. A replacement must not silently take ownership merely by unlinking/rebinding the Unix socket while an old witness can still act. The read/verify/conflict-check/next-sequence/append transaction also needs serialization that survives normal restart semantics on the same host.

Then adversarially test at least:

- two simultaneous starters for one witness store;
- old live connection while a replacement starts;
- `SIGKILL` while holding the store lease and restart after kernel lock release;
- stale socket pathname with no live owner;
- stale lock metadata / PID reuse without permanent deadlock;
- process kill between conflict check and append;
- multiple concurrent clients requesting conflicting terminal outcomes;
- directory rename/copy/clone boundaries and explicit truth limits for filesystem locks;
- local receipt writers under concurrency, separately from witness serialization.

A host-local `flock`/OFD-style lifetime lease plus a transaction lock is one plausible implementation direction, but the verifier should test the chosen contract rather than canonize a specific mechanism in advance.
