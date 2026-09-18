# Flowing Compute Accounting — Self-test Receipt

Status: `PASS`

Date: 2026-09-15

## Subject

- `tools/flowing-compute-accounting.js`
- `tools/flowing-compute-selftest.js`

## Environment

- Node.js: `v22.16.0`
- execution surface: local bounded command/runtime available to the reviewing ChatGPT session

## Result

`20 / 20` self-checks passed.

Observed terminal result:

```text
Flowing compute accounting self-test passed 20 checks.
```

## What the fixture proves

The synthetic fixture demonstrates that the accounting model can keep these states separate:

- setup compute: `100`
- cumulative maintenance compute: `10`
- cumulative external compute: `110`
- reclaimed/idle subset of external compute: `40`
- cumulative useful output: `140`
- total compute input: `220`
- equivalent repeat-from-zero baseline: `350`

Under the fixture's declared comparable normalized unit:

- useful output crosses setup cost at request 4;
- useful output crosses setup + maintenance at request 4;
- the persistent path becomes cheaper than the declared equivalent baseline at request 3;
- useful output still remains below total compute input.

This is intentional. The fixture demonstrates **setup amortization and baseline advantage without a free-compute or physical over-unity claim**.

## Refusal checks

The self-test also verifies that:

- setup-amortization ratios are withheld when useful output is not declared comparable to compute input;
- setup break-even is withheld under the same unit ambiguity;
- reclaimed/idle input cannot exceed total external input;
- baseline-equivalent mode refuses steps that omit baseline compute;
- reclaimed external compute is never relabeled free energy;
- output exceeding setup cost is never labeled proof of free compute.

## Truth boundary

This receipt is evidence for one synthetic deterministic accounting test only.

It does **not** establish that any real AXM workload produces a net compute gain, that the normalized units correspond to physical operations or energy, or that the Flowing Compute Hypothesis is true in the world.

The next evidence step requires a real measured workload with pinned inputs, host/runtime conditions, equivalent-output criteria, and directly observed resource costs.
