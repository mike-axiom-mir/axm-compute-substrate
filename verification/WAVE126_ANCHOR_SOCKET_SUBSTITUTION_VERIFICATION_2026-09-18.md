# Wave 126 independent adversarial verification — anchor socket substitution

Status: **verifier lane only / NON-CANON / unmerged**.

Builder head challenged: `cd1e234cad6da6488296d6f00408f59a57aa9687`  
Builder exact CI-tested source: `b3713154cc1ca587b365ae3647578f791a750e48`  
Wave 126 tool blob: `cf267f87aca1dd53e182f306697eb0e15c529769`

## Adversarial question

Wave 126 moves monotonicity into a separate anchor process and requires the witness to connect to a configured anchor socket plus an externally pinned anchor credential fingerprint. The verifier asks whether the witness actually authenticates the **endpoint speaking on that socket**, rather than merely comparing a public fingerprint string supplied by the peer.

The unchanged `anchor_request(...)` compares the reply's `anchor_credential_fingerprint` field to the expected fingerprint, but the response is not MACed or signed with the anchor credential. `reconcile_with_anchor(...)` checks the returned sequence, witness head SHA, and witness credential fingerprint, but does not verify an anchor signature/record proof from the response.

## Counterexample under test

1. Start a genuine Wave 126 witness and genuine Wave 126 anchor as separate OS processes.
2. Commit one real terminal outcome and confirm the genuine anchor is at sequence 1.
3. Leave the genuine anchor process and durable store untouched and alive.
4. Unlink only its Unix-domain socket **pathname**. The genuine listener remains alive on its already-open socket inode.
5. Bind a protocol-compatible fake anchor at the same pathname. The fake owns **no anchor secret**; it only echoes the already-public expected fingerprint and mirrors the request's record count/head back in the response.
6. Ask the unchanged real Wave 126 witness to commit a second terminal outcome.
7. Check whether the unchanged client records the result as authoritative while the genuine anchor ledger remains at sequence 1 and the witness ledger advances to sequence 2.

Expected failure label if reproduced:

`FAIL_UNAUTHENTICATED_ANCHOR_SOCKET_SUBSTITUTION_ADVANCES_WITNESS_WITHOUT_GENUINE_ANCHOR`

## Boundary

This test is intentionally same-host/same-filesystem. It does not replace/rollback the anchor directory, witness directory, external anchor fingerprint, host-pin namespace, network namespace, or builder code. It does not forge either HMAC credential, rewrite either durable ledger, use an older writer, exploit a hash collision, or make any speed/energy/retained-compute claim.

If reproduced, this is stronger than the already-disclosed whole witness+anchor rollback counterexample: the independently pinned genuine anchor remains alive and newer/current; only its mutable communication pathname is substituted.

## Verification lane

- Reproducer: `verification/wave126_anchor_socket_substitution_repro.py`
- CI: `.github/workflows/verifier-wave126-anchor-socket-substitution.yml`

CI outcome and exact artifact digest will be appended after the executable run. Do not merge automatically or promote this result to CANON.
