# Independent Verifier — Flowing Compute Wave 78 Freshness Boundary

Date: 2026-09-16  
Status: `ADVERSARIAL VERIFICATION — BOUNDED CLAIM SURVIVES; AUTHENTICITY / REFERENTIAL GAPS FOUND`

## Target

This verifier challenged the Wave 76–77 verification-freshness and atomic freshness-bound generation claims on the current experimental lane. It did not alter the primary builder lane.

Primary target code:

- `tools/AXM_FLOWING_COMPUTE_VERIFICATION_FRESHNESS.py`
- `tools/AXM_FLOWING_COMPUTE_FRESHNESS_BOUND_GENERATION.py`

Reproducer:

- `verification/VERIFY_FRESHNESS_BOUNDARY_WAVE78.py`

## What survived

Two narrow controls reproduced correctly:

1. A valid carried-reuse freshness state at sequence 1 validates inside a sequence-1 generation pointer.
2. Changing nested freshness data while recomputing only the outer pointer hash is rejected by the unchanged nested `state_sha256`.
3. Recomputing the pointer sequence to 2 while the nested freshness state remains at sequence 1 is rejected.

So the current format does provide **self-consistency checking against accidental or partial mutation** and enforces equality between pointer sequence and every included freshness state's `current_sequence`.

## Counterexamples found

### 1. Inner + outer rehash forgery is accepted

The verifier changed the nested freshness claim from carried reuse to a zero-age / freshly audited-looking state, recomputed the nested `state_sha256`, then recomputed the outer `pointer_sha256`.

Current validator result: **ACCEPTED**.

This means the hashes are integrity checks, not authentication or authority. A writer able to rewrite the state can also rewrite both hashes. The Wave 77 tamper control therefore proves detection of partial tampering, not resistance to an authorized/compromised/buggy writer that recomputes hashes.

### 2. Audit freshness can reset without an audit receipt

`AXM_FLOWING_COMPUTE_VERIFICATION_FRESHNESS.advance(... mode="audited_reuse")` resets `last_strong_audit_sequence` and carried age based only on the mode string plus unchanged artifact/proof identities. It does not require an audited-reuse receipt, reread byte count, artifact path, or evidence produced by `AXM_FLOWING_COMPUTE_REUSE_PROOF.audited_validate`.

The resulting freshness state and generation pointer validate: **ACCEPTED**.

So the current freshness layer records a caller assertion that an audit happened; it does not independently prove that the strong audit occurred.

### 3. Generation identity is not referentially validated

A pointer whose `generation_sha256` was replaced with `not-a-generation-object`, followed by recomputing `pointer_sha256`, validates: **ACCEPTED**.

The pointer binds bytes to a supplied generation identifier but does not validate SHA-256 shape, object existence, or correspondence between that generation object and the claimed sequence/freshness set.

### 4. Required freshness contract set is not bound

A sequence-999 pointer with `freshness={}` and arbitrary generation identity validates: **ACCEPTED**.

Therefore the pointer does not currently prove that every reused contract requiring freshness evidence is present. Contract-set completeness must come from a higher-level plan/receipt, but that relationship is not bound in this pointer format.

## Interpretation

The strongest safe statement is:

> Wave 77 atomically stores one pointer object containing a generation identifier and included freshness states, and it detects partial corruption plus sequence mismatch inside that object.

The current evidence does **not yet** establish:

- authenticated authority over freshness claims;
- proof that an `audited_reuse` transition actually executed a byte audit;
- existence/validity of the referenced generation object;
- completeness of the freshness contract set relative to the generation plan.

This is a boundary correction, not a rejection of the Flowing Compute direction. The accounting/freshness concept remains useful; the proof chain is simply one layer short of the stronger interpretation.

## Next adversarial gate

Bind the freshness transition to evidence that cannot be supplied by a bare mode string:

1. require an execution/audit receipt identity for `audited_reuse` and validate that receipt against the reuse proof + artifact identity;
2. bind the freshness pointer to the generation/plan receipt that defines the exact required contract set;
3. validate the referenced generation object exists and hashes to `generation_sha256` before pointer acceptance;
4. explicitly state the threat model: content hashes provide integrity, not writer authenticity. If unauthorized-writer resistance is required, add an authority-controlled signature/MAC or append-only trusted root rather than treating recomputable hashes as authority.

No merge or canon promotion was performed.
