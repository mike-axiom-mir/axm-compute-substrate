# Wave 125 independent adversarial verification

Status: **DRAFT / verifier-only / NON-CANON / do not merge automatically.**

Builder evidence head inspected: `f7c5d920a01acae729745aaf0e0b51f8cb928163`.
Exact builder CI-tested source: `d9b9621bd26f6bf981bfd0f8b51881aaf3f0c886`.

This lane leaves the Wave 125 builder files unchanged and tests two boundaries:

1. **hard kill after host-pin publication but before client reply** — expected to recover the exact already-durable terminal receipt after restart;
2. **host-pin namespace pathname replacement** — a narrower form of the trust-domain replacement boundary already excluded by Wave 125. The verifier keeps the accepted newer witness store intact, renames only the trusted `/tmp/axm-flowing-compute-wave125-host-v1-<uid>` namespace aside, creates a fresh same-owner/mode empty namespace at the public pathname, then releases the live credential lease and attempts to start a genuine stale clone.

Expected boundary verdict if reproduced:

`FAIL_HOST_PIN_NAMESPACE_REPLACEMENT_REOPENS_STALE_CLONE`

This is **not** a falsification of Wave 125's explicitly bounded "trusted host-pin namespace" claim. It is intended to determine whether that trust root has any independent identity beyond its mutable pathname and to preserve the next-gate failure precisely.

No credential/HMAC/hash forgery, no modification or deletion of the accepted newer witness ledger, no performance/energy/retained-compute claim, no provider/network-independence claim, and no CANON promotion is made.

CI evidence will be appended after the independent workflow completes.
