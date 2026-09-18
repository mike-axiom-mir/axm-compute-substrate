# Independent verifier — Wave 134 rotation private-key temp residue

Status: **DRAFT / UNMERGED / NON-CANON / DO NOT AUTO-MERGE**.

This verifier lane challenges the newest Wave 134 builder state without rewriting builder evidence or implementation.

- Builder evidence head challenged: `0f326221584e45723e8a9855f4d8fad5635711ac`
- Exact successful Wave 134 implementation named by the builder receipt: `20abcb846a48709dba4ba345380a1782f3fa83c8`
- Exact CI-tested verifier head: `12e96da5486c4bf5372feb2cc7bcac75478655e4`

## What survives independently

The unchanged Wave 134 recoverable-bootstrap self-test passed again in the independent verifier workflow:

- **12/12 normal Python**
- **12/12 `python -O`**

So Wave 134's stated bootstrap-only recovery result survives. In particular, the PR-58-style bootstrap temp residue is recoverable under the exact owner/mode/content rules Wave 134 claims, and wrong-byte / wrong-owner controls still fail closed.

This verifier does not reclassify that bounded result.

## New reproduced next-gate failure

`FAIL_ROTATION_PRIVATE_KEY_ATOMIC_KILLS_RETAIN_HISTORICAL_SECRET_TEMPS`

Wave 134 repairs bootstrap publication but explicitly delegates the actual key rotation transaction to the older Wave 132 implementation. That implementation still writes `response_private.pem` through the random-name shared `_atomic_write` helper (`response_private.pem.tmp-<pid>-<random>`).

The verifier uses the unchanged production rotation path and pauses only the exact `os.replace(temp, response_private.pem)` call after the temp file has already been fully written and `fsync`ed. A parent then delivers real `SIGKILL`.

The exact same rotation was cut **three times** before allowing a normal exact retry. In both normal and optimized Python:

- three authority-owned `0600` temp files remained;
- each file contained the complete **1,704-byte RSA private key** for the pending successor;
- all three files were byte-identical within that run, proving exact retries retained multiple copies of the same secret;
- the clean exact retry still completed rotation sequence 1;
- a second clean rotation completed sequence 2 with a different current response key;
- all three sequence-1 private-key temp files still remained after sequence 2;
- the unchanged Wave 134 validator nevertheless returned success at sequence 2.

Normal-mode retained secret SHA-256: `87a18479cbe949ba3a21eff47b6038c574aad400dad1a669de21a8ff6c8c3e8b`.

Optimized-mode retained secret SHA-256: `5b768094db5b9ab6ce2f482ca56d663158c71d8356061bf5c1f9d91de03a69f5`.

This is a **key-custody / crash-residue / retained-state amplification failure**, not stale-authority acceptance. Under the tested dedicated-UID boundary, the ordinary worker did not read the `0700` authority directory or the stale keys. No signature, key, hash, ledger, certificate, or authority state was forged. The issue is that repeated crash/retry can silently accumulate full historical private-key copies, and normal validation does not treat them as residue once rotation succeeds.

## Exact CI evidence

Independent workflow run: `35328632211`  
Job: `105547531871`  
Conclusion: **success**

The job ran on Ubuntu 24.04.5 / Python 3.12.14 / OpenSSL 3.0.13. Runner worker UID was `1001` with `CapPrm=0` and `CapEff=0`; the test authority UID was `23001`.

All four required executions succeeded:

1. unchanged Wave 134 builder control normal — **12/12 PASS**;
2. unchanged Wave 134 builder control optimized — **12/12 PASS**;
3. adversarial reproducer normal — reproduced `FAIL_ROTATION_PRIVATE_KEY_ATOMIC_KILLS_RETAIN_HISTORICAL_SECRET_TEMPS`;
4. adversarial reproducer optimized — reproduced the same failure.

Artifact: `10539743946` (`wave134-rotation-private-temp-residue-verifier`)  
Artifact size: 7,957 bytes  
Artifact ZIP SHA-256: `36b87d111c3e060370b58dab4ba6e355c8ba23d0550d14be09ee8ff04dc3663c`

Reproducer: `verification/wave134_rotation_private_temp_residue_repro.py`  
Workflow: `.github/workflows/verifier-wave134-rotation-private-temp-residue.yml`

## Truth boundary

This counterexample is deliberately inside the next gate Wave 134 itself names: **the full rotation transaction**. It does not falsify Wave 134's bounded bootstrap-publication recovery claim.

It proves only a same-host Linux/process/filesystem crash-residue condition at the private-key publication boundary. It does not prove an ordinary worker can read the authority-owned residue under the current separate-UID deployment, does not prove cross-host or namespace compromise, and makes no speed, energy, throughput, retained/incremental/dormant-compute performance, hardware, provider, or physical-finality claim.

## Next adversarial gate

Apply recoverable exact-intent publication to the **entire rotation transaction**, especially every write containing private material (`pending_private.pem` and `response_private.pem`). A successful exact retry must either safely resume or remove every provably related helper file; wrong-byte, foreign-owner, stale, ambiguous, and unrelated candidates must remain fail-closed and preserved for inspection.

Then fault every internal write stage at 1 / 10 / 100 repeated SIGKILLs and verify both correctness and secret-residue growth: after successful recovery and a later key rotation, no retired private-key temp copies should remain unless an explicit audited retention policy requires them. After that survives, return to validation→service object identity and copied-genuine-key cross-namespace / cross-host divergence.
