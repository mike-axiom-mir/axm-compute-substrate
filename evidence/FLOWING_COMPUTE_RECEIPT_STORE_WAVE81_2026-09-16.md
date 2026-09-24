# Flowing Compute Wave 81 — Content-Addressed Receipt Store + Rollback-Safe Reachability

Date: 2026-09-16  
Status: `EXPERIMENTAL SINGLE-HOST RECOVERY / GC EVIDENCE`

## Question

Wave 80 committed exact audit-receipt IDs into the atomic generation pointer. The remaining recovery gap was storage: after restart, can retained rollback checkpoints resolve every receipt body they still depend on, while garbage collection removes only receipts that are provably unreachable?

Wave 81 adds a small content-addressed receipt store and tests that boundary.

## Reusable contract

`tools/AXM_FLOWING_COMPUTE_RECEIPT_STORE.py` adds:

- append-only receipt bodies keyed by their own `receipt_sha256`;
- append-only recovery checkpoints keyed by `checkpoint_sha256`;
- explicit hashed retention manifests naming rollback checkpoints that must remain recoverable;
- restart recovery that resolves each checkpoint's exact receipt IDs and verifies key/body integrity, contract, sequence, and predecessor-state identity;
- GC candidate discovery as `stored receipts - receipts reachable from retained checkpoints`;
- fail-closed deletion for any receipt still reachable from a retained checkpoint.

Receipt presence itself grants no authority. A receipt becomes recovery-relevant only when an explicitly retained checkpoint references it.

## Real evidence reused

The primary positive case uses the exact prior Wave 79 monolith-derived audit receipt:

- contract: `axm.execution-fabric.capability-index/v0.1`
- audited artifact bytes: **11,255,808**
- artifact SHA-256: `e676fafb2f825d946c10480ccd2184ab69daf9464ae77cf5703dfe59562644da`
- audit receipt SHA-256: `fb65ba5ad5cc0f4c33a851957ccc42a4142c64a3d0815abb1a4f0886dbf4ecf2`
- exact Wave 80 G1 pointer identity: `1b93525216e04d20e4b5556f8ada44aeefcbb8168b33c9d01c723dfcc6117c58`

Wave 81 does not reread the 11.26 MB monolith artifact. It tests persistence/recovery of the already established real receipt identity.

A second later audit generation was needed to test multi-audit recovery. Instead of pretending another monolith audit existed, the probe performed a real local full-byte audit of the fetched **1,095-byte Wave 79 receipt evidence file**. That second audit is infrastructure evidence, **not a monolith workload**, and is labeled as such.

## Result

Two retained checkpoints recovered two distinct audit receipts after reopening the disk-backed store:

- real Wave 79 monolith receipt: `fb65ba5a...f4ecf2`;
- second AXM-evidence-file audit receipt: `27dc30eb...4ca1b`.

The hashed retention manifest was `53d91b18e1a12eb27bd503bcfa70b4cd74add598ceaef522c88d7c075fdee4d4`.

An additional valid receipt was deliberately stored without any retained checkpoint reference. Recovery ignored it; merely being present in the store did not grant it authority. GC identified exactly that receipt as unreachable and removed it without changing the recovered retained set.

## Negative / recovery controls

All **9/9** controls passed:

1. exact Wave 79 receipt recovered from retained checkpoint after restart;
2. second full-byte audit receipt recovered from a later controlled audited checkpoint;
3. valid but unreferenced receipt remained non-authoritative;
4. deletion of the reachable Wave 79 receipt was refused;
5. restart with the reachable Wave 79 receipt body missing failed closed;
6. wrong/tampered receipt body placed under the correct-looking key failed integrity validation;
7. retained checkpoint body tamper failed checkpoint integrity validation;
8. GC removed only the provably unreachable receipt and retained recovery stayed byte-for-byte equivalent at the report level;
9. when policy explicitly dropped the old rollback root in a test-only retention manifest, the old Wave 79 receipt became collectible — proving retention policy, not store presence, defines reachability.

That ninth control is intentionally not a recommendation to drop rollback history. It exposes the authority boundary that the next wave needs to harden.

## Cost

Over **1,000** local iterations, disk-backed recovery of **2 retained checkpoints + 2 reachable receipt bodies** had median CPU time of about **116.3 microseconds** on this host.

This does **not** include rereading the underlying audited artifacts. It measures receipt/checkpoint recovery bookkeeping only. CPU time is not joules.

## Truth boundary

- The Wave 79 receipt is real prior monolith audit evidence; Wave 81 reuses it rather than inventing another monolith audit.
- The second audit is a real full-byte read of an AXM evidence file, but it is not a monolith workload.
- The orphan artifact is synthetic control-only.
- SHA-256 provides content integrity here, not actor identity, signatures, TPM evidence, or remote attestation.
- The Wave 81 checkpoint is a receipt-recovery root and does not replace validation of the source generation pointer itself.
- Retention policy is explicit state. This wave does not decide how long rollback checkpoints should be retained.
- No canonical branch merge or automatic canon promotion occurred.

## Next gate

**Wave 82: retention evolution + crash-safe GC.** Bind every retention-manifest change to its exact predecessor, require an explicit drop receipt before any rollback root can disappear, and make mark/sweep GC commit against one exact retention generation. Then test crashes between mark, sweep, and retention-pointer movement so a receipt cannot be collected because GC observed a newer/older retention view than the one it was authorized against.
