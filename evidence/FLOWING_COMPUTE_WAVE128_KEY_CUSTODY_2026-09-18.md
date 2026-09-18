# Flowing Compute Wave 128 — response private-key custody

Status: **EXPERIMENTAL / NON-CANON / existing PR lane only / DO NOT AUTO-MERGE**.

## Challenge provenance

Wave 128 continues from Wave 127 evidence head `10140773f21d17fca9f38f04ff1d762a2d0d90e8`, whose exact CI-tested source was `e45a5610879ac2b5fcb46a72222a212a91e6cf68` and fixed runtime tool blob was `1d2fbe3f32b175dbbbcbae3431d9698769b5d0a2`.

Independent verifier PR #52 tested head `b6fa4d78d21410a8691a9554d6a199d6858bc5bb` in run `35302389245`, job `105467548115`, artifact `10530068822`, artifact SHA-256 `779dbaf1a9bc2a13074f9b734c1952a0843643f52dff1bae2f8929b39ca3b1dc`.

The verifier found that Wave 127 authenticated anchor replies but copied the response-signing private PEM into a mode-0600 file created with `tempfile.mkstemp(prefix="axm-w127-private-")` in the process-global temporary directory for each OpenSSL signing operation. A same-Unix-UID observer could capture that short-lived helper key, unlink/rebind the already-known Unix socket, and then produce fresh nonce/request-bound signatures accepted by the genuine witness while the untouched genuine anchor remained one sequence behind. No witness credential, anchor HMAC, or durable ledger rewrite was required.

That counterexample is retained as a real Wave 127 key-custody/authentication failure rather than reclassified away.

## Wave 128 repair

Wave 128 keeps the Wave 127 signed-response protocol but removes the globally named private-key handoff:

- response private-key bytes are never written to a filesystem tempfile for signing;
- signing passes the key to the OpenSSL child through an anonymous Linux `memfd` inherited only through an explicit file descriptor;
- RSA key generation streams private material through pipes rather than a global temporary pathname;
- verification also uses anonymous descriptors for verifier/signature handoff;
- the long-lived anchor and crypto child set `PR_SET_DUMPABLE=0` before secret-key access and fail closed if that boundary cannot be established;
- request nonce, exact request digest, pinned anchor identity, response body, and response signature remain bound exactly as in the authenticated Wave 127 protocol.

The reusable implementation is `tools/AXM_FLOWING_COMPUTE_PROCESS_WITNESS_KEY_CUSTODY.py`, with a full Wave-127-through-Wave-128 protocol regression launcher and a focused custody adversarial suite. Generated run reports stay in CI artifact storage rather than being committed as repository ballast.

## Preserved failed verification runs

First Wave 128 workflow head: `a0ed4efb5ca4243aa9c9350105a5a12d9f0d6cef`.

Run `35304282394`, job `105473165297`: **failed after the unchanged/full protocol regressions passed**. The focused tester attempted to list `/proc/<anchor-pid>/fd`; the tested GitHub Linux runner denied the entire directory once the anchor was non-dumpable. This was a stronger custody denial than the test harness allowed. The implementation was unchanged; the harness was repaired to treat either complete FD-directory denial or listing-with-all-readlinks-denied as the successful boundary.

Second candidate head: `2e9475834da7fcc0bbdfb1d3ecb1131f240867ba`.

Run `35304411869`, job `105473538861`: **failed 6/7 in the focused custody suite after unchanged Wave 127 and full Wave 128 protocol suites were green**. The tester launched 24 simultaneous clients against a deliberately serial anchor whose socket backlog is 16, so some client requests failed before they could be queued. This did not expose key material or a second signer. The implementation was again unchanged; the tester was bounded to 12 concurrent clients, below the documented backlog, and now explicitly records that this is serial signer queue pressure rather than a parallel-signing throughput claim.

Both failed runs remain part of the evidence history; neither was silently rewritten into success.

## Exact successful evidence

Exact CI-tested Wave 128 source: `a84f80672a2c54c02ad89479ec4c7c091a93f1d3`.

Exact blobs:

- key-custody tool: `c77cd2fc5b56848d1c88218a60d17d9df9c0d6bd`;
- full protocol regression launcher: `2b4d8e4be9f5b05f72a31360a6546fc14e2f6269`;
- focused custody adversarial self-test: `40dc519bd2371ee22b28a60d3c234eb856023b3b`.

Run `35304486465`, job `105473753686`: **success** on Ubuntu 24.04 / Python 3.12.3 / OpenSSL 3.0.13.

Results:

- unchanged Wave 127: **9/9 normal + 9/9 under `python -O`**;
- Wave 128 full authenticated-anchor protocol: **9/9 normal + 9/9 optimized**;
- Wave 128 focused custody: **7/7 normal + 7/7 optimized**;
- key generation exposed no matching global private-key helper;
- exact anchor response identity remained pinned;
- ordinary same-UID `/proc/<pid>/fd` access to the non-dumpable anchor exposed no usable file-descriptor target on the tested runner;
- 12 concurrent clients queued through the deliberately serial signer and all received valid exact-identity signatures, with **no parallel-signing claim**;
- the PR-52-style global-temp observer captured no private PEM helper;
- a real `SIGKILL` left no private-key helper pathname behind;
- exact-store restart preserved the same response identity and signing behavior.

Artifact `10530461109` (`wave128-key-custody-evidence`), SHA-256 `a6c30b81f221a5de1cd97ef64345df7f209f746874246f2f7dd38cdc5038c17`.

## Truth boundary / retained counterexamples

Wave 128 proves only the tested Linux same-host/same-UID custody boundary where the observer does not already have anchor-store read access, `CAP_SYS_PTRACE`, root/kernel control, or an independently copied genuine private key. The private key still exists transiently in process memory and in the isolated OpenSSL child; `PR_SET_DUMPABLE=0`, Linux `memfd`, procfs access checks, and the exact tested OpenSSL path are part of this result.

This does **not** prove hardware-backed custody, hostile-kernel/root resistance, secure physical erasure, cross-network-namespace or cross-host uniqueness, device/controller/provider finality, or safety after copying the genuine key into another authority domain. Rolling back/copying both witness and anchor authority domains together remains outside the proof, as does rollback/substitution of the witness-side verifier binding.

No real AXM/monolith performance workload and no synthetic scaling workload were run for this correctness/security gate. Therefore Wave 128 makes **no speed, energy, retained-compute, incremental-compute, dormant-compute, throughput, or scaling claim**.

## Next gate

Resume the cross-kernel clone attack that Wave 127 could not honestly reach while its private-key custody was still porous. Run two cryptographically genuine copied anchor identities — including the exact response private key — in separate Linux network namespaces and preferably on separate hosts, where the same-host lease and `PR_SET_DUMPABLE` boundary cannot create uniqueness.

Make both copies compete against the same witness/client lineage and test divergent signed histories, stale/current clone restart, reconnects, witness/verifier rollback, mixed Wave 126/127/128 downgrade paths, and whole-domain rollback. If two genuine copies can advance conflicting authenticated histories, preserve that counterexample and move uniqueness/rotation to an independently retained authority lineage rather than treating signatures or process isolation as finality.

No merge, auto-merge, or CANON promotion is requested by this evidence note.
