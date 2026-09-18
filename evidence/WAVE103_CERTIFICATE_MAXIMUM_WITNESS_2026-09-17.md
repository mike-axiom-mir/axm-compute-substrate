# Wave 103 — replicated certificate-maximum witnesses

Date: 2026-09-17
Lane: `chatgpt/lane-001-platform-extract` / PR #2
Status: experimental evidence only; no merge or CANON promotion

## Why this wave changed direction

The planned next step after Wave 102 was OS-process separation. Independent verifier PR #27 found a narrower protocol rollback first, so this wave repairs that before making stronger deployment claims.

Exact incoming identity:

- Wave 102 builder head: `46fafcb3b13e5663337c01e185a8972ebc52dda5`
- Wave 102 tool blob: `8bd23cf3db02ba90161f4a7c38f36dca3f3b2733`
- Wave 102 self-test blob: `cc53bd23732acc31e8b85f0998187fba979c8a89`
- verifier PR: #27
- verifier head: `10eb40d2ccde3a8af34f19c75ab069e38e4b9048`
- verifier evidence blob: `c05b1802e0aeebaf69ac2e553aff28e301b74e68`
- verifier repro blob: `f0d868817bdb55c0343c2b422923e7ebd4457d2d`

Verifier #27 showed that Wave 102 could certify epoch 2 on remote A+B, leave remote C legitimately at epoch 1, then regain old epoch-1 authority by restoring only remote B, restoring the local current pointer, and truncating the certificate store from certificate 2 back to certificate 1. Remote A still visibly retained epoch 2 and newer local content-addressed bodies remained present.

## What changed

Wave 103 adds three fixed certificate-maximum witness ledgers: `cert-a`, `cert-b`, and `cert-c`.

Each certificate-witness row:

- embeds the exact already-issued Wave 102 quorum certificate;
- is content-addressed;
- is predecessor-linked;
- binds certificate sequence, authority epoch, authority SHA, checkpoint SHA, and registry SHA;
- has no trusted mutable `head`; the retained maximum is derived from the complete record set.

A non-genesis world now needs at least two online certificate witnesses matching the exact current certificate. More importantly, any valid online certificate witness that retains a newer accepted certificate blocks an older local certificate maximum. This differs intentionally from the earlier remote-witness rule: a remote witness can merely be an ahead scout, but a certificate-witness row means an actual quorum certificate already existed.

Authority reads do not repair state. A separate explicit `reconstruct_certificate_store(...)` helper can produce a candidate certificate store only from two matching certificate-witness maxima, leaving installation/recovery as an explicit action.

Reusable source identity for this wave:

- tool blob: `0a5d6f09189719d705808fe1746c2f032688fd01`
- self-test blob: `6bf8df3d03dd189cfe700ac0f8fbf862593dd7c9`
- CI workflow blob: `8bb8825dd1db3120626b9a8dc244b947d97f5278`

## Verification

GitHub Actions run `35175964236`, job `105057618975`, completed successfully on the exact committed source. It ran:

1. the unchanged Wave 102 regression;
2. the Wave 103 self-test in normal Python;
3. the same Wave 103 self-test under `python -O`;
4. artifact upload of the machine-readable report.

The Wave 103 report passed **40/40 controls**. Artifact `10478910122` has digest `sha256:ad29b9954588d00377b5e2649db0dea6722dc5c0c7d63896a6bd3ac46341631f`.

The exact verifier #27 world was reproduced first against unchanged Wave 102:

- Wave 102 result: `AUTHORITATIVE_QUORUM_2_OF_3_MODELED`
- attacked local certificate maximum: epoch 1
- remote A epochs: `[1, 2]`
- remote B epochs: `[1]`
- remote C epochs: `[1]`

With the Wave 103 certificate witnesses still retaining epoch 2, the same attacked world returns:

- `HOLD_CERTIFICATE_WITNESS_MAXIMUM_AHEAD`

Additional controls cover one offline certificate witness, one stale certificate witness, online tamper, missing predecessor, identity aliasing, explicit certificate-store reconstruction, partial certificate-witness fanout, duplicate sequence, single witness tail truncation, and preserved rollback counterexamples.

## What still fails / remains unproven

This does **not** establish physical, provider, process, or durable-storage independence. All three certificate witnesses are still Python objects in one process.

Two counterexamples are intentionally preserved:

1. Rolling the local state, certificate store, remote stores, and all three certificate-witness ledgers back together can still recreate an internally valid old world.
2. If the *only* certificate witness that remembers a newer accepted certificate is unavailable while the other two have both been restored to a valid stale state, that newer maximum is unobservable and the stale model can become authoritative again.

Hashes protect retained-body integrity and lineage only. They do not prove remote identity, independent durability, moral/root correctness, consent, evaluator legitimacy, or CANON authority. Underlying quorum/signing compromise also remains outside this repair.

No fresh AXM/monolith workload was used in this wave because the independent verifier exposed a narrower correctness defect that had to be repaired first. No synthetic scaling or performance result is claimed here, and there is no energy, network, retained-compute, incremental-compute, or dormant-compute win claim.

## Next gate

Wave 104 should move the repaired authority/certificate/certificate-witness contract into at least three real OS processes with separate durable stores and separately held credentials. Test kill/restart, stale-disk restore, certificate-tail truncation, crashes between certificate creation and witness fanout, partition/reconnect, one witness unavailable, conflicting recovered tails, credential rotation, and process-local rollback of the durable maximum.

The unavailable-only-newer-witness counterexample must stay visible: process separation alone does not make storage monotonic and does not prove physical/provider independence.
