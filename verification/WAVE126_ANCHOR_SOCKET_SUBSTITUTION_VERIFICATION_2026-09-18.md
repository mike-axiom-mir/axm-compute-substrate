# Wave 126 independent adversarial verification — anchor socket substitution

Status: **verifier lane only / NON-CANON / unmerged**.

Builder head challenged: `cd1e234cad6da6488296d6f00408f59a57aa9687`  
Builder exact CI-tested source: `b3713154cc1ca587b365ae3647578f791a750e48`  
Wave 126 tool blob: `cf267f87aca1dd53e182f306697eb0e15c529769`

## Adversarial question

Wave 126 moves monotonicity into a separate anchor process and requires the witness to connect to a configured anchor socket plus an externally pinned anchor credential fingerprint. The verifier asks whether the witness actually authenticates the **endpoint speaking on that socket**, rather than merely comparing a public fingerprint string supplied by the peer.

The unchanged `anchor_request(...)` compares the reply's `anchor_credential_fingerprint` field to the expected fingerprint, but the response is not MACed or signed with the anchor credential. `reconcile_with_anchor(...)` checks the returned sequence, witness head SHA, and witness credential fingerprint, but does not verify an anchor signature/record proof from the response.

## Reproduced counterexample

`FAIL_UNAUTHENTICATED_ANCHOR_SOCKET_SUBSTITUTION_ADVANCES_WITNESS_WITHOUT_GENUINE_ANCHOR`

1. Start a genuine Wave 126 witness and genuine Wave 126 anchor as separate OS processes.
2. Commit one real terminal outcome and confirm the genuine anchor is at sequence 1.
3. Leave the genuine anchor process and durable store untouched and alive.
4. Unlink only its Unix-domain socket **pathname**. The genuine listener remains alive on its already-open socket inode.
5. Bind a protocol-compatible fake anchor at the same pathname. The fake owns **no anchor secret**; it only echoes the already-public expected fingerprint and mirrors the request's record count/head back in the response.
6. Ask the unchanged real Wave 126 witness to commit a second terminal outcome.
7. The unchanged witness accepts the fake pre/post reconciliation responses, appends the genuine witness-signed sequence-2 COMMIT, and the unchanged client/status path reports `AUTHORITATIVE_PROCESS_WITNESS_COMMIT`.
8. Direct diagnostic inspection after the attack shows the genuine anchor process is still alive and its durable anchor ledger is still at sequence 1, while the witness ledger is at sequence 2.

This means the independently pinned **anchor identity string** is checked, but the peer producing the reconciliation response is not proving possession of the anchor credential. A process that can replace the mutable Unix-socket pathname can impersonate the anchor response without reading `credential.bin`.

## Boundary

This test is intentionally same-host/same-filesystem. It does not replace/rollback the anchor directory, witness directory, external anchor fingerprint, host-pin namespace, network namespace, or builder code. It does not forge either HMAC credential, rewrite either durable ledger, use an older writer, exploit a hash collision, or make any speed/energy/retained-compute claim.

This is stronger than the already-disclosed whole witness+anchor rollback counterexample: the independently pinned genuine anchor remains alive and its current durable state remains intact; only its mutable communication pathname is substituted.

## Independent execution evidence

Corrected verifier CI-tested head: `04d803a6e1ecc45fc3dc18b6d3aa845c717d3d2b`  
Run: `35298843623`  
Job: `105456964908`  
Conclusion: **success**

Artifact: `10529270623` (`wave126-anchor-socket-substitution-verifier`)  
Artifact SHA-256: `5d80f023e5f88ca89d096fb8ed6029fccca8a3b218b154dfe12bc48cf5f3e774`

The successful run independently established:

- unchanged Wave 126 builder self-test: **12/12 PASS** normal Python;
- unchanged Wave 126 builder self-test: **12/12 PASS** under `python -O`;
- socket-substitution counterexample: **REPRODUCED** normal Python;
- socket-substitution counterexample: **REPRODUCED** under `python -O`;
- exact source identity and artifact upload: PASS.

In both attack runs, the fake endpoint received reconcile requests first for one witness record and then for two. It did not possess the anchor secret. The unchanged client nevertheless reported `AUTHORITATIVE_PROCESS_WITNESS_COMMIT`, the genuine anchor process remained alive with durable anchor sequence `1`, and the genuine witness ledger advanced to sequence `2`.

An earlier run, `35298748930` / job `105456673196`, had already reproduced the counterexample in both Python modes and passed both unchanged builder controls, but its final source-metadata step failed because the verifier workflow used `git rev-parse HEAD^` under a depth-1 checkout. That provenance-plumbing false negative is preserved rather than hidden; the workflow was corrected with `fetch-depth: 2` before the successful run above.

## Next adversarial gate

The anchor response needs cryptographic endpoint authentication, not a self-asserted fingerprint. The smallest gate is a nonce/challenge or request digest bound into an anchor-HMAC/signature over the exact reconciliation result, with the verifier checking that proof using a key/public-key identity that a pathname substitute cannot derive. Then attack:

- socket unlink/rebind before witness startup and while witness is live;
- replay of a genuine old signed reconciliation response;
- response splicing between two witness heads;
- wrong sequence/head with a valid old proof;
- concurrent genuine + fake endpoints;
- legitimate anchor restart/rotation without accepting an unproved replacement;
- only after that, cross-network-namespace/second-host clone tests.

## Verification lane

- Reproducer: `verification/wave126_anchor_socket_substitution_repro.py`
- CI: `.github/workflows/verifier-wave126-anchor-socket-substitution.yml`

Do not merge automatically or promote this result to CANON.
