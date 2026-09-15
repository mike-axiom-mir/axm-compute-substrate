'use strict';

const assert = require('assert');
const Flow = require('./flowing-compute-accounting');

let checks = 0;
function ok(value, message) {
  assert.ok(value, message);
  checks += 1;
}
function equal(actual, expected, message) {
  assert.strictEqual(actual, expected, message);
  checks += 1;
}
function rejects(fn, pattern, message) {
  assert.throws(fn, pattern, message);
  checks += 1;
}

const fixture = {
  schema: Flow.EXPERIMENT_SCHEMA,
  id: 'persistent-index-example',
  title: 'Persistent index amortization example',
  measurement: {
    unit: 'normalized-compute-unit',
    usefulOutputComparableToCompute: true,
    baselineEquivalent: true
  },
  setupCompute: 100,
  steps: [1, 2, 3, 4, 5].map(index => ({
    id: 'request-0' + index,
    maintenanceCompute: 2,
    externalCompute: 22,
    reclaimedExternalCompute: 8,
    usefulOutput: 28,
    baselineCompute: 70
  }))
};

const report = Flow.evaluate(fixture);
equal(report.schema, Flow.REPORT_SCHEMA, 'report schema is explicit');
equal(report.totals.setupCompute, 100, 'setup cost remains visible');
equal(report.totals.maintenanceCompute, 10, 'maintenance accumulates');
equal(report.totals.externalCompute, 110, 'external compute remains visible');
equal(report.totals.reclaimedExternalCompute, 40, 'reclaimed external input remains separately visible');
equal(report.totals.usefulOutput, 140, 'useful output accumulates');
equal(report.totals.totalComputeInput, 220, 'total physical/runtime compute accounting includes setup maintenance and external input');
equal(report.totals.baselineCompute, 350, 'equivalent baseline cost accumulates');
equal(report.breakEven.setup.stepId, 'request-04', 'setup amortizes only when cumulative useful output crosses setup cost');
equal(report.breakEven.setupPlusMaintenance.stepId, 'request-04', 'setup plus maintenance amortizes independently');
equal(report.breakEven.baselineCost.stepId, 'request-03', 'persistent path can beat an equivalent repeated baseline before setup amortization');
ok(report.ratios.setupAmortization > 1, 'useful output can exceed setup cost');
ok(report.ratios.allInputEfficiency < 1, 'example does not claim output exceeds all compute inputs');
equal(report.truth.outputExceedingSetupProvesFreeCompute, false, 'setup amortization is not free compute proof');
equal(report.truth.reclaimedInputIsFreeEnergy, false, 'reclaimed capacity is not relabeled free energy');

const incomparable = JSON.parse(JSON.stringify(fixture));
incomparable.id = 'incomparable-output';
incomparable.measurement.usefulOutputComparableToCompute = false;
const withheld = Flow.evaluate(incomparable);
equal(withheld.ratios.setupAmortization, null, 'ratio is withheld when output and compute are not comparable');
equal(withheld.breakEven.setup, null, 'setup break-even is withheld when units are not comparable');
ok(withheld.warnings.some(item => /not declared comparable/.test(item)), 'incomparability produces an explicit warning');

const badReclaimed = JSON.parse(JSON.stringify(fixture));
badReclaimed.steps[0].reclaimedExternalCompute = 23;
rejects(() => Flow.evaluate(badReclaimed), /cannot exceed externalCompute/, 'reclaimed input cannot exceed declared external input');

const missingBaseline = JSON.parse(JSON.stringify(fixture));
delete missingBaseline.steps[0].baselineCompute;
rejects(() => Flow.evaluate(missingBaseline), /baselineCompute is required/, 'equivalent-baseline mode requires every step baseline');

console.log('Flowing compute accounting self-test passed ' + checks + ' checks.');
