import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { mkdir, writeFile } from 'node:fs/promises';

const base = process.env.MBDYN_STUDIO_URL || 'http://127.0.0.1:8768';
const browser = await chromium.launch({ headless: true, args: ['--enable-unsafe-swiftshader'], ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } : {}) });
const errors = [], checks = [];
const deferred = () => { let resolve; const promise = new Promise(done => resolve = done); return { promise, resolve }; };

async function desktop(project) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.on('pageerror', error => errors.push(error.message));
  await page.clock.install();
  await page.route('**/api/tour-preference', route => route.fulfill({ json: { enabled: false } }));
  await page.addInitScript(project => {
    const host = window.__autosaveHost = { next: { project, path: 'C:/test/original.mbdyn-studio' }, current: null, pending: null, dirty: false, sequence: 0, autosaves: [], recovery: null, holdAck: false, release: null };
    window.mbdynNative = {
      notify(op) { if (op === 'dirty') host.dirty = true; if (op === 'discard-open') host.pending = null; },
      async call(op, payload = {}) {
        if (op === 'recovery') return {};
        if (op === 'open') { host.pending = structuredClone(host.next); return structuredClone(host.pending); }
        if (op === 'new-project') { host.pending = { project: structuredClone(payload.project), path: null }; return structuredClone(host.pending); }
        if (op === 'accept-open') { host.current = host.pending; host.pending = null; host.dirty = true; return { token: String(++host.sequence) }; }
        if (op === 'finalize-open') return { token: payload.token, dirtyRevision: '1' };
        if (op === 'clean-open') { host.dirty = false; return { token: payload.token, dirtyRevision: payload.dirtyRevision, clean: true }; }
        if (op === 'save') {
          host.current = { project: structuredClone(payload), path: host.current?.path || 'C:/test/new.mbdyn-studio' };
          host.dirty = false; host.recovery = null;
          return { path: host.current.path };
        }
        if (op === 'autosave') {
          if (!host.dirty || host.pending) return { skipped: true };
          const snapshot = { project: structuredClone(payload), path: host.current?.path || null };
          host.autosaves.push(snapshot); host.recovery = snapshot;
          if (host.holdAck) await new Promise(resolve => host.release = resolve);
          return { savedAt: Date.now() };
        }
        throw Error(`Unexpected native operation ${op}`);
      },
    };
  }, project);
  await page.goto(base);
  await page.waitForFunction(() => document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
  await page.locator('#importButton').click();
  await page.waitForFunction(() => /Project opened|Project was not opened/.test(document.querySelector('#notice')?.textContent || ''));
  assert.match(await page.locator('#notice').textContent(), /Project opened/);
  return page;
}
async function changeStiffness(page, value) {
  await page.locator('#field-stiffness').fill(String(value));
  await page.locator('#field-stiffness').dispatchEvent('change');
}
async function settle(page) {
  await page.evaluate(() => new Promise(done => setTimeout(done, 0)));
}
try {
  const request = await browser.newContext();
  const examples = await (await request.request.get(`${base}/api/examples`)).json();
  const model = structuredClone(examples.examples.find(item => item.id === 'mass-spring').model);
  model.name = 'Original autosave document'; model.simulation = { duration: 0.1, step: 0.001 };
  const run = await (await request.request.post(`${base}/api/run`, { data: { model } })).json();
  assert(run.ok, run.error);
  const original = { format: 'mbdyn-studio/1', model, result: run };
  await request.close();

  for (const operation of ['Open', 'New', 'Save', 'Run']) {
    const page = await desktop(original);
    try {
      const csvSeen = deferred(), csvRelease = deferred(), csvDelivered = deferred();
      let newerRun;
      await page.route('**/api/runs/*/results.csv', async route => {
        const response = await route.fetch(); csvSeen.resolve(); await csvRelease.promise; await route.fulfill({ response }); csvDelivered.resolve();
      }, { times: 1 });
      await changeStiffness(page, model.parameters.stiffness + 1);
      await page.clock.fastForward(15001);
      await csvSeen.promise;

      if (operation === 'Open') {
        const replacement = { format: 'mbdyn-studio/1', model: { ...structuredClone(model), name: 'Replacement autosave document' } };
        await page.evaluate(project => { window.__autosaveHost.next = { project, path: 'C:/test/replacement.mbdyn-studio' }; }, replacement);
        await page.locator('#importButton').click();
        await page.waitForFunction(() => document.querySelector('#documentName')?.textContent.includes('Replacement autosave document'));
        await changeStiffness(page, model.parameters.stiffness + 2);
      } else if (operation === 'New') {
        await page.locator('#newButton').click();
        await page.waitForFunction(() => document.querySelector('#documentName')?.textContent.includes('Untitled 3D assembly'));
        await page.locator('#spatial-model-name').fill('Newest untitled document');
        await page.locator('#spatial-model-name').dispatchEvent('change');
      } else if (operation === 'Save') {
        await changeStiffness(page, model.parameters.stiffness + 3);
        await page.locator('#saveButton').click();
      } else {
        const response = page.waitForResponse(response => response.url().endsWith('/api/run') && response.request().method() === 'POST', { timeout: 120000 });
        await page.locator('#runButton').click();
        newerRun = await (await response).json(); assert(newerRun.ok, newerRun.error);
        await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('MBDyn completed successfully'));
      }
      csvRelease.resolve();
      await csvDelivered.promise;
      await settle(page);
      assert.equal(await page.evaluate(() => window.__autosaveHost.autosaves.length), 0, 'a stale autosave reached the host');
      if (operation === 'Save') {
        await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('Project saved'));
        await page.clock.fastForward(60001);
        await settle(page);
        const host = await page.evaluate(() => window.__autosaveHost);
        assert.equal(host.autosaves.length, 0);
        assert.equal(host.recovery, null);
        assert.equal(host.current.project.model.parameters.stiffness, model.parameters.stiffness + 3);
        assert.equal(await page.locator('#dirtyMark').getAttribute('title'), 'Saved project');
      } else {
        await page.clock.fastForward(15001);
        await page.waitForFunction(() => window.__autosaveHost.autosaves.length > 0);
        const host = await page.evaluate(() => window.__autosaveHost);
        if (operation === 'Run') {
          assert(host.autosaves.every(snapshot => snapshot.project.result?.runId === newerRun.runId), 'an older solver result reached recovery');
          assert.equal(host.recovery.path, 'C:/test/original.mbdyn-studio');
        } else {
          assert(host.autosaves.every(snapshot => snapshot.project.model.name !== model.name), 'an old document was autosaved under the new identity');
          assert.equal(host.recovery.project.model.name, operation === 'Open' ? 'Replacement autosave document' : 'Newest untitled document');
          assert.equal(host.recovery.path, operation === 'Open' ? 'C:/test/replacement.mbdyn-studio' : null);
        }
      }
      checks.push(`Delayed CSV autosave followed by ${operation} preserves the latest document and recovery identity`);
    } finally { await page.close(); }
  }

  const page = await desktop({ format: 'mbdyn-studio/1', model });
  try {
    await page.evaluate(() => { window.__autosaveHost.holdAck = true; });
    await changeStiffness(page, model.parameters.stiffness + 4);
    await page.clock.fastForward(15001);
    await page.waitForFunction(() => typeof window.__autosaveHost.release === 'function');
    await page.locator('#saveButton').click();
    await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('Project saved'));
    await page.evaluate(() => window.__autosaveHost.release());
    await settle(page);
    await page.clock.fastForward(60001);
    const host = await page.evaluate(() => window.__autosaveHost);
    assert.equal(host.recovery, null);
    assert.equal(host.autosaves.length, 1);
    assert.equal(await page.locator('#dirtyMark').getAttribute('title'), 'Saved project');
    checks.push('A delayed autosave acknowledgement after Save cannot restore the dirty/recovery marker');
  } finally { await page.close(); }

  assert.deepEqual(errors, []);
  console.log(checks.join('\n'));
} finally {
  await mkdir('tests/evidence', { recursive: true });
  await writeFile('tests/evidence/autosave-race.json', JSON.stringify({ checks, errors }, null, 2));
  await browser.close();
}
