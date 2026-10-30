/** STEP parts added one file at a time keep earlier attachments, label each part with its file and survive save and reopen. */
import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { readFile } from 'node:fs/promises';

const base = process.env.MBDYN_STUDIO_URL || 'http://127.0.0.1:8768';
const PARTS = 'examples/open-aircraft-nose-gear/parts';
const browser = await chromium.launch({ headless: true, args: ['--enable-unsafe-swiftshader'] });
const page = await browser.newPage({ viewport: { width: 1440, height: 960 }, acceptDownloads: true });
const errors = [];
page.on('pageerror', (error) => errors.push(error.message));
page.on('dialog', (dialog) => dialog.accept());
await page.route('**/api/tour-preference', (route) => route.fulfill({ json: { enabled: false } }));
const detail = (pattern) => page.waitForFunction((source) => new RegExp(source).test(document.querySelector('#stepDetail')?.textContent || ''), pattern.source, { timeout: 240000 });
const labels = () => page.locator('#stepPart option').allTextContents();
try {
  await page.goto(base);
  await page.waitForFunction(() => document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
  await page.locator('#newButton').click();
  await page.waitForFunction(() => document.querySelector('#viewportName')?.textContent.includes('Untitled'));
  await page.locator('#stepButton').click();
  assert(await page.locator('#stepAdd').isHidden(), 'nothing to add to before the first import');

  // The first file is imported; the next ones are added to it.
  await page.locator('#stepFile').setInputFiles(`${PARTS}/03-strut.step`);
  await detail(/^1 STEP files · 1 solid parts · 0 attached/);
  assert.deepEqual(await labels(), ['Strut']);
  await page.locator('#stepPart').selectOption('0:part-1');
  await page.locator('#stepBody').selectOption('body1');
  await page.locator('#stepBind').click();
  await detail(/1 attached/);

  await page.locator('#stepAdd').click();
  await page.locator('#stepFile').setInputFiles(`${PARTS}/01-piston.step`);
  await detail(/^2 STEP files · 2 solid parts · 1 attached/);
  await page.locator('#stepAdd').click();
  await page.locator('#stepFile').setInputFiles([`${PARTS}/10-wheel-left.step`, `${PARTS}/11-wheel-right.step`]);
  await detail(/^4 STEP files · 4 solid parts · 1 attached/);
  assert.deepEqual(await labels(), ['03-strut.step · Strut', '01-piston.step · Piston', '10-wheel-left.step · Wheel', '11-wheel-right.step · Wheel']);
  assert.match(await page.locator('#notice').textContent(), /Added 2 STEP files: 4 parts in 4 files\. Earlier attachments are kept\./);
  await page.locator('#stepPart').selectOption('0:part-1');
  assert.equal(await page.locator('#stepBody').inputValue(), 'body1', 'the strut stays attached');

  // Undo removes the last addition only.
  await page.locator('#stepClose').click();
  await page.locator('#undoButton').click();
  await page.locator('#stepButton').click();
  await detail(/^2 STEP files · 2 solid parts · 1 attached/);
  await page.locator('#stepClose').click();
  await page.locator('#redoButton').click();
  await page.locator('#stepButton').click();
  await detail(/^4 STEP files · 4 solid parts · 1 attached/);

  // Saved and reopened, the set keeps every file and the attachment.
  await page.locator('#stepClose').click();
  const saved = page.waitForEvent('download');
  await page.locator('#saveButton').click();
  const path = await (await saved).path();
  const project = JSON.parse(await readFile(path, 'utf8'));
  assert.deepEqual(project.assets.step.files.map((file) => file.name), ['03-strut.step', '01-piston.step', '10-wheel-left.step', '11-wheel-right.step']);
  assert.deepEqual(Object.keys(project.assets.step.bindings), ['0:part-1']);
  await page.locator('#newButton').click();
  await page.locator('#projectFile').setInputFiles(path);
  await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('Project imported'), null, { timeout: 240000 });
  await page.locator('#stepButton').click();
  await detail(/^4 STEP files · 4 solid parts · 1 attached/);
  assert.deepEqual(errors, []);
  console.log('STEP parts added one file at a time: labels, attachments, undo and save/reopen passed.');
} finally {
  await browser.close();
}
