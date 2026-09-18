# Independent verifier — Wave 133 atomic-temp SIGKILL boundary

Status: **DRAFT / UNMERGED / NON-CANON / DO NOT AUTO-MERGE**.

Builder evidence head inspected: `be2bf60d834a4feab9e7a49f166c92a7e464684c`.
Exact green Wave-133 implementation named by the builder receipt: `1a6867e4ee1ddeb8010cf1115da9efe5ac246f5f`.
Builder Wave-133 tool blob: `934dad194c800bcf768bdac918fe02fbe8449495`.
Shared atomic-write helper blob: `2e87f9416d8ec0d9d04b46e842ac2d7a1a9e0f08`.

## What survives independently

The unchanged Wave-133 self-test reran on the verifier head and remained green:

- **12/12 normal Python**
- **12/12 under `python -O`**

Therefore this verifier does not contradict Wave 133's stated result: exact recovery after the seven named **post-publication** SIGKILL boundaries works within the tested same-host boundary.

## New reproduced next-gate failure

`FAIL_EXACT_RETRY_AFTER_SIGKILL_BEFORE_ATOMIC_REPLACE_IS_BLOCKED_BY_OWN_STALE_TEMP`

Wave 133's receipt explicitly excludes a kill *inside* the atomic-write implementation. The verifier widened only that natural boundary. It leaves the production `_atomic_write` path unchanged through creation of the random same-directory temp file, exact data write, `fsync`, close, and the call boundary immediately before `os.replace(temp, final)`. The verifier delays only that `os.replace` call long enough for the parent to send a real `SIGKILL`.

For `response_rotation/bootstrap.json`, both normal and optimized Python reproduced the same result:

1. the exact production temp file existed and was already fsync'd;
2. the process died with SIGKILL before rename;
3. the final `bootstrap.json` did not exist;
4. the orphan `bootstrap.json.tmp-<pid>-<random>` remained unchanged;
5. the first exact Wave-133 retry failed with `RuntimeError:wave133-unexpected-pre-ready-artifacts:<temp>`;
6. a second exact retry failed identically and retained the same temp bytes;
7. removing only that orphan helper temp as a diagnostic immediately restored the unchanged authorized Wave-133 bootstrap + rotation path to sequence 1.

Normal orphan intent size: **826 bytes**, SHA-256 `fbb9a47e7137ac7787654757b145488facda73bafb4620c9db973f0350d57170`.
Optimized orphan intent size: **826 bytes**, SHA-256 `c8fa109b6c4c8d971e2679939e6cad693c6487bd19ed3df6c94f32c53dd851fa`.
The hashes differ because each independently initialized authority has distinct genuine identity material; the important invariant is that each exact orphan temp persisted unchanged across both failed retries.

This is fail-closed liveness loss, not stale-authority acceptance: Wave 133 refuses the unexpected residue rather than silently trusting it. But it means the current "exact crash recovery" envelope stops at publication boundaries and does not yet recover from its own atomic-helper residue.

## Retained-state side effect

A second cut targeted the bootstrap write of the witness-side `anchor_response_rotation.jsonl`. The same pre-`os.replace` SIGKILL left `anchor_response_rotation.jsonl.tmp-*` behind. In this location, Wave 133's retry **did succeed** and completed a genuine sequence-1 rotation, but the zero-byte orphan temp remained resident afterwards in both Python modes.

So the same helper-level crash can have two different outcomes depending on directory placement:

- anchor `response_rotation/` temp residue blocks exact recovery because the strict pre-ready allowlist rejects it;
- witness-directory temp residue is ignored and retained after successful recovery.

This is not a performance benchmark or evidence that retained/incremental/dormant compute is bad generally. It is a concrete retained-filesystem-state cleanup boundary.

## Exact CI evidence

Verifier executable/CI head: `73e8b105ce2e04b66f4305e5861e77b245f1b83c`.
Verifier script blob: `441943f090faa98c91862a5f63920e99c7cb5725`.
Verifier workflow blob: `537c5c6d2a271e050a78a7461fb3ad6272817ae1`.
Wave-133 unchanged self-test blob: `a0ab0a3df04cffc6e849075c3885687ce70e1a4a`.

GitHub Actions run `35323372319`, job `105530718148`: **success**.

Artifact `10537793987` (`wave133-atomic-temp-kill-verifier`), 9,092 bytes, GitHub SHA-256:
`0172b66828877ec78687bef4b083b2d23090b1f38aad825074f0ccd1dc8a05da`.

The artifact contains both unchanged Wave-133 control reports, both adversarial reports, exact builder/tested-source identities, exact tool/self-test/helper/verifier/workflow blob identities, and verifier head/parent.

## Truth boundary

This counterexample is same-host Linux/process/filesystem only and deliberately lands at the real production atomic-helper boundary immediately before rename. It is **outside Wave 133's stated post-publication SIGKILL claim**, so Wave 133 keeps its bounded 12/12 result.

No root/kernel compromise, authority-key forgery, copied-key cross-host uniqueness, provider independence, physical finality, speed, energy, throughput, or broad retained/incremental/dormant-compute claim is made.

## Next adversarial gate

Make atomic-helper crash residue an explicit recoverable state. A safe repair should recognize only temp files that are provably from the exact intended write, validate their bytes/ownership/mode, either finish the exact rename or safely discard them, and never adopt attacker-created lookalikes. Then fault every bootstrap artifact at: temp create, partial temp write, post-write/pre-fsync, post-fsync/pre-close, post-close/pre-rename, post-rename/pre-directory-fsync, plus multiple stale temps and wrong-byte temp collisions.

After that, return to the higher authority gates already open: validation-to-service pathname identity binding and genuine copied-key cross-namespace/cross-host divergence.
