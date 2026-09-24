# Flowing Compute Wave 44 — One-Use Validated Transition Handoff

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST REAL-MONOLITH EVIDENCE`

## Question

Wave 43 spent roughly half its transaction CPU reparsing/reapplying the state just computed by the transition. Can the transition hand its exact parsed before/after state and changed-block sets forward once, while preserving an explicit full-difference proof contract?

## Handoff contract

`ValidatedTransitionHandoff` is one-use. It carries the validated parsed base state, exact target state, full target native semantic identity, exact edge/local/signature block-difference sets, and transition/delta identity.

The overlay/proof builder consumes it once. It compares every base->target block to derive the exact difference sets, requires the overlay to contain exactly those sets and exact target bytes, and binds the overlay target to the semantic identity already computed over the full target state.

It does not reparse both full packed artifacts and then reapply the overlay merely to rediscover the same target semantic hash. Full later revalidation remains possible.

## Creation CPU

11-trial medians before durable-write accounting:

- 58 / 127: ~9.29 ms;
- 127 / 127: ~12.29 ms.

Wave-43 duplicate-proof path was ~22.0 / 25.7 ms respectively.

## Durable benchmark — two independent runs

9 alternating-order trials per run/case.

### Run 1
58 / 127: cold 48.68 ms CPU; handoff-flow 10.17 ms; **79.11% less / 4.79x**; bytes 261,933 -> 10,074 (**96.15% fewer**).

127 / 127: cold 52.73 ms; flow 13.53 ms; **74.34% less / 3.90x**; bytes 261,927 -> 24,427 (**90.67% fewer**).

### Independent run 2
58 / 127: cold 50.98 ms; flow 10.81 ms; **78.80% less / 4.72x**.

127 / 127: cold 50.86 ms; flow 12.94 ms; **74.56% less / 3.93x**.

## Why this is not "skip validation"

The removed work was duplicate reconstruction of evidence already available in the same transaction. The handoff still checks all block differences, target block contents, delta identity, source identity, and full target semantic identity. It is consumed once so stale mutable state cannot be silently reused as a later transition input.

## Truth boundary

- proof method changed from duplicate overlay reapplication to exact one-use transition-difference coverage;
- independent implementation bugs shared by transition and proof code remain possible; later full/cold equivalence checks are still valuable;
- one host/runtime/filesystem;
- CPU time is not joules;
- no compute/energy-from-nothing claim.

## Next gate

Run the validated-handoff architecture across multiple real source generations instead of one baseline->target mutation.
