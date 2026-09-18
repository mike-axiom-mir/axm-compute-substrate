# Wave 137 path-identity TOCTOU adversarial verification

**DRAFT / INDEPENDENT VERIFIER / NON-CANON / DO NOT AUTO-MERGE**

## Builder state challenged

- Active builder lane: `chatgpt/lane-001-platform-extract`
- Latest evidence head observed before and after this verification: `655c9306e457cd6ac24091e93eab9367b91d0693`
- Wave 137 exact repaired implementation parent recorded by builder: `083d356f4fc7c70832d6e30a09bed01d105077ff`
- Wave 137 tool blob at the challenged head: `4d95b9c509485dbfb8f46e0c0ff23357e1d1402c`
- Wave 137 repaired self-test blob: `88f5873ced1ba3fdeca397777691e1d4ec763571`
- Builder evidence says the repaired strict-namespace suite is green and explicitly leaves validation-to-consumer path/inode substitution outside its proved boundary.

## Independent unchanged controls

The final verifier run reran the unchanged repaired Wave 137 suite before the adversarial case:

- normal Python: **7/7 PASS**
- `python -O`: **7/7 PASS**

This independently confirms the repaired Wave 137 namespace tests survive in the same CI environment used for the attack. No performance, energy, retained/incremental/dormant-compute, throughput, scaling, cross-host uniqueness, or physical-finality conclusion is drawn from this run.

## Counterexample

Verdict:

`FAIL_WAVE137_ROTATE_REPORTS_SUCCESS_FOR_VALIDATED_A_WHILE_ROTATING_SWAPPED_B`

Two separately and genuinely initialized authority/witness domains were created: A and B. The verifier paused Wave 137 only at its existing call boundary after its strict preflight scan of A and before the lower Wave 136 rotation consumed the supplied path. An ordinary worker process then renamed the complete B endpoint case into A's pathname. The authority-owned anchor and witness stores themselves were not read or edited by the worker.

Wave 136 then performed a genuine authorized rotation on substituted domain B. Immediately after that lower call returned, but before Wave 137's final strict validation, the same ordinary worker restored the original A pathname. Wave 137 then strictly validated A and returned success.

Observed final state in **both normal and optimized Python**:

- requested/restored domain A: `seq = 0`, `last_rotation_id = null`, strict namespace valid;
- genuine substituted domain B: `seq = 1`, requested rotation id present, strict namespace valid;
- Wave 137 return object: `seq = 1`, requested rotation id present, `wave137_strict_rotation_namespace = true`, and the returned root belongs to domain B;
- worker UID/EUID: `1001`;
- worker `CapEff`: `0000000000000000`;
- mutable ancestor used for the rename: mode `0777`;
- authority UID: `23001`;
- anchor directories remained authority-owned `0700`, and private keys remained authority-owned `0600`.

So the strict preflight object, the object mutated by the lower rotation, and the object used for final strict validation are not bound to one immutable filesystem identity. A path can name A at preflight, B during mutation, and A again at final validation.

### Important bound on the failure

This is a **path/object identity contract failure under a worker-mutable ancestor**, not a cryptographic break. No private key, authority-owned store, signature, hash, or lineage row was forged by the worker. The returned result also exposes B's root identity, so this does **not** prove that a caller which separately pins and checks the expected root identity would be fooled. Likewise, a deployment that makes every relevant ancestor non-worker-writable blocks this exact rename route.

The result does show that Wave 137 itself can set its strict-success flag for the final A namespace while returning the successful rotation state produced from B, without enforcing that preflight, mutation, and final validation refer to one same opened object/domain.

## Verification provenance

Final successful verifier execution:

- verifier branch: `verifier/wave137-rotation-path-toctou-swap`
- exact executable head: `cde16a9629de9a796984afaff41463b0c859947f`
- Actions run: `35349370771`
- job: `105613537784`
- artifact: `10548801628`
- artifact size: `7487` bytes
- artifact SHA-256: `df4548796b5adaf6243a0c6ba9c2ef417fed64de8d5dd7e18d98cd6ad1c9981a`

The artifact contains unchanged Wave 137 normal/optimized control reports, normal/optimized adversarial reports, exact verifier head/parent, Wave 137 tool/self-test blobs, all verifier source blobs, and workflow blob.

### Preserved verifier false starts

Earlier verifier attempts are intentionally retained rather than rewritten away. They tried to move individual anchor entries across per-case parents and were stopped by fixture permissions before Wave 137 was attacked. For example, run `35348981178` / job `105612252191` failed at the worker `rename()` with `EACCES`. A later corrected staging attempt still hit that same fixture boundary. Those are **verifier-harness false negatives, not Wave 137 security passes or product failures**. Versioned verifier files remain on this branch so the diagnostic history is inspectable.

## Next adversarial gate

Bind **preflight validation -> lease acquisition -> mutation -> final validation** to the same opened authority/witness object identity rather than re-resolving mutable pathnames. Candidate approaches include descriptor-relative operations (`openat`/`openat2`-style boundaries), a service-owned non-worker-writable mount/parent, or an explicit immutable identity handle carried through the full transaction. Then attack swaps at every handoff: after bootstrap, after strict preflight, before/after lease acquisition, during pending publication, immediately before final validation, and before serving. Include whole-directory rename, exchange-style swaps where available, symlink/mount-lookalikes where the platform permits them, and verify expected root identity as part of the contract.

After local object identity survives, return to the larger genuine-copy test: two authentic cloned authorities in separate network namespaces/hosts, concurrent forked successors, partition/rejoin, and stale-clone return.
