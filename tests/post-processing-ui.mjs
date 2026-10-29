/** Post-processing II: full-resolution statistics, pinned traces, run comparison and plot export. */
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
const run = async () => {
  const response = page.waitForResponse((r) => r.url().endsWith('/api/run') && r.request().method() === 'POST', { timeout: 300000 });
  await page.locator('#runButton').click();
  const result = await (await response).json();
  assert(result.ok, JSON.stringify(result.error));
  await page.waitForFunction(() => document.querySelector('#resultSource')?.textContent.includes('MBDyn'));
  return result;
};
try {
  await page.goto(base);
  await page.waitForFunction(() => document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
  await page.locator('#examplesButton').click();
  await page.locator('.example-card').filter({ has: page.getByRole('heading', { name: 'Wheel-end drop test', exact: true }) }).getByRole('button').click();
  await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('Wheel-end drop test loaded'), null, { timeout: 240000 });
  const first = await run();

  // Statistics and the plot come from every solver step once the CSV has loaded.
  await page.locator('#signalSelect').selectOption({ label: 'Contact normal force (reconstructed)' });
  await page.waitForFunction(() => /Full resolution · [\d,]+ steps/.test(document.querySelector('#plotStats')?.textContent || ''), null, { timeout: 60000 });
  const steps = Number((await page.locator('#plotStats .stat-source').textContent()).match(/([\d,]+) steps/)[1].replace(/,/g, ''));
  assert(steps > first.samples.length, `${steps} solver steps should exceed ${first.samples.length} displayed samples`);
  const displayedPeak = Math.max(...first.samples.map((sample) => sample.contactStates[0].force));
  const statsText = await page.locator('#plotStats').textContent();
  const reportedMax = Number(statsText.match(/max\s*([-\d.e+]+)/)[1]);
  assert(reportedMax >= displayedPeak * (1 - 1e-4), `full-resolution max ${reportedMax} must not miss the displayed peak ${displayedPeak}`);

  // Pin one body's trace, choose the other body: both appear on one plot.
  await page.locator('#signalSelect').selectOption({ label: 'Node position · X / Y / Z' });
  await page.locator('#nodeSelect').selectOption('wheel');
  await page.locator('#pinTraceButton').click();
  await page.locator('#nodeSelect').selectOption('knuckle');
  await page.waitForFunction(() => document.querySelectorAll('#plot path.plot-overlay').length > 0);
  assert((await page.locator('#plot path.plot-curve').count()) > 0);

  // Pin this run, change the contact stiffness, run again: the earlier response stays as a reference.
  await page.locator('#compareButton').click();
  assert.match(await page.locator('#compareStatus').textContent(), /Comparing with Run 1/);
  await page.locator('[data-step="model"]').click();
  await page.locator('#modelTree [data-entity^="contact-"]').first().click();
  const stiffness = page.locator('[id^="spatial-contact-"][id$="-stiffness"]').first();
  await stiffness.fill('40000');
  await stiffness.dispatchEvent('change');
  await run();
  await page.locator('#signalSelect').selectOption({ label: 'Contact normal force (reconstructed)' });
  await page.waitForFunction(() => document.querySelectorAll('#plot path.plot-reference').length > 0, null, { timeout: 60000 });

  // Export the plot as SVG and PNG.
  const svgDownload = page.waitForEvent('download');
  await page.locator('#plotSvgButton').click();
  const svg = await readFile(await (await svgDownload).path(), 'utf8');
  assert(svg.startsWith('<svg') && svg.includes('<title>') && !svg.includes('var(--'));
  const pngDownload = page.waitForEvent('download');
  await page.locator('#plotPngButton').click();
  const png = await readFile(await (await pngDownload).path());
  assert.deepEqual([...png.subarray(0, 4)], [0x89, 0x50, 0x4e, 0x47]);
  assert.deepEqual(errors, []);
  console.log(`Post-processing II: ${steps} full-resolution steps, pinned trace, run comparison, SVG and PNG export passed.`);
} finally {
  await browser.close();
}
