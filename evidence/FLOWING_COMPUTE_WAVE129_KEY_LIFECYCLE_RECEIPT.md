# AXM Flowing Compute — Wave 129 exact-source receipt

Status: **EXPERIMENTAL / NON-CANON / GREEN**

No merge, auto-merge, or CANON promotion is authorized by this receipt.

## Continuity and provenance

- Wave 128 evidence head: `f3e6c9bb775a9fec8204342e5d0bffff54ea42cb`
- Wave 128 tested source: `a84f80672a2c54c02ad89479ec4c7c091a93f1d3`
- Independent verifier PR: `#53`
- Verifier tested head: `a06cc52793a41a5635e9b9aa23c0a1dcdd3b60ea`
- Verifier CI run: `35306142204`
- Verifier artifact SHA-256: `fb9f915e763b7df9917192c22c4c1fe4cf9b0ca48b1a191ce73ed8dd9079a0f0`

## Preserved Wave 128 counterexample

Wave 128 protected the long-lived anchor process and OpenSSL signing children, but the ordinary Python initializer remained dumpable while a newly generated response private PEM existed in its heap immediately before `response_private.pem` persistence. On the verifier host, a same-UID direct parent without `CAP_SYS_PTRACE` recovered that exact valid private key through `/proc/<pid>/mem`; the recovered private key matched the public verifier later persisted for the witness. That reopened fresh valid signed socket substitution without breaking the cryptography.

Wave 129 keeps this counterexample as a required predecessor control rather than rewriting it away.

## Wave 129 change

Wave 129 makes anchor initialization enter and verify a Linux non-dumpable process boundary **before** anchor initialization, response-key generation, or response private-key bytes can enter Python memory. If `PR_SET_DUMPABLE` cannot be disabled or `PR_GET_DUMPABLE` does not report zero, initialization fails closed.

The Wave 128 protocol and storage behavior otherwise remain unchanged: anonymous `memfd` signing, non-dumpable serving/crypto children, exact response identity pinning, authenticated witness/anchor history, append-only evidence, and the existing fail-closed rules are preserved.

## Exact-source verification

Final tested source:

`d0bab11db00abf9c635d3827b0138f28cbb19fde`

GitHub Actions:

- run: `35308480979`
- job: `105485442852`
- result: success
- artifact: `10532736561` (`wave129-key-lifecycle-custody`)
- artifact SHA-256: `13dc5338813209e28724da3fa804a95a254a8146852a3be5696ffa8c4d0bb242`

Exact regression/adversarial results:

- unchanged Wave 128 full protocol: **9/9 normal + 9/9 under `python -O`**
- unchanged Wave 128 focused key-custody suite: **7/7 normal + 7/7 under `python -O`**
- Wave 129 full initialization-lifecycle custody suite: **8/8 normal + 8/8 under `python -O`**

Wave 129's eight checks require that the CI adversary has no `CAP_SYS_PTRACE`; the unchanged Wave 128 initializer counterexample still reproduces; Wave 129 is already non-dumpable before the private-key persistence cut; the same-UID direct parent cannot recover the Wave 129 private key through `/proc`; the persisted private key remains mode `0600` and exactly matches the pinned public verifier; the completed store restarts with the exact authenticated response identity; a real `SIGKILL` before private-key persistence leaves no response private-key file; and that partial hard-killed initialization refuses to serve instead of inventing or accepting an identity.

The final runner was Ubuntu 24.04.5 / Linux `6.17.0-1022-azure`, Python 3.12.14, OpenSSL 3.0.13, uid 1001, `CapEff=0`, Yama `ptrace_scope=1`.

## Preserved failed exact-source run

The first exact-source Wave 129 workflow run is retained as evidence rather than hidden:

- run: `35308128251`
- job: `105484421897`
- tested head: `404e65decd51326ee5730754fda71f7a3e641a24`
- result: failure

All unchanged Wave 128 controls and the Wave 129 normal lifecycle suite passed. The optimized Wave 129 step failed before its security assertions because the test parent observed the pause-marker pathname during `Path.write_text()` before its JSON payload was readable, causing `json.JSONDecodeError` on an empty marker. No Wave 129 custody implementation changed in response. A CI-only readiness wrapper now waits for complete parseable JSON before treating JSON marker files as ready. The exact rerun above passed in both normal and optimized modes.

## Truth boundary and retained negatives

This wave proves only the tested same-Linux-host, same-UID direct-parent `/proc` memory-custody boundary without `CAP_SYS_PTRACE`. It does **not** claim protection against root/kernel compromise, an actor already permitted to read the durable anchor store, copied genuine response keys in another network namespace or host, hardware-key compromise, device/power/provider failure, or physical finality.

The hard-kill case deliberately leaves another counterexample visible: killing initialization before response-key persistence can leave partial lower anchor initialization. That state fails closed and cannot serve, but Wave 129 does **not** yet make that interrupted initialization automatically resumable. Whole witness+anchor rollback and independently copied genuine identities also remain open.

No real AXM/monolith performance workload and no synthetic scaling workload were run in Wave 129 because this was a correctness/security gate. Therefore there is **no new speed, energy, retained-compute, incremental-compute, dormant-compute, throughput, or scaling claim**.

Reusable implementation, adversarial test, deterministic CI harness, and concise evidence are kept in the repository. Generated JSON reports and exact-source identity outputs remain Actions artifacts rather than repository ballast.

## Next gate

First make interrupted anchor initialization explicitly recoverable using only exact durable identity/provenance, while rejecting mismatched leftovers, rollback, and ambiguous partial state. Then resume the copied-genuine-key fork attack across a separate Linux network namespace and preferably a second host. If two genuine copies carrying the same real response key can advance conflicting authenticated histories across that larger boundary, preserve that counterexample and require independently retained authority/rotation lineage instead of treating signatures as uniqueness.
