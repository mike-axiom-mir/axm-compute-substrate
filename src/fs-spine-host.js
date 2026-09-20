'use strict';

const fs = require('node:fs');
const path = require('node:path');
const Core = require('./core.js');

const META_FORMAT = 'axm-neutral-fs-spine-meta';
const POINTER_FORMAT = 'axm-neutral-fs-spine-pointer';
const HISTORY_FORMAT = 'axm-neutral-fs-history-record';
const VERSION = '0.1';

function clone(value) {
  return value === undefined ? undefined : JSON.parse(JSON.stringify(value));
}

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function fsyncDir(dir) {
  const fd = fs.openSync(dir, 'r');
  try { fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
}

function crashIf(label, requested) {
  if (!requested || !label || requested !== label) return;
  const marker = process.env.AXM_FS_HOST_PAUSE_MARKER;
  if (marker) {
    const fd = fs.openSync(marker, 'w', 0o600);
    try {
      fs.writeFileSync(fd, label + '\n');
      fs.fsyncSync(fd);
    } finally {
      fs.closeSync(fd);
    }
    const wait = new Int32Array(new SharedArrayBuffer(4));
    while (true) Atomics.wait(wait, 0, 0, 1000);
  }
  process.kill(process.pid, 'SIGKILL');
}

function semanticSeal(body, field) {
  const out = clone(body);
  out[field] = Core.hashCanonical(body);
  return out;
}

function verifySemanticSeal(value, field) {
  if (!value || typeof value !== 'object' || typeof value[field] !== 'string') return false;
  const body = clone(value);
  const claimed = body[field];
  delete body[field];
  return claimed === Core.hashCanonical(body);
}

function writeAtomicJson(file, value) {
  ensureDir(path.dirname(file));
  const temp = path.join(path.dirname(file), '.' + path.basename(file) + '.pending-' + process.pid);
  const bytes = Buffer.from(Core.canonicalize(value), 'utf8');
  const fd = fs.openSync(temp, 'wx', 0o600);
  try {
    fs.writeFileSync(fd, bytes);
    fs.fsyncSync(fd);
  } finally {
    fs.closeSync(fd);
  }
  fs.renameSync(temp, file);
  fsyncDir(path.dirname(file));
}

function rawObjectPath(root, kind, sha) {
  if (!/^[0-9a-f]{64}$/.test(String(sha || ''))) throw new Error(kind + ' object sha256 required');
  return path.join(root, 'objects', kind, sha + '.blob');
}

function writeRawObject(root, kind, bytes) {
  const body = Buffer.from(bytes);
  const sha = Core.sha256Bytes(body);
  const finalPath = rawObjectPath(root, kind, sha);
  ensureDir(path.dirname(finalPath));

  if (fs.existsSync(finalPath)) {
    const existing = fs.readFileSync(finalPath);
    if (Core.sha256Bytes(existing) !== sha) throw new Error('existing ' + kind + ' object corrupt: ' + sha);
    return { sha, path: finalPath, bytes: body.length, reused: true };
  }

  const temp = path.join(path.dirname(finalPath), '.' + sha + '.pending-' + process.pid);
  const fd = fs.openSync(temp, 'wx', 0o600);
  try {
    fs.writeFileSync(fd, body);
    fs.fsyncSync(fd);
  } finally {
    fs.closeSync(fd);
  }
  fs.renameSync(temp, finalPath);
  fsyncDir(path.dirname(finalPath));
  return { sha, path: finalPath, bytes: body.length, reused: false };
}

function writeSemanticObject(root, kind, value) {
  return writeRawObject(root, kind, Buffer.from(Core.canonicalize(value), 'utf8'));
}

function artifactBytes(ref, value) {
  const check = Core.verifyArtifact(ref, value);
  if (!check.ok) {
    const error = new Error('artifact body does not match staged ref');
    error.code = 'ARTIFACT_HASH_MISMATCH';
    error.claimed = check.claimed;
    error.observed = check.observed;
    throw error;
  }
  return ref.hash_kind === 'bytes'
    ? Buffer.from(value)
    : Buffer.from(Core.canonicalize(value), 'utf8');
}

function artifactPath(root, sha) {
  return rawObjectPath(root, 'artifact', sha);
}

function writeArtifactObject(root, ref, value) {
  const bytes = artifactBytes(ref, value);
  if (Core.sha256Bytes(bytes) !== ref.artifact_sha256) {
    throw new Error('artifact canonical/raw bytes do not match artifact identity');
  }
  const result = writeRawObject(root, 'artifact', bytes);
  if (result.sha !== ref.artifact_sha256) throw new Error('artifact object identity mismatch');
  return result;
}

function metaBody(runtime) {
  return {
    format: META_FORMAT,
    version: VERSION,
    runtime_format: runtime.format,
    runtime_version: runtime.version,
    label: runtime.label || null,
    registry: clone(runtime.registry),
  };
}

function makeMeta(runtime) {
  return semanticSeal(metaBody(runtime), 'meta_sha256');
}

function verifyMeta(meta) {
  return meta && meta.format === META_FORMAT && meta.version === VERSION && verifySemanticSeal(meta, 'meta_sha256');
}

function historyBody(input) {
  return {
    format: HISTORY_FORMAT,
    version: VERSION,
    append_index: input.append_index,
    generation_sha256: input.generation_sha256,
    generation_object_sha256: input.generation_object_sha256,
    parent_generation_sha256: input.parent_generation_sha256,
    receipt_sha256: input.receipt_sha256 || null,
    receipt_object_sha256: input.receipt_object_sha256 || null,
    previous_record_sha256: input.previous_record_sha256 || null,
  };
}

function makeHistoryRecord(input) {
  return semanticSeal(historyBody(input), 'record_sha256');
}

function verifyHistoryRecord(record) {
  return record && record.format === HISTORY_FORMAT && record.version === VERSION && verifySemanticSeal(record, 'record_sha256');
}

function pointerBody(record) {
  return {
    format: POINTER_FORMAT,
    version: VERSION,
    append_index: record.append_index,
    history_record_sha256: record.record_sha256,
    current_generation_sha256: record.generation_sha256,
  };
}

function makePointer(record) {
  return semanticSeal(pointerBody(record), 'pointer_sha256');
}

function verifyPointer(pointer) {
  return pointer && pointer.format === POINTER_FORMAT && pointer.version === VERSION && verifySemanticSeal(pointer, 'pointer_sha256');
}

function persistGenerationObject(root, generation) {
  if (!verifySemanticSeal(generation, 'generation_sha256')) throw new Error('generation semantic seal invalid');
  return writeSemanticObject(root, 'generation', generation);
}

function persistReceiptObject(root, receipt) {
  if (!verifySemanticSeal(receipt, 'receipt_sha256')) throw new Error('receipt semantic seal invalid');
  return writeSemanticObject(root, 'receipt', receipt);
}

function readRawObject(root, kind, sha) {
  const file = rawObjectPath(root, kind, sha);
  if (!fs.existsSync(file)) throw new Error(kind + ' object missing: ' + sha);
  const bytes = fs.readFileSync(file);
  if (Core.sha256Bytes(bytes) !== sha) throw new Error(kind + ' object hash mismatch: ' + sha);
  return bytes;
}

function parseGenerationObject(root, record) {
  const bytes = readRawObject(root, 'generation', record.generation_object_sha256);
  let generation;
  try { generation = JSON.parse(bytes.toString('utf8')); }
  catch (_) { throw new Error('generation object invalid JSON: ' + record.generation_object_sha256); }
  if (!verifySemanticSeal(generation, 'generation_sha256')) throw new Error('generation semantic seal mismatch');
  if (generation.generation_sha256 !== record.generation_sha256) throw new Error('history/generation semantic identity mismatch');
  if ((generation.parent_generation_sha256 || null) !== (record.parent_generation_sha256 || null)) {
    throw new Error('history/generation parent mismatch');
  }
  return generation;
}

function parseReceiptObject(root, record) {
  if (!record.receipt_sha256 && !record.receipt_object_sha256) return null;
  if (!record.receipt_sha256 || !record.receipt_object_sha256) throw new Error('history receipt reference incomplete');
  const bytes = readRawObject(root, 'receipt', record.receipt_object_sha256);
  let receipt;
  try { receipt = JSON.parse(bytes.toString('utf8')); }
  catch (_) { throw new Error('receipt object invalid JSON: ' + record.receipt_object_sha256); }
  if (!verifySemanticSeal(receipt, 'receipt_sha256')) throw new Error('receipt semantic seal mismatch');
  if (receipt.receipt_sha256 !== record.receipt_sha256) throw new Error('history/receipt semantic identity mismatch');
  return receipt;
}

function appendHistory(root, record, crashAt) {
  const file = path.join(root, 'HISTORY.log');
  ensureDir(root);
  const fd = fs.openSync(file, 'a', 0o600);
  try {
    fs.writeFileSync(fd, Core.canonicalize(record) + '\n');
    fs.fsyncSync(fd);
  } finally {
    fs.closeSync(fd);
  }
  crashIf('after_history_append', crashAt);
}

function scanHistory(root) {
  const file = path.join(root, 'HISTORY.log');
  if (!fs.existsSync(file)) throw new Error('HISTORY log missing');
  const text = fs.readFileSync(file, 'utf8');
  const lines = text.split('\n');
  const records = [];
  const generations = {};
  const receipts = [];
  let previous = null;
  let invalidTail = null;
  let offset = 0;

  for (let index = 0; index < lines.length; index++) {
    const line = lines[index];
    const bytes = Buffer.byteLength(line, 'utf8') + (index < lines.length - 1 ? 1 : 0);
    if (line === '') {
      offset += bytes;
      continue;
    }

    let record;
    try { record = JSON.parse(line); }
    catch (_) {
      invalidTail = { offset, bytes: Buffer.byteLength(text.slice(offset), 'utf8'), reason: 'invalid-json' };
      break;
    }

    try {
      if (!verifyHistoryRecord(record)) throw new Error('record-seal');
      if (!Number.isSafeInteger(record.append_index) || record.append_index !== records.length) throw new Error('append-index');
      if ((record.previous_record_sha256 || null) !== (previous ? previous.record_sha256 : null)) throw new Error('previous-record');
      const generation = parseGenerationObject(root, record);
      if (record.append_index === 0) {
        if (generation.sequence !== 0 || generation.parent_generation_sha256 !== null) throw new Error('invalid-root-generation');
        if (record.receipt_sha256 || record.receipt_object_sha256) throw new Error('root-receipt-not-null');
      } else {
        if (!generation.parent_generation_sha256 || !generations[generation.parent_generation_sha256]) throw new Error('parent-generation-not-yet-known');
        const parent = generations[generation.parent_generation_sha256];
        if (generation.sequence !== parent.sequence + 1) throw new Error('generation-sequence');
      }
      const receipt = parseReceiptObject(root, record);
      generations[generation.generation_sha256] = generation;
      if (receipt) receipts.push(receipt);
    } catch (error) {
      invalidTail = { offset, bytes: Buffer.byteLength(text.slice(offset), 'utf8'), reason: error.message };
      break;
    }

    records.push(record);
    previous = record;
    offset += bytes;
  }

  return {
    records,
    generations,
    receipts,
    invalid_tail: invalidTail,
    valid_bytes: offset,
    total_bytes: Buffer.byteLength(text, 'utf8'),
  };
}

function writeCurrentPointer(root, pointer, crashAt) {
  const target = path.join(root, 'CURRENT.json');
  const temp = path.join(root, '.CURRENT.pending-' + process.pid);
  const bytes = Buffer.from(Core.canonicalize(pointer), 'utf8');

  const fd = fs.openSync(temp, 'wx', 0o600);
  try {
    fs.writeFileSync(fd, bytes);
    fs.fsyncSync(fd);
  } finally {
    fs.closeSync(fd);
  }
  crashIf('after_pointer_temp_fsync', crashAt);

  fs.renameSync(temp, target);
  crashIf('after_pointer_rename', crashAt);

  fsyncDir(root);
  crashIf('after_pointer_dir_fsync', crashAt);
}

function readMeta(root) {
  const file = path.join(root, 'META.json');
  if (!fs.existsSync(file)) throw new Error('META missing');
  let meta;
  try { meta = JSON.parse(fs.readFileSync(file, 'utf8')); }
  catch (_) { throw new Error('META invalid JSON'); }
  if (!verifyMeta(meta)) throw new Error('META integrity check failed');
  return meta;
}

function readPointer(root) {
  const file = path.join(root, 'CURRENT.json');
  if (!fs.existsSync(file)) throw new Error('CURRENT pointer missing');
  let pointer;
  try { pointer = JSON.parse(fs.readFileSync(file, 'utf8')); }
  catch (_) { throw new Error('CURRENT pointer invalid JSON'); }
  if (!verifyPointer(pointer)) throw new Error('CURRENT pointer failed integrity check');
  return pointer;
}

function reconstructRuntime(root, meta, history, pointer) {
  const record = history.records[pointer.append_index];
  if (!record) {
    if (history.invalid_tail) {
      throw new Error('CURRENT depends on invalid history tail: ' + history.invalid_tail.reason);
    }
    throw new Error('CURRENT points beyond valid history prefix');
  }
  if (record.record_sha256 !== pointer.history_record_sha256) throw new Error('CURRENT/history record mismatch');
  if (record.generation_sha256 !== pointer.current_generation_sha256) throw new Error('CURRENT/history generation mismatch');

  const runtime = {
    format: meta.runtime_format,
    version: meta.runtime_version,
    label: meta.label,
    registry: clone(meta.registry),
    generations: clone(history.generations),
    current_generation_sha256: pointer.current_generation_sha256,
    receipts: clone(history.receipts),
    hot: {},
  };

  return Core.importRuntime(Core.exportRuntime(runtime));
}

function verifyCurrentArtifacts(root, runtime) {
  const head = Core.currentHead(runtime);
  for (const [id, ref] of Object.entries(head.contracts)) {
    const bytes = readRawObject(root, 'artifact', ref.artifact_sha256);
    if (Core.sha256Bytes(bytes) !== ref.artifact_sha256) throw new Error('current artifact hash mismatch for ' + id);
  }
}

function recoverSpineHost(root, options) {
  options = options || {};
  const meta = readMeta(root);
  const pointer = readPointer(root);
  const history = scanHistory(root);
  const runtime = reconstructRuntime(root, meta, history, pointer);
  if (options.verify_artifacts !== false) verifyCurrentArtifacts(root, runtime);

  const unpointed = history.records
    .filter((record) => record.append_index > pointer.append_index)
    .map((record) => ({
      append_index: record.append_index,
      record_sha256: record.record_sha256,
      generation_sha256: record.generation_sha256,
    }));

  return {
    status: 'RECOVERED',
    runtime,
    head: Core.currentHead(runtime),
    pointer,
    history: {
      valid_records: history.records.length,
      valid_bytes: history.valid_bytes,
      total_bytes: history.total_bytes,
      invalid_tail: history.invalid_tail,
      unpointed_records: unpointed,
    },
  };
}

function persistAllCurrentArtifacts(root, generation, values) {
  for (const id of Object.keys(generation.contracts).sort()) {
    if (!Object.prototype.hasOwnProperty.call(values, id)) throw new Error('missing artifact body for ' + id);
    writeArtifactObject(root, generation.contracts[id], values[id]);
  }
}

function persistUpdatedArtifacts(root, generation, values, crashAt) {
  for (const id of Object.keys(generation.contracts).sort()) {
    if (generation.contracts[id].decision !== 'UPDATED') continue;
    if (!Object.prototype.hasOwnProperty.call(values, id)) throw new Error('missing artifact body for ' + id);
    writeArtifactObject(root, generation.contracts[id], values[id]);
  }
  crashIf('after_artifacts', crashAt);
}

function initializeSpineHost(root, runtime, artifactValues, options) {
  options = options || {};
  ensureDir(root);
  if (fs.existsSync(path.join(root, 'CURRENT.json')) || fs.existsSync(path.join(root, 'META.json')) || fs.existsSync(path.join(root, 'HISTORY.log'))) {
    throw new Error('spine host already initialized');
  }

  const generation = Core.currentGeneration(runtime);
  if (!generation || generation.sequence !== 0) throw new Error('spine host initialization requires root generation');

  persistAllCurrentArtifacts(root, generation, artifactValues || {});
  writeAtomicJson(path.join(root, 'META.json'), makeMeta(runtime));

  const generationObject = persistGenerationObject(root, generation);
  const record = makeHistoryRecord({
    append_index: 0,
    generation_sha256: generation.generation_sha256,
    generation_object_sha256: generationObject.sha,
    parent_generation_sha256: null,
    receipt_sha256: null,
    receipt_object_sha256: null,
    previous_record_sha256: null,
  });
  appendHistory(root, record, options.crash_at || null);
  const pointer = makePointer(record);
  writeCurrentPointer(root, pointer, options.crash_at || null);
  return { status: 'INITIALIZED', pointer, record };
}

function commitSpineDurable(root, runtime, stage, updatedArtifactValues, options) {
  options = options || {};
  const durable = recoverSpineHost(root);
  const suppliedHead = Core.currentHead(runtime);
  if (!suppliedHead || suppliedHead.generation_sha256 !== durable.head.generation_sha256) {
    return {
      status: 'HOLD_HOST_RUNTIME_MISMATCH',
      durable_generation_sha256: durable.head.generation_sha256,
      supplied_generation_sha256: suppliedHead ? suppliedHead.generation_sha256 : null,
    };
  }
  if (stage.base_generation_sha256 !== durable.head.generation_sha256) {
    return {
      status: 'HOLD_STALE_STAGE',
      staged_base: stage.base_generation_sha256,
      durable_generation_sha256: durable.head.generation_sha256,
    };
  }
  if (durable.history.invalid_tail) {
    return { status: 'HOLD_INVALID_HISTORY_TAIL', invalid_tail: durable.history.invalid_tail };
  }

  const candidate = Core.importRuntime(Core.exportRuntime(durable.runtime));
  const result = Core.commitGeneration(candidate, stage, options.actor || 'fs-spine-host');
  if (result.status !== 'COMMITTED') return result;

  const generation = Core.currentGeneration(candidate);
  persistUpdatedArtifacts(root, generation, updatedArtifactValues || {}, options.crash_at || null);

  const generationObject = persistGenerationObject(root, generation);
  crashIf('after_generation_object', options.crash_at || null);

  const receiptObject = persistReceiptObject(root, result.receipt);
  crashIf('after_receipt_object', options.crash_at || null);

  const scanned = scanHistory(root);
  if (scanned.invalid_tail) return { status: 'HOLD_INVALID_HISTORY_TAIL', invalid_tail: scanned.invalid_tail };
  const previous = scanned.records.at(-1);
  const record = makeHistoryRecord({
    append_index: scanned.records.length,
    generation_sha256: generation.generation_sha256,
    generation_object_sha256: generationObject.sha,
    parent_generation_sha256: generation.parent_generation_sha256,
    receipt_sha256: result.receipt.receipt_sha256,
    receipt_object_sha256: receiptObject.sha,
    previous_record_sha256: previous ? previous.record_sha256 : null,
  });

  appendHistory(root, record, options.crash_at || null);
  const pointer = makePointer(record);
  writeCurrentPointer(root, pointer, options.crash_at || null);

  return {
    status: 'DURABLE_COMMITTED',
    runtime: candidate,
    pointer,
    record,
  };
}

function inspectSpineHost(root) {
  const recovered = recoverSpineHost(root, { verify_artifacts: false });
  const count = (kind) => {
    const dir = path.join(root, 'objects', kind);
    return fs.existsSync(dir) ? fs.readdirSync(dir).filter((name) => name.endsWith('.blob')).length : 0;
  };
  const bytes = (kind) => {
    const dir = path.join(root, 'objects', kind);
    if (!fs.existsSync(dir)) return 0;
    return fs.readdirSync(dir)
      .filter((name) => name.endsWith('.blob'))
      .reduce((sum, name) => sum + fs.statSync(path.join(dir, name)).size, 0);
  };
  return {
    status: 'INSPECTED',
    current_sequence: recovered.head.sequence,
    current_generation_sha256: recovered.head.generation_sha256,
    history: recovered.history,
    objects: {
      artifact: { count: count('artifact'), bytes: bytes('artifact') },
      generation: { count: count('generation'), bytes: bytes('generation') },
      receipt: { count: count('receipt'), bytes: bytes('receipt') },
    },
  };
}

module.exports = {
  META_FORMAT,
  POINTER_FORMAT,
  HISTORY_FORMAT,
  VERSION,
  initializeSpineHost,
  commitSpineDurable,
  recoverSpineHost,
  inspectSpineHost,
  scanHistory,
  makeHistoryRecord,
  makePointer,
  verifyPointer,
};
