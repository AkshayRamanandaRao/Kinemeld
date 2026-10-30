import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import { faceAt, cadPlacement, worldFeature, inBodyFrame, jointFromFeature, frameFromFeature, measureFeatures, worldFromBody, alongAxis, inPlane } from '../frontend/cad-features.js';
import { frameAxis } from '../frontend/frame-editor.js';

const close = (actual, expected, tolerance = 1e-9) => {
  for (const key of ['x', 'y', 'z']) assert(Math.abs(actual[key] - expected[key]) < tolerance, `${key}: ${actual[key]} != ${expected[key]}`);
};
const cylinder = { type: 'cylinder', triangles: [10, 20], centre: [0.1, 0, 0], axis: [1, 0, 0], radius: 0.0275, length: 0.04 };
const plane = { type: 'plane', triangles: [30, 4], point: [0.12, 0, 0], normal: [1, 0, 0] };

test('faceAt finds the face owning a triangle', () => {
  const part = { faces: [cylinder, plane] };
  assert.equal(faceAt(part, 10), cylinder);
  assert.equal(faceAt(part, 29), cylinder);
  assert.equal(faceAt(part, 33), plane);
  assert.equal(faceAt(part, 34), null);
  assert.equal(faceAt({}, 0), null);
});

test('an unattached part keeps CAD coordinates and labels principal axes', () => {
  const feature = worldFeature(cylinder, cadPlacement(null, null));
  close(feature.point, { x: 0.1, y: 0, z: 0 });
  assert.equal(feature.label, 'Cylinder Ø55.0 mm · axis +x');
});

test('an attached part follows its body pose relative to the binding pose', () => {
  // Bound at the CAD origin, the body starts at (1, 2, 0) turned 90° about z: CAD +x becomes world +y.
  const placement = cadPlacement({ body: 'arm', pose: { x: 0, y: 0, z: 0, rx: 0, ry: 0, rz: 0 } }, { id: 'arm', pose: { x: 1, y: 2, z: 0, rx: 0, ry: 0, rz: 90 } });
  const feature = worldFeature(cylinder, placement);
  close(feature.point, { x: 1, y: 2.1, z: 0 });
  close(feature.axis, { x: 0, y: 1, z: 0 });
});

test('a circular edge gives its centre and axis, wherever on the rim it was picked', () => {
  const rim = { type: 'circle', centre: [0.1, 0.02, 0], axis: [0, 0, -1], radius: 0.01 };
  const placement = cadPlacement({ body: 'arm', pose: { x: 0, y: 0, z: 0, rx: 0, ry: 0, rz: 0 } }, { id: 'arm', pose: { x: 1, y: 0, z: 0, rx: 0, ry: 0, rz: 90 } });
  const feature = worldFeature(rim, placement, new THREE.Vector3(1.0, 0.11, 0.0));
  close(feature.point, { x: 0.98, y: 0.1, z: 0 });
  close(feature.axis, { x: 0, y: 0, z: -1 });
  assert.equal(feature.label, 'Circle Ø20.0 mm · axis −z');
  const joint = jointFromFeature({ bodies: [{ id: 'arm', pose: { x: 1, y: 0, z: 0, rx: 0, ry: 0, rz: 90 } }] }, { type: 'revolute', a: 'ground', b: 'arm' }, feature);
  close(joint.anchorA, { x: 0.98, y: 0.1, z: 0 });
  close(joint.anchorB, { x: 0.1, y: 0.02, z: 0 });
});

test('a plane anchor is the clicked point projected onto the plane', () => {
  const feature = worldFeature(plane, cadPlacement(null, null), new THREE.Vector3(0.1205, 0.01, -0.02));
  close(feature.point, { x: 0.12, y: 0.01, z: -0.02 });
  assert.equal(feature.label, 'Plane · normal +x');
});

test('joint ends share the picked point and axis, expressed in each body frame', () => {
  const model = { bodies: [{ id: 'arm', pose: { x: 1, y: 0, z: 0, rx: 0, ry: 0, rz: 90 } }] };
  const feature = { point: new THREE.Vector3(1, 0.5, 0), axis: new THREE.Vector3(1, 0, 0) };
  const revolute = jointFromFeature(model, { type: 'revolute', a: 'ground', b: 'arm' }, feature);
  close(revolute.anchorA, { x: 1, y: 0.5, z: 0 });
  close(revolute.axisA, { x: 1, y: 0, z: 0 });
  close(revolute.anchorB, { x: 0.5, y: 0, z: 0 });
  close(revolute.axisB, { x: 0, y: -1, z: 0 });
  const prismatic = jointFromFeature(model, { type: 'prismatic', a: 'ground', b: 'arm' }, feature);
  assert('axisA' in prismatic && !('axisB' in prismatic));
  const spherical = jointFromFeature(model, { type: 'spherical', a: 'ground', b: 'arm' }, feature);
  assert.deepEqual(Object.keys(spherical).sort(), ['anchorA', 'anchorB']);
  const universal = jointFromFeature(model, { type: 'universal', a: 'ground', b: 'arm' }, feature);
  assert.deepEqual(Object.keys(universal).sort(), ['anchorA', 'anchorB']);
});

test('a frame placed on a feature has its origin there and local +Z along the axis', () => {
  const model = { bodies: [{ id: 'arm', pose: { x: 0, y: 0, z: 0.5, rx: 30, ry: -20, rz: 45 } }] };
  for (const axis of [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, 0, -1], [0.6, 0, 0.8]]) {
    const feature = { point: new THREE.Vector3(0.2, -0.1, 0.4), axis: new THREE.Vector3(...axis).normalize() };
    for (const body of ['ground', 'arm']) {
      const frame = { id: 'f', body, ...frameFromFeature(model, { body }, feature) };
      const expected = inBodyFrame(model.bodies.find((item) => item.id === body), feature.point, feature.axis);
      close(frame.translation, expected.point);
      close(frameAxis(frame, 'z'), expected.direction, 1e-6);
    }
  }
});

test('measurement reports distance, components and the angle between axes', () => {
  const first = { point: new THREE.Vector3(0, 0, 0), axis: new THREE.Vector3(1, 0, 0) };
  const second = { point: new THREE.Vector3(0.03, 0.04, 0), axis: new THREE.Vector3(0, -1, 0) };
  const result = measureFeatures(first, second);
  assert(Math.abs(result.distance - 0.05) < 1e-12);
  close(result.delta, { x: 0.03, y: 0.04, z: 0 });
  assert(Math.abs(result.angle - 90) < 1e-9);
  // Opposite axes are parallel lines: 0°.
  assert(Math.abs(measureFeatures(first, { ...second, axis: new THREE.Vector3(-1, 0, 0) }).angle) < 1e-9);
  assert.equal(measureFeatures({ point: first.point }, second).angle, null);
});

test('world and body frames are inverse placements', () => {
  const body = { pose: { x: 0.3, y: -0.2, z: 1, rx: 20, ry: -35, rz: 60 } };
  const world = worldFromBody(body, { x: 0.1, y: 0.2, z: -0.3 }, { x: 0, y: 0, z: 1 });
  const back = inBodyFrame(body, world.point, world.direction);
  close(back.point, { x: 0.1, y: 0.2, z: -0.3 });
  close(back.direction, { x: 0, y: 0, z: 1 });
});

test('dragging along an axis follows the ray and snaps to millimetres', () => {
  const origin = new THREE.Vector3(1, 2, 3), axis = new THREE.Vector3(0, 0, 2);
  // A ray along -y passing 0.12345 m up the axis and 0.5 m off it to the side.
  const ray = new THREE.Ray(new THREE.Vector3(1.5, 5, 3.12345), new THREE.Vector3(0, -1, 0));
  const moved = alongAxis(origin, axis, ray);
  assert(Math.abs(moved.offset - 0.123) < 1e-12);
  close(moved.point, { x: 1, y: 2, z: 3.123 });
  assert.equal(alongAxis(origin, axis, new THREE.Ray(new THREE.Vector3(1, 2, 0), new THREE.Vector3(0, 0, 1))), null);
});

test('dragging in a plane stays in the plane and snaps both directions', () => {
  const origin = new THREE.Vector3(0, 0, 1), normal = new THREE.Vector3(0, 0, 1);
  const ray = new THREE.Ray(new THREE.Vector3(0.0304, -0.0196, 5), new THREE.Vector3(0, 0, -1));
  const moved = inPlane(origin, normal, ray);
  close(moved.point, { x: 0.03, y: -0.02, z: 1 });
  assert(Math.abs(moved.offset - Math.hypot(0.03, 0.02)) < 1e-12);
  assert.equal(inPlane(origin, normal, new THREE.Ray(new THREE.Vector3(0, 0, 2), new THREE.Vector3(1, 0, 0))), null);
});
