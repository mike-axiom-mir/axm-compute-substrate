# Independent adversarial verification — Wave 102 certificate-tail truncation

Status: **verifier-only, unmerged, no CANON promotion**.

Exact builder base: `46fafcb3b13e5663337c01e185a8972ebc52dda5` (`Wave 102: preserve concise quorum-global maximum evidence`).

Exact Wave 102 tool blob: `8bd23cf3db02ba90161f4a7c38f36dca3f3b2733`.
Exact Wave 102 self-test blob: `cc53bd23732acc31e8b85f0998187fba979c8a89`.

## What was challenged

Wave 102 correctly fixes verifier PR #26 while its quorum-certificate store remains intact. The adversarial question here is narrower than the already disclosed whole-world rollback: **does the remembered quorum-global maximum still protect the newer accepted epoch if only the certificate tail plus one stale witness and the mutable local current pointer are restored, while other newer evidence survives?**

## Reproducer

`verification/wave102_certificate_truncation_repro.py` uses only the committed Wave 102/Wave 101 public Python interfaces and direct modeled durable-state restoration already inside this research boundary.

1. Commit/certify authority epoch 1 normally on A/B/C.
2. Commit epoch 2, publish it to A+B only, and explicitly certify it. C remains a legitimate epoch-1 laggard.
3. Preserve current content-addressed local stores, including epoch-2 authority/checkpoint bodies.
4. Keep remote A completely intact at history `[1,2]`.
5. Restore only remote B to its earlier epoch-1 store snapshot. C is untouched and remains `[1]`.
6. Restore only the mutable local current pointer to epoch 1.
7. Starting from the current certificate store, delete exactly the newest certificate-2 record and move `head` to the still-retained certificate 1. No older certificate body is rewritten.
8. Ask unchanged Wave 102 for authority.

Expected adversarial failure if reproduced: `AUTHORITATIVE_QUORUM_2...` for epoch 1 even though remote A and newer local content-addressed bodies still preserve evidence that epoch 2 had previously crossed quorum and been certified.

## Why this matters

This does **not** falsify Wave 102's bounded claim that an intact certificate store blocks the exact PR #26 stale-quorum replay. It does narrow the remaining failure boundary: the global maximum is currently monotonic only as long as the single modeled certificate store retains its newest tail. A one-record tail truncation plus one stale witness is enough to erase previously certified finality while another witness still visibly retains the newer epoch.

That is a smaller failure set than rolling back all three modeled witnesses or replacing the whole modeled world. It remains within Wave 102's disclosed process-local limitation and directly motivates the next gate: the certificate maximum itself needs an independently monotonic durable boundary before process separation can be treated as stronger stale-proof evidence.

## Benchmark / claim boundary

No performance conclusion is added here. Wave 102's published timing remains synthetic single-process authority bookkeeping only. This verifier does not treat it as retained/incremental/dormant compute, energy, network, or provider evidence.

## Next adversarial gate

Before calling process-separated quorum finality durable, require the certificate maximum/head to be monotonic across restart and storage restoration, ideally with independent witnesses or an authenticated append-only checkpoint boundary. Then test: certificate-tail truncation, stale local pointer + one stale remote + one intact newer remote, crash between certificate record/head publication, stale certificate-store restore after credential rotation, one certificate witness unavailable, and conflicting recovered certificate tails.
