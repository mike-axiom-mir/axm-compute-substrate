# Flowing Compute Wave 88 — Witness Membership as Explicit State

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST MEMBERSHIP / RECONFIGURATION EVIDENCE`

## Question

Wave 87 repaired partial multi-witness fan-out with one predeclared commit-set, but it also exposed a membership hole: a caller-selected runtime witness map could omit a required witness unless the validator explicitly compared it against the commit-set. Wave 88 asks whether **witness membership itself can become content-addressed state**, bound into the primary lineage, so adding/removing/replacing a witness is an explicit crash-safe transition instead of hidden caller configuration.

## Exact prior identities / provenance

No fresh monolith audit ran in this wave. The Wave 88 tool binds the exact Wave 87 reusable source identity:

- Wave 87 tool commit: `357cc16fa6448b335f5586e69796583068a03f79`
- Wave 87 tool blob: `102a28b1f6961987f7e5707fd4ba82c524a73df3`
- Wave 87 tool file SHA-256 recorded by Wave 87: `512ae95192cabd962a4744c94eee1e0f93fed6b49524963dd93ee3b5c20b6f9a`
- Wave 81 retention identity carried forward: `53d91b18e1a12eb27bd503bcfa70b4cd74add598ceaef522c88d7c075fdee4d4`
- Wave 88 reusable tool commit: `76ed78a64825a5c71ff2017ef9383d389b878192`
- Wave 88 reusable tool blob: `efabee7b9c9724e1bd23f37cfc909cc9ed54cf1a`

This is infrastructure/recovery research, not a new retained/incremental/dormant compute-efficiency result.

## Reusable contract

`tools/AXM_FLOWING_COMPUTE_WITNESS_MEMBERSHIP_STATE.py` adds a content-addressed membership object containing:

- exact ordered witness IDs;
- membership generation;
- predecessor membership identity;
- transition kind (`GENESIS`, `ADD`, `REMOVE`, `REPLACE`, or `UNCHANGED`);
- exact Wave 87 source provenance.

The current primary pointer now commits the exact `membership_sha256`. Steady-state validation derives the required witnesses from that committed membership object; the caller does not get to shrink the active set by passing a smaller map.

A reconfiguration object binds:

- exact predecessor pointer + epoch + retention + membership;
- exact target pointer + next epoch + target membership;
- old, retained, added, and removed witness sets;
- exact predecessor record for every old witness;
- one content-addressed reconfiguration identity.

## Crash-safe handoff rule

Membership change is deliberately two-phase before the pointer can move:

1. **Every witness in the old committed membership must hand off from its exact predecessor record.** Removed witnesses write a final append-only `RETIRED` record; retained witnesses write a `RETAINED` record.
2. Only after the old membership has fully handed off may newly added witnesses be bootstrapped. A new witness is accepted only if it has no unrelated pre-existing HEAD; existing unrelated state causes `HOLD` rather than silent overwrite/adoption.
3. The primary pointer moves only after the exact target membership has all required target records.

Recovery may finish an interrupted transition only when each witness is in the exact predecessor/target state declared by the reconfiguration object.

## Positive result

A three-witness membership `A,B,C` was explicitly replaced by `A,B,D`.

- crash after only one old witness handoff -> `OLD_MEMBERSHIP_HANDOFF_PARTIAL_RECOVERABLE`;
- repair completed only the exact lagging old witnesses, then bootstrapped `D`, then moved the pointer;
- `C` retained an append-only `RETIRED` record but stopped being required by current state;
- `D` became required because the current pointer names the new membership object;
- crash during a two-added-witness bootstrap recovered only the exact missing added witness;
- crash after all handoff/bootstrap writes but before pointer move recovered the exact pending reconfiguration;
- separate ADD-only and REMOVE-only transitions also completed successfully.

A removed witness may remain physically present after commit, but its mere existence grants **zero current-state authority** once it is absent from the committed membership state.

## Negative controls / failures kept visible

The key old failure remains reproducible as a negative control: a deliberately legacy validator that trusts a caller-selected subset can report healthy using only `A,B` even after required current witness `D` is removed from disk. The Wave 88 validator instead reads `A,B,D` from the committed membership object and returns `REQUIRED_WITNESS_MISSING_HOLD`.

Other attacks failed closed:

- an old required witness disappeared before handoff -> HOLD;
- an added witness already containing unrelated state -> `ADDED_WITNESS_HAS_UNRELATED_STATE_HOLD`;
- two different membership reconfigurations advanced different old witnesses from the same predecessor -> `COMPETING_RECONFIGURATIONS_HOLD`; no majority vote or newest-looking winner;
- a target membership body was replaced under the old content-addressed filename -> it had zero authority while still merely prepared, then recovery rejected it once a witness actually referenced that reconfiguration;
- prepared membership/reconfiguration objects alone still grant zero authority.

## Controls

Two independent final local executions passed **24/24 controls each**.

The preserved machine-readable summary is:

- `evidence/FLOWING_COMPUTE_WITNESS_MEMBERSHIP_STATE_WAVE88_REPORT.json`

## Cost

The benchmark is explicitly **synthetic single-host orchestration**, not a monolith workload. Each round creates a fresh local primary store, membership store, reconfiguration store, and witness directories, then measures preparation + old-witness handoff + added-witness bootstrap + primary pointer movement for an `A,B,C -> A,B,D` replacement.

- final run 1 median process CPU: **2189.8015 microseconds** over 60 rounds;
- final run 2 median process CPU: **2486.1985 microseconds** over 60 rounds.

These are process CPU timings for local JSON/hash/fsync orchestration. They are not wall-clock storage latency, not joules, and not evidence that this layer improves compute efficiency.

## Truth boundary

- all witness directories remain on one host; this is not independent physical witnessing;
- this is not distributed consensus, quorum authority, Byzantine-fault tolerance, trusted hardware, or actor identity proof;
- content hashes prove exact modeled object relationships, not whether the party requesting a membership change was legitimately authorized;
- old membership unanimity here is a recovery invariant, not a political/governance voting rule;
- restoring the primary, membership store, reconfiguration store, and all witness stores together to one mutually consistent old snapshot can still hide the lost future unless a newer fact survives elsewhere;
- no fresh monolith audit, no new compute-efficiency claim, no energy claim, no silent canon rewrite, and no automatic merge occurred.

## Next gate

**Wave 89: membership-change authorization bound to the exact reconfiguration.** Membership is now real state, which makes unauthorized membership edits more dangerous rather than less. Reconnect the unresolved Wave 83 four-root gate at this exact seam: a membership ADD/REMOVE/REPLACE should not be preparable or recoverable unless explicit authorization evidence binds the predecessor membership, target membership, and exact reconfiguration identity. Preserve the truth boundary that structural root receipts still do not prove evaluator/actor legitimacy; that legitimacy remains a separate unresolved problem.

After that, the membership state is the right seam for reproducing the same protocol across genuinely independent hosts/devices instead of three directories on one machine.
