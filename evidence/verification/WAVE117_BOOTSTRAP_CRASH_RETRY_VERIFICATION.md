# Independent verification — Wave 117 bootstrap crash / exact retry

Status: **adversarial verifier lane only**. Do not merge automatically. Do not promote CANON from this file.

Builder source under test: `1c033d96e792c9f8532bf2355c9f1ec958da969a` (`chatgpt/lane-001-platform-extract`).

## Builder result that survives

Wave 117's intended repair for verifier PR #41 is coherent at the inspected source boundary: accepted Wave-105 checkpoint/binding history indirectly commits one exact Wave-117 outcome-authority root, retained bindings must resolve to that same root while rotation is unsupported, and the mutable Wave-116 signer binding must agree with the checkpoint-anchored root. The builder self-test also includes root-body, root-store, envelope, credential-substitution, and two-epoch controls. This verification does not claim OS-process, physical-device, provider, power-loss, performance, energy, or retained/incremental/dormant-compute evidence.

## Counterexample

Verdict label if reproduced by CI:

`FAIL_WAVE117_BOOTSTRAP_CRASH_HAS_NO_PUBLIC_RETRY_RECOVERY`

Wave 117 `adopt_genesis(...)` currently performs durable modeled writes in this order:

1. reject immediately if either Wave-117 root/envelope store already exists;
2. persist the outcome-authority root;
3. persist the application/root envelope;
4. change the runtime app-state pointer;
5. only then invoke the lower Wave-116 genesis adoption.

The verifier simulates two crash cuts before step 5:

- after the root write only;
- after both root and envelope writes.

For restart, the runtime dictionary is restored to its pre-call value; only the modeled durable records already written into `st` survive. The exact same public Wave-117 `adopt_genesis(...)` call is then retried twice.

Expected recoverability boundary: an exact retry should be able to resume/reconcile its own partial bootstrap, or the implementation should expose a bounded recovery path that proves the partial records belong to the same requested genesis. A different outcome authority must never be allowed to hijack that partial bootstrap.

Observed source-level hazard: the retry reaches the top-level `OUTCOME_ROOT_STORE in st or ENVELOPE_STORE in st` guard and raises `wave117-root-anchor-state-already-present` before lower genesis can run. If reproduced, Wave 117's own pre-genesis records permanently block the normal public initialization path even though no lower authority binding, transition, or accepted genesis was created.

## Security boundary

This is **not** a stale-authority takeover and does not show a forged checkpoint, HMAC, hash collision, or accepted contradictory history. It is a fail-closed **bootstrap liveness / evidence-atomicity** failure: safety remains conservative, but a legitimate exact retry cannot finish initialization after a crash between Wave 117's new durable writes and lower genesis adoption.

## Secondary cost to measure next

`prepare(...)` writes a new content-addressed Wave-117 envelope before delegating to lower preparation. Repeated rejected/abandoned prepares with distinct requested app-state SHAs can therefore leave envelopes that are never referenced by accepted binding history. This is a retained-storage/garbage-growth risk, not yet a timing, energy, or scaling result; it should be measured rather than inferred.

## Next adversarial gate

Make genesis bootstrap two-phase or idempotently resumable. A restart should validate the exact partial root/envelope against the requested outcome authority and original app state, then either safely resume the lower genesis adoption or expose a narrow repair operation. A mismatched retry must fail without rewriting the partial identity. Test crashes after every durable write, repeated restarts, wrong-authority retry, wrong-app-state retry, and cleanup rules for genuinely abandoned pre-genesis records. Then measure rejected-prepare orphan-envelope growth before adding signer rotation or separate-process durability claims.
