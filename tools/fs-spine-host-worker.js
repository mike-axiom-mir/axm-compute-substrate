'use strict';

const Host = require('../src/fs-spine-host.js');
const Core = require('../src/core.js');
const { buildScenario } = require('../test/fs-host-fixture.js');

const root = process.argv[2];
const crashAt = process.argv[3] === 'none' ? null : process.argv[3];
if (!root) throw new Error('usage: fs-spine-host-worker.js ROOT CRASH_POINT|none');

const scenario = buildScenario();
const result = Host.commitSpineDurable(
  root,
  scenario.runtime,
  scenario.stage,
  scenario.updatedArtifacts,
  { crash_at: crashAt, actor: 'spine-crash-worker' },
);

if (!crashAt) {
  process.stdout.write(JSON.stringify({
    status: result.status,
    sequence: result.runtime ? Core.currentHead(result.runtime).sequence : null,
  }) + '\n');
}
