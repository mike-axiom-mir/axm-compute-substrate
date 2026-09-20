'use strict';

const fs = require('node:fs');
const path = require('node:path');
const Core = require('./core.js');

const POINTER_FORMAT = 'axm-neutral-fs-pointer';
const POINTER_VERSION = '0.1';

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function fsyncDir(dir) {
  const fd = fs.openSync(dir, 'r');
  try {
    fs.fsyncSync(fd);
  } finally {
    fs.closeSync(fd);
  }
}

function objectPath(root, kind, sha) {
  if (!/^[0-9a-f]{64}$/.test(String(sha || ''))) throw new Error('object sha256 required');
  return path.join(root, 'objects', kind, sha + '.blob');
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

function writeImmutable(root, kind, sha, bytes, crashAt, crashLabel) {
  const finalPath = objectPath(root, kind, sha);
  ensureDir(path.dirname(finalPath));
  const body = Buffer.from(bytes);
  if (Core.sha256Bytes(body) !== sha) throw new Error(kind + ' object bytes do not match sha256');

  if (fs.existsSync(finalPath)) {
    const existing = fs.readFileSync(finalPath);
    if (Core.sha256Bytes(existing) !== sha) throw new Error('existing ' + kind + ' object is corrupt: ' + sha);
    return finalPath;
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
  crashIf(crashLabel, crashAt);
  return finalPath;
}

function artifactBytes(ref, value) {
  const check = Core.verifyArtifact(ref, value);
  if (!check.ok) {
    const error = new Error('artifact body does not match staged ref');
    error.code = 'ARTIFACT_HASH_MISMATCH';
    error.contract = null;
    error.claimed = check.claimed;
    error.observed = check.observed;
    throw error;
  }
  return ref.hash_kind === 'bytes'
    ? Buffer.from(value)
    : Buffer.from(Core.canonicalize(value), 'utf8');
}

function pointerBody(runtimeObjectSha, generationSha) {
  return {
    format: POINTER_FORMAT,
    version: POINTER_VERSION,
    runtime_object_sha256: runtimeObjectSha,
    current_generation_sha256: generationSha,
  };
}

function makePointer(runtimeObjectSha, generationSha) {
  const body = pointerBody(runtimeObjectSha, generationSha);
  return Object.assign({}, body, { pointer_sha256: Core.hashCanonical(body) });
}

function verifyPointer(pointer) {
  if (!pointer || pointer.format !== POINTER_FORMAT || pointer.version !== POINTER_VERSION) return false;
  const claimed = pointer.pointer_sha256;
  if (!/^[0-9a-f]{64}$/.test(String(claimed || ''))) return false;
  return claimed === Core.hashCanonical(pointerBody(pointer.runtime_object_sha256, pointer.current_generation_sha256));
}

function writeCurrentPointer(root, pointer, crashAt) {
  ensureDir(root);
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

function persistRuntimeObject(root, runtime, crashAt) {
  const exported = Core.exportRuntime(runtime);
  const bytes = Buffer.from(Core.canonicalize(exported), 'utf8');
  const sha = Core.sha256Bytes(bytes);
  writeImmutable(root, 'runtime', sha, bytes, crashAt, 'after_runtime_object');
  return { sha, exported };
}

function persistArtifacts(root, generation, values, onlyUpdated, crashAt) {
  const ids = onlyUpdated
    ? Object.keys(generation.contracts).filter((id) => generation.contracts[id].decision === 'UPDATED').sort()
    : Object.keys(generation.contracts).sort();

  for (const id of ids) {
    if (!Object.prototype.hasOwnProperty.call(values, id)) {
      throw new Error('missing artifact body for ' + id);
    }
    const ref = generation.contracts[id];
    const bytes = artifactBytes(ref, values[id]);
    writeImmutable(root, 'artifact', ref.artifact_sha256, bytes, null, null);
  }
  crashIf('after_artifacts', crashAt);
}

function initializeHost(root, runtime, artifactValues, options) {
  options = options || {};
  ensureDir(root);
  if (fs.existsSync(path.join(root, 'CURRENT.json'))) throw new Error('host already initialized');

  const generation = Core.currentGeneration(runtime);
  if (!generation) throw new Error('runtime has no current generation');
  persistArtifacts(root, generation, artifactValues || {}, false, options.crash_at || null);
  const persisted = persistRuntimeObject(root, runtime, options.crash_at || null);
  const pointer = makePointer(persisted.sha, generation.generation_sha256);
  writeCurrentPointer(root, pointer, options.crash_at || null);
  return { status: 'INITIALIZED', pointer, runtime_object_sha256: persisted.sha };
}

function commitDurable(root, runtime, stage, updatedArtifactValues, options) {
  options = options || {};
  const candidate = Core.importRuntime(JSON.parse(JSON.stringify(Core.exportRuntime(runtime))));
  const result = Core.commitGeneration(candidate, stage, options.actor || 'fs-host');
  if (result.status !== 'COMMITTED') return result;

  const generation = Core.currentGeneration(candidate);
  persistArtifacts(root, generation, updatedArtifactValues || {}, true, options.crash_at || null);
  const persisted = persistRuntimeObject(root, candidate, options.crash_at || null);
  const pointer = makePointer(persisted.sha, generation.generation_sha256);
  writeCurrentPointer(root, pointer, options.crash_at || null);

  return {
    status: 'DURABLE_COMMITTED',
    runtime: candidate,
    pointer,
    runtime_object_sha256: persisted.sha,
  };
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

function recoverHost(root, options) {
  options = options || {};
  const pointerFile = path.join(root, 'CURRENT.json');
  if (!fs.existsSync(pointerFile)) throw new Error('CURRENT pointer missing');
  const pointer = readJson(pointerFile);
  if (!verifyPointer(pointer)) throw new Error('CURRENT pointer failed integrity check');

  const runtimeFile = objectPath(root, 'runtime', pointer.runtime_object_sha256);
  if (!fs.existsSync(runtimeFile)) throw new Error('current runtime object missing');
  const runtimeBytes = fs.readFileSync(runtimeFile);
  if (Core.sha256Bytes(runtimeBytes) !== pointer.runtime_object_sha256) throw new Error('current runtime object hash mismatch');

  const runtime = Core.importRuntime(JSON.parse(runtimeBytes.toString('utf8')));
  const head = Core.currentHead(runtime);
  if (!head || head.generation_sha256 !== pointer.current_generation_sha256) {
    throw new Error('pointer/runtime generation mismatch');
  }

  if (options.verify_artifacts !== false) {
    for (const [id, ref] of Object.entries(head.contracts)) {
      const file = objectPath(root, 'artifact', ref.artifact_sha256);
      if (!fs.existsSync(file)) throw new Error('current artifact missing for ' + id);
      if (Core.sha256Bytes(fs.readFileSync(file)) !== ref.artifact_sha256) {
        throw new Error('current artifact hash mismatch for ' + id);
      }
    }
  }

  return {
    status: 'RECOVERED',
    runtime,
    pointer,
    head,
  };
}

function inspectHost(root) {
  const current = recoverHost(root, { verify_artifacts: false });
  const runtimeDir = path.join(root, 'objects', 'runtime');
  const artifactDir = path.join(root, 'objects', 'artifact');
  const list = (dir) => fs.existsSync(dir) ? fs.readdirSync(dir).filter((x) => x.endsWith('.blob')).sort() : [];
  return {
    status: 'INSPECTED',
    current_generation_sha256: current.head.generation_sha256,
    current_sequence: current.head.sequence,
    runtime_objects: list(runtimeDir),
    artifact_objects: list(artifactDir),
    pending_pointer_files: fs.readdirSync(root).filter((x) => x.startsWith('.CURRENT.pending-')).sort(),
  };
}

module.exports = {
  POINTER_FORMAT,
  POINTER_VERSION,
  initializeHost,
  commitDurable,
  recoverHost,
  inspectHost,
  makePointer,
  verifyPointer,
};
