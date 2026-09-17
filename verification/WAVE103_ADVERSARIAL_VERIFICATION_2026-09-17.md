# Independent adversarial verification — Wave 103 certificate-witness instance identity

Date: 2026-09-17  
Repository: `mike-axiom-mir/axm-compute-substrate`  
Verifier lane: `chatgpt/verifier-wave103-witness-instance-substitution`  
Builder lane: `chatgpt/lane-001-platform-extract` / PR #2  
Exact builder head: `8239c401a9d7ca1a330f76a7f537437fd141bbc6`  
Exact Wave 103 tool blob: `0a5d6f09189719d705808fe1746c2f032688fd01`  
Status: verifier-only evidence; no merge/CANON promotion

## Result

**FAIL — the three "fixed" certificate-witness identities are still caller-substitutable object slots.**

Wave 103 materially repairs verifier PR #27 when the supplied certificate-witness objects are the intended retained instances. A valid online witness that still carries certificate 2 blocks a stale local certificate-1 world, even when one other certificate witness is unavailable and a third is a legitimate laggard.

The new counterexample keeps that real newer witness completely intact and online, but replaces only the caller-supplied `witnesses["cert-a"]` map entry with a legitimate epoch-1 snapshot that has the same `witness_id == "cert-a"`. `verify_certificate_witness()` accepts the substitute because identity is only the expected slot string plus self-hashed record bodies; there is no durable witness registry, instance credential, public key, failure-domain identity, or object/instance continuity binding. `_witness_heads()` then treats the replacement as cert-a and never observes the real still-online cert-a instance that retains certificate 2.

With cert-b genuinely unavailable and cert-c legitimately still at certificate 1, the substituted cert-a + cert-c pair satisfies the Wave 103 2-of-3 certificate-witness check. The unchanged lower Wave 102/101 authority path also sees stale remote B + lagging remote C as its 2-of-3 remote quorum, so the old epoch becomes authoritative again.

Preserved verdict:

`FAIL_FIXED_CERTIFICATE_WITNESS_IDENTITY_IS_CALLER_SUBSTITUTABLE`

## Exact control and attack

The reproducer uses only the published Wave 103/Wave 102 APIs plus ordinary Python mapping substitution.

1. Build legitimate epoch 1; publish/certify it; sync all three certificate witnesses.
2. Build legitimate epoch 2; publish to remote A+B; certify it; sync certificate witnesses cert-a + cert-b only. cert-c remains a legitimate certificate-1 laggard.
3. Confirm epoch 2 is authoritative with two current certificate witnesses.
4. Restore only the local runtime/certificate view and remote B to the legitimate epoch-1 snapshots. Remote A remains at `[1,2]`; remote C remains at `[1]`.
5. Mark cert-b unavailable. Real cert-a is still online at witness sequence `[1,2]`; cert-c is online at `[1]`.
6. Confirm the honest Wave 103 mapping rejects the stale world with `HOLD_CERTIFICATE_WITNESS_MAXIMUM_AHEAD` because real cert-a still remembers certificate 2.
7. Do not modify, truncate, delete, or offline real cert-a. Replace only the supplied map entry for slot `cert-a` with the previously captured legitimate epoch-1 cert-a snapshot. It has the correct schema, `witness_id`, and valid retained hash chain.
8. Re-run unchanged Wave 103 authority. It returns `AUTHORITATIVE_QUORUM_2_OF_3_MODELED` for the stale epoch-1 world.
9. Re-verify the original cert-a object: it remains online and still retains certificate 2.

So this is narrower than Wave 103's disclosed "the only newer witness is unavailable" counterexample: the newer cert-a witness is **available and intact**, but the authority boundary does not know which physical/logical instance is the real cert-a. The caller can substitute a stale same-ID instance.

## What survives

- Wave 103 does fix PR #27's certificate-tail truncation when the supplied witness instances are trusted/stable.
- Full retained witness ledger validation catches body tamper, missing predecessors, duplicate sequences, and mismatched `witness_id` strings.
- A genuinely supplied newer witness still vetoes stale authority.
- Two matching current witnesses are still required for non-genesis authority.
- The builder is explicit that this wave does not prove OS/process/provider/storage independence, energy savings, network behavior, retained/incremental/dormant compute wins, or CANON authority.

## Why this matters before OS-process separation

Moving these objects into three OS processes without first binding witness identity can preserve the same bug in a more realistic deployment: a stale process image/store can be started under the same logical slot name and accepted as the fixed witness unless the authority contract binds the slot to a durable instance identity and authorized continuity.

The next layer should therefore not rely on `cert-a` / `cert-b` / `cert-c` strings alone. At minimum, bind each certificate-witness slot to an explicit registry entry containing a durable credential/public identity and failure-domain identity, and bind registry generation/rotation to the accepted authority history. Authority should reject same-name replacement or stale-instance restart unless an explicit evidenced recovery/reconfiguration transition authorizes it.

## Next adversarial gate

Before calling process separation a stronger finality result:

- bind slot -> durable certificate-witness identity/credential -> failure-domain identity;
- require exact registered witness set/identity on every authority read;
- make restart/recovery prove continuity from the registered witness's retained maximum rather than accepting a same-name stale clone;
- define and test credential rotation/replacement as an explicit authority transition;
- then attack stale process images, cloned disks, same-ID process replacement, credential rollback, one witness outage + one stale clone, two-process restore, registry rollback, and reconnect recovery.

The process-separated test should preserve the real newer witness during these attacks and prove that a stale same-ID process cannot silently stand in for it.
