# Flowing Compute Wave 127 — authenticated anchor response channel

Status: **EXPERIMENTAL / NON-CANON / existing PR lane only / DO NOT AUTO-MERGE**.

## Challenge provenance

Wave 127 continues from Wave 126 evidence head `cd1e234cad6da6488296d6f00408f59a57aa9687`, whose exact CI-tested source was `b3713154cc1ca587b365ae3647578f791a750e48` (`AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ANCHORED.py` blob `cf267f87aca1dd53e182f306697eb0e15c529769`; self-test blob `afbb5938b288a531998ef27fa192361bba5c430d`).

Independent verifier PR #51 tested corrected verifier head `04d803a6e1ecc45fc3dc18b6d3aa845c717d3d2b` in run `35298843623`, job `105456964908`, artifact `10529270623`, artifact SHA-256 `5d80f023e5f88ca89d096fb8ed6029fccca8a3b218b154dfe12bc48cf5f3e774`.

The verifier left the genuine Wave 126 anchor process and durable anchor store alive, unlinked only its filesystem Unix-socket pathname, rebound a fake endpoint there with **no anchor secret**, and then asked the unchanged genuine witness to append sequence 2. Because Wave 126 authenticated only the anchor fingerprint echoed in unsigned JSON, the witness accepted sequence 2 as authoritative while the genuine anchor remained at sequence 1. No anchor/witness credential was forged and no durable ledger was rewritten.

The verifier also preserved an earlier plumbing-failure run (`35298748930`) rather than hiding it: the attacks reproduced, but its provenance step incorrectly requested `HEAD^` from a depth-1 checkout.

## Wave 127 repair

Wave 127 keeps the Wave 126 witness/anchor durable-ledger model, but adds an asymmetric anchor-response identity:

- the anchor owns a distinct RSA-2048 response-signing private key;
- the witness is provisioned only with the corresponding public verifier plus its exact fingerprint binding;
- every anchor request carries a fresh random nonce and exact request payload;
- every response signature binds the request nonce, SHA-256 of the exact canonical request envelope, pinned anchor credential fingerprint, and exact response body;
- unsigned replies, stale signed replies, request/response splicing, response-body/head edits, wrong anchor identity, and verifier substitution fail closed before the response is trusted.

The implementation uses the system OpenSSL CLI on the tested Linux path. The reusable candidate is split between the protocol implementation and a tiny repaired runtime wrapper so the initial failed candidate remains inspectable rather than silently rewritten.

## Preserved failed candidate

First exact Wave 127 candidate: `9fe66ad4a9b61f796816b7a07dac874bbeada47d`.

Run `35300732420`, job `105462610151`: **failed**. The unchanged Wave 126 normal and optimized regressions passed before the Wave 127 normal step failed.

Diagnosis: the first candidate kept the anchor/witness store pinned through an opened directory file descriptor and passed `/proc/self/fd/<n>/...` key paths directly to a newly spawned OpenSSL child. That child did not retain the parent process's store file descriptor, so the cryptographic helper could not use the pinned key path. The repair changes only key handoff: the parent reads the key bytes through its already-pinned store handle, writes a mode-0600 ephemeral helper file for one OpenSSL operation, and deletes it afterward. The response-authentication protocol was not weakened.

## Exact successful evidence

Exact CI-tested source: `e45a5610879ac2b5fcb46a72222a212a91e6cf68`.

Run `35300939205`, job `105463239369`: **success** on Ubuntu 24.04 / Python 3.13 / OpenSSL 3.0.13.

Results:

- unchanged Wave 126: **12/12 normal + 12/12 under `python -O`**;
- Wave 127: **9/9 normal + 9/9 under `python -O`**;
- fake unsigned socket substitution: rejected before witness append; genuine anchor stays unchanged and alive;
- genuine signed response: accepted;
- legitimate anchor restart: preserves exact response-verifier identity and sequence;
- old genuine signed response replay: rejected by nonce/request binding;
- signed head/sequence/body splicing: rejected by signature verification;
- exact legitimate retry after attacks: commits cleanly;
- witness-side public verifier substitution: detected and rejected.

Artifact `10529871770` (`flowing-compute-wave127-authenticated-anchor-evidence`), 12,748 bytes, SHA-256 `c3222107b4a054c66529e9dfaa4b9db651e8e3f3547e7f121326df117bce010e`.

Generated test reports stay in CI artifact storage rather than being committed as repository ballast. The reusable tool, adversarial suite, repaired key-handoff wrapper, fixed-suite launcher, workflow, and this concise evidence note remain in the experimental lane.

## Truth boundary / retained counterexamples

Wave 127 proves only the tested application-layer endpoint-authentication behavior on one Linux host using the tested OpenSSL path. It does **not** prove cross-host or cross-network-namespace uniqueness, physical/device/controller/kernel finality, provider independence, hardware-backed key custody, or secure physical erasure of temporary key material.

The witness-side public-verifier provisioning/rollback boundary remains real. Copying or rolling back both authority domains together remains outside the proof. The Wave 126 whole-witness-plus-anchor rollback counterexample is retained rather than declared solved. Compromise/copying of the anchor response private key is also outside this wave's protection.

No real AXM/monolith performance workload and no synthetic scaling workload were run for this correctness gate. Therefore this wave makes **no speed, energy, retained-compute, incremental-compute, dormant-compute, or scaling claim**.

## Next gate

Attack the authenticated design across the kernel boundary. Run genuine copied anchor credentials/private response keys in separate Linux network namespaces or, preferably, separate hosts where the same-namespace credential lease cannot collide. Make two cryptographically genuine clones compete against one witness/pin history and test divergent signed histories, restart/reconnect, stale clones, client-verifier rollback, and mixed Wave 126/Wave 127 downgrade paths.

If copied genuine private keys can create two authenticated authorities across that boundary, preserve that counterexample and move uniqueness/rotation to an independently retained authority lineage rather than treating endpoint signatures as finality.

No merge, auto-merge, or CANON promotion is requested by this evidence note.
