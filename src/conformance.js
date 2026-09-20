'use strict';

function clone(value) {
  if (value === undefined) return undefined;
  return JSON.parse(JSON.stringify(value));
}

function decodeBody(body) {
  if (!body || typeof body !== 'object') throw new Error('conformance body required');
  if (body.kind === 'json') return clone(body.value);
  if (body.kind === 'bytes-base64') return Buffer.from(String(body.value || ''), 'base64');
  throw new Error('unknown conformance body kind ' + body.kind);
}

function decisionsOf(headLike) {
  const contracts = headLike && headLike.contracts || {};
  return Object.fromEntries(Object.keys(contracts).sort().map((id) => [id, contracts[id].decision]));
}

function actionsOf(plan) {
  const contracts = plan && plan.contracts || {};
  return Object.fromEntries(Object.keys(contracts).sort().map((id) => [id, contracts[id].action]));
}

function matchesExpected(actual, expected, path) {
  path = path || '$';
  if (Array.isArray(expected)) {
    if (!Array.isArray(actual)) return { ok: false, path, expected, actual };
    if (actual.length !== expected.length) return { ok: false, path: path + '.length', expected: expected.length, actual: actual.length };
    for (let i = 0; i < expected.length; i++) {
      const r = matchesExpected(actual[i], expected[i], path + '[' + i + ']');
      if (!r.ok) return r;
    }
    return { ok: true };
  }
  if (expected && typeof expected === 'object') {
    if (!actual || typeof actual !== 'object') return { ok: false, path, expected, actual };
    for (const key of Object.keys(expected)) {
      if (!Object.prototype.hasOwnProperty.call(actual, key)) return { ok: false, path: path + '.' + key, expected: expected[key], actual: undefined };
      const r = matchesExpected(actual[key], expected[key], path + '.' + key);
      if (!r.ok) return r;
    }
    return { ok: true };
  }
  return Object.is(actual, expected) ? { ok: true } : { ok: false, path, expected, actual };
}

function referenceAdapter(Core) {
  const currentSequence = (ctx) => Core.currentHead(ctx.runtime).sequence;
  const hotContracts = (ctx) => Object.keys(ctx.runtime.hot || {}).sort();

  function refForBody(body) {
    const value = decodeBody(body);
    return Core.artifactRef(value, body.kind === 'bytes-base64'
      ? { hash_kind: 'bytes', representation: 'bytes' }
      : { hash_kind: 'canonical-json', representation: 'canonical-json' });
  }

  return {
    id: 'axm-neutral-reference-js/v0.1',

    canonicalHash(value) {
      return Core.hashCanonical(value);
    },

    bytesHash(base64) {
      return Core.sha256Bytes(Buffer.from(base64, 'base64'));
    },

    create(setup) {
      const artifacts = {};
      for (const [id, body] of Object.entries(setup.artifacts || {})) artifacts[id] = refForBody(body);
      return {
        runtime: Core.createRuntime({ label: 'conformance', contracts: setup.contracts || [], artifacts }),
        vars: {},
      };
    },

    step(ctx, spec) {
      switch (spec.op) {
        case 'remember_current': {
          const head = Core.currentHead(ctx.runtime);
          if (spec.save_generation) ctx.vars[spec.save_generation] = head.generation_sha256;
          return { status: 'REMEMBERED', current_sequence: head.sequence };
        }

        case 'plan': {
          const result = Core.planMutation(ctx.runtime, { selectors: spec.selectors || [], reason: 'conformance' });
          if (spec.save_as && result.status === 'PLANNED') ctx.vars[spec.save_as] = result;
          const out = { status: result.status, current_sequence: currentSequence(ctx) };
          if (result.contracts) out.actions = actionsOf(result);
          if (result.unknown_selectors) out.unknown_selectors = clone(result.unknown_selectors);
          return out;
        }

        case 'stage':
        case 'stage_from_current': {
          const plan = ctx.vars[spec.plan];
          let updates = {};
          if (spec.op === 'stage_from_current') {
            const head = Core.currentHead(ctx.runtime);
            for (const [id, route] of Object.entries(spec.routes || {})) {
              updates[id] = Object.assign({}, clone(head.contracts[id]), { route });
            }
          } else {
            for (const [id, update] of Object.entries(spec.updates || {})) {
              updates[id] = Object.assign({}, refForBody(update.body), { route: update.route });
            }
          }
          const result = Core.stageGeneration(ctx.runtime, plan, updates);
          if (spec.save_as && result.status === 'STAGED') ctx.vars[spec.save_as] = result;
          const out = { status: result.status, current_sequence: currentSequence(ctx) };
          if (result.contract) out.contract = result.contract;
          if (result.generation) {
            out.staged_sequence = result.generation.sequence;
            out.decisions = decisionsOf(result.generation);
          }
          return out;
        }

        case 'commit': {
          const stage = ctx.vars[spec.stage];
          const result = Core.commitGeneration(ctx.runtime, stage, 'conformance');
          const head = Core.currentHead(ctx.runtime);
          if (spec.save_generation && result.status === 'COMMITTED') ctx.vars[spec.save_generation] = head.generation_sha256;
          return {
            status: result.status,
            current_sequence: head.sequence,
            decisions: decisionsOf(head),
          };
        }

        case 'rollback': {
          const target = ctx.vars[spec.target] || spec.target;
          const result = Core.rollback(ctx.runtime, target, 'conformance');
          return { status: result.status, current_sequence: currentSequence(ctx) };
        }

        case 'reactivate': {
          const target = ctx.vars[spec.target] || spec.target;
          const result = Core.reactivate(ctx.runtime, target, 'conformance');
          return { status: result.status, current_sequence: currentSequence(ctx) };
        }

        case 'wake': {
          const result = Core.wakeContract(ctx.runtime, spec.contract, decodeBody(spec.body));
          return {
            status: result.status,
            current_sequence: currentSequence(ctx),
            hot_contracts: hotContracts(ctx),
          };
        }

        case 'sleep': {
          const result = Core.sleepContract(ctx.runtime, spec.contract);
          return {
            status: result.status,
            current_sequence: currentSequence(ctx),
            hot_contracts: hotContracts(ctx),
          };
        }

        case 'restart': {
          ctx.runtime = Core.importRuntime(JSON.parse(JSON.stringify(Core.exportRuntime(ctx.runtime))));
          return {
            status: 'RESTARTED',
            current_sequence: currentSequence(ctx),
            hot_contracts: hotContracts(ctx),
          };
        }

        case 'tamper_import': {
          const exported = JSON.parse(JSON.stringify(Core.exportRuntime(ctx.runtime)));
          const generation = exported.generations[exported.current_generation_sha256];
          if (!generation || !generation.contracts[spec.contract]) throw new Error('tamper target contract missing');
          generation.contracts[spec.contract][spec.field] = clone(spec.value);
          let refused = false;
          try {
            Core.importRuntime(exported);
          } catch (_) {
            refused = true;
          }
          return {
            status: refused ? 'REFUSED_TAMPERED_RUNTIME' : 'UNSAFE_ACCEPTED_TAMPERED_RUNTIME',
            current_sequence: currentSequence(ctx),
          };
        }

        default:
          throw new Error('unknown conformance op ' + spec.op);
      }
    },
  };
}

function runVectors(adapter, vectors) {
  if (!vectors || vectors.format !== 'axm-neutral-compute-conformance' || vectors.version !== '0.1') {
    throw new Error('unsupported conformance vectors');
  }
  if (!adapter || typeof adapter.create !== 'function' || typeof adapter.step !== 'function') {
    throw new Error('conformance adapter requires create() and step()');
  }

  const report = {
    format: 'axm-neutral-compute-conformance-report',
    version: '0.1',
    adapter: adapter.id || 'unknown',
    cases: [],
    passed: 0,
    failed: 0,
  };

  const primitiveChecks = [];
  if (typeof adapter.canonicalHash === 'function') {
    const actual = adapter.canonicalHash(vectors.hash_primitives.canonical_json.value);
    primitiveChecks.push({ id: 'canonical-json-sha256', ok: actual === vectors.hash_primitives.canonical_json.sha256, expected: vectors.hash_primitives.canonical_json.sha256, actual });
  }
  if (typeof adapter.bytesHash === 'function') {
    const actual = adapter.bytesHash(vectors.hash_primitives.bytes_base64.value);
    primitiveChecks.push({ id: 'bytes-sha256', ok: actual === vectors.hash_primitives.bytes_base64.sha256, expected: vectors.hash_primitives.bytes_base64.sha256, actual });
  }
  report.primitives = primitiveChecks;

  for (const vector of vectors.cases || []) {
    const result = { id: vector.id, steps: [], ok: true };
    let ctx;
    try {
      ctx = adapter.create(clone(vector.setup || vectors.default_setup));
      for (let i = 0; i < vector.steps.length; i++) {
        const step = vector.steps[i];
        const actual = adapter.step(ctx, clone(step));
        const match = matchesExpected(actual, step.expect || {});
        result.steps.push({ index: i, op: step.op, ok: match.ok, actual, expected: clone(step.expect || {}), mismatch: match.ok ? null : match });
        if (!match.ok) {
          result.ok = false;
          break;
        }
      }
    } catch (error) {
      result.ok = false;
      result.error = error && error.stack || String(error);
    }
    if (result.ok) report.passed += 1;
    else report.failed += 1;
    report.cases.push(result);
  }

  for (const check of primitiveChecks) {
    if (!check.ok) report.failed += 1;
  }

  report.ok = report.failed === 0 && primitiveChecks.every((x) => x.ok);
  return report;
}

module.exports = {
  decodeBody,
  matchesExpected,
  referenceAdapter,
  runVectors,
};
