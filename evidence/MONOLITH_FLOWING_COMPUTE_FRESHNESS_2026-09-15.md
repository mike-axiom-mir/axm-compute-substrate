# Monolith Flowing-Compute Freshness Probe — 2026-09-15

Status: `EXPERIMENTAL RUNTIME EVIDENCE`

This probe tests whether compact retained/compiled state can avoid serving stale results when its large source body changes.

Subject source: copied monolith `EXECUTION_FABRIC.json`, 39,055,991 bytes.

The test operated only on a temporary copy of that file.

## Contract tested

A compiled summary records a cheap source-generation fingerprint from filesystem metadata before and after compilation. Stable requests reuse the compiled state. If the observed source generation changes, the state recompiles before returning an answer.

## Result

- initial compile count: `1`
- stable reuse requests: `10,000`
- rebuilds after all 10,000 stable requests: `1`
- total CPU for the 10,000 generation checks + returns: `34,004,283 ns`
- measured CPU per stable request: about `3,400 ns` (~3.4 microseconds)
- deliberate semantic mutation detected: `true`
- compile count after mutation request: `2`
- mutated summary visible after rebuild: `true`
- mutation absent before source change: `true`

This demonstrates that the earlier compact-derived-state experiment does not inherently require blindly serving stale state. A very cheap freshness check can gate reuse and force rebuilding when the source generation changes.

## Important limitation

The tested fingerprint uses filesystem metadata such as device/inode/size/mtime. It is a freshness mechanism, not an adversarial integrity proof. A deliberately engineered same-size/same-mtime mutation could evade it.

For AXM's stronger direction, immutable/content-addressed source identity or an authenticated generation/version contract is preferable. The cost of whatever freshness mechanism is chosen must remain part of the compute accounting.

## Truth boundary

- temporary source copy only;
- single host;
- no direct joule measurement;
- metadata-generation check is not cryptographic content identity;
- no free-compute or physical-over-unity claim;
- production mutable state still needs a formally specified invalidation contract.

Reproducibility pack: `evidence/probes/axm_flowing_compute_probe_pack_v3.zip`

Pack SHA-256: `8626e79a59cd7f4abd5977a48ffa03ee4bce8531221ccc8219b625728bbc28a7`
