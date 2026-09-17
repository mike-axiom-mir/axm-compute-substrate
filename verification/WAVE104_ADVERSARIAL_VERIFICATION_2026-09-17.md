# Independent adversarial verification — Wave 104 certificate-witness registry root

Date: 2026-09-17  
Repository: `mike-axiom-mir/axm-compute-substrate`  
Builder branch: `chatgpt/lane-001-platform-extract`  
Newest builder head inspected: `b0826840723b4d510f396c91e8f0c5de46a05a43`  
Wave 104 tested-source head named by the builder receipt: `b33c8e0ae155d8e785b25ab608bdf8a3dbb14e65`  
Wave 104 tool blob: `64aef8c32e246f396ca8dc67dbf3b0460b077f77`  
Wave 104 self-test blob: `c2ca76079adfbe9f44fd11c97689be61027a7760`  
Status: verifier-only evidence; no merge or CANON promotion

## Builder result that survives

Wave 104 materially repairs verifier PR #28 **when one exact `CertificateWitnessDomain` remains the trusted root**. Inside that supplied domain, the registry body is content-addressed, slot membership is exact, instance / credential / modeled-domain identities must be distinct, online endpoints prove possession of the registered HMAC test credential using a fresh nonce, and the attested head is cross-checked against the retained endpoint ledger.

The intended PR #28 stale same-ID disk substitution is therefore blocked without stealing the registered credential. The builder also keeps important boundaries explicit: all endpoints still share one Python process; the failure-domain labels are modeled only; HMAC is test-only; stolen credentials remain a known failure; whole modeled durable-state rollback remains possible; registry rotation is absent; and Wave 104 makes no new retained/incremental/dormant-compute, energy, network, or provider-independence claim.

The builder receipt records Wave 103 regression `40/40` and Wave 104 `46/46` in normal and `python -O` modes for the unchanged tool/self-test blobs.

## New adversarial finding

**Verdict:** `FAIL_CERTIFICATE_WITNESS_REGISTRY_ROOT_IS_CALLER_SUBSTITUTABLE`

Wave 104 validates the integrity and credentials **inside whichever `CertificateWitnessDomain` object the caller supplies**, but the exact certificate-witness `registry_sha` is not bound into the lower authority state, the quorum certificate, or another durable/external trust anchor. There is therefore no mechanical rule saying “this exact witness registry is the trusted one for this authority lineage.”

The exact-API reproducer does this:

1. Create a normal Wave 104 witness domain and advance to authority epoch 1. Sync all three registered certificate witnesses.
2. Advance normally to epoch 2; publish to remote A+B; certify it; sync the original `cert-a` and `cert-b` to certificate 2 while original `cert-c` legitimately remains at certificate 1. Wave 104 reports epoch 2 authoritative.
3. Recreate the same stale lower-quorum shape used in the previous verifier series: local current pointer + certificate store at epoch 1; remote A still retains epoch 2; remote B is restored to its legitimate epoch-1 snapshot; remote C legitimately remains at epoch 1.
4. Supply the **original Wave 104 witness domain**. Because original `cert-a` / `cert-b` still retain certificate 2, unchanged Wave 104 correctly returns `HOLD_CERTIFICATE_WITNESS_MAXIMUM_AHEAD`.
5. Do **not** modify, truncate, offline, or steal credentials from that original domain. Instead call the normal Wave 104 constructor to create a second fresh, internally valid generation-0 witness registry/domain with different registry SHA, instance IDs, and credentials. Sync that fresh domain only to the legitimate stale certificate-1 store.
6. Supply the fresh domain to the unchanged `authority()` API for the same stale local/remote/certificate world.
7. The stale epoch becomes `AUTHORITATIVE_QUORUM_2_OF_3_MODELED`, while the original newer registered domain remains online and still retains certificate 2.

No hash collision, record mutation, HMAC forgery, stolen witness credential, original-endpoint outage, registry-body tamper, or deletion of the original newer witness evidence is required. The adversarial change is selection of a different internally valid registry root at the API boundary.

## Why this is distinct from the builder's preserved failures

This is not the disclosed “stolen registered credential authenticates a stale clone” case: the attacker uses only freshly generated credentials belonging to a completely different valid Wave 104 registry.

It is also narrower than restoring all genuine registered witness ledgers with the whole modeled world: the **original registered domain is left untouched, online, and newer**. The stale result appears because the authority call is allowed to nominate a different generation-0 registry as the trust root.

The result does **not** show that one stable, externally trusted `CertificateWitnessDomain` can be internally bypassed. It shows that registry-root selection itself is presently an external caller/configuration assumption rather than an authority-bound invariant.

## Benchmark / compute fairness

Wave 104 deliberately makes no fresh performance or Flowing Compute efficiency claim, so there is no new benchmark result to falsify here. Earlier retained/incremental/dormant-state results remain separate from this authority-layer correctness wave. This verifier therefore does not reinterpret the 46/46 protocol controls as compute-speed or energy evidence.

## Next adversarial gate

Before process separation is treated as stronger stale-proof evidence, bind **one exact certificate-witness registry identity** into a durable root that the caller cannot silently replace. Practical options include binding the witness-registry SHA into each quorum certificate / authority transition and preserving predecessor-linked registry generations, or anchoring the currently authorized registry in a separate monotonic trust root.

Then attack:

- fresh registry replacement without credential theft;
- stale registry replay after a legitimate registry rotation;
- sibling registry generations;
- skipped registry generations;
- one endpoint replacement while two old endpoints remain;
- registry-root rollback across process restart;
- credential rotation with stale disk restoration;
- partial registry fan-out / crash recovery;
- cloned process images using an old but once-authorized registry.

Only after the registry root itself is authority-bound does moving the endpoints into three OS processes test a stronger failure-domain property instead of moving a caller-selected trust root into separate processes.
