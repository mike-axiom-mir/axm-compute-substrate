'use strict';

const EXPERIMENT_SCHEMA = 'axm.flowing-compute-experiment/v0.1';
const REPORT_SCHEMA = 'axm.flowing-compute-report/v0.1';

function finiteNonNegative(value, label) {
  const number = Number(value);
  if (!Number.isFinite(number) || number < 0) throw new Error(label + ' must be a finite non-negative number');
  return number;
}

function nonEmptyText(value, label) {
  const text = String(value == null ? '' : value).trim();
  if (!text) throw new Error(label + ' is required');
  return text;
}

function safeRatio(numerator, denominator) {
  if (denominator === 0) return numerator === 0 ? 0 : null;
  return numerator / denominator;
}

function firstStep(steps, predicate) {
  for (let index = 0; index < steps.length; index += 1) {
    if (predicate(steps[index])) return { stepIndex: index + 1, stepId: steps[index].id };
  }
  return null;
}

function compileExperiment(raw) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new Error('experiment must be an object');
  if (raw.schema !== EXPERIMENT_SCHEMA) throw new Error('unsupported experiment schema');

  const measurement = raw.measurement || {};
  const sameUnit = measurement.usefulOutputComparableToCompute === true;
  const baselineEquivalent = measurement.baselineEquivalent === true;

  const experiment = {
    schema: EXPERIMENT_SCHEMA,
    id: nonEmptyText(raw.id, 'id'),
    title: nonEmptyText(raw.title || raw.id, 'title'),
    measurement: {
      unit: nonEmptyText(measurement.unit, 'measurement.unit'),
      usefulOutputComparableToCompute: sameUnit,
      baselineEquivalent,
      note: String(measurement.note || '')
    },
    setupCompute: finiteNonNegative(raw.setupCompute, 'setupCompute'),
    steps: []
  };

  const inputSteps = Array.isArray(raw.steps) ? raw.steps : [];
  if (!inputSteps.length) throw new Error('at least one step is required');

  const ids = new Set();
  for (const rawStep of inputSteps) {
    const id = nonEmptyText(rawStep && rawStep.id, 'step.id');
    if (ids.has(id)) throw new Error('duplicate step id: ' + id);
    ids.add(id);

    const externalCompute = finiteNonNegative(rawStep.externalCompute || 0, id + '.externalCompute');
    const reclaimedExternalCompute = finiteNonNegative(rawStep.reclaimedExternalCompute || 0, id + '.reclaimedExternalCompute');
    if (reclaimedExternalCompute > externalCompute) throw new Error(id + '.reclaimedExternalCompute cannot exceed externalCompute');

    const baselineCompute = rawStep.baselineCompute == null ? null : finiteNonNegative(rawStep.baselineCompute, id + '.baselineCompute');
    if (baselineEquivalent && baselineCompute == null) throw new Error(id + '.baselineCompute is required when baselineEquivalent=true');

    experiment.steps.push({
      id,
      maintenanceCompute: finiteNonNegative(rawStep.maintenanceCompute || 0, id + '.maintenanceCompute'),
      externalCompute,
      reclaimedExternalCompute,
      usefulOutput: finiteNonNegative(rawStep.usefulOutput || 0, id + '.usefulOutput'),
      baselineCompute,
      note: String(rawStep.note || '')
    });
  }

  return experiment;
}

function evaluate(raw) {
  const experiment = compileExperiment(raw);
  let maintenance = 0;
  let external = 0;
  let reclaimed = 0;
  let useful = 0;
  let baseline = 0;

  const timeline = experiment.steps.map((step, index) => {
    maintenance += step.maintenanceCompute;
    external += step.externalCompute;
    reclaimed += step.reclaimedExternalCompute;
    useful += step.usefulOutput;
    if (step.baselineCompute != null) baseline += step.baselineCompute;

    const totalInput = experiment.setupCompute + maintenance + external;
    const row = {
      stepIndex: index + 1,
      id: step.id,
      cumulative: {
        setupCompute: experiment.setupCompute,
        maintenanceCompute: maintenance,
        externalCompute: external,
        reclaimedExternalCompute: reclaimed,
        usefulOutput: useful,
        totalComputeInput: totalInput,
        baselineCompute: experiment.measurement.baselineEquivalent ? baseline : null
      },
      boundaries: {
        setupBreakEven: experiment.measurement.usefulOutputComparableToCompute ? useful >= experiment.setupCompute : null,
        setupPlusMaintenanceBreakEven: experiment.measurement.usefulOutputComparableToCompute ? useful >= experiment.setupCompute + maintenance : null,
        baselineCostBreakEven: experiment.measurement.baselineEquivalent ? totalInput <= baseline : null
      }
    };
    return row;
  });

  const final = timeline[timeline.length - 1];
  const comparable = experiment.measurement.usefulOutputComparableToCompute;
  const totalComputeInput = final.cumulative.totalComputeInput;

  return {
    schema: REPORT_SCHEMA,
    experiment: {
      id: experiment.id,
      title: experiment.title,
      unit: experiment.measurement.unit,
      usefulOutputComparableToCompute: comparable,
      baselineEquivalent: experiment.measurement.baselineEquivalent
    },
    totals: final.cumulative,
    ratios: {
      setupAmortization: comparable ? safeRatio(useful, experiment.setupCompute) : null,
      setupPlusMaintenanceAmortization: comparable ? safeRatio(useful, experiment.setupCompute + maintenance) : null,
      allInputEfficiency: comparable ? safeRatio(useful, totalComputeInput) : null,
      reclaimedShareOfExternalInput: safeRatio(reclaimed, external)
    },
    breakEven: {
      setup: comparable ? firstStep(timeline, row => row.boundaries.setupBreakEven === true) : null,
      setupPlusMaintenance: comparable ? firstStep(timeline, row => row.boundaries.setupPlusMaintenanceBreakEven === true) : null,
      baselineCost: experiment.measurement.baselineEquivalent ? firstStep(timeline, row => row.boundaries.baselineCostBreakEven === true) : null
    },
    timeline,
    warnings: [
      ...(comparable ? [] : ['Useful output was not declared comparable to compute input; amortization and efficiency ratios are withheld.']),
      ...(experiment.measurement.baselineEquivalent ? [] : ['No equivalent repeat-from-zero baseline was declared; baseline break-even is withheld.']),
      ...(reclaimed > 0 ? ['Reclaimed/idle compute remains real external compute input; reclaimed does not mean free.'] : [])
    ],
    truth: {
      outputExceedingSetupProvesFreeCompute: false,
      allInputEfficiencyAboveOneProvesPhysicalOverUnity: false,
      reclaimedInputIsFreeEnergy: false,
      continuingHostResourcesRemainExternalInput: true,
      reportIsBoundedAccountingNotGeneralProof: true
    }
  };
}

module.exports = { EXPERIMENT_SCHEMA, REPORT_SCHEMA, compileExperiment, evaluate };

if (require.main === module) {
  const fs = require('fs');
  const file = process.argv[2];
  if (!file) {
    console.error('Usage: node tools/flowing-compute-accounting.js EXPERIMENT.json');
    process.exit(2);
  }
  try {
    const input = JSON.parse(fs.readFileSync(file, 'utf8'));
    process.stdout.write(JSON.stringify(evaluate(input), null, 2) + '\n');
  } catch (error) {
    console.error('Flowing compute accounting refused: ' + error.message);
    process.exit(1);
  }
}
