/** Rotary drives through the interface: robot-arm study, drive editing, MBDyn torque results and CSV. */
import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { readFile } from 'node:fs/promises';

const base = process.env.MBDYN_STUDIO_URL || 'http://127.0.0.1:8768';
const browser = await chromium.launch({ headless: true, args: ['--enable-unsafe-swiftshader'] });
const page = await browser.newPage({ viewport: { width: 1440, height: 960 }, acceptDownloads: true });
const errors = [];
page.on('pageerror', (error) => errors.push(error.message));
page.on('dialog', (dialog) => dialog.accept());
await page.route('**/api/tour-preference', (route) => route.fulfill({ json: { enabled: false } }));
try {
  await page.goto(base);
  await page.waitForFunction(() => document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
  await page.locator('#examplesButton').click();
  await page.locator('.example-card').filter({ has: page.getByRole('heading', { name: 'Robot arm inverse dynamics', exact: true }) }).getByRole('button').click();
  await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('Robot arm inverse dynamics loaded'), null, { timeout: 240000 });

  // The inspector shows each drive's law and parameters.
  await page.locator('[data-step="model"]').click();
  await page.locator('#modelTree [data-entity="joint-base_yaw"]').click();
  assert.equal(await page.locator('#spatial-joint-base_yaw-drive-law').inputValue(), 'speed');
  assert.equal(Number(await page.locator('#spatial-joint-base_yaw-motion-speedDegPerS').inputValue()), 45);
  await page.locator('#modelTree [data-entity="joint-shoulder"]').click();
  assert.equal(await page.locator('#spatial-joint-shoulder-drive-law').inputValue(), 'oscillation');

  // Real MBDyn run: every axis follows its command and reports a torque.
  const response = page.waitForResponse((r) => r.url().endsWith('/api/run') && r.request().method() === 'POST', { timeout: 300000 });
  await page.locator('#runButton').click();
  const result = await (await response).json();
  assert(result.ok, JSON.stringify(result.error));
  assert.deepEqual(result.samples[0].rotaryDrives.map((drive) => drive.id).sort(), ['base_yaw', 'elbow', 'shoulder']);
  for (const sample of result.samples) for (const drive of sample.rotaryDrives) assert(Math.abs(drive.angle - drive.commandedAngle) < 1e-6);
  assert(result.samples.some((sample) => Math.abs(sample.rotaryDrives.find((drive) => drive.id === 'shoulder').torque) > 1));

  await page.locator('#signalSelect').selectOption({ label: 'Rotary drive torque (hinge reaction)' });
  await page.locator('#jointSelect').selectOption('shoulder');
  const curve = await page.locator('#plot path.plot-curve').first().getAttribute('d');
  assert((curve.match(/[ML]/g) || []).length > 100 && !/NaN|Infinity/.test(curve));
  await page.locator('#signalSelect').selectOption({ label: 'Rotary drive angle · measured / commanded' });
  assert.equal(await page.locator('#plot path.plot-curve').count(), 2);

  const download = page.waitForEvent('download');
  await page.locator('#csvButton').click();
  const csv = await readFile(await (await download).path(), 'utf8');
  for (const column of ['rotaryDrive:shoulder:angle_rad', 'rotaryDrive:shoulder:torque_Nm', 'rotaryDrive:elbow:power_W']) assert(csv.includes(column), column);

  // Editing a drive makes the results stale; switching it off frees the hinge.
  await page.locator('[data-step="model"]').click();
  await page.locator('#modelTree [data-entity="joint-elbow"]').click();
  await page.locator('#spatial-joint-elbow-motion-amplitudeDeg').fill('30');
  await page.locator('#spatial-joint-elbow-motion-amplitudeDeg').dispatchEvent('change');
  await page.waitForFunction(() => document.querySelector('#resultSource')?.textContent.includes('Stale'));
  await page.locator('#spatial-joint-elbow-drive-law').selectOption('none');
  assert.equal(await page.locator('#spatial-joint-elbow-motion-amplitudeDeg').count(), 0);
  assert.deepEqual(errors, []);
  console.log('Rotary drives: inspector laws, real MBDyn torques, angle tracking, plots, CSV and stale state passed.');
} finally {
  await browser.close();
}
