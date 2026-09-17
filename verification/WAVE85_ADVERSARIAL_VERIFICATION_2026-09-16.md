# Independent Adversarial Verification — Wave 85

Date: 2026-09-16  
Builder head examined: `1a88cdafff7fee0134fdec903a9ee0b74b2562d8`  
Verifier status: `SEPARATE DRAFT / NO MERGE OR CANON CLAIM`

## What survives

Wave 85's narrow tested mechanism remains meaningful:

- a surviving separate anchor can detect the tested rewind of the primary pointer/object store;
- the write-ahead order (pointer object -> anchor -> current pointer) gives a bounded recoverable post-anchor/pre-pointer crash state;
- intentional retention rollback can advance the commit epoch instead of recreating ordinary ABA;
- the report correctly preserves the hard limitation that rolling the primary and software anchor failure domains back together leaves no newer surviving fact;
- the published cost is clearly infrastructure bookkeeping, not a new compute-efficiency, joule, or monolith-workload result.

This verifier did not find a SHA-256 break and does not claim actor authentication, trusted hardware monotonicity, or distributed consensus.

## Primary counterexample — anchor chain can certify a disconnected pointer history

The reusable `AnchorLedger` chains **anchor records** by `predecessor_anchor_sha256`, but it never requires the newly anchored pointer's `predecessor_pointer_sha256` to equal the prior anchor's `pointer_sha256`.

The equal-epoch `recovery_status()` path then validates only the **latest** anchor/current-pointer binding. `w84.read_current()` separately validates the current pointer's predecessor chain, but that chain can begin from a different epoch-0 pointer than the one preserved by anchor epoch 0.

The exact-API reproducer preserves the same anchor directory and does not rewrite/delete anchor files:

1. Wave 85 initializes original `A@0` and anchors it.
2. The published Wave 84 API initializes the primary onto a different epoch-0 pointer `B@0` using the exact prior Wave 83 DROP retention identity.
3. At this point Wave 85 correctly reports `DIVERGENCE`.
4. The published Wave 84 CAS advances that alternate primary branch to `C@1`.
5. Public `Wave85.AnchorLedger.append(C@1, ...)` accepts it because its epoch is 1 and the ledger has one prior anchor.
6. Anchor 1 correctly names anchor 0 as its **anchor predecessor**, but `C@1.predecessor_pointer_sha256 == B@0`, while anchor 0's pointer is `A@0`.
7. `recovery_status()` now returns `CONSISTENT`.

So the latest state is internally hash-valid and the latest anchor exactly binds the current pointer, yet the anchor history and pointer history disagree about the epoch-0 predecessor.

This is not the already-preserved "roll every failure domain back together" limitation. The original separate anchor ledger survives unchanged; the gap is that a later public append can launder a disconnected primary branch into a state labeled `CONSISTENT` because cross-chain continuity is not validated.

### Root cause

`AnchorLedger.records()` enforces:

- contiguous anchor epochs;
- exact anchor-file naming;
- anchor content hash integrity;
- `anchor[i].predecessor_anchor_sha256 == anchor[i-1].anchor_sha256`.

It does **not** enforce:

- `anchor[i].pointer_predecessor_sha256 == anchor[i-1].pointer_sha256`.

`AnchorLedger.append()` similarly checks only that `pointer.commit_epoch == len(records)` before creating the next anchor.

## Secondary boundary — rejected initialize mutates primary first

Wave 85 `initialize()` calls Wave 84 `initialize()` **before** checking whether the anchor ledger is empty.

Exact-API sequence:

1. create a valid Wave 85 history at epoch 1;
2. call Wave 85 `initialize()` again on the same paths;
3. Wave 84 initialization rewrites the primary current pointer to epoch 0;
4. Wave 85 then sees the non-empty anchor ledger and raises `anchor ledger must be empty`;
5. the rejected operation has already changed primary state.

The surviving anchor catches this and reports the existing epoch-1 commit as pending/recoverable, so this is **fail-after-mutation / denial-of-service risk**, not silent accepted rewind. It nevertheless means initialization rejection is not side-effect-free and should be preflighted before primary mutation.

## Bounded verdict

**Survives:** Wave 85 demonstrates bounded detection of the specific tested primary-store rewind when a newer separate anchor fact survives and the system stays on the intended anchored commit path.

**Does not yet survive as a stronger claim:** the current reusable validator does not prove that every anchor epoch and every primary pointer epoch describe one continuous shared history from the same genesis.

## Next adversarial gate

Before or as part of multi-witness Wave 86:

1. require every non-genesis anchor to satisfy `pointer_predecessor_sha256 == prior_anchor.pointer_sha256`;
2. revalidate that cross-chain invariant across the whole ledger on every load/recovery, not only during construction;
3. make initialization creation-exclusive and check anchor state **before** mutating the primary;
4. pin/identify the intended witness set so a fresh empty anchor directory cannot silently become a replacement trust history;
5. then test witness disagreement, one stale witness, one malicious-but-hash-valid disconnected witness, missing witness records, and crash ordering across witnesses.

The next verifier should fail closed on disagreement rather than majority-vote or "newest-looking" selection unless a separate explicit authority policy is actually evidenced.

## Reproducer

`verification/wave85_anchor_history_discontinuity_repro.py`

The reproducer uses the committed Wave 84 and Wave 85 public APIs and asserts both the primary history-discontinuity case and the initialization fail-after-mutation case.
