/** Featured parameter study: the gear drop opens with its sink-speed study preloaded, runs it, and saved projects keep the set-up. */
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
const column = (index) => page.locator('#studyTable tbody tr').evaluateAll((rows, i) => rows.map((row) => Number(row.cells[i].textContent.trim().split(' ')[0])), index);
try {
  await page.goto(base);
  await page.waitForFunction(() => document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
  await page.locator('#examplesButton').click();
  const card = page.locator('.example-card').filter({ has: page.getByRole('heading', { name: 'Oleo-pneumatic gear drop test', exact: true }) });
  assert.equal(await card.locator('.example-study').textContent(), 'Parameter study included · sink speed 1.5–3 m/s');
  await card.getByRole('button').click();
  await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('gear drop test loaded'), null, { timeout: 120000 });

  // The Solve card is preloaded with the featured study.
  await page.locator('[data-step="simulate"]').click();
  assert.equal(await page.locator('#studyParameter').inputValue(), 'bodies/*/velocity/vz');
  assert.equal(await page.locator('#studyValues').inputValue(), '-3, -2.5, -1.5');
  assert.match(await page.locator('#studyHint').textContent(), /Current value -2 m\/s/);
  await page.locator('#studyRunButton').click();
  await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('Parameter study complete · 4 of 4 cases solved'), null, { timeout: 600000 });

  // The study opens on its response quantity; faster descent means a higher tyre load.
  assert.equal(await page.locator('#signalSelect option:checked').textContent(), 'Contact normal force (reconstructed)');
  assert.deepEqual(await column(0), [-3, -2.5, -2, -1.5]);
  const peaks = await column(1);
  assert(peaks.every((peak, i) => i === 0 || peak < peaks[i - 1]), `peak tyre load should fall as the descent slows: ${peaks}`);
  assert.match(await page.locator('#studySummary').textContent(), /All bodies · initial velocity vz \(m\/s\), 4 cases/);

  // A saved project keeps the study set-up; reopening it preloads the Solve card again.
  const saved = page.waitForEvent('download');
  await page.locator('#saveButton').click();
  const path = await (await saved).path();
  const project = JSON.parse(await readFile(path, 'utf8'));
  assert.deepEqual(project.view.study, { input: 'bodies/*/velocity/vz', values: [-3, -2.5, -1.5], response: 'Contact normal force (reconstructed)' });
  await page.locator('#examplesButton').click();
  await page.locator('.example-card').filter({ has: page.getByRole('heading', { name: 'Damped oscillator', exact: true }) }).getByRole('button', { name: /Open example/ }).click();
  await page.evaluate(() => { document.querySelector('#notice').textContent = 'Waiting for import'; });
  await page.locator('#projectFile').setInputFiles(path);
  await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('Project imported'), null, { timeout: 120000 });
  await page.locator('[data-step="simulate"]').click();
  assert.equal(await page.locator('#studyParameter').inputValue(), 'bodies/*/velocity/vz');
  assert.equal(await page.locator('#studyValues').inputValue(), '-3, -2.5, -1.5');
  assert.deepEqual(errors, []);
  console.log(`Featured study: gear drop sink-speed study preloaded, peak tyre loads ${peaks.map((peak) => peak.toFixed(0)).join(' > ')} N, set-up saved and restored.`);
} finally {
  await browser.close();
}
