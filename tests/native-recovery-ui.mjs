/** Desktop crash recovery against a controlled native bridge: recover, discard, and autosave after edits. */
import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import { chromium } from 'playwright';

const base = process.env.MBDYN_STUDIO_URL || 'http://127.0.0.1:8767';
const browser = await chromium.launch({ headless: true, args: ['--enable-unsafe-swiftshader'] });
const errors = [];

/** A page whose desktop host holds `snapshot` (or nothing) from an earlier session. */
async function desktop(snapshot) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
  page.on('pageerror', (error) => errors.push(error.message));
  await page.route('**/api/tour-preference', (route) => route.fulfill({ json: { enabled: false } }));
  await page.addInitScript((snapshot) => {
    const host = window.__host = { snapshot, ops: [], autosaves: [], pending: false };
    window.mbdynNative = {
      notify(op) { host.ops.push(op); },
      async call(op, payload = {}) {
        host.ops.push(op);
        if (op === 'recovery') return host.snapshot ? { savedAt: host.snapshot.savedAt, path: host.snapshot.path, name: host.snapshot.project.model.name } : {};
        if (op === 'recovery-open') { host.pending = true; return { project: structuredClone(host.snapshot.project), path: host.snapshot.path, savedAt: host.snapshot.savedAt, recovered: true }; }
        if (op === 'recovery-discard') { host.snapshot = null; return { setAside: '/data/recovery/declined-00000000000000000001.json' }; }
        if (op === 'recovery-adopted') return {};
        if (op === 'accept-open') { if (!host.pending) throw new Error('No project is awaiting confirmation.'); host.pending = false; return { token: '1' }; }
        if (op === 'finalize-open') return { token: payload.token, dirtyRevision: '1' };
        if (op === 'clean-open') throw new Error('Recovered work must stay dirty.');
        if (op === 'autosave') { host.autosaves.push(structuredClone(payload)); return { savedAt: Date.now() }; }
        if (op === 'save') return { path: '/projects/oscillator.mbdyn-studio', backup: null };
        throw new Error(`Unsupported test operation: ${op}`);
      },
    };
  }, snapshot);
  await page.goto(base);
  await page.waitForFunction(() => document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
  return page;
}

try {
  const examples = await (await fetch(`${base}/api/examples`)).json();
  const model = structuredClone(examples.examples.find((item) => item.id === 'mass-spring').model);
  model.name = 'Isolator mount';
  model.parameters.stiffness = 123;
  const snapshot = { savedAt: Date.UTC(2026, 9, 29, 14, 32), path: '/projects/isolator.mbdyn-studio', project: { format: 'mbdyn-studio/1', schemaVersion: 1, model, view: null } };

  // Recover: the autosaved model opens as unsaved work and autosave resumes after an edit.
  let page = await desktop(snapshot);
  await page.locator('#recoveryDialog').waitFor({ state: 'visible' });
  const text = await page.locator('#recoveryText').textContent();
  assert.match(text, /“Isolator mount” \(\/projects\/isolator\.mbdyn-studio\)/);
  await page.locator('#recoveryOpen').click();
  await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('Recovered the work autosaved at'));
  assert.equal(await page.locator('#field-stiffness').inputValue(), '123');
  assert.match(await page.locator('#notice').textContent(), /Save asks where to write it, starting at \/projects\/isolator\.mbdyn-studio/);
  let ops = await page.evaluate(() => window.__host.ops);
  assert(ops.includes('recovery-adopted') && ops.includes('dirty') && !ops.includes('clean-open'), ops.join(','));
  assert.equal(await page.locator('#dirtyMark').getAttribute('title'), 'Unsaved changes');
  await page.locator('#field-stiffness').fill('150');
  await page.locator('#field-stiffness').dispatchEvent('change');
  await page.waitForFunction(() => window.__host.autosaves.length > 0, null, { timeout: 30000, polling: 500 });
  const autosaved = await page.evaluate(() => window.__host.autosaves.at(-1));
  assert.equal(autosaved.model.parameters.stiffness, 150);
  assert.equal(autosaved.model.name, 'Isolator mount');
  assert.match(await page.locator('#dirtyMark').getAttribute('title'), /autosaved for recovery at/);
  // Saving cancels the pending snapshot; nothing autosaves until the next edit.
  await page.locator('#field-stiffness').fill('160');
  await page.locator('#field-stiffness').dispatchEvent('change');
  await page.locator('#saveButton').click();
  await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('Project saved'));
  const count = await page.evaluate(() => window.__host.autosaves.length);
  await page.waitForTimeout(17000);
  assert.equal(await page.evaluate(() => window.__host.autosaves.length), count, 'a saved project must not autosave');
  await page.close();

  // Discard: the snapshot is set aside and the start-up model stays.
  page = await desktop(snapshot);
  await page.locator('#recoveryDialog').waitFor({ state: 'visible' });
  await page.locator('#recoveryDiscard').click();
  await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('set aside at /data/recovery/'));
  assert(await page.locator('#recoveryDialog').isHidden());
  ops = await page.evaluate(() => window.__host.ops);
  assert(ops.includes('recovery-discard') && !ops.includes('recovery-open'));
  assert.notEqual(await page.locator('#documentName').textContent(), 'Isolator mount');
  await page.close();

  // No snapshot: no prompt.
  page = await desktop(null);
  await page.waitForFunction(() => window.__host.ops.includes('recovery'));
  assert(await page.locator('#recoveryDialog').isHidden());
  await page.close();
  assert.deepEqual(errors, []);
  console.log('Desktop recovery: recovered as unsaved work with autosave after edits and none after save; discard sets the snapshot aside; no prompt without a snapshot.');
} finally {
  await browser.close();
}
