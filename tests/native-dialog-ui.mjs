/** Real English-Windows GUI regression: native executable, WebView2 CDP and owned Win32 dialogs.
 * KINEMELD_NATIVE_EXE, KINEMELD_NATIVE_SOLVER_CONFIG and MBDYN_STUDIO_PYTHON are required.
 * KINEMELD_NATIVE_PROJECT defaults to the shipped nose-gear project; missing results are solved.
 * No native bridge or file dialog is replaced. Evidence is written under tests/evidence/.
 */
import assert from 'node:assert/strict';
import { spawn, execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { readFile, writeFile, mkdir, mkdtemp, copyFile, readdir, access } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { createServer } from 'node:net';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const root = fileURLToPath(new URL('../', import.meta.url)), run = promisify(execFile);
await mkdir(join(root, 'tests/evidence'), { recursive: true });
const output = await mkdtemp(join(root, 'tests/evidence/native-dialogs-'));
const report = { started: new Date().toISOString(), platform: process.platform, ok: false, checks: [], skipped: [], nativeControls: [], output };
const reportPath = join(output, 'report.json'), port = 8793;
let app, browser, page, backendUrl, stopped = false;
const data = join(output, 'user-data'), helper = join(root, 'tests/native-dialog-controls.py');
const exists = path => access(path).then(() => true, () => false);
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const saveReport = () => writeFile(reportPath, JSON.stringify(report, null, 2));
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(read, timeout, label) {
  const deadline = Date.now() + timeout;
  do { const value = await read(); if (value) return value; await sleep(100); } while (Date.now() < deadline);
  throw Error(`Timed out after ${timeout} ms: ${label}`);
}
async function check(name, action) {
  const item = { name, ok: false, started: new Date().toISOString() }; report.checks.push(item);
  try { item.evidence = await action(); item.ok = true; }
  catch (error) { item.error = error.stack; throw error; }
  finally { item.completed = new Date().toISOString(); await saveReport(); }
}
async function control(command, ...args) {
  let stdout;
  try { ({ stdout } = await run(process.env.MBDYN_STUDIO_PYTHON, [helper, '--pid', String(app.pid), command, ...args], { timeout: 20000, maxBuffer: 2 * 1024 * 1024, encoding: 'utf8' })); }
  catch (error) {
    const detail = error.stdout?.trim() || error.message;
    report.nativeControls.push({ command, ok: false, error: detail });
    throw Error(`Native control ${command} failed: ${detail}`);
  }
  const value = JSON.parse(stdout); assert(value.ok, JSON.stringify(value));
  report.nativeControls.push({ command, ...value });
  return value;
}
const screenshot = (name, title = '^Kinemeld$') => control('screenshot', '--title', title, '--out', join(output, `${name}.png`));
const beginClick = selector => { const action = page.locator(selector).click({ timeout: 20000 }); action.catch(() => {}); return action; };
async function settled(title) {
  await until(async () => !(await control('list')).windows.some(window => window.class === '#32770' && new RegExp(title).test(window.text)), 10000, `dialog closed: ${title}`);
  await page.evaluate(() => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done))));
}
async function question(yes, name, closing = false) {
  await control('wait', '--title', '^Unsaved project$');
  if (name) await screenshot(name, '^Unsaved project$');
  await control('button', '--title', '^Unsaved project$', '--text', yes ? '^Yes$' : '^No$');
  if (!closing) await settled('^Unsaved project$');
}
async function chooseFile(title, path, image) {
  await control('wait', '--title', title);
  if (image) await screenshot(image, title);
  await control('file', '--title', title, '--path', path);
}
async function openFile(path, { invalid = false } = {}) {
  const clicking = beginClick('#importButton');
  const first = await control('wait', '--title', '^(Open|Unsaved project)$');
  if (first.window.text === 'Unsaved project') await question(true);
  await chooseFile('^Open$', path, 'native-open-dialog');
  await clicking;
  await page.waitForFunction(invalid => document.querySelector('#notice')?.textContent.includes(invalid ? 'Project was not opened' : 'Project opened'), invalid, { timeout: 120000 });
}
async function saveAs(path, image) {
  const clicking = beginClick('#saveAsButton');
  await chooseFile('^Save As$', path, image);
  await clicking;
  await page.waitForFunction(name => { const text = document.querySelector('#notice')?.textContent || ''; return text.includes('Project saved to') && text.includes(name); }, basename(path), { timeout: 30000 });
  await until(() => exists(path), 5000, 'native saved file');
}
async function cancelSaveAs(selector = '#saveAsButton', image) {
  const clicking = beginClick(selector);
  await control('wait', '--title', '^Save As$');
  if (image) await screenshot(image, '^Save As$');
  await control('cancel', '--title', '^Save As$'); await clicking; await settled('^Save As$');
  await page.waitForFunction(() => !document.querySelector('#saveButton').disabled);
}
async function setName(value) {
  await page.locator('[data-step="model"]').first().click();
  await page.locator('#modelTree [data-entity="body"]').click();
  const field = page.locator('#spatial-model-name'); await field.fill(value); await field.dispatchEvent('change');
}
const stored = project => {
  const result = structuredClone(project.result || null); if (result) delete result.restored;
  return JSON.parse(JSON.stringify({ model: project.model, assets: project.assets || null, result }));
};
async function health() {
  try { return (await fetch(`${backendUrl}/api/health`, { signal: AbortSignal.timeout(1000) })).ok; } catch { return false; }
}
async function freePort() {
  const server = createServer();
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(port, '127.0.0.1', resolve); });
  await new Promise(resolve => server.close(resolve));
}
async function launch() {
  await freePort();
  const environment = { ...process.env }; delete environment.MBDYN_STUDIO_WORKSPACE;
  app = spawn(report.executable, [], { cwd: dirname(report.executable), stdio: 'ignore', env: { ...environment,
    MBDYN_STUDIO_DATA_DIR: data,
    WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS: `${process.env.WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS || ''} --remote-debugging-address=127.0.0.1 --remote-debugging-port=${port}`,
  } });
  let launchError; app.once('error', error => { launchError = error; });
  report.nativePids = [...(report.nativePids || []), app.pid];
  await until(async () => {
    if (launchError) throw launchError;
    if (app.exitCode !== null || app.signalCode !== null) throw Error(`Native app exited during startup: ${app.exitCode ?? app.signalCode}`);
    try { return (await fetch(`http://127.0.0.1:${port}/json/version`, { signal: AbortSignal.timeout(1000) })).ok; } catch { return false; }
  }, 90000, 'native WebView2 CDP endpoint');
  browser = await chromium.connectOverCDP(`http://127.0.0.1:${port}`);
  page = await until(() => browser.contexts().flatMap(context => context.pages()).find(page => /^http:\/\/127\.0\.0\.1:\d+\//.test(page.url())), 30000, 'native app page');
  page.on('pageerror', error => { report.pageErrors = [...(report.pageErrors || []), error.message]; });
  page.setDefaultTimeout(20000);
  backendUrl = new URL(page.url()).origin;
  assert(await page.evaluate(() => Boolean(window.mbdynNative?.call) && Boolean(window.ipc?.postMessage)), 'The actual native IPC bridge is absent');
  await page.waitForFunction(() => document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'), null, { timeout: 90000 });
}
async function stop(crash = false) {
  if (!app) return;
  const children = (await control('children')).children;
  if (crash) { if (app.exitCode === null && app.signalCode === null) app.kill(); }
  else { await control('close'); await question(true, undefined, true); }
  await until(() => app.exitCode !== null || app.signalCode !== null, 15000, 'native process exit');
  if (crash) {
    const remaining = (await control('children')).children;
    for (const child of remaining.filter(item => children.some(before => before.pid === item.pid))) {
      try { await control('terminate-child', '--child-pid', String(child.pid)); }
      catch (error) { if ((await control('children')).children.some(item => item.pid === child.pid)) throw error; }
    }
  }
  await browser?.close().catch(() => {});
  await until(async () => !(await health()), 10000, 'owned backend stopped');
  stopped = true;
}

try {
  assert.equal(process.platform, 'win32', 'This required native GUI suite runs on Windows.');
  for (const key of ['KINEMELD_NATIVE_EXE', 'KINEMELD_NATIVE_SOLVER_CONFIG', 'MBDYN_STUDIO_PYTHON']) assert(process.env[key], `${key} is required`);
  report.executable = resolve(process.env.KINEMELD_NATIVE_EXE);
  report.project = resolve(process.env.KINEMELD_NATIVE_PROJECT || join(root, 'examples/open-aircraft-nose-kinematics/nose-gear-kinematics.mbdyn-studio'));
  const fixtureBytes = await readFile(report.project), fixture = JSON.parse(fixtureBytes);
  assert.equal(fixture.model?.kind, 'spatial-assembly', 'Choose a saved 3D assembly with attached STEP geometry.');
  assert(Object.keys(fixture.assets?.step?.bindings || {}).length, 'The fixture needs CAD bindings to verify persistence.');
  report.executableSha256 = digest(await readFile(report.executable)); report.fixtureSha256 = digest(fixtureBytes);
  let resources = dirname(report.executable);
  while (!(await exists(join(resources, 'backend/server.py'))) && dirname(resources) !== resources) resources = dirname(resources);
  assert(await exists(join(resources, 'backend/server.py')), 'The executable needs an ancestor containing its resources.');
  report.resourceRoot = resources; report.workspaceOverride = false;
  report.frontendSha256 = digest(await readFile(join(resources, 'frontend/app.js')));
  await mkdir(data, { recursive: true });
  await copyFile(resolve(process.env.KINEMELD_NATIVE_SOLVER_CONFIG), join(data, 'solver.json'));
  await mkdir(join(data, 'runs'), { recursive: true }); await writeFile(join(data, 'runs/tour-preference.json'), JSON.stringify({ enabled: false }));
  await launch();
  await check('Actual WebView2 and owned solver service start with isolated user data', async () => {
    assert(await health()); await screenshot('app-startup');
    return { pid: app.pid, url: page.url(), nativeBridge: 'actual IPC, unmodified', data };
  });
  let expected = fixture, recoverySnapshot;
  const copy = join(output, 'roundtrip.mbdyn-studio'), fresh = join(output, 'after-conflict.mbdyn-studio');
  await check('Native Open, Save As and reopen preserve model, STEP bindings, result and full CSV', async () => {
    await openFile(report.project);
    if (!fixture.result?.samples?.length || (fixture.result.source === 'MBDyn' && !fixture.result.csvText)) {
      const response = page.waitForResponse(response => response.url().endsWith('/api/run') && response.request().method() === 'POST', { timeout: 180000 });
      await page.locator('#runButton').click(); const result = await (await response).json(); assert(result.ok, JSON.stringify(result.error));
      if (result.files?.csv) result.csvText = await (await page.request.get(`${backendUrl}${result.files.csv}`)).text();
      result.model = structuredClone(fixture.model); expected = { ...fixture, result };
      await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('MBDyn completed successfully'));
    }
    await saveAs(copy, 'native-save-as-dialog');
    const saved = JSON.parse(await readFile(copy, 'utf8')); assert.deepEqual(stored(saved), stored(expected));
    await openFile(copy); await page.waitForFunction(() => document.querySelector('#resultSource')?.textContent.includes('recorded MBDyn'));
    await screenshot('roundtrip-app');
    return { file: copy, bindings: Object.keys(saved.assets.step.bindings).length, samples: saved.result.samples.length, csvBytes: Buffer.byteLength(saved.result.csvText) };
  });
  await check('Cancel native Save As leaves the file and destination unchanged', async () => {
    const before = await readFile(copy), entries = await readdir(output);
    await cancelSaveAs(); assert.deepEqual(await readFile(copy), before);
    assert.deepEqual((await readdir(output)).filter(name => !name.endsWith('.png') && name !== 'report.json'), entries.filter(name => !name.endsWith('.png') && name !== 'report.json'));
    return { unchangedSha256: digest(before) };
  });
  await check('Declining the native overwrite confirmation preserves the target', async () => {
    const target = join(output, 'overwrite-target.mbdyn-studio'); await writeFile(target, fixtureBytes);
    const clicking = beginClick('#saveAsButton'); await chooseFile('^Save As$', target);
    await control('wait', '--title', 'Confirm Save As'); await screenshot('overwrite-confirmation', 'Confirm Save As');
    await control('button', '--title', 'Confirm Save As', '--text', '^No$');
    await settled('Confirm Save As'); await control('cancel', '--title', '^Save As$'); await clicking; await settled('^Save As$');
    assert.deepEqual(await readFile(target), fixtureBytes);
    return { file: target, unchangedSha256: digest(fixtureBytes) };
  });
  await check('Ordinary native Save retains the prior file as a backup', async () => {
    const before = await readFile(copy), entries = new Set(await readdir(output));
    await setName('Native GUI edited snapshot'); await page.locator('#saveButton').click();
    await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('Previous version retained'));
    const backups = (await readdir(output)).filter(name => !entries.has(name) && name.startsWith(`.${basename(copy)}.mbdyn-backup-`));
    assert.equal(backups.length, 1); assert.deepEqual(await readFile(join(output, backups[0])), before);
    assert.equal(JSON.parse(await readFile(copy, 'utf8')).model.name, 'Native GUI edited snapshot');
    return { backup: join(output, backups[0]), previousSha256: digest(before) };
  });
  await check('External file edits reject Save and survive a fresh native Save As', async () => {
    const external = JSON.parse(await readFile(copy, 'utf8')); external.model.name = 'External edit must survive';
    const bytes = Buffer.from(JSON.stringify(external)); await writeFile(copy, bytes); await setName('Unsaved GUI edit');
    await page.locator('#saveButton').click(); await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('project changed on disk'));
    assert.deepEqual(await readFile(copy), bytes); await saveAs(fresh);
    assert.equal(JSON.parse(await readFile(fresh, 'utf8')).model.name, 'Unsaved GUI edit'); assert.deepEqual(await readFile(copy), bytes);
    return { externalFile: copy, externalSha256: digest(bytes), savedCopy: fresh };
  });
  await check('New → Save opens a real picker on both cancellation attempts and autosaves without the old path', async () => {
    const before = await readFile(fresh); await page.locator('#newButton').click();
    await page.waitForFunction(() => document.querySelector('#viewportName')?.textContent === 'Untitled 3D assembly' && document.querySelector('#notice')?.textContent.includes('New 3D assembly'));
    assert.equal(await page.locator('#dirtyMark').getAttribute('title'), 'Unsaved changes');
    await cancelSaveAs('#saveButton', 'new-project-save-picker'); await cancelSaveAs('#saveButton');
    assert.deepEqual(await readFile(fresh), before);
    const path = join(data, 'recovery/autosave.json');
    const snapshot = await until(async () => { try { const value = JSON.parse(await readFile(path, 'utf8')); return value.document.model.name === 'Untitled 3D assembly' ? value : false; } catch { return false; } }, 25000, 'new document autosave');
    assert.equal(snapshot.projectPath ?? null, null); assert.deepEqual(await readFile(report.project), fixtureBytes);
    return { recovery: path, previousFileUnchanged: digest(before), recoveryProjectPath: null };
  });
  await check('Autosave retains the full CAD and solver result before a crash', async () => {
    await openFile(fresh); await setName('Crash recovery GUI');
    const path = join(data, 'recovery/autosave.json');
    recoverySnapshot = await until(async () => { try { const value = JSON.parse(await readFile(path, 'utf8')); return value.document.model.name === 'Crash recovery GUI' ? value : false; } catch { return false; } }, 25000, 'full project autosave');
    const disk = JSON.parse(await readFile(fresh, 'utf8')); disk.model.name = 'Crash recovery GUI';
    assert.deepEqual(stored(recoverySnapshot.document), stored(disk));
    const retained = join(output, 'pre-crash-autosave.json'); await writeFile(retained, JSON.stringify(recoverySnapshot, null, 2));
    return { file: path, retained, bindings: Object.keys(recoverySnapshot.document.assets.step.bindings).length, samples: recoverySnapshot.document.result.samples.length, projectPath: recoverySnapshot.projectPath };
  });
  await check('Dirty Open refusal and subsequent picker cancellation keep the new work', async () => {
    let clicking = beginClick('#importButton'); await question(false, 'dirty-open-refusal'); await clicking;
    assert.equal(await page.locator('#viewportName').textContent(), 'Crash recovery GUI');
    clicking = beginClick('#importButton'); await question(true); await control('wait', '--title', '^Open$');
    await control('cancel', '--title', '^Open$'); await clicking; await settled('^Open$');
    assert.equal(await page.locator('#viewportName').textContent(), 'Crash recovery GUI');
    return { model: 'Crash recovery GUI', dirty: await page.locator('#dirtyMark').getAttribute('title') };
  });
  await check('Invalid native file open reports failure and preserves current work', async () => {
    const invalid = join(output, 'invalid.mbdyn-studio'); await writeFile(invalid, '{not valid JSON');
    await openFile(invalid, { invalid: true }); assert.equal(await page.locator('#viewportName').textContent(), 'Crash recovery GUI');
    await screenshot('invalid-file-preserved'); return { invalid, notice: await page.locator('#notice').textContent() };
  });
  await check('Crash recovery restores the actual autosave as unsaved work with a native Save picker', async () => {
    await stop(true); stopped = false; await launch();
    await page.locator('#recoveryDialog').waitFor({ state: 'visible' }); await page.locator('#recoveryOpen').click();
    await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('Recovered the work autosaved'));
    assert.equal(await page.locator('#viewportName').textContent(), 'Crash recovery GUI'); assert.equal(await page.locator('#dirtyMark').getAttribute('title'), 'Unsaved changes');
    await screenshot('recovered-app'); await cancelSaveAs('#saveButton', 'recovered-save-picker');
    const recovered = join(output, 'recovered-roundtrip.mbdyn-studio'); await saveAs(recovered);
    assert.deepEqual(stored(JSON.parse(await readFile(recovered, 'utf8'))), stored(recoverySnapshot.document));
    await setName('Recovered GUI close test');
    await until(async () => { try { return JSON.parse(await readFile(join(data, 'recovery/autosave.json'), 'utf8')).document.model.name === 'Recovered GUI close test'; } catch { return false; } }, 25000, 'recovered document autosave');
    return { pid: app.pid, restoredName: 'Crash recovery GUI', file: recovered, bindings: Object.keys(recoverySnapshot.document.assets.step.bindings).length, samples: recoverySnapshot.document.result.samples.length };
  });
  await check('Dirty close refusal retains work; confirmed normal close clears recovery and stops its backend', async () => {
    await control('close'); await question(false, 'dirty-close-refusal'); assert.equal(app.exitCode, null); assert(await health());
    assert.equal(await page.locator('#viewportName').textContent(), 'Recovered GUI close test');
    await stop(); assert(!(await exists(join(data, 'recovery/autosave.json')))); assert.deepEqual(await readFile(report.project), fixtureBytes);
    return { exitCode: app.exitCode, backendStopped: true, recoveryCleared: true, fixtureUnchanged: report.fixtureSha256 };
  });
  assert.deepEqual(report.pageErrors || [], []); assert.equal(report.skipped.length, 0); report.ok = true;
} catch (error) {
  report.error = error.stack; process.exitCode = 1;
  if (app?.pid) await control('list').then(value => { report.failureWindows = value.windows; }).catch(() => {});
  await page?.screenshot({ path: join(output, 'failure-webview.png') }).catch(() => {});
  console.error(error.stack);
} finally {
  if (!stopped && app?.pid) await stop(true).catch(error => { report.cleanupError = String(error); process.exitCode = 1; report.ok = false; });
  report.completed = new Date().toISOString(); await saveReport();
  console.log(JSON.stringify({ ok: report.ok, checks: report.checks.map(({ name, ok }) => ({ name, ok })), skipped: report.skipped, report: reportPath }, null, 2));
}
