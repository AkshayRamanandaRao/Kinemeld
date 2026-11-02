/** Desktop copies must establish a pathless host session, including rollback and cancelled saves. */
import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { mkdir, writeFile } from 'node:fs/promises';

const base = process.env.MBDYN_STUDIO_URL || 'http://127.0.0.1:8782';
const browser = await chromium.launch({ headless: true, args: ['--enable-unsafe-swiftshader'], ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } : {}) });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } }), errors = [], checks = [];
page.on('pageerror', error => errors.push(error.message));
await page.route('**/api/tour-preference', route => route.fulfill({ json: { enabled: false } }));
await page.addInitScript(() => {
  const host = window.__newHost = { current: { path: 'C:/test/original.mbdyn-studio', project: null }, pending: null, previous: null, files: {}, dirty: false, revision: 0, sequence: 0, dialogs: 0, cancelSave: false, cancelNew: false, target: 'C:/test/copy.mbdyn-studio', mode: '', waiting: '', autosaves: [], cleanCalls: 0, rollbacks: 0 };
  window.mbdynNative = {
    notify(op) {
      if (op === 'dirty') { host.dirty = true; host.revision++; }
      if (op === 'discard-open') host.pending = null;
    },
    async call(op, payload = {}) {
      if (op === 'recovery') return {};
      if (op === 'new-project') {
        if (host.cancelNew) return { cancelled: true };
        host.pending = { path: null, project: structuredClone(payload.project) };
        return { project: structuredClone(payload.project) };
      }
      if (op === 'accept-open') {
        assertPending();
        host.previous = host.current; host.current = host.pending; host.pending = null;
        host.sequence++; host.revision++; host.dirty = true;
        if (host.mode === 'accept-delay') { host.waiting = 'accept'; await new Promise(resolve => host.release = resolve); host.waiting = ''; }
        return { token: String(host.sequence) };
      }
      if (op === 'finalize-open') { host.previous = null; return { token: payload.token, dirtyRevision: String(host.revision) }; }
      if (op === 'clean-open') { host.cleanCalls++; throw Error('An unsaved copy must not be marked clean.'); }
      if (op === 'rollback-open') { host.current = host.previous; host.previous = null; host.rollbacks++; return {}; }
      if (op === 'save') {
        host.current.project = structuredClone({ format: 'mbdyn-studio/1', model: payload.model, result: payload.result, view: payload.view, assets: payload.assets });
        if (!host.current.path || payload.saveAs) {
          host.dialogs++;
          if (host.cancelSave) return { cancelled: true };
          host.current.path = host.target;
        }
        host.files[host.current.path] = structuredClone(host.current.project); host.dirty = false;
        return { path: host.current.path };
      }
      if (op === 'autosave') { host.autosaves.push({ path: host.current.path, project: structuredClone(payload) }); return { savedAt: Date.now() }; }
      throw Error(`Unexpected native operation: ${op}`);
    },
  };
  function assertPending() { if (!host.pending) throw Error('No pending project.'); }
});
const host = () => page.evaluate(() => structuredClone({ ...window.__newHost, release: undefined }));
async function save() {
  await page.locator('#saveButton').evaluate(button => button.onclick());
  return host();
}
async function importProject(project) {
  await page.evaluate(async project => {
    await document.querySelector('#projectFile').onchange({ target: { files: [new File([JSON.stringify(project)], 'copy.mbdyn-studio')], value: '' } });
  }, project);
}
async function example(title) {
  await page.locator('#examplesButton').click();
  await page.locator('.example-card').filter({ has: page.getByRole('heading', { name: title, exact: true }) }).getByRole('button').evaluate(button => button.onclick());
}
const contents = project => {
  const result = structuredClone(project.result); if (result) delete result.restored;
  return JSON.parse(JSON.stringify({ model: project.model, assets: project.assets, result }));
};
try {
  await page.goto(base);
  await page.waitForFunction(() => document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
  await page.locator('#stepButton').click(); await page.locator('#stepPendulum').click();
  await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('Matching STEP solid and rigid pendulum loaded'), null, { timeout: 120000 });
  const response = page.waitForResponse(response => response.url().endsWith('/api/run') && response.request().method() === 'POST', { timeout: 120000 });
  await page.locator('#runButton').click(); assert((await (await response).json()).ok);
  await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('MBDyn completed successfully'));
  let state = await save(), original = structuredClone(state.files['C:/test/original.mbdyn-studio']);
  assert.equal(Object.keys(original.assets.step.bindings).length, 1); assert.equal(original.result.source, 'MBDyn'); assert(original.result.csvText);
  const copy = structuredClone(original); copy.model.name = 'Imported unsaved copy'; copy.result.model.name = copy.model.name;
  await importProject(copy);
  assert.equal((await host()).current.path, null); assert.equal(await page.locator('#dirtyMark').getAttribute('title'), 'Unsaved changes');
  await page.evaluate(() => { window.__newHost.cancelSave = true; });
  const beforeDialogs = (await host()).dialogs;
  await save(); state = await save();
  assert.equal(state.dialogs, beforeDialogs + 2); assert.equal(state.current.path, null); assert.deepEqual(state.files['C:/test/original.mbdyn-studio'], original);
  await page.evaluate(() => { window.__newHost.cancelSave = false; });
  state = await save();
  assert.equal(state.current.path, 'C:/test/copy.mbdyn-studio'); assert.deepEqual(contents(state.current.project), contents(copy));
  assert.deepEqual(state.files['C:/test/original.mbdyn-studio'], original);
  checks.push('Desktop text import keeps model, CAD bindings, result and CSV in a pathless copy; repeated cancelled saves keep asking for a file');

  await page.locator('#newButton').evaluate(button => button.onclick());
  assert.equal(await page.locator('#viewportName').textContent(), 'Untitled 3D assembly'); assert.equal((await host()).current.path, null);
  assert.equal(await page.locator('#dirtyMark').getAttribute('title'), 'Unsaved changes');
  await page.waitForFunction(() => window.__newHost.autosaves.some(item => item.project.model.name === 'Untitled 3D assembly'), null, { timeout: 25000 });
  state = await host(); assert.equal(state.autosaves.at(-1).path, null); assert.deepEqual(state.files['C:/test/original.mbdyn-studio'], original);
  checks.push('New clears native file identity and autosaves with no previous project path');

  const template = (await (await page.request.get(`${base}/api/examples`)).json()).examples.find(item => item.id === 'mass-spring').model;
  await page.route('**/api/featured/aircraft-nose-gear', route => route.fulfill({ json: { format: 'mbdyn-studio/1', model: { ...template, name: 'Featured unsaved copy' } } }));
  await example('Aircraft nose-gear kinematics');
  assert.equal((await host()).current.path, null); assert.equal(await page.locator('#dirtyMark').getAttribute('title'), 'Unsaved changes');
  await example('Damped oscillator');
  assert.equal((await host()).current.path, null); assert.match(await page.locator('#notice').textContent(), /unsaved copy/);
  assert.equal((await host()).cleanCalls, 0);
  checks.push('Featured studies and ordinary desktop examples open unsaved and never request a clean acknowledgement');

  await page.evaluate(() => { window.__newHost.target = 'C:/test/latest.mbdyn-studio'; });
  state = await save(); const savedBeforeRace = structuredClone(state.files['C:/test/latest.mbdyn-studio']);
  await page.evaluate(() => { window.__newHost.mode = 'accept-delay'; });
  const opening = page.locator('#newButton').evaluate(button => button.onclick());
  await page.waitForFunction(() => window.__newHost.waiting === 'accept');
  await page.locator('#field-stiffness').fill('222'); await page.locator('#field-stiffness').dispatchEvent('change');
  await page.evaluate(() => window.__newHost.release()); await opening;
  state = await host();
  assert.equal(state.current.path, 'C:/test/latest.mbdyn-studio'); assert.equal(await page.locator('#field-stiffness').inputValue(), '222');
  assert.deepEqual(state.files['C:/test/latest.mbdyn-studio'], savedBeforeRace); assert.equal(state.rollbacks, 1);
  assert.match(await page.locator('#notice').textContent(), /your edits were kept/);
  checks.push('Edits during New acceptance abort the copy and restore the previous native file identity');

  await save();
  await page.evaluate(() => {
    window.__newHost.mode = '';
    const name = document.querySelector('#viewportName'), text = Object.getOwnPropertyDescriptor(Node.prototype, 'textContent');
    Object.defineProperty(name, 'textContent', { configurable: true, get() { return text.get.call(this); }, set(value) { text.set.call(this, value); if (value === 'Untitled 3D assembly') { delete this.textContent; throw Error('Injected new-project display failure'); } } });
  });
  await page.locator('#newButton').evaluate(button => button.onclick());
  state = await host(); assert.equal(state.current.path, 'C:/test/latest.mbdyn-studio'); assert.equal(state.rollbacks, 2);
  assert.equal(await page.locator('#field-stiffness').inputValue(), '222'); assert.match(await page.locator('#notice').textContent(), /Injected new-project display failure/);
  await page.evaluate(() => { window.__newHost.cancelNew = true; });
  await page.locator('#newButton').evaluate(button => button.onclick());
  assert.equal((await host()).current.path, 'C:/test/latest.mbdyn-studio'); assert.deepEqual((await host()).files['C:/test/original.mbdyn-studio'], original);
  checks.push('Display failure rolls back both document and file identity; declining New leaves the current file untouched');
  assert.deepEqual(errors, []);
  await mkdir('tests/evidence', { recursive: true });
  await writeFile('tests/evidence/native-new-project.json', JSON.stringify({ ok: true, checks }, null, 2));
  console.log(checks.join('\n'));
} finally { await browser.close(); }
