# Wave 82 adversarial verification — recovery purge binding gap

Date: 2026-09-16  
Verifier base: builder head `d3bbccd51cebb250221e501cd64db130d483479f`  
Status: **FAIL BOUNDARY CONFIRMED IN PUBLISHED REUSABLE MODEL**  
Scope: independent verification evidence only; no builder files changed; no merge/canon authority claimed.

## What was challenged

Wave 82 claims predecessor-bound retention state plus crash-safe garbage collection. The published evidence is careful that its ~150.489 us benchmark is only GC mark planning over two receipt-key envelopes and excludes receipt-body revalidation and underlying artifact rereads. This verification therefore focused on the stronger semantic question: **does the reusable recovery/validation contract preserve the exact receipts that current retention says remain reachable?**

The reproducer imports `tools/AXM_FLOWING_COMPUTE_RETENTION_GC_MODEL.py` unchanged and reconstructs the exact published Wave 82 G1 identity:

- G1 retention: `f9cb087d701268b4f7eb660161776f37d46d312f0e46c1fbc883c46a452d3eb5`
- dropped/unreachable Wave 79 receipt A: `fb65ba5ad5cc0f4c33a851957ccc42a4142c64a3d0815abb1a4f0886dbf4ecf2`
- still-retained/reachable Wave 81 receipt B: `27dc30ebd1172695c8873cb919efc59de9adde8a546533b64f6b7d6199c4ca1b`

## Primary failure — recovery can authorize purge of a reachable receipt

The reusable model's `recovery_action(staged_receipts, sweep_commit, current)` treats a sweep as committed when only these two values match current retention:

- `retention_sha256`
- `retention_sequence`

It does **not** validate a sweep schema/hash, bind the sweep to a GC mark, bind it to the mark's exact candidates/inventory, or verify that the supplied `staged_receipts` remain unreachable.

The model's own self-test uses the minimal sweep object:

```python
sweep = {
    'retention_sha256': rid(g1),
    'retention_sequence': seq(g1),
}
```

Baseline behaves as intended:

```text
recovery_action([A], sweep, g1) -> PURGE A
```

But substituting the still-reachable receipt B also succeeds:

```text
reachable(g1) == {B}
recovery_action([B], sweep, g1) -> PURGE B
```

No hash was broken and the current retention generation was not changed. The recovery interface simply does not prove that the staged receipt is one the exact committed mark authorized for deletion.

### Interpretation

Wave 82 establishes a useful **current-retention freshness check**, but in the reusable model `exact current retention generation` is necessary and **not sufficient** to authorize the identity of the receipt being purged.

That narrows the crash-safe GC claim: crash recovery is safe only if an external harness already guarantees that the staged receipt set is exactly the validated mark candidate set and cannot be substituted before recovery. That guarantee is not present in the reusable model itself.

## Secondary boundary — retention reload does not resolve drop-receipt references

`evolve()` validates a real drop receipt before constructing a retention generation. However `validate_ret()` on reload checks only that the **keys** in `drop_receipts` exactly equal the removed rollback roots. It does not resolve or validate the referenced receipt values.

Counterexample:

1. take exact G1;
2. replace the C1 drop-receipt SHA with `0000...0000`;
3. recompute the outer `retention_sha256`;
4. call `validate_ret(tampered_g1, wave81)`.

Result: **accepted**.

Wave 82's report says its measured restart harness rejected a missing referenced drop receipt, so this finding is intentionally bounded: the one-off harness evidently performs an additional store-resolution check. The published **reusable validator alone does not** re-establish that property.

## Secondary boundary — GC mark validator does not rederive its claimed sets

`validate_mark()` correctly checks the mark hash, current retention identity/sequence, candidate/reachable intersection, and (by default) exact inventory hash. It does not check:

- mark schema;
- `reachable_receipts == reachable(current)`;
- `candidates == inventory - reachable(current)`.

A rehashed mark with the wrong schema, an empty `reachable_receipts` list, and an empty candidate list validates under the exact G1/inventory even though actual reachability contains B and the exact candidate set contains A.

This particular gap alone tends toward leaked garbage rather than unsafe deletion because a listed candidate that is currently reachable is still rejected. It nevertheless means validator success does not prove the mark is the exact derived mark that `make_mark()` would construct.

## What survived

The following bounded parts did survive inspection/reproduction:

- the published Wave 81 identity and exact Wave 82 G1 identity reconstruct deterministically;
- retention sequence/predecessor gaps are checked;
- silent root removal without a drop-receipt **key** is rejected;
- stale marks are rejected after the current retention pointer changes;
- exact-inventory marks reject inventory changes before stage;
- `can_select()` refuses a retention state whose reachable receipt evidence is absent;
- the benchmark truth boundary is appropriately narrow: it does not include receipt-body validation, artifact rereads, joules, or a new monolith audit.

## Truth boundary

- This verification tests the published reusable Wave 82 model at builder head `d3bbccd51cebb250221e501cd64db130d483479f`.
- It does not claim SHA-256 is broken.
- It does not reread or independently reaudit the 11,255,808-byte monolith-derived artifact.
- The one-off filesystem probe may contain additional harness checks not exposed by the reusable model; where that distinction matters it is stated explicitly.
- No canonical branch merge, automatic promotion, or authority claim is made.

## Next adversarial gate

Before Wave 83's authorization/CAS layer can make GC authority meaningful, bind recovery to an **exact validated sweep object** containing at minimum the committed mark SHA, exact candidate identities, exact inventory identity, and retention identity/sequence. Recovery must revalidate the sweep/mark and re-check candidate unreachability before irreversible purge.

Then attack:

1. staged-receipt substitution after mark but before crash;
2. valid mark + forged/minimal sweep;
3. stale sweep under unchanged retention but changed staged set;
4. missing or substituted drop-receipt bodies after restart;
5. concurrent add/drop writers under the planned Wave 83 CAS contract.

Reproducer: `verification/wave82_gc_recovery_boundary_repro.py`.
