# Flowing Compute Wave 105 — authority-bound certificate-witness registry root

Date: 2026-09-17  
Repository: `mike-axiom-mir/axm-compute-substrate`  
Experimental lane: `chatgpt/lane-001-platform-extract`  
Status: experimental evidence only; no merge or CANON promotion

## Why this wave changed direction

Independent verifier PR #29 found a narrower Wave 104 finality gap before process separation was worth testing. Wave 104 correctly validates endpoint identity, credential possession, resolver membership, registry integrity and retained witness ledgers **inside the supplied certificate-witness domain**, but the exact certificate-witness registry SHA was not bound into durable authority state.

The verifier left the original newer Wave 104 domain online and intact, built a second fresh valid generation-0 domain with unrelated fresh credentials, synchronized that fresh domain only to the legitimate stale certificate-1 store, and supplied it to `authority()`. Unchanged Wave 104 returned stale modeled 2-of-3 authority. No original credential theft, registry-body tamper, endpoint outage, record deletion or hash collision was required.

Exact verifier identity used by this builder wave:

- verifier PR: `#29`
- verifier head: `cc0ecfe2a40b0a39b20b85230578ddc3902c44ad`
- verifier evidence blob: `afbfa47432c29ad41f5c0d56a1904ca94e996e30`
- verifier repro blob: `51cc2266f47b4cfaeae32ad6744cead9f9d104b0`
- Wave 104 builder head: `b0826840723b4d510f396c91e8f0c5de46a05a43`
- Wave 104 tool blob: `64aef8c32e246f396ca8dc67dbf3b0460b077f77`
- Wave 104 self-test blob: `c2ca76079adfbe9f44fd11c97689be61027a7760`

## Wave 105 repair

Wave 105 adds a reusable sealed, content-addressed, predecessor-linked root-binding body. It records:

- the user/application state SHA;
- the exact remote-witness registry SHA;
- the exact certificate-witness registry SHA;
- sequence and predecessor binding SHA.

The lower authority/checkpoint machinery already signs a state digest derived from `app_state_sha + remote_registry_sha`. Wave 105 makes the lower `app_state_sha` be the root-binding SHA. Therefore every accepted checkpoint transitively commits the exact certificate-witness registry root without modifying the older signed-checkpoint format.

The current root-binding chain is also cross-checked against every retained predecessor authority checkpoint. This matters because merely checking the newest binding would still allow a caller to manufacture a complete parallel replacement-root chain and try to attach it through an older primitive.

## Adversarial result

The exact PR #29 stale-world attack is reproduced first against unchanged Wave 104:

`AUTHORITATIVE_QUORUM_2_OF_3_MODELED`

The same stale local/remote/certificate world with the same fresh replacement domain under Wave 105 returns:

`HOLD_CERTIFICATE_WITNESS_REGISTRY_ROOT_MISMATCH`

A stronger bypass test deliberately constructs a complete parallel replacement-root binding chain and calls the older lower prepare/commit primitive directly. The lower commit still occurs, which is kept visible. Wave 105 authority then rejects the result because the retained predecessor checkpoint does not cross-bind to that replacement binding chain.

Missing or tampered current root-binding evidence also fails closed.

## Exact-source CI

Tested source head: `b12ef029d741a7d60d9ffea7e01c299172977c61`

- Wave 105 tool blob: `1e0e543c57f880c3e631619fa1859c24ace5ff79`
- Wave 105 self-test blob: `c6d39f469e98590823af3a576c4efbb18957d00b`
- Wave 105 workflow blob: `b65aad6c417042ec67f225e2f8e4c5a400481860`
- GitHub Actions run: `35183374940`
- job: `105080144977`
- artifact: `10480239491`
- artifact ZIP SHA-256: `03a6d08e7aa51e190fe59488b5e9541998586c6ca66cea0c20fd76b18b868c40`

Results:

- unchanged Wave 104 regression: `46/46`
- Wave 105 normal Python: `35/35`
- Wave 105 `python -O`: `35/35`

The generated report artifact is preserved by run identity; the repository keeps a concise machine-readable summary in `evidence/wave105_certificate_witness_root_binding_report.json` rather than copying runner ballast.

## Counterexamples intentionally kept

1. Bootstrap registry-root selection before the first accepted checkpoint is still an initialization/configuration trust boundary.
2. Stealing a symmetric credential for an endpoint in the **already-bound** root can still authenticate a stale clone in this model.
3. Rolling local/certificate/remote state and all genuine certificate-witness endpoints back together under that same already-bound root can still recreate an internally valid old world.
4. All stores, credentials and endpoints are still Python objects in one process. Modeled failure-domain labels are not process/device/provider independence.
5. Certificate-witness registry rotation is deliberately unsupported. Wave 105 rejects root changes rather than silently inventing a rotation rule.

## Truth boundary

This is a protocol/finality correctness wave. No fresh AXM/monolith workload benchmark was run because verifier PR #29 exposed a stronger correctness gate first. There is no new performance, energy, retained-compute, incremental-compute, dormant-compute, networking, OS-process, device or provider-independence claim.

## Next gate

Wave 106 should keep this exact fixed root contract and move the three registered certificate witnesses into genuinely separate OS processes with separate durable stores and separately held credentials. Then test kill/restart, stale process image restore, cloned disks, partition/reconnect, one process unavailable while another is stale, credential theft, two-process rollback, root-binding store loss/tamper and restart bootstrap.

Do **not** treat process separation as witness-registry rotation. A later rotation experiment should be an explicit predecessor-linked authority transition with its own positive/negative evidence rather than mutable configuration.
