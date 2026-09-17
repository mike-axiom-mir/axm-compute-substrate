# Independent adversarial verification — Wave 106

Status: **verifier lane; draft/unmerged; no CANON promotion**

Builder head inspected: `eb8ac4d23a3399af82885afc435dae6de0aa28b6`  
Wave-106 exact tested source: `652f3da1acd88e02f085cf1ace92c6bfb412e065`  
Wave-106 tool blob: `daaa9e33b3418138972701bac1cecca928378a17`  
Wave-106 self-test blob: `3da3ebd06bed5b756ca58d5b77ac9eb5de12bbc6`

## What survives

Wave 106 materially closes verifier PR #30 when the retained authority store is internally complete. After a real accepted epoch, deleting only the Wave-106 lineage store is detected because `_retained_authority_evidence()` resolves the retained authority link; saved-genesis re-entry remains blocked. The builder also keeps the truth boundary narrow: this wave makes no retained/incremental/dormant-compute, energy, network, OS-process, device, provider, or new performance claim.

## New counterexample

The bootstrap-closing fallback is fail-open under partial evidence loss.

`_retained_authority_evidence()` iterates `st["L"]`, calls `resolve()`, and catches **all** resolution failures with `continue`. An unresolved retained authority link is therefore treated the same as no retained authority history.

The exact-API reproducer:

1. adopts a normal Wave-106 root;
2. advances normally to accepted authority epoch 1, with quorum certificate/witness evidence;
3. confirms the accepted world is authoritative;
4. confirms deleting only `W106_BOOTSTRAP_LINEAGE` correctly returns `HOLD_BOOTSTRAP_LINEAGE_MISSING_WITH_AUTHORITY_HISTORY`;
5. starts from the same accepted retained state and deletes only:
   - the Wave-106 lineage store; and
   - the one signer-use body referenced by the retained epoch-1 authority link;
6. leaves the sealed authority-link body and signed checkpoint body retained in `st`;
7. supplies the same saved-genesis runtime/remotes used by the prior re-entry attack, plus a fresh empty certificate store, fresh legitimate certificate-witness domain, and fresh binding store;
8. calls unchanged Wave-106 `adopt_genesis()` and `authority()`.

Because the missing signer-use body makes `resolve()` fail, the retained-history scanner silently drops the still-retained authority link. Bootstrap is treated as open again. The fresh replacement root is accepted and the stale world becomes `AUTHORITATIVE_GENESIS_MODELED`.

Expected verifier verdict:

`FAIL_PARTIAL_EVIDENCE_LOSS_REOPENS_BOOTSTRAP`

## Why this is narrower than the disclosed Wave-106 limitation

This does **not** restore or substitute the entire retained authority state to a pre-adoption image. The retained state still contains the previously accepted sealed authority-link body and signed checkpoint body. The attack removes the new lineage memory plus one auxiliary referenced signer-use body. The original accepted world and its external evidence can remain intact elsewhere.

No old certificate-witness credential is stolen, no hash collision is used, and no builder file is rewritten. The fresh stale branch uses a new legitimate certificate-witness domain only after the fail-open retained-history scan has forgotten the earlier accepted authority.

## Root cause

Corrupt/missing referenced authority evidence is being classified as **absence** rather than **proof of possible prior authority**. For bootstrap closure, that direction is unsafe: once any retained authority-link identity exists, inability to prove it resolves should fail closed rather than erase its historical significance.

## Next adversarial gate

Before OS-process separation, make bootstrap closure monotonic under partial local evidence loss:

- if `st["L"]` contains any authority-link key/body that cannot be fully resolved, return a bootstrap/history corruption HOLD rather than omitting it;
- consider all authority stores (`L`, `C`, `U`, signer-key bodies and binding/certificate lineage) when deciding whether the substrate has ever left bootstrap;
- distinguish `no history` from `history exists but is incomplete/corrupt` mechanically;
- then attack deletion of one checkpoint body, one signer-use body, one signer-key body, one predecessor authority body, one binding body, partial store truncation, and restart from saved genesis views.

Only after these partial-loss cases fail closed should process-level persistence be treated as a stronger finality experiment.
