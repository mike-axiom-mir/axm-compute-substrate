# Flowing Compute Wave 91 — Current Evaluator-Registry Authority

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST AUTHORITY-STATE EVIDENCE`

## Question

Wave 90 proved evaluator provenance/registry lineage, but preserved a precise authority hole: an authorization could resolve a structurally valid registry merely because that registry existed in the content-addressed store. Wave 91 asks whether root authorization can be forced to use the exact **currently committed evaluator registry**, with all required registry witnesses agreeing on that same identity.

This is an infrastructure/authority-state experiment. It is not a fresh monolith workload and it makes no retained/incremental/dormant-state performance claim.

## Exact prior identity

Wave 90 reusable tool:

- commit: `57435f3f21b017b6a532a39c31e0a8a58ca70182`
- Git blob: `35f756d023fcbfa1e24fff94a2dcf87b29d8962e`
- file SHA-256: `35355bb17ab069cf1de5d32168e2bf8153bf489eda30b27057e82ccab9743679`

Wave 91 reusable tool:

- path: `tools/AXM_FLOWING_COMPUTE_CURRENT_REGISTRY_AUTHORITY.py`
- tool commit: `0e275b6ea43c6a8cfbd66266e210bcf93a9ecddb`
- Git blob: `f378627bc2f8752fc8e20f73f0737c15f9e2ddff`
- file SHA-256: `28b7da0d40b53f2ba9ec58161c0531530c2bfaa7e63eada4c5e7cd7eb27ad4f5`

Machine-readable report:

- path: `evidence/FLOWING_COMPUTE_CURRENT_REGISTRY_AUTHORITY_WAVE91_REPORT.json`
- report commit: `a3d91046edfef83d6133d18e6e040cb844315e2b`
- Git blob: `5925050a6505332798acb537037346e708c3bf3e`

The executed local Wave 91 tool bytes were verified against the committed Git blob identity before preserving this evidence.

## Result

Two independent runs passed **27/27 controls each**.

The new authority rule is deliberately simple and strict:

- the runtime current-registry pointer must name an existing, valid registry body;
- all three required registry witnesses must name that exact same registry identity;
- the authorization receipt must name that exact current registry;
- no 2-vs-1 vote, newest-wins rule, or prepared-successor shortcut exists.

A stored/prepared successor can still be structurally valid, but it now has **zero authorization authority** until the exact handoff commits. A new evaluator therefore cannot authorize its own admission early merely by appearing in a prepared successor registry.

## Negative / recovery cases kept

The probe also required the following to fail closed or `HOLD`:

- partial registry witness fan-out;
- predecessor authorization during partial fan-out;
- target authorization during partial fan-out;
- one lone newer witness;
- missing required witness;
- current pointer ahead of witnesses;
- competing successor histories;
- missing current-registry body;
- corrupt current-registry body;
- replay of an old authorization after the successor becomes current.

Intentional rollback remains possible without reviving an old authority identity: the old evaluator set is restored through a **new forward-lineage registry identity**, and only a fresh authorization bound to that new identity is accepted.

## Important counterexample preserved

Wave 91 closes the **prepared successor = authority** hole, but it does not yet authorize evaluator-registry transitions themselves.

The test deliberately commits a self-minted evaluator registry through the still-unguarded transition primitive. Once that transition is allowed to finish, the self-minted registry is mechanically current and its authorization validates under the Wave 91 rule.

So current-state binding is real progress, but it does **not** prove evaluator-registry governance, moral evaluator legitimacy, or canonical AXM root judgment. That failure remains explicit rather than being hidden behind the passing controls.

## Cost / truth boundary

This benchmark is synthetic single-host authority bookkeeping only. Across 100 rounds per run, median process CPU was:

- run 1: **60.8145 microseconds**;
- run 2: **58.6380 microseconds**.

Those numbers are not wall-clock distributed latency, storage latency, joules, or evidence of compute savings. No fresh monolith audit ran. No distributed-consensus, moral-legitimacy, canonical-root, or automatic-merge claim is made.

## Next gate

**Wave 92: predecessor-root-authorize evaluator-registry transitions themselves.**

An ADD / REMOVE / REPLACE / MIXED evaluator-registry transition should require an exact authorization produced only by the **currently authoritative predecessor registry**. Bind the exact predecessor registry, target registry, transition identity/kind, and complete added/removed/replaced/retained evaluator sets. Target/new evaluators must have zero ability to authorize their own admission, replacement, or removal before commit. Partial handoff stays `HOLD`; prior transition authorization must not replay after commit; competing transitions stay frozen rather than voting. Rollback should remain a forward-lineage transition, not a silent resurrection of an old registry identity.
