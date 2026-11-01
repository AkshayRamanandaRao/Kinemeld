/* Actual viewer/IPC GUI regression, injected only by --native-gui-test. */
(() => {
  if (window.top !== window) return;
  const config = window.__kinemeldGuiTest;
  const report = { phase: config.phase, checks: [], pageErrors: [], status: 'running', url: location.origin };
  const io = (command, args = {}) => window.mbdynNative.call('gui-test', { command, ...args });
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const element = selector => document.querySelector(selector);
  const text = selector => element(selector)?.textContent || '';
  const assert = (condition, message) => { if (!condition) throw Error(message); };
  function canonical(value) {
    if (Array.isArray(value)) return value.map(canonical);
    if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])]));
    return value;
  }
  const equal = (a, b, message) => assert(JSON.stringify(canonical(a)) === JSON.stringify(canonical(b)), message);
  const read = async name => (await io('read', { name })).text;
  const json = async name => { const value = await read(name); return value === null ? null : JSON.parse(value); };
  const write = (name, value) => io('write', { name, text: typeof value === 'string' ? value : JSON.stringify(value) });
  const saveReport = () => io('report', { report });
  const path = name => `${config.root}/${name}`;
  const notice = () => text('#notice');
  async function until(reading, label, timeout = 30000) {
    const deadline = Date.now() + timeout;
    do { const value = await reading(); if (value) return value; await sleep(100); } while (Date.now() < deadline);
    throw Error(`Timed out: ${label}; notice: ${notice()}`);
  }
  async function check(name, action) {
    const item = { name, ok: false }; report.checks.push(item); await saveReport();
    item.evidence = await action(); item.ok = true; await saveReport();
  }
  function stored(project) {
    const result = structuredClone(project.result || null); if (result) delete result.restored;
    return { model: project.model, assets: project.assets || null, result };
  }
  let sequence = Date.now();
  async function arm(actions) { const id = ++sequence; await io('action', { id, actions }); return id; }
  async function completed(id) {
    return until(async () => {
      const result = await io('status'); if (!result || result.id !== id) return false;
      if (result.error) throw Error(`Native GUI driver: ${result.error}`);
      return result.done ? result : false;
    }, 'native control action', 45000);
  }
  async function click(selector, actions = []) {
    await until(() => element(selector) && !element(selector).disabled, `enabled ${selector}`);
    const id = actions.length ? await arm(actions) : null;
    element(selector).click();
    if (id !== null) await completed(id);
  }
  async function setName(name) {
    element('[data-step="model"]').click(); element('#modelTree [data-entity="body"]').click();
    const input = element('#spatial-model-name'); assert(input, 'The actual model name field is missing.');
    input.value = name; input.dispatchEvent(new Event('input', { bubbles: true })); input.dispatchEvent(new Event('change', { bubbles: true }));
    await until(() => text('#viewportName') === name, 'model edit');
  }
  async function open(name, dirty = false, invalid = false) {
    await click('#importButton', [...(dirty ? [{ kind: 'button', text: 'Yes' }] : []), { kind: 'open', path: path(name) }]);
    await until(() => notice().includes(invalid ? 'Project was not opened' : 'Project opened'), 'native Open', 120000);
  }
  async function saveAs(name) {
    await click('#saveAsButton', [{ kind: 'save', path: path(name) }]);
    await until(() => notice().includes('Project saved to') && notice().includes(name), 'native Save As');
    return json(name);
  }
  async function cancelSave(selector = '#saveAsButton') {
    await click(selector, [{ kind: 'cancel', dialog: 'save' }]);
    await until(() => !element('#saveButton').disabled, 'cancel Save settled');
  }
  async function autosave(name) {
    return until(async () => { const snapshot = await json('user-data/recovery/autosave.json'); return snapshot?.document.model.name === name ? snapshot : false; }, 'full autosave', 35000);
  }
  window.addEventListener('error', event => report.pageErrors.push(event.message));
  window.addEventListener('unhandledrejection', event => report.pageErrors.push(String(event.reason)));
  (async () => {
    await saveReport();
    await until(() => text('#solverStatus').includes('MBDyn ready'), 'actual viewer/solver startup', 90000);
    await sleep(500);
    if (config.phase === 'initial') {
      await check('Actual embedded viewer and owned solver service start with isolated user data', async () => {
        assert(window.ipc?.postMessage && window.mbdynNative?.call, 'Actual native IPC is absent.');
        assert(document.querySelector('#viewport canvas'), 'The viewer canvas is missing.');
        return { nativeBridge: 'actual IPC, unmodified', url: location.origin };
      });
      const fixture = await json('fixture.mbdyn-studio');
      await check('Native Open, Save As and reopen preserve model, STEP bindings, result and full CSV', async () => {
        await open('fixture.mbdyn-studio');
        if (!fixture.result?.samples?.length || !fixture.result?.csvText) {
          await click('#runButton');
          await until(() => notice().includes('MBDyn completed successfully'), 'actual MBDyn run', 180000);
        }
        const saved = await saveAs('roundtrip.mbdyn-studio');
        equal(saved.model, fixture.model, 'Open/Save changed the model.');
        equal(saved.assets, fixture.assets, 'Open/Save changed original STEP bytes or bindings.');
        assert(Object.keys(saved.assets?.step?.bindings || {}).length > 0, 'No CAD bindings survived.');
        assert(saved.result?.source === 'MBDyn' && saved.result.samples.length > 0 && saved.result.csvText?.length > 100, 'Actual MBDyn samples/full CSV are missing.');
        if (fixture.result?.samples?.length && fixture.result.csvText) equal(stored(saved), stored(fixture), 'Saved solver result differs from fixture.');
        await open('roundtrip.mbdyn-studio');
        await until(() => text('#resultSource').includes('recorded MBDyn'), 'reopened result');
        const reopened = await saveAs('reopened.mbdyn-studio');
        equal(stored(reopened), stored(saved), 'Save/reopen changed CAD/result/CSV.');
        return { bindings: Object.keys(saved.assets.step.bindings).length, samples: saved.result.samples.length, csvBytes: new TextEncoder().encode(saved.result.csvText).length };
      });
      await check('Cancel native Save As leaves the file and destination unchanged', async () => {
        const before = await read('reopened.mbdyn-studio'); await cancelSave();
        equal(await read('reopened.mbdyn-studio'), before, 'Cancel modified the saved project.');
        await setName('Cancel destination check'); await click('#saveButton');
        await until(() => notice().includes('Previous version retained'), 'ordinary Save after cancel');
        assert((await json('reopened.mbdyn-studio')).model.name === 'Cancel destination check', 'Cancel altered the active save destination.');
        return { destination: 'reopened.mbdyn-studio' };
      });
      await check('Declining native overwrite confirmation preserves the target', async () => {
        const before = await read('fixture.mbdyn-studio'); await write('overwrite-target.mbdyn-studio', before);
        await click('#saveAsButton', [{ kind: 'save', path: path('overwrite-target.mbdyn-studio') }, { kind: 'button', text: 'refuse-overwrite' }, { kind: 'cancel', dialog: 'save' }]);
        equal(await read('overwrite-target.mbdyn-studio'), before, 'Declined overwrite changed the target.');
        return { targetUnchanged: true };
      });
      await check('Ordinary native Save retains the exact prior file as a backup', async () => {
        const before = await read('reopened.mbdyn-studio'), entries = new Set(await io('list'));
        await setName('Native GUI edited snapshot'); await click('#saveButton');
        await until(() => notice().includes('Previous version retained'), 'ordinary native Save');
        const backups = (await io('list')).filter(name => !entries.has(name) && name.startsWith('.reopened.mbdyn-studio.mbdyn-backup-'));
        assert(backups.length === 1, 'Expected one new backup.'); equal(await read(backups[0]), before, 'Backup bytes differ.');
        return { backup: backups[0] };
      });
      await check('External disk edits reject Save and survive a fresh native Save As', async () => {
        const external = await json('reopened.mbdyn-studio'); external.model.name = 'External edit must survive';
        const bytes = JSON.stringify(external); await write('reopened.mbdyn-studio', bytes); await setName('Unsaved GUI edit');
        await click('#saveButton'); await until(() => notice().includes('project changed on disk'), 'external conflict detection');
        equal(await read('reopened.mbdyn-studio'), bytes, 'Conflict modified the external file.');
        const fresh = await saveAs('after-conflict.mbdyn-studio'); assert(fresh.model.name === 'Unsaved GUI edit', 'Fresh copy lost edits.');
        equal(await read('reopened.mbdyn-studio'), bytes, 'Save As modified the external file.');
        return { externalPreserved: true };
      });
      await check('New → Save opens a real picker twice and autosaves without the previous path', async () => {
        const before = await read('after-conflict.mbdyn-studio'); await click('#newButton');
        await until(() => text('#viewportName') === 'Untitled 3D assembly' && notice().includes('New 3D assembly'), 'new unsaved project');
        await cancelSave('#saveButton'); await cancelSave('#saveButton');
        equal(await read('after-conflict.mbdyn-studio'), before, 'New project overwrote previous document.');
        const snapshot = await autosave('Untitled 3D assembly'); assert(snapshot.projectPath == null, 'New autosave inherited an existing path.');
        return { recoveryProjectPath: null };
      });
      await check('Autosave retains full CAD, samples and CSV before a real process crash', async () => {
        await open('after-conflict.mbdyn-studio', true); await setName('Crash recovery GUI');
        const snapshot = await autosave('Crash recovery GUI'), disk = await json('after-conflict.mbdyn-studio'); disk.model.name = 'Crash recovery GUI';
        equal(stored(snapshot.document), stored(disk), 'Autosave lost CAD or results.');
        await write('pre-crash-autosave.json', snapshot);
        return { bindings: Object.keys(snapshot.document.assets.step.bindings).length, samples: snapshot.document.result.samples.length };
      });
      await check('Dirty Open refusal and picker cancellation retain the current work', async () => {
        await click('#importButton', [{ kind: 'button', text: 'No' }]);
        assert(text('#viewportName') === 'Crash recovery GUI', 'Dirty Open refusal lost edits.');
        await click('#importButton', [{ kind: 'button', text: 'Yes' }, { kind: 'cancel', dialog: 'open' }]);
        assert(text('#viewportName') === 'Crash recovery GUI', 'Cancelled Open lost edits.');
        return { model: text('#viewportName') };
      });
      await check('Malformed native file Open reports failure and preserves work', async () => {
        await write('invalid.mbdyn-studio', '{not valid JSON'); await open('invalid.mbdyn-studio', true, true);
        assert(text('#viewportName') === 'Crash recovery GUI', 'Invalid Open replaced current work.');
        return { notice: notice() };
      });
      assert(report.pageErrors.length === 0, `Page errors: ${report.pageErrors.join('; ')}`);
      report.status = 'crash-ready'; await saveReport();
    } else {
      await check('Crash recovery restores the actual autosave and Save requests a native destination', async () => {
        await until(() => element('#recoveryDialog')?.open, 'actual recovery prompt'); await click('#recoveryOpen');
        await until(() => notice().includes('Recovered the work autosaved'), 'recovered project shown', 120000);
        assert(text('#viewportName') === 'Crash recovery GUI', 'Recovery changed the model name.');
        assert(element('#dirtyMark').title.startsWith('Unsaved changes'), 'Recovered work is not unsaved.');
        await cancelSave('#saveButton');
        const saved = await saveAs('recovered-roundtrip.mbdyn-studio'), snapshot = await json('pre-crash-autosave.json');
        equal(stored(saved), stored(snapshot.document), 'Recovered Save lost model, STEP, samples or CSV.');
        await setName('Recovered GUI close test'); await autosave('Recovered GUI close test');
        return { bindings: Object.keys(saved.assets.step.bindings).length, samples: saved.result.samples.length };
      });
      await check('Dirty close refusal retains work before confirmed normal close', async () => {
        const id = await arm([{ kind: 'close' }, { kind: 'button', text: 'No' }]); await completed(id);
        assert(text('#viewportName') === 'Recovered GUI close test', 'Close refusal lost work.');
        const response = await fetch('/api/health'); assert(response.ok, 'Close refusal stopped the backend.');
        return { closeRefused: true, backendAlive: true };
      });
      assert(report.pageErrors.length === 0, `Page errors: ${report.pageErrors.join('; ')}`);
      report.status = 'close-ready'; await saveReport();
      await arm([{ kind: 'close' }, { kind: 'button', text: 'Yes' }]);
    }
  })().catch(async error => {
    report.status = 'failed'; report.error = error.stack || String(error);
    report.viewer = { userAgent: navigator.userAgent, readyState: document.readyState, solverStatus: text('#solverStatus'), notice: notice(), resources: performance.getEntriesByType('resource').map(item => ({name: item.name, duration: item.duration})) };
    try { await saveReport(); } catch { /* The supervisor also fails on timeout/early process exit. */ }
  });
})();
