# Flowing Compute Wave 138 — Object-Bound Consumption Receipt

Status: experimental evidence only / NON-CANON / no automatic merge.

## Provenance

- predecessor evidence head (Wave 137): `655c9306e457cd6ac24091e93eab9367b91d0693`
- exact tested Wave 138 source head: `badefa4af2199168fba3907e3144f8bc95180b76`
- exact tested parent: `5a0a1fad4baa4fc48e4daf767b39429f6583364d`
- Wave 137 namespace tool blob: `4d95b9c509485dbfb8f46e0c0ff23357e1d1402c`
- Wave 138 object-binding tool blob: `c58b454c5fb0f5c4dc3942e8943d2e4346cf3fcb`
- Wave 138 adversarial self-test blob: `1e1f145497186a1cd56b37d1420ca5a952aaa9af`
- Wave 138 workflow blob: `d3c9e6559583e04c168146ea9b0c7cdd0b54bb5b`
- GitHub Actions run: `35352395375`
- job: `105623403324`
- artifact: `10550446638` (`wave138-exact-object-binding`)
- artifact digest: `sha256:978f3197049de5a302310fb668a2ce4e2b0753b5fe66ad62dd76fa990e0b6d02`

## Result

The exact source above completed successfully on Ubuntu 24.04 / Python 3.12 / OpenSSL with:

- unchanged Wave 137 regression: **7/7 normal + 7/7 `python -O`**;
- Wave 138 exact-object adversarial suite: **8/8 normal + 8/8 `python -O`**.

No failed Wave-138 implementation CI preceded this first green exact-source run. The important failures are retained adversarial predecessor counterexamples below rather than hidden by the successful replacement.

## Counterexamples retained

Wave 137 validated the stable rotation namespace correctly, but a later consumer could still reopen a pathname and therefore consume a different object than the one implicitly trusted during validation.

1. **Current response private key substitution:** validate key A, replace `response_private.pem` with genuine key B, then call the predecessor path-based signer. The produced signature verifies under B and **does not** verify under the public key for A that validation had just accepted.
2. **Authority lineage rollback substitution:** validate a legitimate sequence-2 lineage, replace the authority-lineage pathname with the canonical historical sequence-1 file, then reopen the pathname. The predecessor consumer reads sequence 1 despite having just validated sequence 2.

These are controlled same-authority-UID attack fixtures that demonstrate validation-to-use pathname drift; they are not claims of an unprivileged worker bypass.

## Wave 138 behavior

Wave 138 adds a reusable bound-object boundary for stable rotation state:

- open with `O_NOFOLLOW` where available;
- `fstat` the opened regular file and bind device/inode, owner, mode, size and SHA-256;
- read the exact bytes through that already-open descriptor;
- require the path to still identify the same inode at bind completion;
- compare bound lineage/state/key bytes back to the sequence, lineage head and current public-key fingerprint returned by Wave 137;
- derive the public key from the bound private bytes and require an exact match;
- consume those already-bound bytes for cryptographic signing instead of reopening the private-key pathname.

Positive/negative evidence includes:

- clean sequence-2 state binds successfully;
- private-key substitution between Wave-137 validation and Wave-138 binding fails closed (`wave138-current-private-public-snapshot-mismatch`) and the substituted object remains visible;
- after successful binding, swapping the private-key pathname no longer changes the signer: the signature verifies under the bound original public key, not the substituted key, while `path_still_matches_bound_inode` reports false;
- lineage rollback between validation and binding fails closed (`wave138-lineage-seq-mismatch`) and remains visible;
- after successful binding, pathname rollback to sequence 1 leaves the bound consumer at sequence 2 while a fresh reopen sees sequence 1;
- public-key symlink substitution is rejected by the no-follow open and the symlink remains visible.

## Truth boundary

This is **same-host Linux stable-state filesystem TOCTOU evidence**, not a proof against an attacker who controls the authority process or its memory, an attacker generally operating as the authority UID, root/kernel compromise, user-namespace UID aliasing, copied genuine keys on another host, coordinated whole-domain rollback, hardware-backed non-exportable custody, provider independence, or physical finality.

Wave 138 does **not yet** thread descriptor/byte binding through the live pending-transaction rotation writer; that path remains the next local TOCTOU target. It also does not turn path metadata into an external uniqueness/finality source.

No real AXM/monolith performance workload and no synthetic scaling workload were run in this wave because this was a correctness/security gate. Therefore there is **no new speed, energy, retained/incremental/dormant-compute, throughput or scaling claim**.

Generated JSON reports remain CI artifact ballast rather than being committed. The reusable tool, adversarial self-test, workflow, and this concise receipt are preserved in-repo.

No merge, auto-merge, CANON promotion, or predecessor evidence rewrite was performed.

## Next gate

Thread the same exact-object discipline through the **pending rotation transaction writer**: bind/read the pending intent, predecessor certificate, successor key material and lineage inputs so validation cannot be followed by a path/inode substitution before signing or publication. Preserve positive recovery and negative substitution fixtures. After the remaining same-host validation-to-use seams are bounded, resume the larger architectural test with two genuinely current copied authorities in separate namespaces/hosts attempting divergent successor authorization; if both chains validate, preserve that as evidence that signatures prove possession, not uniqueness.
