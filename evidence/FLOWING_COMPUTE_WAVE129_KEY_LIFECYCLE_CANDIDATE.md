# AXM Flowing Compute — Wave 129 candidate evidence

Status: EXPERIMENTAL / NON-CANON / exact-source green receipt not yet recorded at this note.

## Source continuity

- Wave 128 evidence head: `f3e6c9bb775a9fec8204342e5d0bffff54ea42cb`
- Wave 128 tested source: `a84f80672a2c54c02ad89479ec4c7c091a93f1d3`
- Independent verifier PR: `#53`
- Verifier tested head: `a06cc52793a41a5635e9b9aa23c0a1dcdd3b60ea`
- Verifier CI run: `35306142204`
- Verifier artifact SHA-256: `fb9f915e763b7df9917192c22c4c1fe4cf9b0ca48b1a191ce73ed8dd9079a0f0`
- Wave 129 candidate head before this note: `404e65decd51326ee5730754fda71f7a3e641a24`

## Preserved counterexample

Wave 128 protected the long-lived anchor and crypto children, but its ordinary initializer process remained dumpable while a newly generated response private PEM existed in Python heap immediately before `response_private.pem` persistence. On the verifier host, a same-UID direct parent without `CAP_SYS_PTRACE` recovered that exact valid key through `/proc/<pid>/mem`. The counterexample is retained and is required to reproduce in the Wave 129 adversarial suite before the fix is accepted.

## Candidate change

Wave 129 makes the initializer enter and verify Linux non-dumpable custody before anchor initialization, key generation, or private response-key bytes can enter Python memory. The Wave 128 memfd signing path, response protocol, durable layout, identity pins, authenticated ledger behavior, and fail-closed rules are otherwise preserved.

The new adversarial suite also retains a second boundary deliberately: `SIGKILL` immediately before private-key persistence must leave no private response-key file and must not allow the partial anchor to serve. That partial initialization is not yet claimed to be automatically resumable.

## Verification contract

The exact-source workflow must rerun unchanged Wave 128 full protocol and focused custody tests in normal and `python -O`, then run the Wave 129 lifecycle suite in both modes. Generated JSON reports remain CI artifacts rather than repository ballast. A later receipt may claim green only from the exact tested source and artifact identity actually produced by CI.

## Truth boundary

This candidate concerns same-Linux-host, same-UID process-memory custody against the tested direct-parent `/proc` adversary. It does not claim root/kernel resistance, protection from an actor already permitted to read the anchor store, cross-host/cross-namespace key uniqueness, whole-domain rollback resistance, hardware-backed key custody, device/power/provider/physical finality, or any speed, energy, retained/incremental/dormant-compute, throughput, or scaling result.

No merge, auto-merge, or CANON promotion is authorized by this note.
