# Wave 99 exact-source addendum

Date: 2026-09-17  
Lane: `chatgpt/lane-001-platform-extract`  
Status: append-only correction; no prior evidence rewritten.

The first Wave 99 machine-readable evidence file recorded the protocol tool identity from the local pre-upload bytes. The GitHub Contents write omitted one final trailing newline from that protocol file, so the committed protocol blob is `c4c0a6bcabeafcf19502303857d1fc4da6fe8ea5` (20,495 bytes, SHA-256 `ba58a3bd7207c5e48a43043ba1a85564be7e1000b04a41b86a2db280621fe00d`) rather than the pre-upload blob recorded in that first report. The self-test blob remained exact at `6efa792265c4fd3b54e7cfb192f5e1440402010a`.

Nothing was silently rewritten. The original report remains preserved as historical evidence of the upload-byte mismatch. I then changed the local protocol copy to the exact committed GitHub bytes and reran the same adversarial suite twice. Both the normal interpreter and `python -O` passed **41/41 controls** against the exact committed protocol/self-test byte identities.

Exact-byte synthetic CPU medians, five rounds each: normal Python depth 1 `14.168 ms`, depth 4 `15.879 ms`, depth 8 `15.012 ms`; `python -O` depth 1 `14.214 ms`, depth 4 `14.847 ms`, depth 8 `19.282 ms`. These remain synthetic single-process bookkeeping timings only; the depth-8 optimized outlier is preserved rather than smoothed away.

The research result and truth boundary are unchanged: Wave 99 repairs verifier PR #23's duplicate-service alias and mutable-head rewind attacks, adds registry-bound 2-of-3 modeled quorum, and demonstrates predecessor-bound credential rotation plus append-only poisoned-witness recovery. It still does **not** demonstrate physical failure-domain independence. Whole-modeled-domain rollback and signer-plus-quorum compromise remain counterexamples.

Machine-readable exact-source rerun: `evidence/raw/WAVE99_REMOTE_WITNESS_REGISTRY_QUORUM_EXACT_GITHUB_2026-09-17.json`.
