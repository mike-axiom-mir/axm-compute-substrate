# Flowing Compute Policy ABI — Wave 10

Status: `EXPERIMENTAL ARCHITECTURE CHECKPOINT`

## Why this wave exists

Fast research produced multiple valid policy bodies with different shapes:

- Execution Graph: fitted global/incremental CPU models over graph features.
- Totality Matrix: fitted global/incremental CPU models over affected modules.
- FrameState manifest: an evidence-backed structural retained-work rule rather than a fitted CPU model.

Forcing all three into one model family would rewrite what the evidence actually established. Leaving multiple incompatible registries would make the runtime ambiguous.

## Change

Wave 10 adds a policy ABI dispatcher and canonical registry v0.2.

The registry binds an exact `contract_id` to:

1. a preserved profile file;
2. its exact `profile_id`;
3. an explicit `evaluator_kind`.

Supported evaluator kinds in v0.2:

- `linear_cpu_models_v1`
- `retained_work_fraction_v1`

Unknown contracts, duplicate bindings, unsupported evaluators, wrong feature shapes, negative features, and impossible retained-work fractions fail closed / HOLD.

## Preservation rule

No legacy profile, receipt, calibration, or registry is rewritten. Both earlier registries remain as historical evidence. `POLICY_PROFILE_REGISTRY.v0.2.json` becomes the forward canonical dispatcher surface only after its self-test and schema validation pass.

## Local verification

- policy ABI self-test: PASS (8 checks)
- registry v0.2 JSON schema: PASS
- linear evaluator: incremental and global boundary cases PASS
- retained-work evaluator: partial invalidation -> incremental PASS
- full invalidation -> global PASS
- unknown contract -> HOLD PASS
- impossible affected > total -> rejection PASS
- out-of-measured-domain feature -> HOLD PASS

## Truth boundary

This is an interoperability layer, not evidence that one universal compute policy exists. It deliberately preserves different policy families because prior experiments showed that different state contracts have different crossover behavior.

## Measured-domain guard repair

A real-profile smoke test intentionally tried an impossible-looking combination: all 127 Execution Graph components affected while only 8 source components were declared mutated. The linear model produced a confident-looking answer even though the preserved Wave 6 measurements reached 127/127 only with 82 mutated source components.

Wave 10 therefore adds profile-domain guards:

- Execution Graph: nearest measured two-feature surface from the actual 11 Wave-6 cases; out-of-surface combinations HOLD.
- Totality Matrix: affected module count must remain inside the measured 1–38 module range.
- FrameState manifest: current evidence admits the measured 24- and 48-frame totals; other totals HOLD until measured or explicitly extended.

The repaired smoke test now gives:

- measured `127 affected / 82 mutated` -> global, matching Wave 6;
- extrapolated `127 / 8` -> HOLD;
- FrameState `47 / 48` -> incremental;
- unmeasured 60-frame FrameState body -> HOLD.

This prevents a fitted policy from turning mathematical extrapolation into fake empirical confidence.
