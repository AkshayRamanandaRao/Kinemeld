/** Contact friction: the spin-up drag study opens with friction set, solves, plots the friction force at full resolution and edits it. */
import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import { chromium } from 'playwright';

const base = process.env.MBDYN_STUDIO_URL || 'http://127.0.0.1:8768';
const browser = await chromium.launch({ headless: true, args: ['--enable-unsafe-swiftshader'] });
const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
const errors = [];
page.on('pageerror', (error) => errors.push(error.message));
page.on('dialog', (dialog) => dialog.accept());
await page.route('**/api/tour-preference', (route) => route.fulfill({ json: { enabled: false } }));
const field = (key) => page.locator(`#spatial-contact-tyre-${key}`);
try {
  await page.goto(base);
  await page.waitForFunction(() => document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
  await page.locator('#examplesButton').click();
  const card = page.locator('.example-card').filter({ has: page.getByRole('heading', { name: 'Landing-gear spin-up drag', exact: true }) });
  assert.equal(await card.locator('.example-study').textContent(), 'Parameter study included · tyre friction 0.3–0.8');
  await card.getByRole('button').click();
  await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('spin-up drag'), null, { timeout: 120000 });

  // The tyre contact carries its friction coefficient and slip velocity; frictionless hides the slip velocity.
  await page.locator('[data-step="model"]').click();
  await page.locator('#modelTree [data-entity="contact-tyre"]').click();
  assert.equal(Number(await field('friction').inputValue()), 0.55);
  assert.equal(Number(await field('slipVelocity').inputValue()), 0.5);
  await field('friction').evaluate((input) => { input.value = '0'; input.dispatchEvent(new Event('change')); });
  await page.waitForFunction(() => !document.querySelector('#spatial-contact-tyre-slipVelocity'));
  await page.locator('#undoButton').click();
  await page.locator('#modelTree [data-entity="contact-tyre"]').click();
  assert.equal(Number(await field('friction').inputValue()), 0.55);
  assert.equal(Number(await field('slipVelocity').inputValue()), 0.5);

  // The Solve card is preloaded with the friction study.
  await page.locator('[data-step="simulate"]').click();
  assert.equal(await page.locator('#studyParameter').inputValue(), 'contacts/tyre/friction');
  assert.equal(await page.locator('#studyValues').inputValue(), '0.3, 0.8');
  assert.match(await page.locator('#studyHint').textContent(), /Current value 0\.55/);

  const response = page.waitForResponse((r) => r.url().endsWith('/api/run') && r.request().method() === 'POST', { timeout: 300000 });
  await page.locator('#runButton').click();
  const result = await (await response).json();
  assert(result.ok, JSON.stringify(result.error));
  await page.waitForFunction(() => document.querySelector('#resultSource')?.textContent.includes('MBDyn'));
  const labels = await page.locator('#signalSelect option').allTextContents();
  for (const label of ['Contact friction force', 'Contact slip speed', 'Friction dissipated energy']) assert(labels.includes(label), `${label} is offered`);

  // Full-resolution friction force: drag is 0.55 × the vertical tyre load while the tyre slides.
  await page.locator('#signalSelect').selectOption({ label: 'Contact friction force' });
  await page.waitForFunction(() => /Full resolution · [\d,]+ steps/.test(document.querySelector('#plotStats')?.textContent || ''), null, { timeout: 60000 });
  const peak = Number((await page.locator('#plotStats').textContent()).match(/max\s*([-\d.e+]+)/)[1]);
  const normal = Math.max(...result.samples.map((sample) => sample.contactStates[0].force));
  assert(Math.abs(peak / normal - 0.55) < 0.01, `peak drag ${peak} N should be 0.55 × peak vertical load ${normal} N`);
  const energy = result.samples.at(-1).contactStates[0].frictionEnergy;
  const wheel = result.model.bodies.find((body) => body.id === 'wheel');
  const spin = 0.5 * wheel.inertia.yy * wheel.velocity.wy ** 2;
  assert(Math.abs(energy / spin - 1) < 0.005, `friction dissipates the spin energy (${energy} of ${spin} J)`);
  // KINEMELD_SCREENSHOT=docs/images/contact-friction.png captures the documentation image.
  if (process.env.KINEMELD_SCREENSHOT) {
    await page.locator('#timeSlider').evaluate((slider, i) => { slider.value = String(i); slider.dispatchEvent(new Event('input', { bubbles: true })); },
      result.samples.findIndex((sample) => sample.contactStates[0].frictionForce === Math.max(...result.samples.map((s) => s.contactStates[0].frictionForce))));
    await page.waitForTimeout(400);
    await page.screenshot({ path: process.env.KINEMELD_SCREENSHOT });
  }
  assert.deepEqual(errors, []);
  console.log(`Contact friction: spin-up drag peaks at ${(peak / 1000).toFixed(1)} kN (${(peak / normal).toFixed(3)} × vertical load) and dissipates ${energy.toFixed(0)} J of spin energy.`);
} finally {
  await browser.close();
}
