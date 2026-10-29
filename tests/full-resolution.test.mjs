import test from 'node:test';
import assert from 'node:assert/strict';
import { columnFor, parseSolverCsv, fullSeries, seriesStatistics, envelope } from '../frontend/full-resolution.js';

const csv = [
  'time,id,label,x,y,z,rx,ry,rz,vx,vy,vz,wx,wy,wz,force:spring:length_m,force:spring:extension_m,force:spring:rate_m_s,force:spring:tension_N,jointReaction:hinge:force_x_N,jointReaction:hinge:force_y_N,jointReaction:hinge:force_z_N,jointReaction:hinge:moment_x_Nm,jointReaction:hinge:moment_y_Nm,jointReaction:hinge:moment_z_Nm',
  '0,a,A,0,0,1,0,0,0,0,0,0,0,0,1,1,0,0,0,1,2,3,4,5,6',
  '0,b,B,1,0,1,0,0,0,0,0,0,0,0,0,1,0,0,0,1,2,3,4,5,6',
  '0.5,a,A,0.2,0,1,0,0,90,0,0,0,0,0,1,1.5,0.5,1,10,1,2,30,4,5,6',
  '0.5,b,B,1.1,0,1,0,0,0,0,0,0,0,0,0,1.5,0.5,1,10,1,2,30,4,5,6',
  '1,a,A,0.1,0,1,0,0,180,0,0,0,0,0,1,1.2,0.2,-1,4,1,2,3,4,5,6',
  '1,b,B,1.2,0,1,0,0,0,0,0,0,0,0,0,1.2,0.2,-1,4,1,2,3,4,5,6',
].join('\n');

test('channel keys map to solver CSV columns', () => {
  assert.deepEqual(columnFor('node:a:x'), { node: 'a', column: 'x' });
  assert.deepEqual(columnFor('force:spring:force'), { column: 'force:spring:tension_N' });
  assert.deepEqual(columnFor('oleo:oleo:gasPressure'), { column: 'force:oleo:gasPressure_Pa' });
  assert.deepEqual(columnFor('reaction:hinge:moment.z'), { column: 'jointReaction:hinge:moment_z_Nm' });
  assert.deepEqual(columnFor('load:pad:force.z'), { column: 'load:pad:force_z_N' });
  assert.deepEqual(columnFor('actuationWork'), { column: 'actuationWork_J' });
  assert.equal(columnFor('angle'), null);
});

test('rows are grouped by time and body', () => {
  const data = parseSolverCsv(csv);
  assert.deepEqual(data.times, [0, 0.5, 1]);
  assert.deepEqual(fullSeries(data, 'node:b:x'), [1, 1.1, 1.2]);
  assert.deepEqual(fullSeries(data, 'force:spring:force'), [0, 10, 4]);
  assert.deepEqual(fullSeries(data, 'reaction:hinge:force.z'), [3, 30, 3]);
  const bw = fullSeries(data, 'node:a:bwz', (n) => [0, 0, n.wz]);
  assert.deepEqual(bw, [1, 1, 1]);
});

test('statistics find the extreme and its time and use time-weighted RMS', () => {
  const stats = seriesStatistics([0, 1, 2, 4], [0, 2, -2, 0]);
  assert.equal(stats.max, 2);
  assert.equal(stats.maxAt, 1);
  assert.equal(stats.min, -2);
  assert.equal(stats.minAt, 2);
  // Trapezoid of v² over 4 s: (0+4)/2·1 + (4+4)/2·1 + (4+0)/2·2 = 10.
  assert.ok(Math.abs(stats.rms - Math.sqrt(10 / 4)) < 1e-12);
});

test('envelope keeps a single-sample spike that uniform decimation would drop', () => {
  const times = Array.from({ length: 10001 }, (_, i) => i * 1e-4);
  const values = times.map((_, i) => (i === 5003 ? 50 : Math.sin(i / 300)));
  const points = envelope(times, values, 0, 1, 200);
  assert.ok(points.length <= 400);
  assert.ok(points.some((p) => p && p.v === 50 && Math.abs(p.t - 0.5003) < 1e-9));
  const stride = values.filter((_, i) => i % 50 === 0);
  assert.ok(!stride.includes(50));
});
