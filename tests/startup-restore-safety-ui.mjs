import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { mkdir, readFile, writeFile } from 'node:fs/promises';

const base = process.env.MBDYN_STUDIO_URL || 'http://127.0.0.1:8768';
const browser = await chromium.launch({ headless: true, args: ['--enable-unsafe-swiftshader'], ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } : {}) });
const errors = [], checks = [];
const network = [];
const held = new WeakMap();
let phase = 'Read example catalog', activePage, failure, state;
const deferred = () => { let resolve, reject; const promise = new Promise((done, fail) => { resolve = done; reject = fail; }); promise.catch(() => {}); return { promise, resolve, reject }; };
const start = text => { phase = text; console.log(`Starting: ${text}`); };
const passed = text => { checks.push(text); console.log(`Passed: ${text}`); };
async function bounded(promise, label) {
  let timer;
  try { return await Promise.race([promise, new Promise((_, reject) => { timer = setTimeout(() => reject(Error(`Timed out after 30 seconds: ${label}; phase: ${phase}`)), 30000); })]); }
  finally { clearTimeout(timer); }
}
async function close(page) {
  state = await page.evaluate(() => ({ title: document.querySelector('#documentName')?.textContent, solver: document.querySelector('#solverStatus')?.textContent, notice: document.querySelector('#notice')?.textContent, readyState: document.readyState })).catch(() => null);
  await mkdir('tests/evidence', { recursive: true });
  await page.screenshot({ path: 'tests/evidence/startup-restore-safety-last-page.png', fullPage: true }).catch(() => {});
  for (const release of held.get(page) || []) release();
  await page.close();
}
async function desktop(model) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
  activePage = page;
  page.on('request', request => { network.push({ phase, event: 'request', method: request.method(), path: new URL(request.url()).pathname }); });
  page.on('response', response => { network.push({ phase, event: 'response', status: response.status(), path: new URL(response.url()).pathname }); });
  page.on('requestfailed', request => { network.push({ phase, event: 'failed', error: request.failure()?.errorText, path: new URL(request.url()).pathname }); });
  page.on('pageerror', error => errors.push(error.message));
  page.on('dialog', dialog => dialog.accept());
  await page.addInitScript(model => localStorage.setItem('mbdyn-studio-project', JSON.stringify({ format: 'mbdyn-studio/1', model })), model);
  const ready = deferred();
  await page.route('**/api/tour-preference', async route => { await route.fulfill({ json: { enabled: false } }); ready.resolve(); });
  return { page, ready: ready.promise };
}
async function hold(page, pattern, match = () => true) {
  const seen = deferred(), released = deferred();
  if (!held.has(page)) held.set(page, []);
  held.get(page).push(released.resolve);
  await page.route(pattern, async route => {
    if (!match(route.request())) return route.continue();
    try {
      const response = await route.fetch(); seen.resolve(); await released.promise; await route.fulfill({ response });
    } catch (error) { seen.reject(error); await route.abort().catch(() => {}); }
  });
  return { seen: seen.promise, release: released.resolve };
}
try {
  const request = await browser.newContext();
  const examples = await (await request.request.get(`${base}/api/examples`)).json();
  const cached = structuredClone(examples.examples.find(item => item.id === 'mass-spring').model);
  cached.name = 'Cached startup document'; cached.parameters.stiffness = 123;
  await request.close();

  start("Restore unchanged cached document");
  let { page, ready } = await desktop(cached);
  try {
    await page.goto(base); await bounded(ready, "startup tour initialization");
    assert.equal(await page.locator('#documentName').textContent(), cached.name);
    assert.equal(await page.locator('#field-stiffness').inputValue(), '123');
    passed('Unchanged startup restores the validated cached model');
  } finally { await close(page); }

  start("Edit while initial service responses are held");
  ({ page, ready } = await desktop(cached));
  try {
    const initial = await hold(page, '**/api/status');
    await page.goto(base); await bounded(initial.seen, "initial service response");
    await page.locator('#field-angle').fill('31'); await page.locator('#field-angle').dispatchEvent('change');
    initial.release(); await bounded(ready, "startup after releasing service response");
    assert.equal(await page.locator('#field-angle').inputValue(), '31');
    assert.equal(await page.locator('#documentName').textContent(), 'Gravity pendulum');
    passed('Edits before the initial service responses survive startup');
  } finally { await close(page); }

  for (const action of ['edit', 'pending input', 'New', 'Open']) {
    start(`Cached validation against newer ${action}`);
    ({ page, ready } = await desktop(cached));
    try {
      const startup = await hold(page, '**/api/validate', request => request.postDataJSON()?.model?.name === cached.name);
      await page.goto(base); await bounded(startup.seen, "cached-model validation response");
      let opening;
      let latest;
      let project;
      if (action === 'edit' || action === 'pending input') {
        await page.locator('#field-angle').fill('32');
        if (action === 'edit') await page.locator('#field-angle').dispatchEvent('change');
      } else if (action === 'New') {
        await page.locator('#newButton').click();
        await page.waitForFunction(() => document.querySelector('#documentName')?.textContent.includes('Untitled 3D assembly'));
      } else {
        project = { format: 'mbdyn-studio/1', model: { ...structuredClone(cached), name: 'Explicit latest project' } };
        latest = await hold(page, '**/api/validate', request => request.postDataJSON()?.model?.name === project.model.name);
        opening = page.evaluate(async project => document.querySelector('#projectFile').onchange({ target: { files: [new File([JSON.stringify(project)], 'latest.mbdyn-studio')], value: '' } }), project);
        opening.catch(() => {});
        await bounded(latest.seen, "explicit project validation response");
      }
      startup.release(); await bounded(ready, "startup after releasing cached validation");
      if (action === 'edit' || action === 'pending input') assert.equal(await page.evaluate(() => document.querySelector('#field-angle')?.value), '32', 'cached startup state overwrote the newer edit');
      else if (action === 'New') assert.equal(await page.locator('#documentName').textContent(), 'Untitled 3D assembly');
      else {
        assert.notEqual(await page.locator('#documentName').textContent(), cached.name);
        latest.release(); await bounded(opening, "explicit project open completion");
        assert.equal(await page.locator('#documentName').textContent(), project.model.name);
      }
      passed(`Delayed cached-model validation preserves a newer ${action} operation`);
    } finally { await close(page); }
  }

  start("Preserve typed input during CAD generation and import");
  ({ page, ready } = await desktop(cached));
  try {
    await page.goto(base); await bounded(ready, "startup tour initialization");
    await page.locator('#newButton').click();
    await page.waitForFunction(() => document.querySelector('#documentName')?.textContent.includes('Untitled 3D assembly'));
    await page.getByText('Calculate mass and inertia from a uniform solid').click();
    const generation = await hold(page, '**/api/step/primitive');
    await page.getByRole('button', { name: 'Create STEP solid and apply mass' }).click();
    await bounded(generation.seen, "generated STEP primitive response");
    await page.locator('#spatial-model-name').fill('Still editing during generation');
    generation.release();
    await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('nothing was applied'));
    assert.equal(await page.locator('#spatial-model-name').inputValue(), 'Still editing during generation');
    assert(await page.locator('#stepStatus').isHidden());
    passed('A stale generated solid preserves typed input before change/blur');

    const conversion = await hold(page, '**/api/step/convert');
    await page.locator('#stepButton').click();
    await page.locator('#stepFile').setInputFiles({ name: 'pendulum.step', mimeType: 'application/step', buffer: await readFile('examples/step-pendulum/pendulum.step') });
    await bounded(conversion.seen, "STEP conversion response");
    await page.locator('#stepClose').click();
    await page.locator('#spatial-model-name').fill('Still editing during import');
    conversion.release();
    await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('your edits were kept'));
    assert.equal(await page.locator('#spatial-model-name').inputValue(), 'Still editing during import');
    assert(await page.locator('#stepStatus').isHidden());
    passed('A stale STEP import preserves typed input before change/blur');
  } finally { await close(page); }
  assert.deepEqual(errors, []);
} catch (error) {
  failure = error.stack;
  if (activePage && !activePage.isClosed()) {
    state = await activePage.evaluate(() => ({ title: document.querySelector('#documentName')?.textContent, solver: document.querySelector('#solverStatus')?.textContent, notice: document.querySelector('#notice')?.textContent, readyState: document.readyState })).catch(() => null);
    await mkdir('tests/evidence', { recursive: true });
    await activePage.screenshot({ path: 'tests/evidence/startup-restore-safety-failure.png', fullPage: true }).catch(() => {});
  }
  throw error;
} finally {
  await mkdir('tests/evidence', { recursive: true });
  await writeFile('tests/evidence/startup-restore-safety.json', JSON.stringify({ checks, errors, phase, failure, state, network: network.slice(-80) }, null, 2));
  await browser.close();
}
