# Flowing Compute Wave 87 — Explicit Witness Commit-Set / Partial Fan-Out Recovery

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST COMMIT-SET RECOVERY EVIDENCE`

## Question

Wave 86 deliberately froze after a crash that advanced only part of the three-witness fan-out, because one advanced witness had no shared predeclared transaction identity and therefore could not safely become an accidental leader. Wave 87 asks whether the transition can be made recoverable by creating one exact content-addressed **commit-set identity before fan-out**, while still refusing majority vote, newest-wins, or arbitrary witness catch-up.

## Exact prior identities / provenance

No fresh monolith audit ran in this wave. The reusable Wave 87 tool binds the exact latest Wave 86 source identity and prior retention identities:

- Wave 86 branch/tool commit: `23870591e0a8fae2e1bbf9b5b598ffbb3bac9eea`
- Wave 86 tool blob: `0059e3ab5d5e069a959a3571d50461f7309ead10`
- Wave 81 retention A: `53d91b18e1a12eb27bd503bcfa70b4cd74add598ceaef522c88d7c075fdee4d4`
- Wave 83 DROP retention B: `4078169dce33c5816c7dd1073eaff5920bcfb07284a023726322e67970378dd1`
- Wave 83 KEEP retention: `0f918393dc9d4dfb33fe150bbdca9bd4ecbdca8fab0317becdf94fb9296b1721`
- Wave 87 reusable tool commit: `357cc16fa6448b335f5586e69796583068a03f79`
- Wave 87 reusable tool blob: `102a28b1f6961987f7e5707fd4ba82c524a73df3`
- Wave 87 tool file SHA-256: `512ae95192cabd962a4744c94eee1e0f93fed6b49524963dd93ee3b5c20b6f9a`

This is an infrastructure/recovery wave, not a new retained/incremental/dormant compute-efficiency result.

## Reusable contract

`tools/AXM_FLOWING_COMPUTE_WITNESS_COMMIT_SET.py` creates a content-addressed commit-set **before any witness advances**. The commit-set binds:

- exact predecessor primary pointer + epoch + retention identity;
- exact target primary pointer + next epoch + target retention identity;
- exact ordered witness membership;
- exact predecessor record identity for every witness;
- transition kind (`FORWARD` or intentional `ROLLBACK`);
- exact Wave 86 source provenance.

A witness transition record then binds the same commit-set ID plus its own exact declared predecessor. Merely storing a commit-set object grants no authority.

Recovery is allowed only when every configured witness is in one of two exact states for the same commit-set:

1. already advanced to that commit-set's exact target record; or
2. still exactly at that commit-set's declared predecessor record.

An arbitrarily older witness is **not** swept forward. A lagging witness is repairable only from the exact predecessor named before fan-out.

## Positive result

The Wave 86 useful failure is repaired under this bounded model:

- crash before witness fan-out: current state stays `CONSISTENT`; the prepared commit-set has zero authority;
- crash after 1/3 witness writes: `PARTIAL_COMMIT_SET_RECOVERABLE`;
- crash after 2/3 witness writes: `PARTIAL_COMMIT_SET_RECOVERABLE`;
- crash after 3/3 witness writes but before primary pointer move: `UNANIMOUS_COMMIT_SET_PENDING_POINTER_MOVE`;
- repair completes only the exact lagging predecessors, revalidates all witness records against the same commit-set, then moves the primary pointer;
- intentional rollback still works while the commit epoch continues forward.

An unused competing commit-set object can coexist in the content-addressed store without gaining authority or blocking the active exact commit-set. Authority comes from the bound state transition, not object existence.

## Competing-set / stale-predecessor attacks

Two different commit-sets were prepared from the same predecessor. One witness advanced under C1 and another under C2. Recovery returned `WITNESS_COMPETING_COMMIT_SET_HOLD`; no majority and no newest-looking transition was selected.

A separate case rewound one lagging witness to an epoch older than the commit-set's declared predecessor. Recovery refused to repair it. This prevents a valid commit-set from becoming a general-purpose catch-up token.

Missing commit-set bodies, a rehashed replacement stored under the old content address, a validly rehashed witness record with altered retention semantics, a missing witness, and a primary pointer moved ahead of only a partial witness fan-out all failed closed.

## Useful failure found during this wave

The first implementation had a real membership hole: after a clean three-witness commit, a caller could omit `witness-c` from the runtime witness map and the steady-state validator still returned `CONSISTENT`, because that branch checked the shared commit-set ID but did not compare the commit-set's exact `witness_ids` with the configured witness set.

That failure was reproduced before preservation, then repaired. The final tool now performs the membership comparison in both steady-state and recovery paths, and the regression control `steady_state_witness_omission_holds` passes. This failure is the reason witness-set identity should become a first-class state object rather than remain only caller configuration.

## Controls

Two independent final local executions passed **25/25** controls each.

The suite covers exact Wave 86 provenance, exact Wave 81 genesis retention, prepared-object non-authority, unused competing-object non-authority, 1-witness and 2-witness partial recovery, unanimous pending-pointer recovery, intentional rollback, explicit witness omission, competing commit-sets, no majority/newest authority, exact-predecessor enforcement, missing/tampered commit-set bodies, semantically forged witness records, missing witness, primary-ahead ordering, crash points at 0/1/2/3 witness writes, and the preserved all-domain rollback limitation.

## Cost

The benchmark is **synthetic single-host orchestration**, not a monolith workload. Each round creates a fresh temporary primary store, commit-set store, and three witness stores, then measures commit-set preparation + three witness fsync/hash writes + primary pointer move.

- final run 1 median process CPU: **1987.462 microseconds** over 60 rounds;
- final run 2 median process CPU: **1552.188 microseconds** over 60 rounds.

These are process CPU timings for local JSON/hash/fsync orchestration. They are not wall-clock storage latency, not joules, and not evidence that this witness layer improves compute efficiency.

## Preserved counterexample / truth boundary

Restoring the primary, all three witnesses, and the commit-set store together to the same old snapshot still makes the old state look internally `CONSISTENT`. Wave 87 does not create an external clock or trusted independent failure domain.

Also:

- all witnesses are still directories on one host;
- this is not distributed consensus, quorum authority, Byzantine-fault tolerance, or trusted hardware;
- content hashes prove exact modeled relationships, not actor identity or evaluator legitimacy;
- a commit-set enables bounded completion of a transition that was already durably declared; it does not grant a witness independent authority;
- no fresh monolith audit, no new compute-efficiency claim, no energy claim, no silent canon rewrite, and no automatic merge occurred.

## Next gate

**Wave 88: witness-membership state / explicit reconfiguration.** The discovered omission bug shows that witness membership itself must not remain an implicit runtime argument. Bind the active witness set into a content-addressed membership state and into the primary/commit-set lineage. Adding, removing, or replacing a witness should require an explicit predecessor-bound membership transition with crash-safe handoff; silently dropping one required witness must stay `HOLD`. This also creates the right seam for later reproduction across genuinely independent hosts/devices.

Evaluator provenance from Wave 83 remains a separate unresolved gate.
