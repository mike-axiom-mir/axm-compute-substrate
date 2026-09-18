# Wave 109 exact-source receipt

Date: 2026-09-17
Lane: `chatgpt/lane-001-platform-extract` / PR #2
Status: append-only evidence, experimental, unmerged, not CANON

## Tested commit

`1747e087d3ab07312484980da987b88f8e8f56cd`

Commit message: `Wave 109: fail closed on ambiguous commit status`

The evidence/receipt commit that contains this file is intentionally later and does not alter the tested implementation blobs below.

## Exact implementation identity

- tool `tools/AXM_FLOWING_COMPUTE_COMMIT_STATUS_AMBIGUITY_GUARD.py`
  - Git blob: `6dbb03509100fdd724c3576a4938a9406e0eaf3e`
- self-test `tools/AXM_FLOWING_COMPUTE_COMMIT_STATUS_AMBIGUITY_GUARD_SELFTEST.py`
  - Git blob: `f2142dc67475eba86d4c20975d53551cfb1170b0`
- workflow `.github/workflows/wave109-commit-status-ambiguity-guard.yml`
  - Git blob: `09137ac0dc550867542ec998300f43aa64082589`
- written evidence `evidence/WAVE109_COMMIT_STATUS_AMBIGUITY_GUARD_2026-09-17.md`
  - Git blob: `385a94fc0149db0211eadd0f1a6a4c93a4bb0cc1`

## CI identity

- GitHub Actions run: `35201878046`
- job: `105138315989`
- head SHA: `1747e087d3ab07312484980da987b88f8e8f56cd`
- workflow conclusion: `success`
- Wave-108 unchanged regression: `27/27`
- Wave-109 normal Python: `18/18`, verdict `PASS`
- Wave-109 `python -O`: `18/18`, verdict `PASS`

The unchanged Wave-108 regression completed before the Wave-109 tests. Both normal and optimized Wave-109 runs reproduce the verifier PR #33 stale-quorum condition against unchanged Wave 108, then show Wave 109 returning `HOLD_COMMIT_STATUS_UNRESOLVED` while surviving unmanifested transaction evidence remains.

## Artifact identity

- artifact ID: `10488072837`
- artifact name: `wave109-commit-status-ambiguity-reports`
- artifact digest: `sha256:eb228050d20ce696b0d7dd06fc82a478896c12b4f5398c0101cbb10663d374e5`
- `wave109_normal.json`: `sha256:a263f009ce693b0f5815975bc4277633d99b7205a84b2ab6b65d3839350feba8`
- `wave109_optimized.json`: `sha256:ee1abd548c28d907644ed6e561ab5651141ffeb5c83c6594590dbe175a8667b2`
- `wave109_wave108_regression.json`: `sha256:d6c5cb9c732ab464d07028d9afd4a9d6e926896ed5461992d0405a2a7347db3d`

## Preserved source/provenance chain

Wave-108 builder head tested by verifier PR #33:

`7573e1e97d026ed07065fcca46cc0d88a26e64b5`

Exact Wave-108 tested source commit:

`7b9ec8548bde69df1d8971567aaf04abd0fa2e5c`

Wave-108 tool/self-test blobs:

- `629318c9645649a29d7a4d4c97f106a0ba958f6d`
- `aeac803084fc05e82c626bb830cee48146c710e2`

Independent verifier PR #33 identity:

- PR head: `49a8bfe61d7e062c52e419d9670cb95e41730e98`
- CI head: `d2d5851a1bf3088d1d2c96af909777bc6ea2ed6f`
- evidence blob: `b69e34546378a0e7a38f550e89afb926a8909e21`
- reproducer blob: `196482bc43391d151508f70fa176f20ea7e8e72a`
- CI run: `35198901311`
- normal job: `105128625588`
- optimized job: `105128625455`

Preserved verifier verdict:

`FAIL_COMMITTED_MARKER_TAIL_TRUNCATION_RECLASSIFIES_ACCEPTED_EPOCH_AS_PREPARED_AND_PERMITS_STALE_QUORUM`

## Result boundary

What is supported by this receipt:

- Wave 109 stops Wave 108 from silently treating surviving unmanifested L/C/U/root-binding evidence as harmless prepared-only state.
- A legitimate in-flight prepare now also causes a read-side HOLD until commit markers are appended; this is an explicit safety-over-availability tradeoff.
- The exact PR #33 stale-quorum path is blocked while any of the tested newer local transaction evidence survives.
- Clean genesis and accepted forward progress through multiple epochs remain valid in the tested model.

What is **not** supported:

- if both marker tails and every newer local L/C/U/root-binding body are erased, the local world becomes an older genuine prefix; with the same partial stale quorum and the only newer certificate witness unavailable, the test still returns `AUTHORITATIVE_QUORUM_2_OF_3_MODELED`;
- therefore Wave 109 does not establish durable commit finality, process independence, physical monotonicity, device/provider independence, or atomic crash recovery;
- the depth-6 walk is synthetic correctness-only scaling, not a benchmark;
- no fresh AXM/monolith, performance, energy, retained-compute, incremental-compute, or dormant-compute win is claimed.

## Next gate

Add an independently durable commit-decision witness/receipt and then exercise the protocol across separate OS processes and durable stores. The critical negative case is marker-tail truncation plus complete newer local L/C/U/root-binding erasure while one newer external witness is unavailable. The new durable decision boundary must survive that case before process separation can be treated as meaningful safety evidence.

No merge, auto-merge, or CANON promotion was performed.