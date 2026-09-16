# Flowing Compute Wave 86 — Multiple Anchor Witnesses / Fail-Closed Disagreement

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST MULTI-WITNESS EVIDENCE`

## Question

Wave 85 showed that a separate software anchor can expose whole-primary-store rewind only while some newer fact survives outside the primary store. Wave 86 asks whether multiple witness histories can make that surviving fact harder to erase **without silently turning disagreement into a vote**.

## Exact prior identities / provenance

No fresh monolith audit ran in this wave. The probe continues from the existing Wave 84/85 pointer contract and exact retained-state identities:

- Wave 81 retention A: `53d91b18e1a12eb27bd503bcfa70b4cd74add598ceaef522c88d7c075fdee4d4`
- Wave 83 DROP retention B: `4078169dce33c5816c7dd1073eaff5920bcfb07284a023726322e67970378dd1`
- Wave 83 KEEP retention: `0f918393dc9d4dfb33fe150bbdca9bd4ecbdca8fab0317becdf94fb9296b1721`
- Wave 86 reusable tool commit: `23870591e0a8fae2e1bbf9b5b598ffbb3bac9eea`

This is an infrastructure/recovery wave, not a new retained/incremental/dormant compute-efficiency result.

## Reusable contract

`tools/AXM_FLOWING_COMPUTE_MULTI_ANCHOR_WITNESS.py` uses three required witness ledgers. Each witness independently stores the same content-bound Wave 85 anchor chain. A write is allowed only when **all configured witnesses are readable and exact-agree** with the current primary state.

The recovery rule is deliberately strict:

- one missing/corrupt witness -> `WITNESS_INCOMPLETE_HOLD`;
- multiple valid but different witness heads -> `WITNESS_DIVERGENCE_HOLD`;
- a 2-vs-1 majority does **not** win;
- a newer-looking minority witness does **not** win;
- if all witnesses exact-agree one epoch ahead of the primary and the exact committed pointer object + predecessor binding exist, the interrupted pointer move is recoverable.

No witness is silently promoted to canonical authority.

## Positive result

A normal three-witness forward transition and an intentional rollback both committed while the history epoch continued forward.

Then the primary and **two of the three witnesses** were restored to genesis while the third witness remained at epoch 2. The remaining newer witness exposed that rollback: validation returned `WITNESS_DIVERGENCE_HOLD`, named the surviving newer witness, and set `authority_selected = false`.

The same happened when only the primary + one witness were rewound and two newer witnesses survived. This is detection, not majority consensus.

## Disagreement attacks

The probe constructed a fully valid 2-vs-1 equal-epoch fork: two witnesses described the intentional rollback state while the third held a different valid epoch-2 history. The system held instead of using the majority.

A separate valid witness was then advanced to epoch 3 while the primary and other two remained at epoch 2. The system again held instead of trusting the newest-looking record.

Corruption, valid truncation to an older witness head, and removal of an entire witness also failed closed.

## Crash boundary / useful failure

A crash before any witness append left the staged pointer object non-authoritative.

A crash **after only one witness append** produced valid witness disagreement and deliberately blocked every new commit. Wave 86 does not auto-repair this case because doing so without an explicit shared commit-set identity could turn one partially written witness into an accidental leader. This is the main useful failure found in this wave.

By contrast, when **all three witnesses** had durably appended the exact same next anchor but the primary pointer move had not happened yet, restart recognized one unanimous one-epoch-ahead commit and safely completed the pointer move.

## Preserved counterexample

The primary and **all three software witnesses** were restored together to the same old genesis snapshot. Validation reported that old state as internally `CONSISTENT`.

So multiple software witnesses do not create a magical external clock: if every modeled failure domain loses the same newer history, the lost future is still unprovable from these records alone.

## Controls

Two independent local executions passed **19/19** controls each. The suite covers forward commit, intentional rollback, primary-only rewind, primary + witness rewind, a single surviving newer witness, valid 2-vs-1 fork, newest-looking minority fork, corruption, truncation, missing witness, pre-witness crash, partial fan-out crash, blocked write-through, unanimous pending commit, recovery, and the all-domain rollback limitation.

## Cost

A synthetic single-host three-witness commit benchmark used 100 fresh temporary stores per run:

- run 1 median process CPU: **1106.538 microseconds**;
- run 2 median process CPU: **1179.388 microseconds**.

These are process CPU timings for local JSON/hash/fsync orchestration. They are not wall-clock storage latency, not joules, not monolith workload timing, and not evidence that the witness layer improves compute efficiency.

## Truth boundary

- The three witnesses are **separate directories on one host**. They model independently rewindable histories but do not prove independent physical machines, disks, accounts, or trust domains.
- This is not distributed consensus, quorum authority, trusted hardware, or Byzantine-fault tolerance.
- A surviving newer witness can expose tested rollback, but disagreement grants no witness authority.
- If every witness and the primary are rolled back together, this software-only contract cannot prove the lost future.
- Hashes prove exact content relationships inside the modeled evidence; they do not establish actor identity or evaluator legitimacy.
- No fresh monolith audit, no new compute-efficiency win, no energy claim, and no automatic canon/merge action occurred.

## Next gate

**Wave 87: explicit multi-witness commit-set identity / partial fan-out recovery.** Bind one exact commit-set identity before fan-out, then allow completion of a partial witness fan-out only when every advanced witness names that same commit-set and every lagging witness is exactly at its declared predecessor. Any competing commit-set remains `HOLD`; no majority vote and no newest-wins rule.

A later independent-host/device reproduction is still required before treating the witness directories as real independent failure domains. Evaluator provenance from Wave 83 also remains a separate gate.
