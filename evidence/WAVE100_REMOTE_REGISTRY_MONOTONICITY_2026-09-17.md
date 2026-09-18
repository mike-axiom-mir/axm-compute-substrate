# Wave 100 — monotonic live registry transitions

Date: 2026-09-17  
Lane: `chatgpt/lane-001-platform-extract`  
Status: experimental evidence only; no merge or CANON promotion.

## Exact predecessor / verifier identity

Wave 100 continues from Wave 99 builder head `0c3ea28b4d731cde942d337c87a046f363d496c2`, exact Wave 99 protocol blob `c4c0a6bcabeafcf19502303857d1fc4da6fe8ea5`, and exact Wave 99 self-test blob `6efa792265c4fd3b54e7cfb192f5e1440402010a`.

It directly addresses independent verifier PR #24 at head `0c13b87882df2a6a18bd3dff032b47b92a36a3a6`, evidence blob `367d8627679e76114a1dd767e95b4b92090447ad`.

The verifier reproduced a narrower failure than whole-world rollback: Wave 99 could move normally through registry generations 0 -> 1 -> 2, then prepare a new signed checkpoint naming old generation 0, append ordinary new remote records under that stale registry to two witnesses, and regain `AUTHORITATIVE_QUORUM_2_OF_3_MODELED` while the authority epoch advanced and newer registry records remained retained.

## What changed

Wave 100 adds a new additive protocol layer rather than rewriting Wave 99.

A state-only checkpoint must retain the exact current registry SHA. A registry-changing checkpoint must name the exact direct successor of the current registry and must have generation `current + 1`. The transition itself is now a sealed content-addressed object binding the predecessor authority, target authority/checkpoint, current and target registry identities/generations, exact changed slot/fields, and target state binding. Commit resolves that stored object and reconstructs the legacy Wave 99 metadata internally instead of trusting caller-mutated transition metadata.

This wave deliberately authorizes only one registry mutation shape: exactly one slot may change, and the only changed field may be `credential_hash`. No-op successor registries, sibling jumps, skipped generations, service-identity migration, and failure-domain migration fail closed until separately specified and tested.

Remote retained histories now also enforce registry monotonicity. Consecutive records may keep the same registry or move to the exact direct successor; a lower, sibling, skipped, or stale registry after a newer one causes `HOLD_REMOTE_REGISTRY_LINEAGE`. This makes the remote history a second defense even if the unchanged Wave 99 primitive is called directly.

## Verification

The exact committed source at CI-tested commit `c235f8f0682a98f9d5777df12ef97dce8ca0560d` ran in GitHub Actions on Ubuntu 24.04 / Python 3.13.15. Both normal Python and `python -O` passed **39/39 controls**.

The controls include positive state-only progression, partial commit/resume, 2-of-3 and 3-of-3 publication, a legitimate credential-only successor, partial registry fan-out, retired-token rejection, one stale witness with two exact current witnesses, and the preserved whole-modeled-domain rollback counterexample.

Negative/adversarial controls include tampered transition bodies, no-op registry successors, skipped-generation targets, sibling registry jumps, direct generation rollback from a valid Wave-100 current registry, one-offline-plus-one-stale quorum loss, sibling remote-history injection, and the exact PR #24 attack.

The test deliberately re-runs the PR #24 attack through the unchanged Wave 99 API. Wave 99 again accepts the stale-registry prepare/commit, remote A/B appends, and false quorum authority. The Wave 100 authority path rejects that same retained world with `HOLD_REMOTE_REGISTRY_LINEAGE`.

Reusable exact blobs:

- `tools/AXM_FLOWING_COMPUTE_REMOTE_REGISTRY_MONOTONICITY.py` — `9fc2dc55c2d3973010b1804ad766cc632b89fa1f`
- `tools/AXM_FLOWING_COMPUTE_REMOTE_REGISTRY_MONOTONICITY_SELFTEST.py` — `12491f9996bd7bada33ea742dacbb186dfd037c8`

Machine-readable evidence is preserved at `evidence/raw/WAVE100_REMOTE_REGISTRY_MONOTONICITY_2026-09-17.json`.

## Synthetic timing boundary

The benchmark is **synthetic single-process protocol bookkeeping only**.

Normal Python authority-read medians over five rounds were approximately:

- depth 1: 21.541 ms CPU;
- depth 4: 23.600 ms CPU;
- depth 8: 25.649 ms CPU.

`python -O` medians were approximately 21.760 ms, 23.704 ms, and 25.425 ms respectively.

These are not physical network latency, distributed consensus, energy measurements, monolith workload results, or evidence that retained/incremental/dormant compute wins. No fresh monolith workload was read because the newest verifier exposed an authority-boundary defect that needed repair before stronger deployment claims.

## Counterexamples / truth boundary

The three witnesses are still modeled Python objects inside one process. Rolling local runtime, all three modeled remote stores, registry store, and transition store back together remains internally self-consistent. One restored stale witness cannot outvote two exact current witnesses, but there is still no independent durable maximum proving that provider itself was rolled back. Remote credentials remain symmetric test tokens. Enough current local signer compromise plus a remote quorum can still create a competing structurally valid world. Mechanical provenance/registry/quorum validity does not prove root judgment correctness, consent, evaluator legitimacy, or canonical AXM authority.

No merge, silent CANON rewrite, automatic promotion, energy claim, or retained/incremental/dormant-compute claim is made.

## Next gate

**Wave 101: real OS-process separation with durable stores.** Run the monotonic registry/record/quorum contract across at least three separate OS processes, each with its own durable store and separately held credential. Test process kill/restart, partition/reconnect, stale file-store restoration, credential rotation/recovery, two-process compromise, and whether an independent durable maximum survives provider-local rollback. Treat OS-process separation as stronger runtime evidence, not as proof of physical/provider independence.
