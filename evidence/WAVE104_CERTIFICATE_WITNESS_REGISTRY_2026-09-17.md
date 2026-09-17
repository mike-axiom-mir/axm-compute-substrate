# Wave 104 — credential-bound certificate-witness registry

Date: 2026-09-17  
Repository: `mike-axiom-mir/axm-compute-substrate`  
Experimental lane: `chatgpt/lane-001-platform-extract` / PR #2  
Status: experimental evidence only; no merge or CANON promotion

## Why this wave changed direction

Independent verifier PR #28 tested exact Wave 103 head `8239c401a9d7ca1a330f76a7f537437fd141bbc6` and tool blob `0a5d6f09189719d705808fe1746c2f032688fd01`. It found that `cert-a` / `cert-b` / `cert-c` were fixed only by caller-supplied map position plus string identity. A legitimate epoch-1 `cert-a` snapshot could replace the caller map entry for the still-online real `cert-a` that retained epoch 2. With cert-b unavailable and cert-c legitimately lagging, unchanged Wave 103 returned stale `AUTHORITATIVE_QUORUM_2_OF_3_MODELED`.

That protocol defect was repaired before attempting OS-process separation. Moving an unbound logical slot into another process would make the deployment look stronger without fixing which instance is actually trusted.

Exact verifier provenance:
- verifier PR: #28
- verifier head: `2384c08109e0c1414921029e7f4f29577838a0da`
- verifier evidence blob: `5b75cf95aa2203e9a5c57f529fdfcad00fa96aea`
- verifier reproducer blob: `9031bcfaf13afaee4628db0c8d486d066c6efd04`

## What Wave 104 adds

Reusable tool: `tools/AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY.py`  
Tool blob: `64aef8c32e246f396ca8dc67dbf3b0460b077f77`  
Self-test: `tools/AXM_FLOWING_COMPUTE_CERTIFICATE_WITNESS_REGISTRY_SELFTEST.py`  
Self-test blob: `c2ca76079adfbe9f44fd11c97689be61027a7760`

Wave 104 introduces a content-addressed, fixed generation-0 certificate-witness registry. Each of the three slots is bound to a fresh instance identity, a distinct HMAC-SHA256 test credential identity, and a distinct modeled failure-domain identity. Every retained Wave 104 witness record binds the registry SHA and exact instance/credential/domain identity.

Authority no longer treats a caller-supplied same-name dictionary as a witness. Every read requires the exact three-slot resolver set and, for each online endpoint, a fresh nonce challenge plus HMAC proof-of-possession. The attested maximum is then cross-checked against the endpoint's complete retained ledger. An outage remains explicit: the registered endpoint stays in the resolver but is marked offline; deleting or replacing its slot is not silently treated as an outage.

Disk snapshots deliberately contain ledger state but not endpoint credentials. This gives a clean process/storage model for the next wave: disk can be restored while endpoint identity is a separate boundary.

## Positive and negative evidence

GitHub Actions run `35179665157` tested head `8c4ffb13f3a0f3f2847af37de882b76890bcab9a` on Python 3.12.14. Wave 103 regression remained green at **40/40**. Wave 104 passed **46/46** normally and **46/46 under `python -O`**. The uploaded report artifact was ID `10479946113`, ZIP digest `sha256:63307f4756f8265965509ad84405b5a3e4a50ad2b3fd9632fb2140f58ea7efa9`.

The test deliberately reproduces the verifier's old result first: unchanged Wave 103 accepts the same-ID stale substitution as `AUTHORITATIVE_QUORUM_2_OF_3_MODELED`. With Wave 104, the honest live newer endpoint still blocks the stale world as `HOLD_CERTIFICATE_WITNESS_MAXIMUM_AHEAD`, while replacing that endpoint with the plain stale same-ID disk snapshot now fails closed as `HOLD_CERTIFICATE_WITNESS_IDENTITY_OR_CREDENTIAL_INVALID`.

Negative controls also cover a same-visible-identity endpoint with the wrong credential, resolver membership shrink, registry-body tamper, one endpoint offline, one genuine endpoint on stale disk, partial certificate fan-out, explicit reconstruction, and restoration to newest state after adversarial tests.

## Preserved failures / truth boundary

A stolen registered symmetric witness credential is still enough to authenticate a stale clone in this model; that counterexample is explicitly tested and kept. Restoring all three genuine registered endpoint ledgers together with local, certificate, and remote state can still recreate an internally valid old world because no storage domain is physically monotonic. Registry rotation/replacement is intentionally absent rather than being silently invented; changing an instance or credential must become an explicit authority-bound transition.

All endpoints, registry state, verification credentials, remotes, and certificate stores still live inside one Python process. The three failure-domain labels are modeled labels, not OS, device, provider, or physical independence. HMAC proves possession of a test shared secret, not public identity, operator legitimacy, root judgment correctness, consent, or CANON authority.

No fresh AXM/monolith workload, performance benchmark, energy result, network result, or retained/incremental/dormant-compute win is claimed in this wave. The newest independent correctness defect was the stronger gate and was repaired first.

## Next gate — Wave 105

Move this exact registered endpoint contract into three real OS processes with separate durable stores and separately held credentials. Then attack kill/restart, stale process images, cloned disks, one outage plus one stale clone, partition/reconnect, credential theft and rollback, two-process restore, registry rollback, and explicit credential/instance rotation. Rotation/replacement must be predecessor-linked and authority-bound rather than a mutable registry edit. Process-level success will still not prove physical/provider independence.
