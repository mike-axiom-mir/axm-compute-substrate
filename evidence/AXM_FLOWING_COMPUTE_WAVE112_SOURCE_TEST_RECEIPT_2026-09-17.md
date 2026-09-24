# AXM Flowing Compute — Wave 112 Exact Source/Test Receipt

Date: 2026-09-17
Lane: `chatgpt/lane-001-platform-extract`
Purpose: bind the successful Wave-112 test result to exact immutable source/evidence identities without rewriting the tested source.

## Successful tested source

- exact CI-tested source commit: `1be9303bba0712869d40444f5cf1b0e878948ab7`
- implementation blob, `tools/AXM_FLOWING_COMPUTE_RECOVERABLE_TRANSITION_PROVENANCE.py`: `41e73e8f042df974b161fa9b85b128c99b1bb819`
- original self-test blob, `tools/AXM_FLOWING_COMPUTE_RECOVERABLE_TRANSITION_PROVENANCE_SELFTEST.py`: `7a48968a851c23129b6ae31ef017483407e70e8f`
- CI instrumentation wrapper blob, `tools/AXM_FLOWING_COMPUTE_RECOVERABLE_TRANSITION_PROVENANCE_CI_SELFTEST.py`: `0a1bad2b8f6f6745c8ba5b575e92587f1f7e9ba4`
- workflow blob, `.github/workflows/wave112-recoverable-transition-provenance.yml`: `3f19ace7de0477635af459758134eb2caf36b034`

## Successful test identity

- GitHub Actions run: `35218596920`
- job: `105192939604`
- conclusion: success
- unchanged Wave-111 regression: 27/27 PASS
- Wave-112 normal Python: 22/22 PASS
- Wave-112 `python -O`: 22/22 PASS
- report artifact ID: `10496246899`
- report artifact digest: `sha256:9bb6bf33f04be3ff3b0b08b963da50130f08e42c9ab36452a44dc8f345b3333a`
- synthetic structural probe in both Wave-112 reports: depths 1/4/8 all `VALID`, marker-chain linearization calls `2/2/2`

## Preserved failed harness attempt

The earlier failed CI run is evidence, not erased history:

- run: `35217553400`
- artifact ID: `10495459907`
- artifact digest: `sha256:207224560c5ef6640f3d54a431276f00e58f7bdf32e5d68f517696ce5a4a5f1b`
- Wave-111 regression: 27/27 PASS
- Wave-112 normal: 20/22; the two failures were created by the synthetic instrumentation wrapper omitting Wave-108's keyword-only `allow_missing` argument
- the successful CI wrapper changes only that instrumentation signature; it does not monkeypatch Wave-112 implementation behavior

## Written evidence identity

- evidence path: `evidence/AXM_FLOWING_COMPUTE_WAVE112_RECOVERABLE_TRANSITION_PROVENANCE_2026-09-17.md`
- evidence commit: `0d591fa8c021a35a7a53add6a02b8b6bf27f3549`
- evidence blob: `b01985afa4e8734f1ae66869148e7368674aa37b`

## Receipt boundary

This receipt is appended after the successful exact-source CI. The evidence and receipt commits do not alter the implementation, original self-test, CI wrapper, or workflow blobs listed above. They therefore must not be described as the source commit that CI tested.

No merge, auto-merge, CANON promotion, physical-finality claim, provider-independence claim, energy claim, or general retained/incremental/dormant-compute win is implied by this receipt.
