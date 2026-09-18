# Flowing Compute Wave 98 — content-addressed authority boundary + dual remote-witness protocol model

Date: 2026-09-16  
Lane: `chatgpt/lane-001-platform-extract`  
Status: experimental research only; append-only evidence; no merge/CANON authority.

## Exact source / provenance identity

Wave 98 continues from exact Wave 97 builder head `20e82977205040168c5fa79b967ee6868aa3f7db`, Wave 97 tool blob `f5ca09a21e64ec390c15e5825751d0d6977d023d`, and Wave 97 report blob `9e5fcdba8c6dbac9916c2fefd2c05f78e34ed31b`.

It incorporates independent verifier PR #22 at exact head `84cbc21db30540e9cdd2e8973a68573aebd317b3`, evidence blob `2cb814b195a8c53833b169871db1dab606b66c02`. That verifier showed two authority-boundary failures in Wave 97: local commit gating trusted an unsealed caller wrapper separately from the stored authority object, and final authority trusted mutable external-anchor fields without validating the anchor record seal/lineage.

Wave 98 reusable tool: `tools/AXM_FLOWING_COMPUTE_DUAL_REMOTE_WITNESS.py`, blob `bc4347a75f04f6d9ff97e58128d2f5f0a16c85a1`, introduced by commit `96ed283942bb5ff69a10c2ae988bdf395a61917f`.

Machine-readable report: `evidence/FLOWING_COMPUTE_DUAL_REMOTE_WITNESS_WAVE98_REPORT.json`, blob `397e1023f1ec1e233e3b0a6943d4b6e62854512b`, introduced by commit `955ca4dc4fd56e1d19c29c492192d0129422afc4`.

No verifier branch was merged or rewritten.

## What changed

The local commit API now accepts only the exact content-addressed `authority_sha`. It immediately resolves the stored sealed authority-link body and uses only fields from that resolved body for predecessor and epoch gating. A modified/unsealed Python wrapper cannot influence commit decisions anymore.

The prior single caller-supplied external-anchor list is replaced by a protocol model with two named remote witnesses, `remote-a` and `remote-b`, each carrying a distinct append credential, its own immutable content-addressed record store, its own monotonic sequence, and its own head. Read-time authority walks and validates the full record chain: exact key/body identity, record seal, service identity, sequence continuity, previous-record lineage, and exact binding of the remote head to the resolved local authority + checkpoint.

Final authority is deliberately strict: both remote witnesses must be online and must independently report the exact current local authority/checkpoint. One missing, stale, corrupted, forked, poisoned, or unavailable witness causes `HOLD`; the machine does not vote or guess.

## Positive and negative controls

Two local executions completed with **29/29 controls passing** each: one normal Python run and one `python -O` run.

Controls include the verifier's unsealed-wrapper attack being rejected; partial local witness fan-out staying non-authoritative; authority staying on HOLD until both remote witnesses publish; remote-record seal corruption being detected; a remote outage during publication; reconnect + exact catch-up restoring authority; stale valid remote-head replay being rejected; surviving dual remotes detecting local rollback; wrong remote credentials being rejected; one compromised remote credential poisoning only that witness and causing HOLD rather than false authority; both remote credentials forcing HOLD rather than matching an honest local state; and the prior all-current-signer compromise remaining visible as a counterexample.

## Important result: two witnesses expose a real availability/integrity tradeoff

With exactly two required remote witnesses, the model can safely refuse authority when either one is unavailable or disagrees. That protects against silently trusting a single potentially compromised witness, but it also means there is no fail-open path when one witness disappears.

This is not treated as an implementation annoyance. Under a threat model where one remote may be arbitrarily compromised, two witnesses cannot provide both strong disagreement detection and continued authority with one witness unavailable without adding another trust assumption. If AXM wants availability through one remote outage while still tolerating one Byzantine/compromised witness, the next design should add a third genuinely independent witness and define an explicit bounded quorum rather than weakening HOLD semantics.

## Counterexamples kept alive

- The two remote witnesses in Wave 98 are still separate **modeled** state/credential domains inside one Python process. They are not physically independent machines, providers, networks, or credential infrastructures.
- A compromised append credential can advance/poison one remote witness's monotonic head and create denial of authority. No credential-rotation or poisoned-witness recovery protocol exists yet.
- Compromise of all four current checkpoint signer seeds plus both remote append credentials before first publication can still construct and publish a competing valid world.
- Rolling local authority state and both modeled remote service states back together remains internally self-consistent.
- Valid signatures and witness records prove only the modeled mechanical chain. They do not prove evaluator legitimacy, human consent, root correctness, moral correctness, or canonical AXM authority.

## Synthetic scaling boundary

Wave 98 does **not** read a fresh AXM/monolith workload because verifier PR #22 exposed authority-integrity failures that had to be repaired before stronger remote claims.

Normal five-round synthetic authority-read medians: depth 1 `19,114.001 µs`, depth 4 `20,117.243 µs`, depth 8 `19,860.163 µs` process CPU.

Optimized-Python five-round repeat: depth 1 `18,225.443 µs`, depth 4 `19,328.080 µs`, depth 8 `20,016.977 µs` process CPU.

These are single-process protocol/retained-chain costs only. They are not network latency, remote-service performance, joules, monolith compute efficiency, or evidence that retained/incremental/dormant computation wins. The short 1/4/8-depth sample is intentionally not extrapolated into a scaling law.

## Next gate — Wave 99

Deploy the exact monotonic witness-record contract against at least two genuinely independent failure domains with separately held credentials and measure real partition/reconnect behavior. Add explicit remote credential rotation and poisoned-witness recovery. If the goal includes continuing authority with one witness offline while still tolerating one compromised witness, add a third independent witness and test a bounded quorum with positive and negative cases.

Keep the all-current-signer compromise and whole-domain rollback counterexamples visible. A remote witness may improve rollback/equivocation detection; it must not be described as consensus, solved anti-rollback, or independent failure-domain protection until real deployment evidence exists.
