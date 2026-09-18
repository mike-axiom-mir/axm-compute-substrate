# Independent verifier — Wave 130 UID authority boundary

**Lane:** verifier-only / NON-CANON / DO NOT AUTO-MERGE  
**Builder state examined:** `08701ae0cee15007a37f0edd8d01f61f6aa2ab22`  
**Unchanged Wave 130 tool blob:** `17241b23bc7104410ae39c4ebfa258d32cd934f1`  
**Verifier branch head executed:** `1e942411959d919cc627a12ebaa9c15468d758a2`  
**Verifier CI run / job:** `35314687612` / `105503712602`  
**Artifact:** `10534139591` (`wave130-userns-uid-alias-verifier-v2`)  
**GitHub artifact digest:** `sha256:7fd7eab5f34a15d283cf3d79af879cbb67f8c7116451131279206171c0d6dbed`  
**Inner exact evidence ZIP SHA-256:** `b302bd42df8d3b7ffddc5b081f34ab7690cf00073f2ca771bcb839c9e24ad62b`  
**Result:** Wave 130 survives its tested dedicated-UID claim on this runner; the stronger user-namespace alias challenge remains **UNPROVED / ENVIRONMENT-BLOCKED**, not disproved.

## What survived

The unchanged Wave 130 control suite passed **8/8 in normal Python** and **8/8 under `python -O`**. The direct PR #54 repair therefore remains boundedly verified on the tested Ubuntu/Linux path: with an actually distinct configured Unix UID, the durable response private key is authority-owned `0600`, the anchor directory is authority-owned `0700`, direct worker reads are denied, the authenticated protocol still works, and the same-UID configuration is rejected before private key generation.

No speed, energy, throughput, retained-compute, incremental-compute, dormant-compute, cross-host, physical-finality, hardware-custody, or provider-independence conclusion follows from this verification.

## Source-level challenge

Wave 130 decides separation using namespace-visible Unix IDs:

- `authority_uid = os.geteuid()`;
- `authority_uid != AXM_W130_FORBIDDEN_WORKER_UID`;
- `anchor_dir.stat().st_uid == authority_uid`;
- `response_private.pem.stat().st_uid == authority_uid` and mode `0600`.

Those checks are correct within one trusted user-namespace view. They are not, by themselves, proof that two numeric UIDs represent different underlying host credentials across Linux user namespaces/container UID remapping.

## User-namespace attack attempts

### V1 — preserved setup failure

The first verifier attempted both UID and GID namespace setup. It stopped before Wave 130 at:

`PermissionError:[Errno 13] Permission denied: '/proc/self/setgroups'`

That failure is preserved rather than rewritten. GID mapping was unnecessary because Wave 130's authority decision is UID-only.

### V2 — UID-only attack

The corrected verifier removed the irrelevant GID/setgroups operation and tried only to map the ordinary worker's host UID to namespace-local UID `23001`, then drop effective/permitted capabilities and execute unchanged Wave 130.

The attack still did not reach Wave 130. Both normal and optimized runs stopped during UID namespace setup with:

`PermissionError:[Errno 1] Operation not permitted`

The runner evidence was:

- worker UID/GID: `1001/1001`;
- `CapPrm=0`, `CapEff=0`;
- `kernel.unprivileged_userns_clone = 1`;
- `kernel.apparmor_restrict_unprivileged_userns = 1`;
- initial `uid_map = 0 0 4294967295`.

So the important interpretation is **policy block, not security proof**: this Ubuntu runner permits the unprivileged-userns sysctl but AppArmor restricts the namespace operation needed for the counterexample. No private key was created during either attack attempt, so there is no key-exfiltration result to claim.

## Bounded conclusion

Wave 130's direct dedicated-UID repair survives on the current tested host and remains a real improvement over Wave 129. The stronger statement "numeric UID inequality is sufficient as a host-wide authority identity across user namespaces/containers" is not verified by this run. The current evidence only establishes the single trusted UID-namespace case exercised by the builder harness.

## Next adversarial gate

Repeat the UID-alias test on a controlled Linux host where an ordinary worker is actually allowed to create its own user namespace, or explicitly harden/deploy Wave 130 so the authority refuses non-approved user namespaces and binds its identity to an external service-manager / namespace / LSM boundary that the worker cannot choose. Also make `AXM_W130_FORBIDDEN_WORKER_UID` an externally owned policy input rather than a worker-controlled declaration if that is intended to be a security boundary.

After that, attack container UID remapping, nested user namespaces, inherited descriptors, authority restart, public-verifier provisioning/rollback, key rotation, and then the copied-genuine-key second-network-namespace / second-host fork.
