# Independent verifier — Wave 130 UID authority boundary

**Lane:** verifier-only / NON-CANON / DO NOT AUTO-MERGE  
**Builder state examined:** `08701ae0cee15007a37f0edd8d01f61f6aa2ab22`  
**Unchanged Wave 130 tool blob:** `17241b23bc7104410ae39c4ebfa258d32cd934f1`  
**Status:** adversarial execution pending in this verifier lane.

## Source-level challenge

Wave 130 correctly repairs verifier PR #54 for the ordinary single-user-namespace case by moving durable response-key ownership to a separately configured numeric Unix uid. The implementation checks:

- `authority_uid = os.geteuid()`;
- `authority_uid != AXM_W130_FORBIDDEN_WORKER_UID`;
- `anchor_dir.stat().st_uid == authority_uid`;
- `response_private.pem.stat().st_uid == authority_uid` and mode `0600`.

Those values are namespace-local Linux uid representations. They are not, by themselves, proof that the authority process and worker resolve to different underlying host kernel credentials across Linux user namespaces.

## Adversarial gate

Attempt, as the ordinary worker uid and without root or `CAP_SYS_PTRACE`, to create an unprivileged Linux user namespace mapping that same host uid to namespace-local uid `23001`. Drop effective/permitted capabilities after establishing the map, then run the unchanged Wave 130 initializer with the real parent worker uid still configured as forbidden.

The counterexample is established only if all of these hold:

1. unchanged Wave 130 controls remain 8/8 in normal Python and 8/8 under `python -O`;
2. the worker itself creates the user namespace without privileged orchestration;
3. immediately before executing Wave 130, the child reports namespace euid `23001`, parent host uid equal to the ordinary worker uid, and `CapEff=0`;
4. unchanged Wave 130 reports `separate_uid=true`, authority uid `23001`, forbidden worker uid equal to the real parent worker uid, and private-key owner uid `23001`;
5. outside that namespace, the resulting `response_private.pem` is owned by the ordinary worker host uid, remains mode `0600`, and is directly readable by that worker;
6. the public key derived from the recovered private PEM exactly matches the witness-pinned response public key;
7. the same result reproduces under normal and optimized Python.

If unprivileged user namespaces are disabled by the runner kernel/policy, that is an environmental block rather than evidence that the numeric-uid model is safe; the result must remain unproved rather than being promoted to a failure.

## Boundaries

This verifier does not claim root/kernel compromise, ACL/LSM bypass, cross-host uniqueness, physical finality, hardware-backed key custody, or any speed/energy/retained/incremental/dormant-compute result. It targets only whether namespace-local numeric uid inequality is sufficient evidence of a host-wide authority boundary.
