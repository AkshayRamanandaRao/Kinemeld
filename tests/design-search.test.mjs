import test from 'node:test';
import assert from 'node:assert/strict';
import { designGrid, rankDesigns, designCsv, csvResponses, responseSeries, MAX_DESIGNS } from '../frontend/design-search.js';
import { parseSolverCsv } from '../frontend/full-resolution.js';

const model = { kind: 'mass-spring', parameters: { mass: 1, stiffness: 100, damping: 2 } };
const fields = { 'mass-spring': [['mass', 'Mass', 'kg'], ['stiffness', 'Stiffness', 'N/m'], ['damping', 'Damping', 'N·s/m']] };
const variables = [{ path: ['parameters', 'stiffness'], values: [50, 100, 150] }, { path: ['parameters', 'damping'], values: [1, 2] }];
const response = (values, times = [0, 1, 2]) => ({ torque: { times, values } });

test('bounded Cartesian candidates preserve the original model and deterministic order', () => {
  const original = structuredClone(model), cases = designGrid(model, variables, fields);
  assert.equal(cases.length, 6);
  assert.deepEqual(cases.map(item => item.values), [[50, 1], [50, 2], [100, 1], [100, 2], [150, 1], [150, 2]]);
  assert.equal(cases[3].model.parameters.damping, 2);
  cases[0].model.parameters.mass = 9;
  assert.deepEqual(model, original);
  assert.equal(cases[1].model.parameters.mass, 1);
});

test('unavailable, duplicate, non-finite or excessive input grids fail before a run', () => {
  assert.throws(() => designGrid(model, [{ path: ['parameters', 'missing'], values: [1, 2] }], fields), /unavailable/);
  assert.throws(() => designGrid(model, [variables[0], variables[0]], fields), /same property/);
  assert.throws(() => designGrid(model, [{ ...variables[0], values: [1, Infinity] }], fields), /finite/);
  assert.throws(() => designGrid(model, [{ ...variables[0], values: [1, true] }], fields), /finite/);
  assert.throws(() => designGrid(model, [{ ...variables[0], values: [1, 1] }], fields), /distinct/);
  assert.throws(() => designGrid(model, variables.map(item => ({ ...item, values: Array.from({ length: 6 }, (_, i) => i) })), fields), new RegExp(`at most ${MAX_DESIGNS}`));
});

test('feasibility prevents an attractive failed or constrained candidate from winning', () => {
  const rows = [{ values: [1], series: response([0, 2, 0]) }, { values: [2], series: response([0, 1, 0]) }, { values: [3], series: response([0, 0, 0]), error: 'solver failed' }];
  let ranked = rankDesigns(rows, { signal: 'torque', metric: 'rms', sense: 'min' });
  assert.equal(ranked.bestIndex, 1);
  ranked = rankDesigns(rows, { signal: 'torque', metric: 'rms', sense: 'min' }, [{ signal: 'torque', metric: 'peakAbs', lower: 1.5 }]);
  assert.equal(ranked.bestIndex, 0);
  assert.equal(ranked.feasibleCount, 1);
  assert.equal(ranked.rows[2].score, null);
  assert.equal(rankDesigns(rows, { signal: 'torque', metric: 'peakAbs', sense: 'max' }).bestIndex, 0);
  assert.equal(rankDesigns(rows, { signal: 'torque', metric: 'peakAbs', sense: 'target', target: 1.2 }).bestIndex, 1);
});

test('invalid/incomplete response data and unknown signals cannot become zero-score optima', () => {
  const rows = [response([0, NaN, 0]), response([0, 1], [0, 0]), response([0, 1, 2], [0, 1]), {}].map(series => ({ values: [], series }));
  const ranked = rankDesigns(rows, { signal: 'torque', metric: 'rms', sense: 'min' });
  assert.equal(ranked.bestIndex, null);
  assert(ranked.rows.every(row => row.error && !row.feasible));
  assert.throws(() => rankDesigns([], { signal: 'torque', metric: 'rms', sense: 'target' }), /objective/);
  assert.throws(() => rankDesigns([], { signal: 'torque', metric: 'rms', sense: 'min' }, [{ signal: 'torque', metric: 'final', lower: 2, upper: 1 }]), /ordered/);
  assert.equal(rankDesigns([{ values: [], series: response([1e200, 1e200, 1e200]) }], { signal: 'torque', metric: 'rms', sense: 'min' }).bestIndex, null);
  assert.equal(rankDesigns([{ values: [], series: response([1e308, 1e308, 1e308]) }], { signal: 'torque', metric: 'final', sense: 'target', target: -1e308 }).bestIndex, null);
});

test('ties are deterministic and CSV retains evaluated inputs, failures and objectives', () => {
  const objective = { signal: 'torque', label: 'Joint torque', metric: 'final', sense: 'min' };
  const ranked = rankDesigns([{ values: [1], series: response([1, 1, 1]) }, { values: [2], series: response([1, 1, 1]) }], objective);
  assert.equal(ranked.bestIndex, 0);
  const csv = designCsv([{ label: 'Mass', unit: 'kg' }], objective, ranked);
  assert.match(csv, /"Mass \(kg\)"/);
  assert.match(csv, /"1","1","1","true",""/);
  assert(designCsv([{ label: '=formula', unit: '' }], objective, ranked).includes('"\'=formula"'));
});

test('response catalog and extraction use complete CSV channels with explicit units', () => {
  const data = parseSolverCsv('time,id,label,x,y,z,rx,ry,rz,vx,vy,vz,wx,wy,wz,jointFriction:hinge:torque_Nm\n0,arm,Arm,0,0,0,0,0,0,0,0,0,0,0,0,2\n1,arm,Arm,0,0,1,0,0,30,0,0,1,0,0,0.2,3\n');
  const catalog = csvResponses(data, { bodies: [{ id: 'arm', name: 'Robot arm' }], joints: [{ id: 'hinge', name: 'Elbow' }] });
  const torque = catalog.find(item => item.key.includes('torque_Nm'));
  assert.equal(torque.unit, 'N·m'); assert.match(torque.label, /Elbow/);
  assert.deepEqual(responseSeries(data, torque.key).values, [2, 3]);
  assert(catalog.some(item => item.label === 'Robot arm · angular velocity Z' && item.unit === 'rad/s'));
  assert.throws(() => responseSeries(data, '["global","constructor"]'), /absent/);
  assert.throws(() => responseSeries(data, '["node","missing","x"]'), /absent/);
  assert.throws(() => responseSeries(data, '["global","x","extra"]'), /absent/);
  assert.deepEqual(csvResponses({ times: [0, 1] }, {}), []);
  const scalar = parseSolverCsv('time,velocity,value\n0,0,0\n1,1,2');
  assert.equal(csvResponses(scalar, { kind: 'suspension' }).find(item=>item.label==='velocity').unit, 'm/s');
  assert.equal(csvResponses(scalar, { kind: 'pendulum' }).find(item=>item.label==='velocity').unit, 'rad/s');
});
