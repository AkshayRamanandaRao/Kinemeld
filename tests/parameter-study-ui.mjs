/** Parameter study: sweep the tyre contact stiffness of the wheel-end drop, compare cases, export, cancel. */
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
const rows = () => page.locator('#studyTable tbody tr');
const column = async (index) => (await rows().evaluateAll((items, i) => items.map((row) => Number(row.cells[i].textContent.trim().split(' ')[0])), index));
try {
  await page.goto(base);
  await page.waitForFunction(() => document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
  await page.locator('#examplesButton').click();
  await page.locator('.example-card').filter({ has: page.getByRole('heading', { name: 'Wheel-end drop test', exact: true }) }).getByRole('button').click();
  await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('Wheel-end drop test loaded'), null, { timeout: 240000 });

  // Choose the tyre contact stiffness; the suggested values bracket the current 20 kN/m.
  await page.locator('#modelTree [data-entity^="contact-"]').first().click();
  await page.locator('[data-step="simulate"]').click();
  assert.equal(await page.locator('#studyParameter').inputValue(), 'contacts/tire_plane/stiffness', 'the selected contact preselects its inputs');
  assert.equal(await page.locator('#studyValues').inputValue(), '10000, 15000, 20000, 30000, 40000');
  assert.match(await page.locator('#studyHint').textContent(), /Current value 20000 N\/m, always solved as the baseline/);
  assert.equal(await page.locator('#studyUnit').textContent(), 'N/m');
  await page.locator('#studyValues').fill('40000, 10000');
  await page.locator('#studyRunButton').click();
  await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('Parameter study complete · 3 of 3 cases solved'), null, { timeout: 300000 });
  assert(await page.locator('#studyResults').isVisible());
  assert.deepEqual(await column(0), [10000, 20000, 40000], 'cases run in ascending order with the baseline included');
  assert.equal(await page.locator('#studyTable tr.shown .study-baseline').count(), 1, 'the baseline case is shown first');
  const baselineRun = await page.locator('#runId').textContent();

  // Peak contact force rises with contact stiffness, and every case is on the plot.
  await page.locator('#signalSelect').selectOption({ label: 'Contact normal force (reconstructed)' });
  await page.waitForFunction(() => document.querySelectorAll('#plot path.plot-curve').length === 3);
  await page.waitForFunction(() => /Contact normal force/.test(document.querySelector('#studySummary')?.textContent || ''));
  const peaks = await column(1);
  assert(peaks[0] < peaks[1] && peaks[1] < peaks[2], `peak contact force should rise with stiffness: ${peaks}`);
  assert(await page.locator('#studyChannelField').isHidden());

  // Show the stiffest case: it animates and its curve is drawn heavier.
  await rows().nth(2).click();
  await page.waitForFunction(() => document.querySelector('#studyTable tbody tr:nth-child(3)')?.classList.contains('shown'));
  assert.notEqual(await page.locator('#runId').textContent(), baselineRun);
  assert.equal(await page.locator('#plot path.plot-curve[stroke-width="2.6"]').count(), 1);
  await page.locator('#playButton').click();
  await page.waitForTimeout(400);
  await page.locator('#playButton').click();

  // Multi-channel quantities offer a channel choice.
  await page.locator('#signalSelect').selectOption({ label: 'Node position · X / Y / Z' });
  await page.waitForFunction(() => !document.querySelector('#studyChannelField').hidden);
  await page.locator('#studyChannel').selectOption({ label: 'Z' });
  await page.waitForFunction(() => /· Z \(m\)/.test(document.querySelector('#studySummary')?.textContent || ''));

  // Export the table.
  const download = page.waitForEvent('download');
  await page.locator('#studyCsvButton').click();
  const csv = (await readFile(await (await download).path(), 'utf8')).trim().split('\n');
  assert.match(csv[0], /^"Contact tire_plane stiffness \(N\/m\)","Node position · X \/ Y \/ Z · Z max \(m\)"/);
  assert.deepEqual(csv.slice(1).map((line) => Number(line.split(',')[0])), [10000, 20000, 40000]);

  // A saved project keeps the baseline result even while another case is shown.
  const saved = page.waitForEvent('download');
  await page.locator('#saveButton').click();
  const project = JSON.parse(await readFile(await (await saved).path(), 'utf8'));
  assert.equal(project.result.runId, baselineRun);
  assert.equal(project.model.contacts[0].stiffness, 20000);

  // Clearing the study returns to the baseline result.
  await page.locator('#studyClearButton').click();
  assert(await page.locator('#studyResults').isHidden());
  assert.equal(await page.locator('#runId').textContent(), baselineRun);

  // Cancel stops the remaining cases and keeps those already solved.
  await page.locator('[data-step="simulate"]').click();
  await page.locator('#studyValues').fill('30000, 40000');
  // Press Cancel as soon as case 2 is running; short cases can finish faster than a test click.
  await page.evaluate(() => {
    const observer = new MutationObserver(() => {
      const button = document.querySelector('#cancelRunButton');
      if (/Case 2 of 3/.test(document.querySelector('#studyProgressText').textContent) && !button.hidden && !button.disabled) {
        observer.disconnect();
        button.click();
      }
    });
    observer.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true });
  });
  await page.locator('#studyRunButton').click();
  await page.waitForFunction(() => /Study stopped · [12] of 3 cases solved/.test(document.querySelector('#notice')?.textContent || ''), null, { timeout: 120000 });
  assert.equal(await rows().count() >= 1, true);
  assert.deepEqual(errors, []);
  console.log(`Parameter study: 3 contact stiffness cases with peak contact force ${peaks.map((value) => value.toFixed(0)).join(' < ')} N; case display, channel choice, CSV, baseline save, clear and cancel passed.`);
} finally {
  await browser.close();
}
