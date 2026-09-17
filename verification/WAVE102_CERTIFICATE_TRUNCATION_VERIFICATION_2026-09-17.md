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

## Reproduced result

GitHub Actions run `35173730345`, normal Python job `105050726148`, passed the unchanged Wave 102 self-test **33/33** and then reproduced the counterexample against the same code. The exact output included:

- epoch 2: `COMMITTED`, A `APPENDED`, B `APPENDED`, certificate `CERTIFIED`, authority `AUTHORITATIVE_QUORUM_2_OF_3_MODELED`;
- after the attack: remote A epochs `[1,2]`, restored B `[1]`, untouched lagging C `[1]`;
- newer local authority/checkpoint bodies both still retained;
- certificate 1 retained, only certificate 2 tail deleted, resulting certificate maximum epoch `1`;
- unchanged Wave 102 returned `AUTHORITATIVE_QUORUM_2_OF_3_MODELED` for the old world;
- verifier verdict: `FAIL_GLOBAL_MAXIMUM_CAN_BE_REWOUND_BY_CERTIFICATE_TAIL_TRUNCATION_PLUS_ONE_STALE_WITNESS`.

The optimized `python -O` matrix job was still queued when this evidence note was updated, so no optimized result is claimed here.

## Why this matters

This does **not** falsify Wave 102's bounded claim that an intact certificate store blocks the exact PR #26 stale-quorum replay. It does narrow the remaining failure boundary: the global maximum is currently monotonic only as long as the single modeled certificate store retains its newest tail. A one-record tail truncation plus one stale witness is enough to erase previously certified finality while another witness still visibly retains the newer epoch.

That is a smaller failure set than rolling back all three modeled witnesses or replacing the whole modeled world. It remains within Wave 102's disclosed process-local limitation and directly motivates the next gate: the certificate maximum itself needs an independently monotonic durable boundary before process separation can be treated as stronger stale-proof evidence.

## Benchmark / claim boundary

No performance conclusion is added here. The unchanged self-test's one-round synthetic authority read rose from about `82.1 ms` at retained depth 1 to `88.7 ms` at depth 4 and `91.9 ms` at depth 8 on this runner. That is only a small depth-sensitivity signal, not a stable complexity estimate. Wave 102's published timing remains synthetic single-process authority bookkeeping only; this verifier does not treat it as retained/incremental/dormant compute, energy, network, or provider evidence.

## Next adversarial gate

Before calling process-separated quorum finality durable, require the certificate maximum/head to be monotonic across restart and storage restoration, ideally with independent witnesses or an authenticated append-only checkpoint boundary. Then test: certificate-tail truncation, stale local pointer + one stale remote + one intact newer remote, crash between certificate record/head publication, stale certificate-store restore after credential rotation, one certificate witness unavailable, and conflicting recovered certificate tails.
