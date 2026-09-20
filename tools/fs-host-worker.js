'use strict';

const Host = require('../src/fs-host.js');
const { buildScenario } = require('../test/fs-host-fixture.js');

const root = process.argv[2];
const crashAt = process.argv[3] === 'none' ? null : process.argv[3];
if (!root) throw new Error('usage: fs-host-worker.js ROOT CRASH_POINT|none');

const scenario = buildScenario();
const result = Host.commitDurable(
  root,
  scenario.runtime,
  scenario.stage,
  scenario.updatedArtifacts,
  { crash_at: crashAt, actor: 'crash-worker' },
);
if (!crashAt) {
  process.stdout.write(JSON.stringify({
    status: result.status,
    sequence: result.runtime ? require('../src/core.js').currentHead(result.runtime).sequence : null,
  }) + '\n');
}
