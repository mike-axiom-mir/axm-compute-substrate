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

No legacy profile, receipt, calibration, or registry is rewritten. Both earlier registries remain as historical evidence. `POLICY_PROFILE_REGISTRY.v0.2.json` is the forward canonical dispatcher surface after its self-test and schema validation pass.

## Local verification

- policy ABI self-test: PASS (7 checks)
- registry v0.2 JSON schema: PASS
- linear evaluator: incremental and global boundary cases PASS
- retained-work evaluator: partial invalidation -> incremental PASS
- full invalidation -> global PASS
- unknown contract -> HOLD PASS
- impossible affected > total -> rejection PASS

## Truth boundary

This is an interoperability layer, not evidence that one universal compute policy exists. It deliberately preserves different policy families because prior experiments showed that different state contracts have different crossover behavior.
