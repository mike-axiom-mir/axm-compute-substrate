# Wave 136 Independent Adversarial Verification — Genuine Cloned Current Authority Fork

Status: **DRAFT / UNMERGED / NON-CANON / DO NOT AUTO-MERGE**

This verifier lane challenges the newest Wave 136 builder state without rewriting builder implementation or prior evidence.

## Builder state challenged

- builder evidence head: `411bd123b193eca34f44bec1ff3d9d9af32247c5`
- exact Wave 136 tested source named by the builder receipt: `49d0bd8aa24a91036a85e1cd265985dfd97585b7`
- Wave 136 tool blob named by the builder receipt: `47fe034330c808b48ee39f64f70b07778b533372`

## What survives independently

The unchanged Wave 136 transaction-recovery self-test reran successfully in the verifier workflow in both modes:

- **11/11 normal Python**
- **11/11 `python -O`**

That independently preserves the bounded Wave 136 result: repeated 1/10/100 partial pending-private SIGKILL residue remains bounded; a complete 1,704-byte staged private candidate is preserved exactly; partial pending metadata and authority/witness lineage replacement recover; wrong-byte lineage residue fails closed and remains visible; post-commit cleanup SIGKILL points resume idempotently; corrupt cleanup residue fails closed; and two ordinary rotations retain a valid predecessor-signed lineage.

## New reproduced next-gate failure

`FAIL_GENUINE_CLONED_CURRENT_AUTHORITY_FORKS_INDIVIDUALLY_VALID_ROTATION_LINEAGES`

The verifier first established a **genuine Wave 136 sequence-1 rotation**. It then copied the entire current authority and witness domains byte-for-byte, preserving ownership/modes, current private key, current public key, authority lineage, witness lineage, binding, state, credentials, and all current durable evidence.

At the clone point the verifier proved:

- original and cloned anchor file trees were byte-identical;
- original and cloned witness file trees were byte-identical;
- current response private-key bytes were identical;
- authority lineage and witness lineage were identical;
- both copies therefore shared the same genuine current predecessor identity and sequence-1 history.

The two copies were then advanced **sequentially**, not concurrently, using the unchanged Wave 136 rotation implementation:

- original A authorized one new successor at sequence 2;
- clone B later authorized a different new successor at sequence 2;
- both sequence-2 certificates named the same exact predecessor rotation SHA and the same old response-public fingerprint;
- their new response-public fingerprints and head rotation SHAs differed;
- the unchanged Wave 136 validator accepted both local authority+witness domains as valid sequence-2 histories.

This reproduced in both normal and optimized Python.

No response private key was forged, no signature was forged, and no prior builder ledger/certificate was rewritten to manufacture the result. Root orchestration was used only to construct the exact byte-for-byte clone and preserve the dedicated authority UID ownership; the actual Wave 136 rotations and validations ran through the normal authority-UID path.

The result does **not** falsify Wave 136's stated same-host crash-recovery claim. Wave 136 explicitly leaves genuinely copied current authority identity/private-key uniqueness across another namespace/host unproved. This verifier demonstrates the underlying semantic issue on one host without requiring simultaneous processes: the current abstract-socket credential lease prevents overlapping use only while held. Once one valid holder exits and releases the lease, an exact authentic clone can later acquire the same lease name and extend a contradictory successor lineage. Signatures prove possession of the copied authority key, not uniqueness of the authority instance.

## Exact independent evidence

CI-tested verifier head: `ad385906219ad150a6043fa5a8ee025b61941fa4`.

GitHub Actions:

- run: `35338872054`
- job: `105579964969`
- conclusion: **success**
- environment: Ubuntu 24.04.5, Linux `6.17.0-1022-azure`, Python 3.12.14, OpenSSL 3.0.13; runner uid 1001 with `CapPrm=0` and `CapEff=0` before orchestration

Artifact:

- id: `10544660604`
- name: `wave136-cloned-current-authority-fork-verifier`
- size: 6,426 bytes
- SHA-256: `739e94bc6bae5ef7f3c7b2337fbd06b9e4d3a9e2e75bc2c563884ae703fe900a`

Verifier files:

- `verification/wave136_cloned_current_authority_fork_repro.py`
- `.github/workflows/verifier-wave136-cloned-authority-fork.yml`
- this evidence record

The current branch head after this evidence-only commit is intentionally not the executable CI-tested head above.

## Truth boundary

This is a **same-host whole-domain clone** counterexample. It does not claim cross-host execution, cross-user-namespace execution, live root/kernel compromise, authority-UID compromise during rotation, hardware-key extraction, physical finality, provider independence, speed, energy, throughput, or retained/incremental/dormant-compute performance.

It also does not establish whether two cloned authorities can run simultaneously in one network namespace: the existing abstract-socket lease is expected to block that narrower case. The reproduced issue is that the lease is temporary process mutual exclusion, not a durable external uniqueness fact.

## Next adversarial gate

Run the same genuine copied-current-authority experiment with **both copies live concurrently in separate Linux network namespaces, and preferably on a second host**, so the abstract-socket lease namespace is no longer shared. Force both to authorize different successors from the same exact predecessor and preserve both complete evidence domains.

Then test reconciliation explicitly: reconnect the divergent copies to one verifier domain and require a defined fail-safe response rather than silently choosing either branch. Include network partition/rejoin, legitimate migration, key rotation, stale clone return, and deliberate sequence/head collisions.

If both authentic copies can independently advance and remain locally valid, the design needs an independently retained monotonic **uniqueness / rotation authority** (or equivalent consensus/non-exportable hardware boundary), not another local pathname, lock, or process lease.
