# Conformance-kit provenance

Date: 2026-09-20

The Neutral Compute conformance kit reuses **patterns**, not domain semantics, from existing AXM repositories.

## MorphTile

Repository: `mike-axiom-mir/axm-morphtile`  
Pinned commit inspected: `4346df01ed18cd1336064f9323d7766ff4f6338a`  
Relevant source: `tools/conformance.js` (blob `da60507e30b9d8e8bc001299b6e645e24029a517`)

Reused pattern:

- plain committed JSON vectors;
- vectors describe input plus what an independent correct implementation must produce;
- cross-language comparability is preferred over implementation-specific internals.

No MorphTile world/schema/render code is copied into this kit.

## AXM Invariant Lab

Repository: `mike-axiom-mir/axm-invariant-lab`  
Pinned main observed: `48164b812728fe52e922e539fd4ab4b469028e0d`

Reused pattern:

- unknown/incomplete evidence is not silently promoted to PASS;
- negative/counterexample behavior is part of the retained test surface;
- a check command is expected to fail closed when the bounded claim no longer holds.

No state-explorer implementation is copied.

## AXM Protocol Evolution

Repository: `mike-axiom-mir/axm-protocol-evolution`  
Pinned main observed: `f347fac1602864b73aaaaca70e4e0be3c9e88f02`  
Relevant sources: `COMPATIBILITY_STATES.md`, `UNKNOWN_FIELD_RULE.md`

Reused pattern:

- refusal is a valid truthful outcome;
- parseability/transport does not imply understanding or compatibility;
- unknown state must not be silently erased or reinterpreted.

No protocol migration code is copied.

## License

All three inspected AXM-owned donor repositories are currently under AXM-controlled licensing surfaces; this neutral core repository remains under its existing MPL-2.0 license. This note is provenance, not a legal opinion.
