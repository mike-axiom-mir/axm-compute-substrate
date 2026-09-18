# AXM Flowing Compute — Wave 112 Recoverable Transition Provenance

Date: 2026-09-17
Lane: `chatgpt/lane-001-platform-extract`
Status: experimental evidence only; no merge or CANON promotion

## Starting evidence

Wave 112 continues from the exact Wave-111 builder/evidence state rather than repeating earlier work.

- Wave-111 builder head before independent verification: `ea430afcade876dee771c972028a4c02761a737f`
- Wave-111 exact tested source: `8b3c7e727fb1110259da15a9e9e62b720c520045`
- Wave-111 tool blob: `638294762fc84245e265bfad138869f83c621fd6`
- Wave-111 self-test blob: `d48f09c80900ad3a8ab1667f524832ca3a2892db`
- Independent verifier: PR #36, base `ea430afcade876dee771c972028a4c02761a737f`
- Verifier exact CI-tested head: `5f71aee8ecacd1565b0dc74f0e525762deacd2be`
- Verifier current head when Wave 112 began: `07e920990787eec76d5dd0ef0483240f3cf6dc52`
- Verifier CI run: `35214808338`
- Verifier verdict: `FAIL_COMMIT_TO_PROVENANCE_CRASH_HAS_NO_PUBLIC_RETRY_RECOVERY`

The verifier's new result was a bounded liveness/recovery failure, not stale-authority acceptance. If Wave 110's lower commit became durable and the process crashed before Wave 111 appended its provenance row, Wave 111 correctly HOLDed authority. But retrying the public Wave-111 `commit(...)` with the exact same authority and transition could not finish that already-committed decision. The verifier also measured deterministic structural marker-store scans of 4/40/144 rows at committed depths 1/4/8, matching `2*N*(N+1)` for that Wave-111 validation path. This was structural work evidence, not wall-clock, energy, or end-to-end performance evidence.

## Wave 112 repair

Reusable implementation:

- `tools/AXM_FLOWING_COMPUTE_RECOVERABLE_TRANSITION_PROVENANCE.py`

Wave 112 adds an intentionally narrow idempotent recovery path. It appends exactly one missing trailing provenance row only when all of the following are already proven by retained lower-layer evidence:

1. Wave-110 commit status is `VALID`.
2. The requested authority is already in the committed authority sequence.
3. Existing provenance is an exact prefix with exactly one missing trailing row.
4. Exactly one validated retained transition targets that committed authority.
5. The caller supplies that exact transition SHA.
6. Wave-111 transition semantics replay against the exact authority/checkpoint/registry lineage.
7. The post-recovery state validates as exact committed history.

The successful recovery result is `COMMITTED_RECOVERED_PROVENANCE`. A different transition SHA, multiple missing provenance rows, malformed history, non-trailing loss, or any wider ambiguity is not inferred or repaired.

Wave 112 also indexes the already-validated Wave-108 commit/high-water marker chains once for its own provenance pass instead of re-linearizing those full chains once per committed epoch.

## Positive and negative cases

The exact Wave-112 control set verifies:

- normal genesis and two accepted epochs;
- exact old/latest committed retries remain idempotent;
- the verifier PR #36 Wave-111 crash/retry failure is reproduced before the repair is credited;
- the crashed exact decision is HOLDed before retry, then the exact retry appends only the missing provenance row;
- repeated exact retry after recovery is idempotent;
- authority can return after normal remote publication/certification;
- a wrong transition SHA cannot recover and does not mutate the held state into validity;
- the exact transition can still recover after the rejected wrong-SHA attempt;
- deletion of multiple provenance rows remains `INCOMPLETE_OR_CORRUPT`; recovery refuses to infer multiple missing facts;
- abandoned prepared-but-uncommitted work remains `UNRESOLVED_COMMIT_STATUS`/HOLD and is not silently cleaned;
- whole-modeled-domain rollback to a genuine older prefix remains an explicit counterexample: if every newer modeled fact disappears together, the older prefix can still look authoritative.

## Structural scaling probe — synthetic and correctness-only

Synthetic committed depths 1, 4, and 8 were used only to instrument validation structure. Each Wave-112 `commit_status_state(...)` remained `VALID`, and the Wave-108 marker-chain linearizer was invoked exactly 2 times at each tested depth: `2 / 2 / 2`.

This is evidence that the added Wave-112 validation path removed the verifier's per-epoch repeated marker-chain linearization. It is **not** a wall-clock speedup claim, not an energy claim, and not evidence that retained, incremental, or dormant state wins generally. Lower layers still perform their own bounded validation work, and no asymptotic claim is made beyond the exact instrumented call boundary.

## Preserved failed CI attempt

The first Wave-112 CI attempt is intentionally not hidden.

- run: `35217553400`
- failed-run artifact: `10495459907`
- artifact digest: `sha256:207224560c5ef6640f3d54a431276f00e58f7bdf32e5d68f517696ce5a4a5f1b`
- run head from artifact metadata: `c7b24bb68c1e0d92d0bfd3f62cbf1322a700001f`
- Wave-111 regression: 27/27 PASS
- Wave-112 normal: 20/22, with both failures confined to the synthetic scaling instrumentation
- optimized Wave-112 step did not produce a report because the normal step failed first

The failed harness replaced Wave-108 `_marker_chains` with a wrapper that accepted only one positional argument, while the real API legitimately calls `_marker_chains(..., allow_missing=True)`. That test wrapper caused the observed `INCOMPLETE_OR_CORRUPT` states before the implementation under test reached the indexed-marker validator. The original failed test and CI run remain in repository/history evidence; a small CI wrapper repairs only the instrumentation signature and does not patch implementation behavior.

## Final exact-source CI

Exact successful CI-tested source head:

`1be9303bba0712869d40444f5cf1b0e878948ab7`

Exact blobs at that source head:

- Wave-112 implementation: `41e73e8f042df974b161fa9b85b128c99b1bb819`
- original Wave-112 self-test: `7a48968a851c23129b6ae31ef017483407e70e8f`
- CI instrumentation wrapper: `0a1bad2b8f6f6745c8ba5b575e92587f1f7e9ba4`
- Wave-112 workflow: `3f19ace7de0477635af459758134eb2caf36b034`

Successful CI:

- run: `35218596920`
- job: `105192939604`
- Wave-111 regression: 27/27 PASS
- Wave-112 normal Python: 22/22 PASS
- Wave-112 `python -O`: 22/22 PASS
- uploaded artifact: `10496246899`
- artifact digest: `sha256:9bb6bf33f04be3ff3b0b08b963da50130f08e42c9ab36452a44dc8f345b3333a`
- synthetic structural scaling in both Wave-112 reports: depths 1/4/8 all `VALID`, marker-chain call counts `2/2/2`

## Truth boundary / failures retained

Wave 112 still does **not** solve the larger failure-domain problem.

- All authority, transition, provenance, certificate and witness objects are still modeled inside the same Python-process experiment.
- Whole-domain rollback can erase every newer fact together and recreate a genuine older self-consistent prefix.
- An abandoned PREPARE remains ambiguous and intentionally blocks progress; Wave 112 does not invent an abort decision or delete it.
- There is still no independently durable commit-decision witness.
- No process/device/provider independence is claimed.
- No fresh real AXM/monolith workload was run this wave because the newly verified correctness/recovery gate took priority.
- No fresh wall-clock, energy, network, retained/incremental/dormant-compute, or general performance win is claimed.

## Next gate — Wave 113

Put the commit-decision/provenance witness into a genuinely separate OS process with its own durable store and separately held credential/identity. Then attack every important publication boundary: crash before decision publication, after decision publication but before local provenance persistence, complete local rollback while the independent witness remains newer, stale/cloned local disks, witness outage or stale witness state, restart recovery, partitions/reconnects, and simultaneous old/new process views.

The target is evidence that an independently retained newer decision can safely close or block local recovery. Even a clean result would establish only process/store separation under the tested host conditions, not physically monotonic storage or independent-provider finality.
