import test from 'node:test';
import assert from 'node:assert/strict';
import { studyParameters, parameterValue, caseModel, parseValues, suggestValues, caseSummary, summaryCsv, caseColors, pathKey, MAX_CASES } from '../frontend/studies.js';

const spatial = {
  kind: 'spatial-assembly', name: 'Drop',
  bodies: [{ id: 'wheel', name: 'Wheel', mass: 30, inertia: { xx: 1, yy: 1, zz: 1, xy: 0, xz: 0, yz: 0 }, centerOfMass: { x: 0, y: 0, z: 0 }, pose: { x: 0, y: 0, z: 0.6, rx: 0, ry: 0, rz: 0 }, velocity: { vx: 0, vy: 0, vz: -1, wx: 0, wy: 0, wz: 0 } }],
  joints: [{ id: 'hub', type: 'revolute', a: 'ground', b: 'wheel', anchorA: { x: 0, y: 0, z: 0 }, axisA: { x: 0, y: 1, z: 0 }, motion: { amplitude: 10, frequencyHz: 2 } }],
  forces: [{ id: 'strut', type: 'oleo-strut', a: 'ground', b: 'wheel', anchorA: { x: 0, y: 0, z: 1 }, pressure: 1.2e6, gasVolume: 2e-4 }],
  contacts: [{ id: 'tyre', body: 'wheel', center: { x: 0, y: 0, z: 0 }, radius: 0.3, planePoint: { x: 0, y: 0, z: 0 }, planeNormal: { x: 0, y: 0, z: 1 }, stiffness: 2e5, damping: 500 }],
  jointTorques: [{ id: 'drive', joint: 'hub', amplitude: 3, frequencyHz: 1, offset: 0 }],
  frames: [{ id: 'f', body: 'wheel', translation: { x: 1, y: 2, z: 3 }, rotation: { rx: 0, ry: 0, rz: 0 } }],
  simulation: { duration: 1, step: 0.001 },
};

test('assembly parameters list physical inputs and leave out geometry, vectors and frames', () => {
  const parameters = studyParameters(spatial);
  const keys = parameters.map((item) => pathKey(item.path));
  for (const key of ['bodies/wheel/mass', 'bodies/wheel/pose/z', 'bodies/wheel/velocity/vz', 'forces/strut/pressure', 'contacts/tyre/stiffness', 'contacts/tyre/damping', 'contacts/tyre/radius', 'joints/hub/motion/frequencyHz', 'jointTorques/drive/amplitude'])
    assert(keys.includes(key), `${key} missing from ${keys.join(', ')}`);
  for (const key of keys) assert.doesNotMatch(key, /inertia|centerOfMass|anchor|axis|planePoint|planeNormal|center\/|pose\/r|frames|simulation/);
  assert.deepEqual(keys.filter((key) => key.startsWith('contacts/')), ['contacts/tyre/stiffness', 'contacts/tyre/damping', 'contacts/tyre/radius'], 'design inputs come first');
  assert.equal(keys[0], 'bodies/wheel/mass');
  const stiffness = parameters.find((item) => pathKey(item.path) === 'contacts/tyre/stiffness');
  assert.deepEqual([stiffness.group, stiffness.label, stiffness.unit, stiffness.value], ['Contact tyre', 'stiffness', 'N/m', 2e5]);
  const torque = parameters.find((item) => pathKey(item.path) === 'jointTorques/drive/amplitude');
  assert.equal(torque.unit, 'N·m');
  const mass = parameters.find((item) => pathKey(item.path) === 'bodies/wheel/mass');
  assert.equal(mass.group, 'Body Wheel');
  const drive = parameters.find((item) => pathKey(item.path) === 'joints/hub/motion/frequencyHz');
  assert.deepEqual([drive.label, drive.unit], ['drive frequency', 'Hz']);
});

test('a velocity shared by every body is one input that sets them all', () => {
  const drop = structuredClone(spatial);
  drop.bodies.push({ ...structuredClone(drop.bodies[0]), id: 'frame', name: 'Frame', velocity: { vx: 0, vy: 0, vz: -1, wx: 0, wy: 0, wz: 0 } });
  const parameters = studyParameters(drop);
  const shared = parameters.filter((item) => item.path[1] === '*');
  assert.deepEqual(shared.map((item) => [pathKey(item.path), item.group, item.label, item.unit, item.value]), [['bodies/*/velocity/vz', 'All bodies', 'initial velocity vz', 'm/s', -1]], 'zero and unequal velocities are not offered');
  assert.equal(parameters[0], shared[0], 'a shared drop speed is listed first');
  const copy = caseModel(drop, ['bodies', '*', 'velocity', 'vz'], -3);
  assert.deepEqual(copy.bodies.map((body) => body.velocity.vz), [-3, -3]);
  assert.equal(parameterValue(copy, ['bodies', '*', 'velocity', 'vz']), -3);
  drop.bodies[1].velocity.vz = -2;
  assert(!studyParameters(drop).some((item) => item.path[1] === '*'));
});

test('template parameters come from the field definitions', () => {
  const model = { kind: 'mass-spring', parameters: { mass: 1, stiffness: 100, damping: 0.5, displacement: 0.1 } };
  const fields = { 'mass-spring': [['mass', 'Translating mass', 'kg'], ['stiffness', 'Spring stiffness', 'N/m'], ['missing', 'Missing', '']] };
  assert.deepEqual(studyParameters(model, fields).map((item) => [pathKey(item.path), item.label, item.unit, item.value]), [['parameters/mass', 'Translating mass', 'kg', 1], ['parameters/stiffness', 'Spring stiffness', 'N/m', 100]]);
});

test('a case model changes only the swept input', () => {
  const path = ['contacts', 'tyre', 'stiffness'];
  const copy = caseModel(spatial, path, 4e5);
  assert.equal(parameterValue(copy, path), 4e5);
  assert.equal(parameterValue(spatial, path), 2e5);
  copy.contacts[0].stiffness = spatial.contacts[0].stiffness;
  assert.deepEqual(copy, spatial);
  assert.equal(parameterValue(caseModel(spatial, ['bodies', 'wheel', 'velocity', 'vz'], -2), ['bodies', 'wheel', 'velocity', 'vz']), -2);
  assert.throws(() => caseModel(spatial, ['contacts', 'gone', 'stiffness'], 1), /no longer exists/);
});

test('values are parsed, de-duplicated and bounded', () => {
  assert.deepEqual(parseValues('1e4, 2e4; 4e4 2e4\n8e4'), [1e4, 2e4, 4e4, 8e4]);
  assert.throws(() => parseValues('1, two'), /“two” is not a number/);
  assert.throws(() => parseValues('5, 5'), /at least two/);
  assert.throws(() => parseValues(Array.from({ length: MAX_CASES + 1 }, (_, i) => i).join(',')), /at most/);
  assert.deepEqual(suggestValues(2e5), [1e5, 1.5e5, 2e5, 3e5, 4e5]);
  assert.deepEqual(suggestValues(0.123456), [0.0617, 0.0926, 0.123, 0.185, 0.247]);
  assert.deepEqual(suggestValues(0), []);
});

test('case summaries report extremes, their times, rms and the final value', () => {
  const times = [0, 1, 2, 3], values = [0, 4, -2, NaN];
  const summary = caseSummary(times, values);
  assert.deepEqual([summary.max, summary.maxAt, summary.min, summary.minAt, summary.final], [4, 1, -2, 2, -2]);
  assert(Math.abs(summary.rms - Math.sqrt((0.5 * 16 + 0.5 * (16 + 4)) / 2)) < 1e-12);
  const csv = summaryCsv({ group: 'Contact tyre', label: 'stiffness', unit: 'N/m' }, { label: 'Contact force', unit: 'N' }, [{ value: 2e5, summary }]).split('\n');
  assert.equal(csv[0], '"Contact tyre stiffness (N/m)","Contact force max (N)","Contact force time of max (s)","Contact force min (N)","Contact force time of min (s)","Contact force rms (N)","Contact force final (N)"');
  assert.match(csv[1], /^200000,4,1,-2,2,[\d.]+,-2$/);
});

test('case colours are distinct, ordered and valid hex', () => {
  for (const count of [1, 2, 5, MAX_CASES]) {
    const colors = caseColors(count);
    assert.equal(colors.length, count);
    assert(colors.every((color) => /^#[0-9a-f]{6}$/.test(color)));
    assert.equal(new Set(colors).size, count);
  }
  assert.equal(caseColors(2)[0], '#2a78d6');
  assert.equal(caseColors(2)[1], '#e8902a');
});


test('robot drive and brake inputs have editor units and paired centers stay geometric', () => {
  const model = structuredClone(spatial);
  model.joints[0].friction = { coefficient: .3, radius: .1, preload: 20 };
  model.joints[0].motion = { speedDegPerS: 30, rampTime: .2 };
  model.contacts[0].otherCenter = { x: 1, y: 2, z: 3 };
  model.jointTorques[0] = { id: 'drive', joint: 'hub', type: 'servo', kp: 8, kd: 1, targetAngleDeg: 30, rampTime: .4, torqueLimit: 2 };
  const parameters = studyParameters(model);
  assert(!parameters.some(item => pathKey(item.path).includes('otherCenter')));
  for (const [path, unit] of [['friction.coefficient', ''], ['friction.radius', 'm'], ['friction.preload', 'N'], ['motion.rampTime', 's']]) {
    const input = parameters.find(item => pathKey(item.path) === `joints/hub/${path.replaceAll('.', '/')}`);
    assert(input, path);
    assert.equal(input.unit, unit);
  }
  for (const [key, unit] of [['kp', 'N·m/rad'], ['kd', 'N·m·s/rad'], ['targetAngleDeg', '°'], ['rampTime', 's'], ['torqueLimit', 'N·m']])
    assert.equal(parameters.find(item => pathKey(item.path) === `jointTorques/drive/${key}`).unit, unit);
});
