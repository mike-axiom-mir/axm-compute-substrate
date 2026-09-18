# Wave 125 independent adversarial verification

Status: **DRAFT / verifier-only / NON-CANON / do not merge automatically.**

Builder evidence head inspected: `f7c5d920a01acae729745aaf0e0b51f8cb928163`.  
Exact builder CI-tested source: `d9b9621bd26f6bf981bfd0f8b51881aaf3f0c886`.  
Independent executable verifier head: `b9a3253c0dd2d1d510db75aa5b10ba5b45e3518e`.

## What was tested

This lane leaves the Wave 125 builder files unchanged and attacks two boundaries:

1. **Hard `SIGKILL` after host-pin publication but before the client reply.** This is later than Wave 125's built-in `SIGKILL` cut after ledger fsync but before pin publication. Expected safe behavior is restart with the witness ahead of the local receipt, exact recovery of that already-durable receipt, then restored authority.
2. **Host-pin namespace pathname replacement.** This is a narrower form of the trust-domain replacement boundary already excluded by Wave 125. The accepted newer witness store is left intact. Only `/tmp/axm-flowing-compute-wave125-host-v1-<uid>` is renamed aside and replaced by a fresh same-owner mode-0700 directory at the same public pathname. After the original witness releases its kernel credential lease, a genuine stale clone is started against the fresh namespace.

No credential, HMAC, hash, root, or accepted-current witness ledger is forged or rewritten. No builder evidence is deleted or rewritten.

## Independent CI

Run `35294548142`, job `105444280453`, conclusion **success** on Ubuntu 24.04 / CPython 3.13.15.

- unchanged Wave 125 self-test: **11/11 PASS normal**;
- unchanged Wave 125 self-test: **11/11 PASS under `python -O`**;
- adversarial verifier: **3/3 expected controls PASS normal**;
- adversarial verifier: **3/3 expected controls PASS under `python -O`**.

Artifact `10528325110` (`wave125-host-pin-namespace-verifier`), ZIP SHA-256:

`ddebc0894e994ad5a2cffc66ac66a6537d5e7f55810abcd28f0f6bc965b5abf8`

The artifact preserves both unchanged builder reports, both adversarial reports, the tested Git head, and exact source blob identities.

## Result A — late crash survives

`sigkill_after_host_pin_before_reply_recovers_exact_receipt` reproduced safely in both Python modes.

At the kill point the witness ledger already contained the terminal COMMIT and the external host pin had already advanced to sequence 1, but the client had received no reply and therefore had no local receipt. After restart:

- the host pin remained at sequence 1;
- the witness ledger remained at sequence 1;
- local status was correctly `HOLD_WITNESS_AHEAD`;
- `recover_exact` recovered the exact existing witness record rather than creating a competing decision;
- final status became `AUTHORITATIVE_PROCESS_WITNESS_COMMIT`.

This strengthens Wave 125 inside its same-host trusted-host-pin boundary.

## Result B — host-pin namespace identity fails at the next boundary

The adversarial result reproduced in both Python modes:

`FAIL_HOST_PIN_NAMESPACE_REPLACEMENT_REOPENS_STALE_CLONE`

Exact sequence:

1. The original Wave 125 witness accepted a genuine HOLD prefix at sequence 1.
2. A byte-identical stale witness clone was taken at that legitimate prefix.
3. The original then accepted a genuine stable COMMIT at sequence 2. Its local state reported `AUTHORITATIVE_PROCESS_WITNESS_COMMIT`, and the external host pin advanced to sequence 2.
4. While that original server remained live, only the public host-pin namespace pathname was renamed aside and a fresh empty same-owner/mode directory was created at the expected pathname.
5. The already-running original continued to report host-pin sequence 2 through its previously opened host-directory file descriptor. This confirms the newer witness state itself was not rolled back or rewritten.
6. The original server was then stopped, releasing only the abstract credential lease.
7. The genuine stale witness clone started successfully against the fresh replacement namespace. With no previous pin visible at that pathname, it bootstrapped a new host pin at sequence 1 and served the older valid prefix with no terminal record.
8. The original witness store and the original sequence-2 host namespace both still existed intact.
9. After stopping the stale clone and restoring the exact original host namespace, the exact current witness immediately returned to host-pin sequence 2 and `AUTHORITATIVE_PROCESS_WITNESS_COMMIT`.

So the high-water protection is monotonic only while the external host-pin namespace itself is trusted and continuously identified. Its current identity is effectively the mutable pathname plus OS-user assumptions; the newer accepted witness did not have to be erased for an older cloned world to become serviceable after that namespace was substituted.

This is **not a falsification of Wave 125's stated claim**, because Wave 125 explicitly excludes replacement/rollback of the host-pin namespace. It is a preserved failure of the next trust boundary and must not be silently promoted into physical finality, host-independent monotonicity, or anti-rollback claims.

## Performance / retained-state truth boundary

No real AXM workload, scaling benchmark, energy measurement, or retained/incremental/dormant-compute comparison was run in this verifier wave. There is therefore no new performance win or loss to claim from these results.

## Next adversarial gate

Move the monotonicity anchor outside a mutable host-local `/tmp` namespace and give that anchor an independently verifiable identity before advancing referee rotation.

Required attacks for the next gate:

- replace/rename the host-pin storage namespace while the witness is live and after it exits;
- attempt stale-clone bootstrap against a fresh namespace and require HOLD rather than silent re-initialization;
- clone the exact credential/witness into a second Linux network namespace or second host where the abstract-socket lease cannot collide;
- test mixed Wave 124/Wave 125 downgrade paths;
- retain the now-passing hard kill after pin fsync but before reply as a regression control;
- distinguish legitimate host-pin migration/recovery from rollback or namespace substitution without trusting only a pathname.

Until an actually independent monotonicity domain defeats these cases, whole-domain rollback/substitution remains a live counterexample and no CANON promotion is justified.
