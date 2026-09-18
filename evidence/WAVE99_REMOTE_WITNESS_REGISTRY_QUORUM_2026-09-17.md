# Wave 99 — registry-bound three-witness quorum

Date: 2026-09-17  
Lane: `chatgpt/lane-001-platform-extract`  
Status: experimental evidence only; no merge or CANON promotion.

## Exact predecessor / verifier identity

Wave 99 continues from Wave 98 builder head `56bb92218f9af62aceacee1ee625755b8ef54789`, exact Wave 98 tool blob `bc4347a75f04f6d9ff97e58128d2f5f0a16c85a1`, and exact Wave 98 report blob `397e1023f1ec1e233e3b0a6943d4b6e62854512b`. It directly addresses independent verifier PR #23 at head `ac4929e3404a14b6fe6d902f4c923b16a31427b5`, evidence blob `5933c0c720507e4a760b2166eedfe07973942632`.

The verifier's two reproduced failures were: one real remote service could be counted twice through caller-map aliasing, and mutable remote `head` fields could be rewound while newer immutable records remained in the store. Both could restore a false authoritative verdict in Wave 98 without forging record bodies.

## What changed

Wave 99 adds a reusable protocol tool plus a separate adversarial self-test. The protocol tool adds a content-addressed remote-witness registry with exact `slot -> service_id -> credential_hash -> failure_domain_id` bindings and uniqueness checks across all three identities. The current registry SHA is folded into the state hash signed by the existing Wave 98 checkpoint signers, so an unsigned runtime registry swap no longer retargets committed authority.

Remote verification now validates the complete retained record store, not only the chain reachable from a mutable selected head. Sequence numbers must be unique and contiguous, every predecessor must match, and `head` must equal the maximal committed record. The exact PR #23 duplicate-service alias and old-head-with-newer-records attacks therefore fail closed.

The modeled witness set is now three services with a bounded 2-of-3 rule anchored to the exact local authority: the witnesses do not vote for a competing state. One offline witness or one stale/poisoned witness can be tolerated if two distinct registered witnesses match the exact current local authority; one offline plus one non-current witness loses quorum and HOLDs.

A predecessor-linked registry successor can rotate one remote credential. After the new registry identity is signed into the next local checkpoint, a poisoned witness can append an explicit recovery record using the new credential while preserving the poisoned record in append-only history. The retired token is then rejected.

## Verification

Two independent local executions passed **41/41 controls** each, including one under `python -O`. Positive and negative controls cover registry identity uniqueness, partial local commit, 2-of-3 and 3-of-3 authority, duplicate-service aliasing, service-slot swap, unsigned registry substitution, one-witness outage, reconnect/catch-up, mutable-head rewind with newer records retained, local rollback, one-witness poisoning, one-offline-plus-one-poisoned loss of quorum, wrong credentials, credential rotation, append-only poisoned-witness recovery, retired-token rejection, whole-modeled-domain rollback, and the inherited current-signer compromise counterexample.

Synthetic single-process authority-read medians (5 rounds each) were:

- normal Python: depth 1 = 13.981 ms, depth 4 = 14.715 ms, depth 8 = 14.958 ms CPU;
- `python -O`: depth 1 = 13.956 ms, depth 4 = 15.831 ms, depth 8 = 15.215 ms CPU.

These timings are **synthetic protocol bookkeeping only**. They are not physical network latency, distributed consensus, energy use, monolith compute-efficiency, or evidence that retained/incremental/dormant compute wins.

## Counterexamples / truth boundary

All three witnesses are still Python objects in one process. Distinct service, credential, and failure-domain identities are now mechanically enforced, but physical independence is not demonstrated. Rolling the local runtime, all three modeled remote stores, and registry state back together still produces a self-consistent old world. The remote append credentials are symmetric test access-control tokens rather than public-key remote attestations. Compromise of enough current local signer material plus a remote quorum can still create a competing structurally valid world. None of this proves root judgment correctness, consent, evaluator legitimacy, or canonical AXM authority.

No fresh monolith workload was read in this wave because the newest independent verifier exposed authority-boundary defects that needed repair before stronger failure-domain claims. No merge, CANON rewrite, automatic promotion, energy claim, or retained/incremental/dormant-compute claim is made.

## Next gate

**Wave 100: real failure-domain deployment.** Run this exact registry/record/quorum contract across three genuinely separate processes/providers or devices with independently held credentials. Test real partition/reconnect, credential rotation, poisoned-witness recovery, stale-store restoration, two-provider compromise, and durable anti-rollback of each provider's maximal head. Keep whole-domain rollback and signer-compromise counterexamples visible; do not equate modeled identity fields with physical independence.
