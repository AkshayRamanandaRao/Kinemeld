/** Exercise user workflows against the running local server, including a real MBDyn job. */
import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdir, writeFile, readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const evidence = path.join(root, 'tests', 'evidence');
await mkdir(evidence, { recursive: true });
const report = { started: new Date().toISOString(), baseURL: process.env.MBDYN_STUDIO_URL || 'http://127.0.0.1:8766', checks: [], pageErrors: [], consoleErrors: [], screenshots: [] };
const browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } : {}), args: ['--enable-unsafe-swiftshader'] });
const context = await browser.newContext({ viewport: { width: 1366, height: 900 }, acceptDownloads: true });
const page = await context.newPage();
page.on('pageerror', error => report.pageErrors.push(error.message));
page.on('console', message => { if (message.type() === 'error') report.consoleErrors.push(message.text()); });
const waitText = (selector, text, timeout = 15000) => page.waitForFunction(({ selector, text }) => document.querySelector(selector)?.textContent.includes(text), { selector, text }, { timeout });
const value = selector => page.locator(selector).inputValue();
async function number(selector, text) { await page.locator(selector).fill(text); await page.locator(selector).press('Tab'); }
async function check(name, action) {
  const started = Date.now();
  try { const details = await action(); report.checks.push({ name, ok: true, milliseconds: Date.now() - started, ...(details ? { details } : {}) }); }
  catch (error) { report.checks.push({ name, ok: false, milliseconds: Date.now() - started, error: error.message }); console.error(`${name}: ${error.message}`); }
}
async function screenshot(name, fullPage = false) {
  const file = path.join(evidence, name);
  await page.screenshot({ path: file, fullPage });
  report.screenshots.push(file);
}
try {
  await page.goto(report.baseURL);
  await waitText('#solverStatus', 'MBDyn ready', 30000);
  await page.waitForFunction(() => document.querySelector('#validationBadge')?.textContent === 'Ready');
  await check('Initial editable model and working WebGL canvas', async () => {
    assert.equal(await value('#field-mass'), '1');
    assert.equal(await page.locator('#canvasMount canvas').count(), 1);
    assert(await page.locator('#canvasMount canvas').evaluate(canvas => !!canvas.getContext('webgl2')));
    const before = await page.locator('#canvasMount').screenshot();
    const rect = await page.locator('#canvasMount canvas').boundingBox();
    await page.mouse.move(rect.x + rect.width * .5, rect.y + rect.height * .55);
    await page.mouse.down();
    await page.mouse.move(rect.x + rect.width * .65, rect.y + rect.height * .59, { steps: 12 });
    await page.mouse.up();
    await page.waitForTimeout(250);
    const after = await page.locator('#canvasMount').screenshot();
    assert(!before.equals(after), 'Orbit interaction did not change the viewport image');
    await page.locator('#resetViewButton').click();
    await page.waitForTimeout(250);
    await page.locator('[data-entity="ground"]').click();
    const bodyLabel = await page.locator('.object-label').last().boundingBox();
    await page.mouse.click(bodyLabel.x - 15, bodyLabel.y + 8);
    await waitText('#selectionTitle', 'Point mass');
    await screenshot('desktop-initial.png');
  });
  await check('Parameter edit, invalid mass guidance, undo and redo', async () => {
    await number('#field-length', '2');
    await number('#field-mass', '0');
    await page.locator('#validateButton').click();
    await waitText('#validationBadge', 'Needs attention');
    assert(await page.locator('#issuesSection').isVisible());
    assert((await page.locator('#issuesList').textContent()).toLowerCase().includes('mass'));
    await page.locator('#issuesList button').first().click();
    assert.equal(await page.evaluate(() => document.activeElement?.id), 'field-mass');
    await page.locator('#undoButton').click();
    assert.equal(await value('#field-mass'), '1');
    assert.equal(await value('#field-length'), '2');
    await page.locator('#redoButton').click();
    assert.equal(await value('#field-mass'), '0');
    await page.locator('#undoButton').click();
    await waitText('#validationBadge', 'Ready');
  });
  await check('Connections diagram and entity selection', async () => {
    await page.locator('[data-view="topology"]').click();
    assert(await page.locator('#topology').isVisible());
    assert((await page.locator('#topology').textContent()).includes('Revolute joint'));
    await page.locator('[data-entity="joint"]').click();
    await waitText('#selectionTitle', 'Revolute joint');
    await page.locator('[data-view="scene"]').click();
    assert(await page.locator('#canvasMount').isVisible());
  });
  await check('Mass–spring example loading', async () => {
    await page.locator('#examplesButton').click();
    assert(await page.locator('#examplesDialog').isVisible());
    await page.locator('#exampleCards .example-card').filter({ has: page.getByRole('heading', { name: 'Damped oscillator', exact: true }) }).getByRole('button', { name: /Open example/ }).click();
    await page.waitForSelector('#field-stiffness');
    assert.equal(await value('#field-stiffness'), '100');
    assert.equal(await value('#field-damping'), '0.5');
    await number('#durationInput', '2');
    await number('#stepInput', '0.005');
    await waitText('#validationBadge', 'Ready');
  });
  await check('Reference preview is labelled and drives chart/timeline', async () => {
    await page.locator('#previewButton').click();
    await waitText('#resultSource', 'Reference preview', 30000);
    assert.equal(await page.locator('#plot path.plot-curve').count(), 1);
    assert.equal(await page.locator('#playButton').isEnabled(), true);
    await page.locator('#timeSlider').fill('100');
    assert.notEqual((await page.locator('#timeOutput').textContent()).trim(), '0.000 s');
    const before = await page.locator('#timeOutput').textContent();
    await page.locator('#playButton').click();
    await page.waitForTimeout(200);
    const after = await page.locator('#timeOutput').textContent();
    assert.notEqual(before, after);
    await page.locator('#playButton').click();
    await page.locator('#rewindButton').click();
    assert.equal((await page.locator('#timeOutput').textContent()).trim(), '0.000 s');
  });
  await check('Real MBDyn solve and inspectable run log', async () => {
    const responsePromise = page.waitForResponse(response => response.url().endsWith('/api/run') && response.request().method() === 'POST', { timeout: 60000 });
    await page.locator('#runButton').click();
    const response = await responsePromise;
    const body = await response.json();
    assert.equal(response.status(), 200, JSON.stringify(body));
    assert.equal(body.ok, true);
    assert.equal(body.source, 'MBDyn');
    assert(body.samples.length > 300);
    await waitText('#resultSource', 'MBDyn solver');
    assert.match(await page.locator('#runId').textContent(), /[0-9a-f]{32}/);
    await page.locator('#logButton').click();
    assert.match(await page.locator('#documentBody pre').textContent(), /MBDyn/i);
    await page.locator('#documentDialog [data-close]').last().click();
    await page.locator('.inspector').evaluate(element => { element.scrollTop = 0; });
    await screenshot('desktop-mbdyn-results.png');
    return { runId: body.runId, sampleCount: body.samples.length, source: body.source };
  });
  await check('Parameter edits mark results stale and prevent playback', async () => {
    await number('#field-stiffness', '140');
    await waitText('#resultSource', 'Stale');
    if (await page.locator('#playButton').isEnabled()) {
      await page.locator('#playButton').click();
      await waitText('#notice', 'Run the edited model again');
    } else {
      assert(await page.locator('#notice').textContent(), 'Stale playback needs explanatory guidance');
    }
    assert.equal(await page.locator('#playButton').getAttribute('aria-label'), 'Play result animation');
    await page.locator('#undoButton').click();
    assert.equal(await value('#field-stiffness'), '100');
    assert.equal((await page.locator('#resultSource').textContent()).trim(), 'MBDyn solver');
    assert(!(await page.locator('#viewSource').textContent()).includes('Previous'));
  });
  await check('Generated input deck and download', async () => {
    await page.locator('#deckButton').click();
    await page.locator('#documentDialog').waitFor({ state: 'visible' });
    const deck = await page.locator('#documentBody pre').textContent();
    assert.match(deck, /begin: data/i);
    assert.match(deck, /initial value/i);
    const event = page.waitForEvent('download');
    await page.locator('#documentDownload').click();
    const file = await event;
    await file.saveAs(path.join(evidence, 'exported-model.mbd'));
    assert.equal(await readFile(path.join(evidence, 'exported-model.mbd'), 'utf8'), deck);
    await page.locator('#documentDialog [data-close]').last().click();
  });
  await check('Project save/import and invalid import preserve the model', async () => {
    const event = page.waitForEvent('download');
    await page.locator('#saveButton').click();
    const file = await event;
    const saved = path.join(evidence, 'exported-project.mbdyn-studio');
    await file.saveAs(saved);
    const project = JSON.parse(await readFile(saved, 'utf8'));
    assert.equal(project.format, 'mbdyn-studio/1');
    assert.equal(project.model.parameters.stiffness, 100);
    await number('#field-stiffness', '160');
    page.on('dialog', dialog=>dialog.accept());await page.locator('#projectFile').setInputFiles(saved);
    await waitText('#notice', 'Project imported and validated');
    assert.equal(await value('#field-stiffness'), '100');
    await page.locator('#projectFile').setInputFiles({ name: 'invalid.json', mimeType: 'application/json', buffer: Buffer.from('{"format":"invalid"}') });
    await waitText('#notice', 'Project was not opened');
    assert.equal(await value('#field-stiffness'), '100');
  });
  await check('CSV includes solver provenance and numerical rows', async () => {
    const event = page.waitForEvent('download');
    await page.locator('#csvButton').click();
    const file = await event;
    const destination = path.join(evidence, 'exported-results.csv');
    await file.saveAs(destination);
    const csv = await readFile(destination, 'utf8');
    assert.match(csv, /^# source: MBDyn/m);
    assert.match(csv, /time_s,x_m,y_m,z_m,angle_deg,velocity_m_s/);
    assert(csv.split('\n').length > 300);
  });
  await check('Full CSV preserves every native sample when the viewport response is decimated', async () => {
    await number('#durationInput', '12');
    const responsePromise = page.waitForResponse(response => response.url().endsWith('/api/run') && response.request().method() === 'POST', { timeout: 60000 });
    await page.locator('#runButton').click();
    const response = await responsePromise;
    const result = await response.json();
    assert.equal(result.ok, true, JSON.stringify(result));
    assert(result.metrics.sampleCount > 2001);
    assert(result.samples.length < result.metrics.sampleCount);
    await waitText('#resultSource', 'MBDyn solver');
    const event = page.waitForEvent('download');
    await page.locator('#csvButton').click();
    const file = await event;
    const destination = path.join(evidence, 'exported-full-results.csv');
    await file.saveAs(destination);
    const lines = (await readFile(destination, 'utf8')).trim().split(/\r?\n/).filter(line => !line.startsWith('#'));
    assert.equal(lines[0], 'time_s,x_m,y_m,z_m,angle_deg,velocity_m_s,value_m');
    assert.equal(lines.length - 1, result.metrics.sampleCount);
    assert.equal(lines.at(-1).split(',').length, 7);
    assert.equal(Number(lines.at(-1).split(',')[0]), result.metrics.duration);
    await number('#durationInput', '2');
    const restoredResponse = page.waitForResponse(item => item.url().endsWith('/api/run') && item.request().method() === 'POST', { timeout: 60000 });
    await page.locator('#runButton').click();
    assert.equal((await (await restoredResponse).json()).ok, true);
    await waitText('#resultSource', 'MBDyn solver');
    return { runId: result.runId, nativeSamples: result.metrics.sampleCount, viewportSamples: result.samples.length, csvRows: lines.length - 1 };
  });
  await check('Guide describes reference and solver boundaries', async () => {
    await page.locator('#helpButton').click();
    const text = await page.locator('#documentBody').textContent();
    assert.match(text, /Reference preview/);
    assert.match(text, /not a general assembly editor/);
    assert.match(text, /RK4/);
    await page.locator('#documentDialog [data-close]').last().click();
  });
  await check('Dark theme and browser model recovery', async () => {
    await page.locator('#validateButton').click();
    await waitText('#notice', 'Model checks passed');
    await page.locator('[data-step="results"]').click();
    await page.locator('#themeButton').click();
    assert.equal(await page.locator('html').getAttribute('data-theme'), 'dark');
    await page.waitForTimeout(250);
    const colors = await page.evaluate(() => ['#validateButton', '.tree-item.active', '.view-tabs button.active'].map(selector => {
      const style = getComputedStyle(document.querySelector(selector));
      return { selector, foreground: style.color, background: style.backgroundColor };
    }));
    const luminance = color => color.match(/[\d.]+/g).slice(0, 3).map(Number).map(value => {
      const srgb = value / 255; return srgb <= .04045 ? srgb / 12.92 : ((srgb + .055) / 1.055) ** 2.4;
    }).reduce((sum, value, index) => sum + value * [.2126, .7152, .0722][index], 0);
    for (const color of colors) {
      const foreground = luminance(color.foreground), background = luminance(color.background);
      color.ratio = (Math.max(foreground, background) + .05) / (Math.min(foreground, background) + .05);
      assert(color.ratio >= 4.5, `Dark control contrast below4.5: ${JSON.stringify(color)}`);
    }
    await screenshot('desktop-dark.png');
    await page.reload();
    await page.waitForSelector('#field-stiffness');
    assert.equal(await value('#field-stiffness'), '100');
    assert.equal(await page.locator('html').getAttribute('data-theme'), 'dark');
    await page.locator('#themeButton').click();
    return colors;
  });
  await check('Mobile layout has no horizontal document overflow and editor controls remain visible', async () => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(150);
    const sizes = await page.evaluate(() => ({ document: document.documentElement.scrollWidth, viewport: window.innerWidth }));
    assert(sizes.document <= sizes.viewport + 1, `Horizontal overflow: ${JSON.stringify(sizes)}`);
    assert(await page.locator('#runButton').isVisible());
    assert(await page.locator('#field-stiffness').isVisible());
    assert(await page.locator('#examplesButton').isVisible(), 'Example selection must remain accessible on mobile');
    assert(await page.locator('#importButton').isVisible(), 'Project import must remain accessible on mobile');
    await screenshot('mobile-workspace.png', true);
    return sizes;
  });
  let coupledBaseline;
  await check('Coupled double pendulum has two bodies, two joint entries and two real response channels', async () => {
    await page.setViewportSize({ width: 1366, height: 900 });
    await page.locator('#examplesButton').click();
    await page.locator('#exampleCards .example-card').filter({ has: page.getByRole('heading', { name: 'Coupled double pendulum', exact: true }) }).getByRole('button', { name: /Open example/ }).click();
    for (const field of ['mass1', 'mass2', 'length1', 'length2', 'angle1', 'angle2', 'gravity']) {
      assert(await page.locator(`#field-${field}`).isVisible(), `Missing physical field: ${field}`);
    }
    assert.equal(await page.locator('[data-entity="body"]').count(), 1);
    assert.equal(await page.locator('[data-entity="body2"]').count(), 1);
    assert.equal(await page.locator('[data-entity="joint"]').count(), 1);
    assert.equal(await page.locator('[data-entity="joint2"]').count(), 1);
    assert.match(await page.locator('#modelKindBadge').textContent(), /2 moving bodies.*2 joints/);
    await number('#durationInput', '2');
    await number('#stepInput', '0.005');
    const responsePromise = page.waitForResponse(response => response.url().endsWith('/api/run') && response.request().method() === 'POST', { timeout: 60000 });
    await page.locator('#runButton').click();
    coupledBaseline = await (await responsePromise).json();
    assert.equal(coupledBaseline.ok, true, JSON.stringify(coupledBaseline));
    assert.equal(coupledBaseline.source, 'MBDyn');
    assert.equal(coupledBaseline.model.kind, 'double-pendulum');
    assert(coupledBaseline.samples.length > 300);
    for (const sample of coupledBaseline.samples) {
      for (const key of ['x', 'y', 'z', 'angle', 'velocity', 'x2', 'y2', 'z2', 'angle2', 'velocity2']) assert(Number.isFinite(sample[key]), `Non-finite coupled channel: ${key}`);
    }
    await waitText('#resultSource', 'MBDyn solver');
    assert.equal(await page.locator('#plot path.plot-curve').count(), 2);
    assert.notEqual(await page.locator('#plot path.plot-curve').nth(0).getAttribute('d'), await page.locator('#plot path.plot-curve').nth(1).getAttribute('d'));
    await page.locator('[data-entity="body2"]').click();
    await waitText('#selectionTitle', 'Mass 2');
    await page.evaluate(async () => {
      const { MechanismView } = await import('/viewport.js');
      const setSample = MechanismView.prototype.setSample;
      // Observe actual rendered node transforms without changing the implementation or response.
      MechanismView.prototype.setSample = function(sample) {
        setSample.call(this, sample);
        if (this.model.kind === 'double-pendulum' && sample) window.__qaCoupledPose = {
          sample, first: this.bob.position.toArray(), second: this.bob2.position.toArray(), floorOffset: this.pivot.z,
        };
      };
    });
    await page.locator('#timeSlider').fill('50');
    const pose = await page.evaluate(() => window.__qaCoupledPose);
    assert(pose, 'No actual coupled pose was rendered after scrubbing');
    assert.equal(pose.sample.time, coupledBaseline.samples[50].time);
    assert.deepEqual(pose.first, [pose.sample.x, pose.sample.y, pose.floorOffset + pose.sample.z]);
    assert.deepEqual(pose.second, [pose.sample.x2, pose.sample.y2, pose.floorOffset + pose.sample.z2]);
    await page.locator('.inspector').evaluate(element => { element.scrollTop = 0; });
    await screenshot('desktop-coupled-mbdyn.png');
    const downloadEvent = page.waitForEvent('download');
    await page.locator('#csvButton').click();
    const downloaded = await downloadEvent;
    const destination = path.join(evidence, 'exported-coupled-results.csv');
    await downloaded.saveAs(destination);
    const lines = (await readFile(destination, 'utf8')).trim().split(/\r?\n/).filter(line => !line.startsWith('#'));
    const headers = lines[0].split(',');
    for (const expected of ['x2_m', 'y2_m', 'z2_m', 'angle2_deg', 'angular_velocity2_rad_s', 'value2_deg']) assert(headers.includes(expected), `Missing coupled CSV header: ${expected}`);
    assert.equal(lines.length - 1, coupledBaseline.metrics.sampleCount);
    assert.equal(lines[1].split(',').length, headers.length);
    const firstRow = lines[1].split(',').map(Number);
    assert.equal(firstRow[headers.indexOf('angle2_deg')], coupledBaseline.samples[0].angle2);
    return { runId: coupledBaseline.runId, sampleCount: coupledBaseline.metrics.sampleCount, renderedTime: pose.sample.time, csvColumns: headers };
  });
  await check('Editing the second link changes both coupled solver responses', async () => {
    assert(coupledBaseline?.ok, 'The baseline coupled run must succeed first');
    const originalFirst = await page.locator('#plot path.plot-curve').nth(0).getAttribute('d');
    const originalSecond = await page.locator('#plot path.plot-curve').nth(1).getAttribute('d');
    await number('#field-length2', '1.4');
    await waitText('#resultSource', 'Stale');
    assert.equal(await page.locator('#playButton').isEnabled(), false);
    const responsePromise = page.waitForResponse(response => response.url().endsWith('/api/run') && response.request().method() === 'POST', { timeout: 60000 });
    await page.locator('#runButton').click();
    const changed = await (await responsePromise).json();
    assert.equal(changed.ok, true, JSON.stringify(changed));
    assert.equal(changed.model.parameters.length2, 1.4);
    await waitText('#resultSource', 'MBDyn solver');
    assert.equal(await page.locator('#plot path.plot-curve').count(), 2);
    assert.notEqual(await page.locator('#plot path.plot-curve').nth(0).getAttribute('d'), originalFirst);
    assert.notEqual(await page.locator('#plot path.plot-curve').nth(1).getAttribute('d'), originalSecond);
    const paired = Math.min(coupledBaseline.samples.length, changed.samples.length);
    let firstDifference = 0, secondDifference = 0;
    for (let i = 0; i < paired; i++) {
      assert(Math.abs(coupledBaseline.samples[i].time - changed.samples[i].time) < 1e-10);
      firstDifference = Math.max(firstDifference, Math.abs(coupledBaseline.samples[i].angle - changed.samples[i].angle));
      secondDifference = Math.max(secondDifference, Math.abs(coupledBaseline.samples[i].angle2 - changed.samples[i].angle2));
    }
    assert(firstDifference > .5, 'Changing link2 must affect link1 through coupling');
    assert(secondDifference > .5, 'Changing link2 must affect its own response');
    await page.locator('[data-entity="body2"]').click();
    await page.locator('#timeSlider').fill('50');
    await screenshot('desktop-coupled-edited.png');
    return { runId: changed.runId, maxFirstAngleChangeDeg: firstDifference, maxSecondAngleChangeDeg: secondDifference };
  });
  await check('No uncaught browser errors', async () => assert.deepEqual(report.pageErrors, []));
} catch (error) {
  report.fatalError = error.stack || error.message;
  await screenshot('failure.png', true).catch(() => {});
} finally {
  report.completed = new Date().toISOString();
  report.ok = !report.fatalError && report.checks.length > 0 && report.checks.every(item => item.ok);
  await writeFile(path.join(evidence, 'ui-verification.json'), JSON.stringify(report, null, 2));
  await browser.close();
}
console.log(JSON.stringify(report, null, 2));
process.exitCode = report.ok ? 0 : 1;
