# Wave 132 independent verifier — rotation-gate pathname swap

Status: **DRAFT / UNMERGED / NON-CANON / independent verifier evidence**.

## Challenged state

- Newest reviewed Wave-132 evidence head: `d9471ae0583a11c8531c8b6f100f5bed1ffeef5f` (`Wave 132: preserve predecessor-authorized rotation evidence`).
- That receipt identifies exact tested implementation head: `60865699c2c2fe1f53860bcb5d0196860ee98086`.
- Wave-132 tool blob challenged here: `6839f537cccb31b913e3206980f8a2a99b81c3b9`.
- Wave-132 self-test blob: `c9039853a0cfd70adb7070ea63d6ac1659369cb9`.
- Builder workflow blob: `f79076586bf333254923f3edf31bc362ccc576ef`.

## Independent controls

The unchanged Wave-132 self-test was rerun from the exact implementation above:

- normal Python: **14/14 PASS**;
- `python -O`: **14/14 PASS**.

This independently preserves the bounded positive result: predecessor-signed successor-key lineage, two consecutive rotations, named post-publication `SIGKILL` recovery/idempotent retry, tampered-certificate rejection, pending-rotation-id separation, witness-verifier rollback detection, witness-lineage tamper detection, and authenticated service with the rotated key all survived their existing modeled checks.

## New counterexample

Verdict in both normal and optimized Python:

`FAIL_WAVE132_ROTATION_GATE_REOPENS_REPLACEABLE_PATH_BEFORE_LOWER_SERVICE`

Wave 132's `serve_anchor()` validates `validate_authority_rotation_state(anchor_dir)` by pathname and then passes the same pathname to the lower Wave-129 server, which opens it again. The verifier widened only that natural validation-to-delegation handoff.

Setup and result:

1. Store A was a genuine authority-owned `0700` Wave-131 anchor, then completed one genuine Wave-132 predecessor-authorized rotation (`seq=1`) and had valid Wave-132 rotation metadata.
2. Store B was a separate genuine authority-owned `0700` Wave-131-ready anchor but was deliberately never bootstrapped into Wave 132, so it had **no** `response_rotation/` state or signed rotation lineage.
3. Both directory entries lived below the same builder-style `0777` parent used by the test harness.
4. The Wave-132 server genuinely validated Store A and the verifier recorded its `seq=1` identity.
5. After validation but before lower-server delegation, an ordinary worker process running as UID `1001` renamed Store A aside and renamed Store B into the exact active pathname. It did not read or enter either authority-owned `0700` store.
6. The unchanged lower authenticated server reopened the pathname, acquired its normal leases, and served Store B. A worker client successfully authenticated a fresh `ping` against Store B's genuine public verifier.
7. At service time the active pathname had **no Wave-132 rotation directory**, while the originally validated Wave-132 store remained preserved under the renamed path.

Normal-mode identities: validated Wave-132 anchor `c4b1d0d15bfef6a24d840030c0c9a910a3e22056d73e28436871d9b2cf6d89b3`; actually served replacement anchor `adac997de7d95b757c1fedcde23493a4c20e680a90f73c970acbb369d89a753a`.

Optimized-mode identities: validated Wave-132 anchor `23c4c388f41d095b2299546bdbd90cb359dac2c436076552ba9db74c361bdf11`; actually served replacement anchor `c6d2f333fdf9dba414a71510db15ec7c60cbd7431c3f2b54fd1f8e009574f0c2`.

## What survives / what fails

**Survives:** the predecessor-signed rotation certificate logic and the named post-publication crash-recovery matrix remain independently green within their stated same-host/dedicated-UID model.

**Fails:** successful Wave-132 rotation validation is not bound to the filesystem object later served when the anchor pathname's parent is writable by the ordinary worker. Under that deployment condition, a Wave-131-ready but Wave-132-unbootstrapped store can be substituted after validation and then served with a fully genuine authenticated response.

This is a state/authority binding failure, not a signature forgery. The attack step did not read an authority private key or authority store, forge any certificate/signature, rewrite a ledger or rotation lineage, use root/kernel compromise, or establish any speed/energy/retained/incremental/dormant-compute claim. Root was used only as the test orchestrator to create distinct UIDs; the pathname swap itself ran as UID `1001`.

## Exact verifier evidence

- Verifier executable head: `ebcaac13c941c3136057a1d414be1fe8c858f07a`.
- GitHub Actions run: `35319507665`.
- Job: `105518626968`.
- Artifact: `10536761384` (`wave132-rotation-gate-path-swap-verifier`).
- Artifact SHA-256: `3f6a92a8ffadd9db91a99305b223905dfe18d9989f2d175b1bb3f49be9d9a6c0`.
- Verifier script blob: `572e5ef7d66cab2d884ed3e4369e78ef32790c93`.
- Verifier workflow blob: `eaddde5b33a72666b893109461a447358eb181fc`.

## Next adversarial gate

Bind validation, lease acquisition, and service to the same stable filesystem object rather than re-resolving a mutable pathname. A protected parent directory is a useful deployment precondition, but the stronger implementation gate is an opened directory/file-descriptor identity carried through validation into serving, with device/inode checks where appropriate. Then attack rename/swap before validation, after validation, while waiting for the lifetime lease, after lease acquisition, and during restart; include both a Wave-131 downgrade store and a different valid Wave-132 store. After that survives, return to the builder's planned rotation-bootstrap hard-kill window and genuine copied-key second-namespace/second-host fork tests.