# Flowing Compute Wave 130 — dedicated UID durable-key authority receipt

**Status:** EXPERIMENTAL / NON-CANON / GREEN on the exact source named below.  
**Lane:** `chatgpt/lane-001-platform-extract` / PR #2.  
**Merge policy:** no merge, no auto-merge, no CANON promotion.

## Continuity and independent counterexample

Wave 130 continues from Wave 129 evidence head `f0afa88d8e03404b4a985a91b3efc62d1cec000f` and its exact successful tested source `d0bab11db00abf9c635d3827b0138f28cbb19fde`.

Independent verifier PR #54 (`verifier/wave129-same-uid-durable-key-boundary`) tested exact head `ece88c7181355c834ead613b59e5e3a2fd14bdac`. Verifier CI run `35310042572`, job `105490011541`, artifact `10533296352`, SHA-256 `a43586a2b6a7a0f1c43aac80f93014c628567b2a960734dc350e48e1f58930c7` was green.

The verifier preserved Wave 129's 8/8 normal + 8/8 optimized lifecycle controls, then reproduced a new real boundary: after successful initialization, `response_private.pem` is mode `0600` but owned by the same Unix uid as ordinary worker processes. A separate process under that exact uid, with `CapEff=0`, no `CAP_SYS_PTRACE`, and no `/proc` memory access, could directly read the real 1,704-byte RSA private key and derive the exact witness-pinned public key. Therefore Wave 129's narrow pre-persistence non-dumpable `/proc` result remains valid, while broad post-persistence same-uid key confidentiality does not.

## Wave 130 change

Wave 130 does not try to make `0600` mean something it does not mean. It adds an explicit Unix-uid authority boundary for durable response-key custody:

- anchor initialization and serving must run under an authority uid different from the declared worker uid;
- the anchor directory is established as authority-owned mode `0700` before private-key generation;
- `response_private.pem` must remain authority-owned mode `0600`;
- same-uid authority/worker configuration fails before private-key generation;
- workers keep only the authenticated protocol surface and pinned public verifier rather than direct private-key access;
- the Wave 128 memfd signing/verification and non-dumpable process/crypto-child path remains active;
- non-empty pre-init anchor directories are refused rather than silently interpreted as recoverable state. Interrupted initialization recovery remains a later explicit gate.

Exact green tested source commit: `d5f3cbc678559b139d7b622ecbbacd3987fdac65`.

Exact source blobs:

- Wave 130 authority tool: `17241b23bc7104410ae39c4ebfa258d32cd934f1`
- Wave 130 adversarial self-test: `630504c9768293e7e53ef3ce91e70cb4b4f58434`
- Wave 130 workflow: `ac276f9ab823b6d9d9e5a89aeaa74cdcbd948929`
- unchanged Wave 129 lifecycle tool: `643b747762e904cd07efcccc36036fb7cba8b4f4`

## Exact green verification

GitHub Actions run `35313219079`, job `105499330823`: **success**.

Environment recorded by CI: Ubuntu 24.04.5, Linux `6.17.0-1022-azure`, Python 3.12.14, OpenSSL 3.0.13, runner worker uid `1001`, `CapEff=0`, Yama `ptrace_scope=1`. The test harness uses root only to orchestrate two numeric identities; the claimed worker/adversary remains uid `1001`, while the anchor authority runs as uid `23001`.

Unchanged predecessor controls:

- Wave 129 lifecycle: **8/8 normal**
- Wave 129 lifecycle: **8/8 `python -O`**

Wave 130 controls:

- dedicated-UID authority self-test: **8/8 normal**
- dedicated-UID authority self-test: **8/8 `python -O`**

The Wave 130 suite first preserves the predecessor failure: another process under Wave 129's same uid directly reads the 1,704-byte private key and derives the matching public key. Under Wave 130 it then verifies:

1. the private anchor store is uid-23001-owned `0700`, with uid-23001-owned private key `0600`;
2. uid 1001 receives `PermissionError` on direct private-key read;
3. uid 1001 cannot open the anchor process `/proc/<pid>/mem` or list its `/proc/<pid>/fd` under the tested Linux boundary;
4. uid 1001 can use the genuine authenticated anchor without possessing the private key;
5. uid 1001 can replace the shared socket pathname, but an unsigned fake endpoint is rejected before authority is accepted;
6. real `SIGKILL` of the anchor followed by restart under the authority uid preserves the exact anchor credential and response-public identity;
7. collapsing authority and worker onto the same uid is rejected before a private key exists.

Artifact `10534127481` (`wave130-dedicated-uid-key-authority`) contains 10 exact evidence files, 7,398 bytes. Uploaded artifact ZIP SHA-256: `7f73004c895df5f17f791a9a8306e3408c452a824bbe2cf40489261d0523cccd`.

## Failed attempts preserved — no silent rewrite

The path to the green run contained four failed Wave 130 CI attempts. They remain part of the append-only lane history:

- Run `35312543080`, job `105497360169`: unchanged Wave 129 controls were green, but the new root-orchestrated harness created a handoff directory as `0755` because of umask, so dropped worker uid 1001 could not create its witness store. This was a harness-permission failure; the Wave 130 authority implementation was not implicated.
- Run `35312829635`, job `105498199696`: a malformed attempted harness rewrite introduced a non-UTF-8 byte and Python stopped with a syntax/encoding error. The malformed harness commit remains in history; the clean source was restored rather than history being rewritten.
- Run `35312930466`, job `105498498722`: numeric authority uid 23001 could not traverse the GitHub runner's `/home/runner/...` checkout path to execute the test tool. This was a test-environment accessibility failure, not a key-boundary result. The workflow was changed to stage read-only test code under `/tmp` for both numeric identities.
- Run `35313056252`, job `105498862704`: the first real Wave 130 protocol test reached the genuine anchor but the test client had imported the bare Wave 127 verifier before installing Wave 128/129 memfd hooks, so it rejected the genuine current reply as `anchor-response-signature-algorithm-mismatch`. The authority implementation was unchanged; the self-test was corrected to import the current Wave 130 chain first so both sides verify the exact active protocol.

The next exact run then passed all predecessor and Wave 130 controls in both normal and optimized Python.

## Truth boundary

Wave 130 establishes only the tested Linux Unix-uid/process boundary. It does **not** establish confidentiality or uniqueness against root/kernel compromise, an attacker running as the authority uid, ACL/LSM policy that grants equivalent access, copied genuine authority credentials/private keys in another namespace or host, coordinated rollback of all authority state, hardware-backed/non-exportable key custody, device/controller failure, provider independence, or physical finality.

The socket pathname remains replaceable in the deliberately shared run directory; the important tested property is that pathname replacement alone cannot forge the authenticated response. The private key is still an exportable file for the authority uid. A copied genuine key remains a live future counterexample candidate.

No real AXM/monolith performance workload and no synthetic scaling workload was run in Wave 130. This wave therefore makes **no** new speed, energy, retained-compute, incremental-compute, dormant-compute, throughput, or scaling claim.

## Next gate

First make interrupted Wave 130 anchor initialization recoverable **only from exact durable identity/provenance**, while retaining ambiguous or mismatched partial state as fail-closed counterexamples. Attack kills around root creation, response-key persistence, public-verifier/binding publication, and final readiness; test rollback and mismatched leftovers rather than assuming recovery must win.

If that gate survives, add exact old-authority-authorized key/authority rotation and attack kill points around the rotation lineage. Then resume the larger copied-genuine-key test across a separate network namespace and preferably a second host. If two genuine copies can both advance conflicting authenticated histories, preserve that counterexample and move uniqueness to an independently retained authority/rotation lineage rather than claiming signatures alone create uniqueness.
