# AXM Flowing Compute Wave 137 — Strict Rotation Namespace Receipt

Status: **EXPERIMENTAL / NON-CANON / unmerged**

This receipt continues from Wave 136 without rewriting predecessor evidence. It records both the failed first Wave 137 implementation and the repaired exact-source result. It does not authorize merge, auto-merge, or CANON promotion.

## Source / provenance identity

- Wave 136 evidence head inherited by this wave: `411bd123b193eca34f44bec1ff3d9d9af32247c5`
- Wave 136 exact tool blob: `47fe034330c808b48ee39f64f70b07778b533372`
- First Wave 137 candidate: `e6ac6962c6ee1e4b5e6023daa999838873644f56`
- First Wave 137 tool blob: `c12caebe367407878e70233140863f3a2c3385cb`
- Repaired exact tested Wave 137 source: `083d356f4fc7c70832d6e30a09bed01d105077ff`
- Repaired Wave 137 tool blob: `4d95b9c509485dbfb8f46e0c0ff23357e1d1402c`
- Wave 137 self-test blob: `88f5873ced1ba3fdeca397777691e1d4ec763571`
- Wave 137 workflow blob: `d12d77a92b9152cff14422173ebafe4543a57765`

Reusable implementation and verification remain in:

- `tools/AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ROTATION_NAMESPACE.py`
- `tools/AXM_FLOWING_COMPUTE_PROCESS_WITNESS_ROTATION_NAMESPACE_SELFTEST.py`
- `.github/workflows/wave137-strict-rotation-namespace.yml`

Generated JSON reports remain CI-artifact ballast rather than repository source.

## What Wave 137 changes

Wave 136 could validate a legitimate signed rotation state while unrelated artifacts still existed inside the authority-owned `response_rotation` directory. Examples include a stale future public generation or an unrelated authority-owned file. That meant the cryptographic lineage could be valid while the surrounding durable namespace was not an exact representation of that lineage.

Wave 137 adds strict namespace provenance around the existing Wave 136 transaction machinery. Before rotation and at stable validation it checks that artifacts are regular authority-owned mode-0600 files and belong to the exact known bootstrap/lineage/state/generation namespace or to a narrowly recognized active recovery target. Stable state rejects stale future generations, unrelated files, foreign-owned lookalike recovery files, and unrelated recovery stages. Rejected artifacts are deliberately retained for inspection; Wave 137 does not silently delete, adopt, or rewrite them.

Known legitimate Wave 134 staging (`.axm-stage-...`), Wave 135/136 deterministic staging (`.axm-w135-stage-...`), and legacy exact temp naming are recognized only through their base target and transaction state. This preserves crash recovery without treating arbitrary files as authorized.

## Preserved failed first implementation

The first candidate `e6ac6962c6ee1e4b5e6023daa999838873644f56` failed in GitHub Actions run `35341670954`, job `105588741984`.

Unchanged Wave 136 regression had already passed, but the new Wave 137 clean rotation hit:

`RuntimeError: wave137-unexpected-rotation-artifact:authority_lineage.jsonl.axm-w135-stage-...`

Cause: the new namespace scanner recognized Wave 134 `.axm-stage-...` and older `.tmp-...` recovery names but omitted the already-authorized Wave 135/136 deterministic `.axm-w135-stage-...` form. The failure was therefore a compatibility defect in the new scanner, not evidence that the predecessor recovery path was corrupt.

The repair commit `083d356f4fc7c70832d6e30a09bed01d105077ff` changed only recovery-name recognition to include the known Wave 135/136 marker. It did not relax ownership, mode, regular-file, stale-generation, unknown-file, or stable-state rejection rules. The failed candidate remains in history and is not rewritten as a pass.

## Green evidence

GitHub Actions run `35346057663`, job `105602789508`, completed successfully on exact source `083d356f4fc7c70832d6e30a09bed01d105077ff`.

Artifact:

- id: `10547525354`
- name: `wave137-strict-rotation-namespace`
- size: `5859` bytes
- SHA-256 digest: `f61bc47273282ba812926324b1a62d72bce5fcc1b9609e7d8251211519417242`

Regression and new-wave results:

- unchanged Wave 136: **11/11 normal + 11/11 under `python -O`**
- Wave 137: **7/7 normal + 7/7 under `python -O`**

The Wave 137 suite proves, on the tested same-host Linux/filesystem boundary:

- two clean rotations reach sequence 2 while keeping the expected durable namespace;
- a stale future generation (`public-999999.pem`) that Wave 136 tolerated is rejected and retained;
- an unrelated authority-owned file that Wave 136 tolerated is rejected and retained;
- a foreign-owned recovery lookalike is rejected before rotation and sequence does not advance;
- a known pending partial stage remains recoverable;
- a known lineage partial stage remains recoverable, including the Wave 135/136 deterministic stage form that exposed the first implementation defect;
- an unrelated authority-owned recovery stage fails closed and remains visible.

## Truth boundary

This is same-host Linux/filesystem **namespace-integrity** evidence around the rotation transaction. It does not prove:

- safety against validation-to-service path or inode substitution after the namespace check;
- resistance to an attacker already running as the authority UID;
- root/kernel resistance or user-namespace UID-alias safety;
- uniqueness of a genuinely copied current private key/authority on another namespace or host;
- whole-domain rollback resistance;
- hardware-backed non-exportable key custody, provider independence, or physical finality.

No real AXM/monolith performance workload and no synthetic scaling workload were run in Wave 137 because this was a correctness/provenance gate. Therefore Wave 137 makes **no new speed, energy, retained/incremental/dormant-compute, throughput, or scaling claim**.

## Next gate

Attack the remaining local time-of-check/time-of-use seam: validate a pending/lineage/current-key artifact and then substitute its path or inode before the consumer actually opens/uses it. The useful success condition is not merely detecting a changed path later; the consumer should bind use to the exact object/bytes that were validated or fail closed while preserving the counterexample.

After that local seam is bounded, resume the larger architectural test: copy the genuinely current authority identity, full rotation lineage, and real current private key into another Linux namespace and preferably another host, then let both authentic copies authorize different successors. If both can advance individually valid divergent chains, retain that failure: signatures prove possession, not uniqueness, and the next architecture needs an independently retained uniqueness/rotation authority rather than another local lock.
