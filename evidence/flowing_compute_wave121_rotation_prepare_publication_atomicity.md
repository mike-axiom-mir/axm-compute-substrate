# AXM Flowing Compute — Wave 121 evidence

Status: experimental lane only. No merge, auto-merge, or CANON promotion.

## Trigger / preserved counterexample

Independent verifier PR #45 (`ad230a162462fba3636b6e2a264b83a4d10a7295`) reproduced a fail-closed Wave 120 liveness/evidence defect at the builder-exposed post-lower-prepare / pre-transition-sync boundary.

Unchanged Wave 120 could let lower preparation write checkpoint/use/authority-link state, signer reservations/successors, and a root-binding into caller-visible state while the exact transition body still existed only in a temporary effective transition store. Injecting the fault before `_sync_prepared_transition` left one new outcome root, one new envelope, at least one binding referencing that envelope, and zero corresponding new transition rows in the public transition store. Commit status became `UNRESOLVED_COMMIT_STATUS`, authority became `HOLD_COMMIT_STATUS_UNRESOLVED`, and the exact public retry was rejected by the predecessor-authority gate.

This counterexample is preserved as fail-closed: it did **not** demonstrate stale authority acceptance, hash/credential forgery, power-loss atomicity, timing/energy behavior, or a retained/incremental/dormant-compute win.

Verifier evidence: PR #45; workflow run `35269713222`; job `105365655523`; artifact `10517938412`; artifact ZIP SHA-256 `c3cb43b205a442f124d7578414ba50f61a53a6300582467931a29e37439f7b44`.

## Wave 121 change

Wave 121 stages every modeled mutable prepare surface before making any new prepare evidence caller-visible:

- retained state (`P`, `C`, `U`, `L`, outcome-root store, envelope store);
- private signer state (new successor keys plus current-key reservations);
- exact transition store;
- root-binding store.

The lower Wave 114 prepare runs only against those staged copies. The exact lower-produced transition is synchronized into staged transition evidence before publication. Wave 121 then verifies append-only/exact deltas against the returned checkpoint, use, authority link, transition, binding, outcome root, envelope, and signer identities. It also checks that prepare did not mutate runtime, remote services, registry state, or certificate state.

Only a fully checked staged result is published. Five injected same-process exception boundaries cover publication after the exact transition, retained state, binding state, private signer state, plus the boundary after lower preparation but before publication. If an exception occurs after publication begins, Wave 121 restores the exact pre-call snapshots of all caller-visible prepare mutation surfaces. It does not reconstruct a missing transition from semantic similarity.

## Exact-source verification

Tested source commit: `a3c763a106bc5aea6245816de67f220f2b8695bc`

- Wave 121 implementation blob: `b0909097c6af1d6aa5dd522664aa9f8caaade587`
- Wave 121 self-test blob: `c73fc1b19f517927643ebb771bc8cd17d873776f`
- Wave 121 workflow blob: `d5b1a4fa17c330aa988093c48b0a721b20e2fd17`
- exact-source workflow run: `35273822562`
- job: `105379427177`
- artifact: `10518619363`
- artifact SHA-256: `6b983953f0cd6513da6b68ea6192bd2ee1159bf7d505d0ed6cd8c4bd1d3e6339`

The bounded Wave 120 predecessor control passed. Wave 121 passed all 8 adversarial/positive controls normally and all 8 again under `python -O`. The suite explicitly reproduces verifier PR #45 against unchanged Wave 120, contains arbitrary lower partial writes inside staging, checks exact rollback + successful exact retry at all five Wave 121 fault boundaries, and verifies a clean rotation publishes the exact identities before `COMMITTED_ROTATED`, VALID history, certification, and authoritative settlement.

The full Wave 120 suite was not needlessly repeated inside this focused Wave 121 gate; it was already green at current predecessor source head `d8d466181ffc80554549899c1dcafa115a27e7ec` in workflow run `35269779977`. No synthetic scaling run and no real AXM/monolith performance workload were run in Wave 121.

## Truth boundary / surviving failures

Wave 121 proves only **same-process exception transactionality for this modeled prepare boundary**. Publication is still several in-memory writes. A hard process kill or power loss between those writes cannot execute the rollback handler and remains an explicit counterexample. All authority, witness, credential, and store state is still inside the modeled Python failure domain; coordinated whole-world rollback remains possible. This wave makes no performance, energy, network, OS/device/provider-independence, physical-finality, or retained/incremental/dormant-compute claim.

## Next gate

Move the COMMIT / stable-REJECT / retriable-HOLD outcome/decision witness into a genuinely separate OS process with its own durable store and credential, and make publication/recovery survive actual process kills rather than injected Python exceptions. Kill after every durable write; test complete local rollback while the witness stays newer, stale/cloned local disks, witness restart/truncation/corruption, credential substitution, old/new simultaneous views, partitions/reconnects, and outcome-authority rotation across the process boundary. Success would establish only the tested process/store separation, not physical or provider-independent finality.
