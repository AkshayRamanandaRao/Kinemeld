import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { isDeepStrictEqual } from 'node:util';

const base = process.env.MBDYN_STUDIO_URL || 'http://127.0.0.1:8768';
const browser = await chromium.launch({ headless: true, args: ['--enable-unsafe-swiftshader'], ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } : {}) });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true }), errors = [], checks = [];
page.on('pageerror', error => errors.push(error.message));
page.on('dialog', dialog => dialog.accept());
await page.route('**/api/tour-preference', route => route.fulfill({ json: { enabled: false } }));
const deferred = () => { let resolve; const promise = new Promise(done => resolve = done); return { promise, resolve }; };
async function hold(pattern, match = () => true) {
  const seen = deferred(), release = deferred();
  const handler = async route => {
    if (!match(route.request())) return route.continue();
    await page.unroute(pattern, handler);
    const response = await route.fetch();
    seen.resolve();
    await release.promise;
    await route.fulfill({ response });
  };
  await page.route(pattern, handler);
  return { seen: seen.promise, release: release.resolve };
}
async function save() {
  const event = page.waitForEvent('download');
  await page.locator('#saveButton').click();
  return JSON.parse(await readFile(await (await event).path(), 'utf8'));
}
const documentState = project => ({ model: project.model, assets: project.assets, result: project.result });
async function open(project) {
  await page.evaluate(async project => {
    const input = document.querySelector('#projectFile');
    await input.onchange({ target: { files: [new File([JSON.stringify(project)], 'project.mbdyn-studio')], value: '' } });
  }, project);
}
async function importStep(append = false) {
  return page.evaluate(async ({ append, data }) => {
    if (append) document.querySelector('#stepAdd').click();
    else document.querySelector('#stepImport').click();
    const bytes = Uint8Array.from(atob(data), character => character.charCodeAt(0));
    await document.querySelector('#stepFile').onchange({ target: { files: [new File([bytes], 'replacement.step')], value: '' } });
  }, { append, data: (await readFile('examples/step-pendulum/pendulum.step')).toString('base64') });
}
async function editMass(value) {
  if (await page.locator('#stepDialog').evaluate(dialog => dialog.open)) await page.locator('#stepClose').click();
  await page.locator('#graph-body-upper_link-mass').fill(String(value));
  await page.locator('#graph-body-upper_link-mass').dispatchEvent('change');
}
try {
  await page.goto(base);
  await page.waitForFunction(() => document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
  await page.locator('#stepButton').click();
  await page.locator('#stepPendulum').click();
  await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('Matching STEP solid and rigid pendulum loaded'), null, { timeout: 120000 });
  const response = page.waitForResponse(response => response.url().endsWith('/api/run') && response.request().method() === 'POST', { timeout: 120000 });
  await page.locator('#runButton').click();
  assert((await (await response).json()).ok);
  await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('MBDyn completed successfully'));
  const baseline = await save();
  assert.equal(baseline.result.source, 'MBDyn');
  assert.equal(Object.keys(baseline.assets.step.bindings).length, 1);

  for (const append of [false, true]) {
    await open(baseline);
    const blocked = await hold('**/api/step/convert');
    const importing = importStep(append);
    await blocked.seen;
    await editMass(1.7);
    const newer = documentState(await save());
    blocked.release();
    await importing;
    assert(isDeepStrictEqual(documentState(await save()), newer), `${append ? 'append' : 'replacement'} overwrote newer work`);
    assert.match(await page.locator('#notice').textContent(), /changed|kept/);
    checks.push(`Delayed STEP ${append ? 'append' : 'replacement'} preserves model, CAD, bindings and result`);
  }

  await open(baseline);
  const unchanged = documentState(await save());
  await page.evaluate(() => document.querySelector('#stepFile').onchange({ target: { files: [], value: '' } }));
  assert(isDeepStrictEqual(documentState(await save()), unchanged), 'cancelled file selection changed the project');
  await page.route('**/api/step/convert', route => route.fulfill({ status: 500, json: { error: 'Injected conversion failure' } }), { times: 1 });
  await importStep();
  assert.match(await page.locator('#notice').textContent(), /Injected conversion failure/);
  assert(isDeepStrictEqual(documentState(await save()), unchanged), 'failed conversion changed the project');
  checks.push('Cancelled selection and failed CAD conversion leave the document unchanged');

  const reading = page.evaluate(async ({ data }) => {
    const bytes = Uint8Array.from(atob(data), character => character.charCodeAt(0));
    await document.querySelector('#stepFile').onchange({ target: { files: [{ name: 'reading.step', size: bytes.length, arrayBuffer: async () => {
      await new Promise(resolve => window.__releaseStepRead = resolve);
      return bytes.buffer;
    } }], value: '' } });
  }, { data: (await readFile('examples/step-pendulum/pendulum.step')).toString('base64') });
  await page.waitForFunction(() => typeof window.__releaseStepRead === 'function');
  await editMass(1.6);
  const duringRead = documentState(await save());
  await page.evaluate(() => window.__releaseStepRead());
  await reading;
  assert(isDeepStrictEqual(documentState(await save()), duringRead), 'file reading captured state after intervening edits');
  checks.push('STEP import captures the document before asynchronous file reading');

  await open(baseline);
  const suspension = await hold('**/api/step/suspension');
  const loadingParts = page.evaluate(() => document.querySelector('#stepExample').onclick());
  await suspension.seen;
  await editMass(1.8);
  const suspensionNewer = documentState(await save());
  suspension.release();
  await loadingParts;
  assert(isDeepStrictEqual(documentState(await save()), suspensionNewer), 'suspension parts overwrote newer work');
  checks.push('Delayed suspension example preserves current document');

  await open(baseline);
  const pendulum = await hold('**/api/step/convert');
  const loadingPendulum = page.evaluate(() => document.querySelector('#stepPendulum').onclick());
  await pendulum.seen;
  await page.locator('#stepButton').click();
  await page.locator('#stepBody').selectOption('');
  await page.locator('#stepBind').click();
  await page.locator('#stepClose').click();
  const unbound = documentState(await save());
  pendulum.release();
  await loadingPendulum;
  assert(isDeepStrictEqual(documentState(await save()), unbound), 'pendulum example overwrote a newer binding edit');
  checks.push('Delayed pendulum example preserves newer CAD bindings');

  await open(baseline);
  await page.getByText('Calculate mass and inertia from a uniform solid').click();
  const primitive = await hold('**/api/step/primitive');
  await page.getByRole('button', { name: 'Create STEP solid and apply mass' }).click();
  await primitive.seen;
  await editMass(1.9);
  await page.locator('#undoButton').click();
  const undone = documentState(await save());
  primitive.release();
  await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('nothing was applied'));
  assert(isDeepStrictEqual(documentState(await save()), undone), 'generated solid applied after intervening edit/Undo');
  checks.push('Generated solid rejects intervening edit/Undo even when model values return to their original values');

  await open(baseline);
  const older = structuredClone(baseline), latest = structuredClone(baseline);
  older.model.name = 'Older project'; latest.model.name = 'Latest project';
  const validation = await hold('**/api/validate', request => request.postDataJSON()?.model?.name === older.model.name);
  const olderOpen = open(older);
  await validation.seen;
  const geometry = await hold('**/api/step/convert');
  const latestOpen = open(latest);
  await geometry.seen;
  validation.release();
  await olderOpen;
  geometry.release();
  await latestOpen;
  assert.equal((await save()).model.name, latest.model.name, 'an older project request superseded the latest one');
  checks.push('Overlapping project opens keep the latest requested project');

  await open(baseline);
  const featured = await hold('**/api/featured/aircraft-nose-gear');
  await page.locator('#examplesButton').click();
  const openingFeatured = page.locator('.example-card').filter({ has: page.getByRole('heading', { name: 'Aircraft nose-gear kinematics', exact: true }) }).getByRole('button').evaluate(button => button.onclick());
  await featured.seen;
  await page.locator('#examplesDialog [data-close]').click();
  await editMass(2.1);
  const featuredNewer = documentState(await save());
  featured.release();
  await openingFeatured;
  assert.match(await page.locator('#notice').textContent(), /changed|kept/);
  assert(isDeepStrictEqual(documentState(await save()), featuredNewer), 'featured study overwrote edits made while fetching');
  checks.push('Featured study captures current work before its initial fetch');

  const desktop = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  try {
    desktop.on('pageerror', error => errors.push(error.message));
    await desktop.route('**/api/tour-preference', route => route.fulfill({ json: { enabled: false } }));
    const candidate = structuredClone(baseline); delete candidate.result.csvText;
    await desktop.addInitScript(candidate => {
      const host = window.__saveHost = { candidate, payload: null, notifications: [], waiting: false, release: null };
      window.mbdynNative = {
        notify(op) { host.notifications.push(op); },
        async call(op, payload) {
          if (op === 'recovery') return {};
          if (op === 'autosave') return { skipped: true };
          if (op === 'open') return { project: host.candidate, path: 'C:/test/current.mbdyn-studio' };
          if (op === 'accept-open') return { token: '1' };
          if (op === 'finalize-open') return { token: payload.token, dirtyRevision: '1' };
          if (op === 'clean-open') return { token: payload.token, dirtyRevision: payload.dirtyRevision, clean: true };
          if (op === 'save') {
            host.payload = structuredClone(payload); host.waiting = true;
            await new Promise(resolve => host.release = resolve);
            return { path: 'C:/test/current.mbdyn-studio' };
          }
          throw Error(`Unexpected native operation ${op}`);
        },
      };
    }, candidate);
    await desktop.goto(base);
    await desktop.waitForFunction(() => document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
    await desktop.locator('#importButton').click();
    await desktop.waitForFunction(() => /Project opened|Project was not opened/.test(document.querySelector('#notice')?.textContent || ''));
    assert.match(await desktop.locator('#notice').textContent(), /Project opened/);
    const csvSeen = deferred(), csvRelease = deferred();
    await desktop.route('**/api/runs/*/results.csv', async route => {
      const response = await route.fetch(); csvSeen.resolve(); await csvRelease.promise; await route.fulfill({ response });
    });
    await desktop.locator('#saveButton').click();
    await csvSeen.promise;
    await desktop.locator('#graph-body-upper_link-mass').fill('2.7');
    await desktop.locator('#graph-body-upper_link-mass').dispatchEvent('change');
    csvRelease.resolve();
    await desktop.waitForFunction(() => window.__saveHost.waiting);
    await desktop.locator('#graph-body-upper_link-mass').fill('2.8');
    await desktop.locator('#graph-body-upper_link-mass').dispatchEvent('change');
    await desktop.evaluate(() => window.__saveHost.release());
    await desktop.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('newer edits remain unsaved'));
    const host = await desktop.evaluate(() => ({ payload: window.__saveHost.payload, notifications: window.__saveHost.notifications }));
    assert.equal(host.payload.model.bodies[0].mass, baseline.model.bodies[0].mass);
    assert.deepEqual(host.payload.assets, baseline.assets);
    assert.equal(host.payload.result.csvText, baseline.result.csvText);
    assert(host.notifications.includes('dirty'));
    assert.equal(await desktop.locator('#graph-body-upper_link-mass').inputValue(), '2.8');
    checks.push('Native snapshot save preserves edits during CSV loading and save acknowledgement, leaving them dirty');
  } finally { await desktop.close(); }

  assert.deepEqual(errors, []);
  console.log(checks.join('\n'));
} finally {
  await mkdir('tests/evidence', { recursive: true });
  await writeFile('tests/evidence/cad-async-safety.json', JSON.stringify({ checks, errors }, null, 2));
  await browser.close();
}
