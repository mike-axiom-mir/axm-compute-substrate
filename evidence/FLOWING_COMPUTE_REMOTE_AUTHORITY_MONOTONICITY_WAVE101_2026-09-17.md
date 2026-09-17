# Flowing Compute — Wave 101 remote authority monotonicity

Date: 2026-09-17  
Lane: `chatgpt/lane-001-platform-extract`  
Status: experimental evidence; open/unmerged; no CANON promotion.

## Why this wave changed direction

Wave 100's planned next step was OS-process separation. Independent verifier PR #25 found a protocol defect that had to be repaired first: remote record sequence and registry lineage could both advance while the authority epoch moved backward. With two current symmetric append credentials, the unchanged Wave 99 raw append primitive could leave retained histories shaped like `authority epoch 1 -> 2 -> 1`; Wave 100 then accepted the rolled-back local epoch through modeled 2-of-3 quorum. Moving that contract into separate processes would not repair the protocol flaw.

Exact verifier identity:

- verifier PR: `#25`
- verifier head: `100e45fb18f7cfc52663af3ad53753eeab4c8365`
- verifier evidence blob: `246138d4a3a1e8757ef1044e4e7a0928536870f5`

## Exact builder sources

Wave 100 source identity retained by this experiment:

- builder head: `0fb2caa805cebf29185d0b40c9f1bbd46199263b`
- CI-tested source commit: `c235f8f0682a98f9d5777df12ef97dce8ca0560d`
- Wave 100 protocol blob: `9fc2dc55c2d3973010b1804ad766cc632b89fa1f`
- Wave 100 self-test blob: `12491f9996bd7bada33ea742dacbb186dfd037c8`

Wave 101 reusable sources:

- `tools/AXM_FLOWING_COMPUTE_REMOTE_AUTHORITY_MONOTONICITY.py` — blob `9283b748aefcc1914eb763748674ee83a5ec3b15`
- `tools/AXM_FLOWING_COMPUTE_REMOTE_AUTHORITY_MONOTONICITY_SELFTEST.py` — blob `4bddbd849319b7475ac399dd96cd72ceb498545a`
- `.github/workflows/wave101-authority-monotonicity.yml` — blob `8198fd5c7c6c3605c760878a0f445124be5b645a`

CI-tested branch head: `9ef7fd00ea5e06591a98eef038c6816f7d6fdc3d`. GitHub Actions run `35167884262`, job `105032949949`.

## What changed

Wave 101 adds a second monotonic dimension to the retained remote witness contract. Registry lineage from Wave 100 still has to be valid, and now each retained remote authority history must begin at epoch 1 and advance exactly `+1` for every new record. A normal later record therefore cannot silently endorse an older epoch, repeat the same epoch as a sibling world, or skip forward as if missing authority steps did not matter.

When a remote head exactly claims the current local authority, it is additionally cross-bound to the local authority's exact predecessor authority SHA and the checkpoint's exact predecessor checkpoint SHA. Record order is therefore not used as a substitute for semantic authority lineage.

Invalid retained authority histories are not repaired or rewritten. They are quarantined and cannot count toward quorum. This preserves the append-only evidence boundary: one poisoned witness may be ignored while two healthy exact witnesses still satisfy the existing 2-of-3 contract; two poisoned histories lose quorum and HOLD.

## Positive and negative evidence

The exact PR #25 attack is deliberately reproduced against the old path first. Two raw appends still make Wave 100 accept the rolled-back epoch, proving the counterexample did not disappear by accident. The same attacked histories are then rejected by Wave 101, and rolled-back authority is not regained.

Additional negative controls reproduce and reject:

- an equal-epoch sibling authority appended at a higher record sequence;
- a skipped authority epoch appended at a higher record sequence;
- two poisoned remote histories attempting to remain a quorum.

Positive controls preserve:

- ordinary epoch 1 -> epoch 2 progression;
- 3-of-3 authority on healthy history;
- one poisoned witness quarantined while two healthy witnesses remain authoritative;
- direct credential rotation under Wave 100's exact registry-successor rule, with the authority epoch continuing as the direct successor.

## CI result

The read-only workflow completed successfully on Python 3.13:

- Wave 100 regression: **39/39 PASS**
- Wave 101 normal Python: **27/27 PASS**
- Wave 101 `python -O`: **27/27 PASS**

Synthetic single-process authority-read medians from the two Wave 101 runs were approximately:

| retained depth | normal Python | `python -O` |
| ---: | ---: | ---: |
| 1 | 63.479 ms CPU | 68.416 ms CPU |
| 4 | 68.547 ms CPU | 70.568 ms CPU |
| 8 | 70.849 ms CPU | 73.892 ms CPU |

These numbers are protocol-bookkeeping observations only. They are **not** network measurements, energy measurements, a fresh AXM/monolith workload result, or evidence that retained/incremental/dormant compute wins.

Machine-readable evidence is preserved at `evidence/raw/wave101_remote_authority_monotonicity_report_2026-09-17.json` (blob `cc140049609563a9aa25828f5f00cb420cb35d6a`).

## Counterexamples kept alive

All three remote witnesses are still modeled Python objects inside one process. Rolling the local runtime and all modeled witness/supporting stores back together remains internally self-consistent. Two current symmetric append credentials can still poison two witness histories and force a denial-of-authority HOLD, although they no longer regain the old world as authoritative. A poisoned witness cannot yet be legitimately rehabilitated without a new explicit recovery protocol. Remote credentials remain symmetric test tokens, and enough local signer compromise plus a valid remote quorum can still create a competing structurally valid forward world.

None of this mechanical chronology evidence establishes moral/root judgment correctness, consent, evaluator legitimacy, or canonical AXM authority.

## Why no fresh monolith workload here

The newest independent evidence exposed an authority-protocol rollback before the planned deployment experiment. Repairing that defect is a prerequisite to making stronger failure-domain claims. Re-running unrelated compute-efficiency workloads would not answer this gate, so no new monolith/retained-state performance claim is made in Wave 101.

## Next gate — Wave 102

Move the repaired registry + authority chronology + quorum contract across at least three real OS processes with separate durable stores and separately held credentials. Test actual process kill/restart, partition/reconnect, stale store restoration, credential rotation, one poisoned-process quarantine, two-process compromise, and whether a separately durable maximum catches process-local rollback.

Even a successful Wave 102 will demonstrate **process-level separation only**. It must not be described as physical/provider independence until genuinely separate failure domains are tested.
