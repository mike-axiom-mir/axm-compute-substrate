'use strict';

const crypto = require('node:crypto');

const FORMAT = 'axm-neutral-compute-runtime';
const VERSION = '0.1';
const SHA256 = /^[0-9a-f]{64}$/;

function isPlainObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value) && !Buffer.isBuffer(value) && !(value instanceof Uint8Array);
}

function canonicalize(value) {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return JSON.stringify(value);
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new TypeError('non-finite numbers are not canonical');
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return '[' + value.map(canonicalize).join(',') + ']';
  if (isPlainObject(value)) {
    const keys = Object.keys(value).filter((key) => value[key] !== undefined).sort();
    return '{' + keys.map((key) => JSON.stringify(key) + ':' + canonicalize(value[key])).join(',') + '}';
  }
  throw new TypeError('unsupported canonical value');
}

function sha256Bytes(value) {
  const bytes = Buffer.isBuffer(value) ? value : value instanceof Uint8Array ? Buffer.from(value) : Buffer.from(String(value), 'utf8');
  return crypto.createHash('sha256').update(bytes).digest('hex');
}

function hashCanonical(value) {
  return sha256Bytes(canonicalize(value));
}

function clone(value) {
  if (value === undefined) return undefined;
  return JSON.parse(JSON.stringify(value));
}

function seal(body, field) {
  const out = clone(body);
  out[field] = hashCanonical(body);
  return out;
}

function verifySeal(value, field) {
  if (!isPlainObject(value) || typeof value[field] !== 'string') return false;
  const body = clone(value);
  const claimed = body[field];
  delete body[field];
  return claimed === hashCanonical(body);
}

function hold(status, extra) {
  return Object.assign({ status }, extra || {});
}

function selectorMatches(pattern, selector) {
  pattern = String(pattern || '');
  selector = String(selector || '');
  if (!pattern || !selector) return false;
  if (pattern === '**' || pattern === selector) return true;
  if (pattern.endsWith('/**')) {
    const prefix = pattern.slice(0, -3);
    return selector === prefix || selector.startsWith(prefix + '/');
  }
  if (pattern.endsWith('**')) return selector.startsWith(pattern.slice(0, -2));
  if (pattern.endsWith('*')) return selector.startsWith(pattern.slice(0, -1));
  return false;
}

function normalizeContract(input) {
  if (!isPlainObject(input) || typeof input.id !== 'string' || !input.id) throw new Error('contract id required');
  const dependsOn = [...new Set((input.depends_on || []).map(String).filter(Boolean))].sort();
  if (!dependsOn.length) throw new Error('contract ' + input.id + ' requires depends_on');
  const routes = [...new Set((input.allowed_routes || []).map(String).filter(Boolean))].sort();
  return {
    id: input.id,
    kind: input.kind || 'derived-state',
    depends_on: dependsOn,
    allowed_routes: routes,
    policy_kind: input.policy_kind || 'contract-local',
    metadata: input.metadata == null ? null : clone(input.metadata),
  };
}

function normalizeArtifactRef(input) {
  if (!isPlainObject(input) || !SHA256.test(String(input.artifact_sha256 || ''))) throw new Error('artifact_sha256 must be a sha256');
  const hashKind = input.hash_kind || 'canonical-json';
  if (!['canonical-json', 'bytes'].includes(hashKind)) throw new Error('unsupported artifact hash_kind ' + hashKind);
  if (input.source_sha256 != null && !SHA256.test(String(input.source_sha256))) throw new Error('source_sha256 must be a sha256');
  if (input.proof_sha256 != null && !SHA256.test(String(input.proof_sha256))) throw new Error('proof_sha256 must be a sha256');
  return {
    artifact_sha256: String(input.artifact_sha256),
    hash_kind: hashKind,
    representation: input.representation || 'opaque',
    source_sha256: input.source_sha256 == null ? null : String(input.source_sha256),
    proof_sha256: input.proof_sha256 == null ? null : String(input.proof_sha256),
    metadata: input.metadata == null ? null : clone(input.metadata),
  };
}

function artifactRef(value, options) {
  options = options || {};
  const hashKind = options.hash_kind || (Buffer.isBuffer(value) || value instanceof Uint8Array ? 'bytes' : 'canonical-json');
  const artifactSha = hashKind === 'bytes' ? sha256Bytes(value) : hashCanonical(value);
  return normalizeArtifactRef({
    artifact_sha256: artifactSha,
    hash_kind: hashKind,
    representation: options.representation || (hashKind === 'bytes' ? 'bytes' : 'canonical-json'),
    source_sha256: options.source_sha256 || null,
    proof_sha256: options.proof_sha256 || null,
    metadata: options.metadata || null,
  });
}

function verifyArtifact(ref, value) {
  const normalized = normalizeArtifactRef(ref);
  const observed = normalized.hash_kind === 'bytes' ? sha256Bytes(value) : hashCanonical(value);
  return {
    ok: observed === normalized.artifact_sha256,
    claimed: normalized.artifact_sha256,
    observed,
    hash_kind: normalized.hash_kind,
  };
}

function generationBody(sequence, parent, planSha, selectors, contracts) {
  return {
    sequence,
    parent_generation_sha256: parent,
    plan_sha256: planSha,
    mutation_selectors: clone(selectors || []),
    contracts: clone(contracts),
  };
}

function createRuntime(options) {
  options = options || {};
  const contracts = (options.contracts || []).map(normalizeContract);
  if (!contracts.length) throw new Error('at least one contract required');

  const registry = {};
  for (const contract of contracts) {
    if (registry[contract.id]) throw new Error('duplicate contract ' + contract.id);
    registry[contract.id] = contract;
  }

  const baseContracts = {};
  for (const id of Object.keys(registry).sort()) {
    const initial = options.artifacts && options.artifacts[id];
    if (!initial) throw new Error('missing initial artifact for ' + id);
    baseContracts[id] = Object.assign({
      decision: 'BASE',
      route: null,
      previous_artifact_sha256: null,
    }, normalizeArtifactRef(initial));
  }

  const base = seal(generationBody(0, null, null, [], baseContracts), 'generation_sha256');
  return {
    format: FORMAT,
    version: VERSION,
    label: options.label || null,
    registry,
    generations: { [base.generation_sha256]: base },
    current_generation_sha256: base.generation_sha256,
    receipts: [],
    hot: {},
  };
}

function currentGeneration(runtime) {
  return runtime && runtime.generations && runtime.generations[runtime.current_generation_sha256] || null;
}

function currentHead(runtime) {
  const generation = currentGeneration(runtime);
  if (!generation) return null;
  return {
    sequence: generation.sequence,
    generation_sha256: generation.generation_sha256,
    parent_generation_sha256: generation.parent_generation_sha256,
    contracts: clone(generation.contracts),
  };
}

function planMutation(runtime, request) {
  request = request || {};
  const base = currentGeneration(runtime);
  if (!base) return hold('HOLD_NO_CURRENT_GENERATION');

  const selectors = [...new Set((request.selectors || []).map(String).filter(Boolean))].sort();
  if (!selectors.length) return hold('HOLD_MUTATION_SELECTORS_REQUIRED');

  const rows = {};
  const claimed = new Set();

  for (const id of Object.keys(runtime.registry).sort()) {
    const contract = runtime.registry[id];
    const matched = [];
    for (const selector of selectors) {
      if (contract.depends_on.some((pattern) => selectorMatches(pattern, selector))) {
        matched.push(selector);
        claimed.add(selector);
      }
    }
    rows[id] = {
      action: matched.length ? 'UPDATE_REQUIRED' : 'REUSE_EXACT',
      matched_selectors: matched,
      allowed_routes: clone(contract.allowed_routes),
      policy_kind: contract.policy_kind,
    };
  }

  const unknown = selectors.filter((selector) => !claimed.has(selector));
  if (unknown.length) return hold('HOLD_UNKNOWN_SELECTOR', { selectors, unknown_selectors: unknown });

  const body = {
    base_generation_sha256: base.generation_sha256,
    base_sequence: base.sequence,
    selectors,
    reason: request.reason || null,
    contracts: rows,
  };
  return Object.assign({ status: 'PLANNED' }, seal(body, 'plan_sha256'));
}

function validatePlan(plan) {
  if (!isPlainObject(plan) || plan.status !== 'PLANNED') return false;
  const body = clone(plan);
  delete body.status;
  return verifySeal(body, 'plan_sha256');
}

function stageGeneration(runtime, plan, updates) {
  updates = updates || {};
  if (!validatePlan(plan)) return hold('HOLD_INVALID_PLAN');
  if (plan.base_generation_sha256 !== runtime.current_generation_sha256) {
    return hold('HOLD_STALE_BASE', {
      planned_base: plan.base_generation_sha256,
      current_generation_sha256: runtime.current_generation_sha256,
    });
  }

  const prior = currentGeneration(runtime);
  const contracts = {};
  const updated = [];
  const reused = [];

  for (const id of Object.keys(runtime.registry).sort()) {
    const decision = plan.contracts[id];
    if (!decision) return hold('HOLD_PLAN_CONTRACT_MISSING', { contract: id });

    if (decision.action === 'REUSE_EXACT') {
      if (Object.prototype.hasOwnProperty.call(updates, id)) return hold('HOLD_REUSE_OVERRIDE', { contract: id });
      contracts[id] = Object.assign({}, clone(prior.contracts[id]), {
        decision: 'REUSED_EXACT',
        route: null,
        previous_artifact_sha256: prior.contracts[id].artifact_sha256,
      });
      reused.push(id);
      continue;
    }

    if (decision.action !== 'UPDATE_REQUIRED') return hold('HOLD_UNKNOWN_PLAN_ACTION', { contract: id, action: decision.action });

    const update = updates[id];
    if (!update) return hold('HOLD_UPDATE_MISSING', { contract: id });
    if (typeof update.route !== 'string' || !update.route) return hold('HOLD_ROUTE_REQUIRED', { contract: id });
    if (decision.allowed_routes.length && !decision.allowed_routes.includes(update.route)) {
      return hold('HOLD_ROUTE_NOT_ALLOWED', {
        contract: id,
        route: update.route,
        allowed_routes: clone(decision.allowed_routes),
      });
    }

    let ref;
    try {
      ref = normalizeArtifactRef(update);
    } catch (error) {
      return hold('HOLD_INVALID_ARTIFACT_REF', { contract: id, detail: error.message });
    }

    contracts[id] = Object.assign({}, ref, {
      decision: 'UPDATED',
      route: update.route,
      previous_artifact_sha256: prior.contracts[id].artifact_sha256,
    });
    updated.push(id);
  }

  for (const id of Object.keys(updates)) {
    if (!runtime.registry[id]) return hold('HOLD_UNKNOWN_UPDATE_CONTRACT', { contract: id });
  }

  const generation = seal(
    generationBody(prior.sequence + 1, prior.generation_sha256, plan.plan_sha256, plan.selectors, contracts),
    'generation_sha256',
  );

  const stageBody = {
    base_generation_sha256: prior.generation_sha256,
    plan_sha256: plan.plan_sha256,
    generation,
    updated,
    reused,
  };
  return Object.assign({ status: 'STAGED' }, seal(stageBody, 'stage_sha256'));
}

function validateStage(stage) {
  if (!isPlainObject(stage) || stage.status !== 'STAGED') return false;
  const body = clone(stage);
  delete body.status;
  return verifySeal(body, 'stage_sha256') && verifySeal(stage.generation, 'generation_sha256');
}

function invalidateHot(runtime) {
  const current = currentGeneration(runtime);
  for (const id of Object.keys(runtime.hot || {})) {
    if (!current || !current.contracts[id] || runtime.hot[id].artifact_sha256 !== current.contracts[id].artifact_sha256) {
      delete runtime.hot[id];
    }
  }
}

function commitGeneration(runtime, stage, actor) {
  if (!validateStage(stage)) return hold('HOLD_INVALID_STAGE');
  if (stage.base_generation_sha256 !== runtime.current_generation_sha256) {
    return hold('HOLD_STALE_STAGE', {
      staged_base: stage.base_generation_sha256,
      current_generation_sha256: runtime.current_generation_sha256,
    });
  }

  const generation = clone(stage.generation);
  runtime.generations[generation.generation_sha256] = generation;
  runtime.current_generation_sha256 = generation.generation_sha256;
  invalidateHot(runtime);

  const receipt = seal({
    type: 'generation.commit',
    sequence: generation.sequence,
    generation_sha256: generation.generation_sha256,
    parent_generation_sha256: generation.parent_generation_sha256,
    plan_sha256: generation.plan_sha256,
    updated: clone(stage.updated),
    reused: clone(stage.reused),
    actor: actor || null,
  }, 'receipt_sha256');

  runtime.receipts.push(receipt);
  return { status: 'COMMITTED', head: currentHead(runtime), receipt: clone(receipt) };
}

function isAncestor(runtime, target, from) {
  let cursor = from;
  const seen = new Set();
  while (cursor) {
    if (cursor === target) return true;
    if (seen.has(cursor)) return false;
    seen.add(cursor);
    const generation = runtime.generations[cursor];
    if (!generation) return false;
    cursor = generation.parent_generation_sha256;
  }
  return false;
}

function isDescendant(runtime, target, from) {
  return isAncestor(runtime, from, target);
}

function rollback(runtime, targetGenerationSha, actor) {
  if (!runtime.generations[targetGenerationSha]) return hold('HOLD_UNKNOWN_GENERATION', { target_generation_sha256: targetGenerationSha });
  const from = runtime.current_generation_sha256;
  if (from === targetGenerationSha) return { status: 'ALREADY_CURRENT', head: currentHead(runtime) };
  if (!isAncestor(runtime, targetGenerationSha, from)) {
    return hold('HOLD_TARGET_NOT_ANCESTOR', {
      current_generation_sha256: from,
      target_generation_sha256: targetGenerationSha,
    });
  }

  runtime.current_generation_sha256 = targetGenerationSha;
  invalidateHot(runtime);
  const receipt = seal({
    type: 'generation.rollback',
    from_generation_sha256: from,
    to_generation_sha256: targetGenerationSha,
    actor: actor || null,
  }, 'receipt_sha256');
  runtime.receipts.push(receipt);
  return { status: 'ROLLED_BACK', head: currentHead(runtime), receipt: clone(receipt) };
}

function reactivate(runtime, targetGenerationSha, actor) {
  if (!runtime.generations[targetGenerationSha]) return hold('HOLD_UNKNOWN_GENERATION', { target_generation_sha256: targetGenerationSha });
  const from = runtime.current_generation_sha256;
  if (from === targetGenerationSha) return { status: 'ALREADY_CURRENT', head: currentHead(runtime) };
  if (!isDescendant(runtime, targetGenerationSha, from)) {
    return hold('HOLD_TARGET_NOT_DESCENDANT', {
      current_generation_sha256: from,
      target_generation_sha256: targetGenerationSha,
    });
  }

  runtime.current_generation_sha256 = targetGenerationSha;
  invalidateHot(runtime);
  const receipt = seal({
    type: 'generation.reactivate',
    from_generation_sha256: from,
    to_generation_sha256: targetGenerationSha,
    actor: actor || null,
  }, 'receipt_sha256');
  runtime.receipts.push(receipt);
  return { status: 'REACTIVATED', head: currentHead(runtime), receipt: clone(receipt) };
}

function wakeContract(runtime, contractId, artifactValue) {
  const generation = currentGeneration(runtime);
  if (!generation || !generation.contracts[contractId]) return hold('HOLD_UNKNOWN_CONTRACT', { contract: contractId });
  const check = verifyArtifact(generation.contracts[contractId], artifactValue);
  if (!check.ok) return hold('HOLD_ARTIFACT_HASH_MISMATCH', {
    contract: contractId,
    claimed: check.claimed,
    observed: check.observed,
    hash_kind: check.hash_kind,
  });

  runtime.hot[contractId] = {
    artifact_sha256: check.observed,
    value: Buffer.isBuffer(artifactValue) || artifactValue instanceof Uint8Array
      ? Buffer.from(artifactValue).toString('base64')
      : clone(artifactValue),
    encoded_as: Buffer.isBuffer(artifactValue) || artifactValue instanceof Uint8Array ? 'base64-bytes' : 'canonical-json',
  };

  return {
    status: 'AWAKE_VERIFIED',
    contract: contractId,
    artifact_sha256: check.observed,
    generation_sha256: generation.generation_sha256,
  };
}

function hotArtifact(runtime, contractId) {
  const hot = runtime.hot && runtime.hot[contractId];
  if (!hot) return null;
  return hot.encoded_as === 'base64-bytes' ? Buffer.from(hot.value, 'base64') : clone(hot.value);
}

function sleepContract(runtime, contractId) {
  if (!runtime.hot || !runtime.hot[contractId]) return { status: 'ALREADY_DORMANT', contract: contractId };
  delete runtime.hot[contractId];
  return { status: 'DORMANT', contract: contractId };
}

function persistentBody(runtime) {
  return {
    format: runtime.format,
    version: runtime.version,
    label: runtime.label,
    registry: clone(runtime.registry),
    generations: clone(runtime.generations),
    current_generation_sha256: runtime.current_generation_sha256,
    receipts: clone(runtime.receipts),
  };
}

function exportRuntime(runtime) {
  return seal(persistentBody(runtime), 'runtime_sha256');
}

function validateRuntime(data) {
  if (!isPlainObject(data) || data.format !== FORMAT || data.version !== VERSION) throw new Error('unsupported neutral compute runtime');
  if (!verifySeal(data, 'runtime_sha256')) throw new Error('runtime hash mismatch');

  const registryIds = Object.keys(data.registry || {}).sort();
  if (!registryIds.length) throw new Error('runtime registry empty');

  const generations = data.generations || {};
  if (!generations[data.current_generation_sha256]) throw new Error('current generation missing');

  for (const [sha, generation] of Object.entries(generations)) {
    if (sha !== generation.generation_sha256 || !verifySeal(generation, 'generation_sha256')) {
      throw new Error('generation hash mismatch ' + sha);
    }
    if (generation.parent_generation_sha256) {
      const parent = generations[generation.parent_generation_sha256];
      if (!parent) throw new Error('missing parent ' + generation.parent_generation_sha256);
      if (generation.sequence !== parent.sequence + 1) throw new Error('generation sequence mismatch ' + sha);
    } else if (generation.sequence !== 0) {
      throw new Error('non-root generation missing parent ' + sha);
    }
    for (const id of registryIds) {
      if (!generation.contracts || !generation.contracts[id]) throw new Error('generation missing contract ' + id);
      normalizeArtifactRef(generation.contracts[id]);
    }
  }

  for (const receipt of data.receipts || []) {
    if (!verifySeal(receipt, 'receipt_sha256')) throw new Error('receipt hash mismatch');
  }

  return true;
}

function importRuntime(data) {
  validateRuntime(data);
  const body = clone(data);
  delete body.runtime_sha256;
  return Object.assign(body, { hot: {} });
}

function commitRecord(stage) {
  if (!validateStage(stage)) throw new Error('invalid stage');
  return seal({
    type: 'neutral-generation-pointer',
    generation_sha256: stage.generation.generation_sha256,
    parent_generation_sha256: stage.generation.parent_generation_sha256,
    sequence: stage.generation.sequence,
    stage_sha256: stage.stage_sha256,
  }, 'pointer_sha256');
}

module.exports = {
  FORMAT,
  VERSION,
  canonicalize,
  sha256Bytes,
  hashCanonical,
  selectorMatches,
  artifactRef,
  verifyArtifact,
  createRuntime,
  currentGeneration,
  currentHead,
  planMutation,
  stageGeneration,
  commitGeneration,
  commitRecord,
  rollback,
  reactivate,
  wakeContract,
  hotArtifact,
  sleepContract,
  exportRuntime,
  importRuntime,
  validateRuntime,
};
