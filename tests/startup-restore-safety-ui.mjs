import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { mkdir, readFile, writeFile } from 'node:fs/promises';

const base = process.env.MBDYN_STUDIO_URL || 'http://127.0.0.1:8768';
const browser = await chromium.launch({ headless: true, args: ['--enable-unsafe-swiftshader'], ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } : {}) });
const errors = [], checks = [];
const deferred = () => { let resolve; const promise = new Promise(done => resolve = done); return { promise, resolve }; };
async function desktop(model) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
  page.on('pageerror', error => errors.push(error.message));
  page.on('dialog', dialog => dialog.accept());
  await page.addInitScript(model => localStorage.setItem('mbdyn-studio-project', JSON.stringify({ format: 'mbdyn-studio/1', model })), model);
  const ready = deferred();
  await page.route('**/api/tour-preference', async route => { await route.fulfill({ json: { enabled: false } }); ready.resolve(); });
  return { page, ready: ready.promise };
}
async function hold(page, pattern, match = () => true) {
  const seen = deferred(), released = deferred();
  await page.route(pattern, async route => {
    if (!match(route.request())) return route.continue();
    const response = await route.fetch(); seen.resolve(); await released.promise; await route.fulfill({ response });
  });
  return { seen: seen.promise, release: released.resolve };
}
try {
  const request = await browser.newContext();
  const examples = await (await request.request.get(`${base}/api/examples`)).json();
  const cached = structuredClone(examples.examples.find(item => item.id === 'mass-spring').model);
  cached.name = 'Cached startup document'; cached.parameters.stiffness = 123;
  await request.close();

  let { page, ready } = await desktop(cached);
  try {
    await page.goto(base); await ready;
    assert.equal(await page.locator('#documentName').textContent(), cached.name);
    assert.equal(await page.locator('#field-stiffness').inputValue(), '123');
    checks.push('Unchanged startup restores the validated cached model');
  } finally { await page.close(); }

  ({ page, ready } = await desktop(cached));
  try {
    const initial = await hold(page, '**/api/status');
    await page.goto(base); await initial.seen;
    await page.locator('#field-angle').fill('31'); await page.locator('#field-angle').dispatchEvent('change');
    initial.release(); await ready;
    assert.equal(await page.locator('#field-angle').inputValue(), '31');
    assert.equal(await page.locator('#documentName').textContent(), 'Gravity pendulum');
    checks.push('Edits before the initial service responses survive startup');
  } finally { await page.close(); }

  for (const action of ['edit', 'pending input', 'New', 'Open']) {
    ({ page, ready } = await desktop(cached));
    try {
      const startup = await hold(page, '**/api/validate', request => request.postDataJSON()?.model?.name === cached.name);
      await page.goto(base); await startup.seen;
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
        await latest.seen;
      }
      startup.release(); await ready;
      if (action === 'edit' || action === 'pending input') assert.equal(await page.evaluate(() => document.querySelector('#field-angle')?.value), '32', 'cached startup state overwrote the newer edit');
      else if (action === 'New') assert.equal(await page.locator('#documentName').textContent(), 'Untitled 3D assembly');
      else {
        assert.notEqual(await page.locator('#documentName').textContent(), cached.name);
        latest.release(); await opening;
        assert.equal(await page.locator('#documentName').textContent(), project.model.name);
      }
      checks.push(`Delayed cached-model validation preserves a newer ${action} operation`);
    } finally { await page.close(); }
  }

  ({ page, ready } = await desktop(cached));
  try {
    await page.goto(base); await ready;
    await page.locator('#newButton').click();
    await page.waitForFunction(() => document.querySelector('#documentName')?.textContent.includes('Untitled 3D assembly'));
    await page.getByText('Calculate mass and inertia from a uniform solid').click();
    const generation = await hold(page, '**/api/step/primitive');
    await page.getByRole('button', { name: 'Create STEP solid and apply mass' }).click();
    await generation.seen;
    await page.locator('#spatial-model-name').fill('Still editing during generation');
    generation.release();
    await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('nothing was applied'));
    assert.equal(await page.locator('#spatial-model-name').inputValue(), 'Still editing during generation');
    assert(await page.locator('#stepStatus').isHidden());
    checks.push('A stale generated solid preserves typed input before change/blur');

    const conversion = await hold(page, '**/api/step/convert');
    await page.locator('#stepButton').click();
    await page.locator('#stepFile').setInputFiles({ name: 'pendulum.step', mimeType: 'application/step', buffer: await readFile('examples/step-pendulum/pendulum.step') });
    await conversion.seen;
    await page.locator('#stepClose').click();
    await page.locator('#spatial-model-name').fill('Still editing during import');
    conversion.release();
    await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('your edits were kept'));
    assert.equal(await page.locator('#spatial-model-name').inputValue(), 'Still editing during import');
    assert(await page.locator('#stepStatus').isHidden());
    checks.push('A stale STEP import preserves typed input before change/blur');
  } finally { await page.close(); }
  assert.deepEqual(errors, []);
  console.log(checks.join('\n'));
} finally {
  await mkdir('tests/evidence', { recursive: true });
  await writeFile('tests/evidence/startup-restore-safety.json', JSON.stringify({ checks, errors }, null, 2));
  await browser.close();
}
