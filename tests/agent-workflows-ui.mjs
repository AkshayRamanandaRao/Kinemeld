/** Real proposal/validator/solver GUI workflows with an owned local model fixture. */
import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { once } from 'node:events';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { chromium } from 'playwright';

const binary = process.env.MBDYN_AGENT_TEST_SOLVER || 'verification/dependency-audit/ci-audit2-windows/solver/bin/mbdyn.exe';
const service = spawn('python', ['tests/agent-workflows-server.py', binary], { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
let diagnostics = '', browser, page;
service.stderr.on('data', data => { diagnostics += data; });
const lines = createInterface({ input: service.stdout });
const report = { scope: 'Real browser controls, actual agent/validator HTTP, deterministic owned model transport, actual native MBDyn runs; no live-model accuracy claim.', checks: [], errors: [] };
const record = text => { report.checks.push(text); console.log(text); };
async function bounded(promise,label) { let timer; try { return await Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error(`Timed out: ${label}`)),20000);})]); } finally {clearTimeout(timer);} }
try {
  let timer;
  const ready = await Promise.race([once(lines, 'line').then(([line]) => JSON.parse(line)), once(service, 'exit').then(() => { throw Error(diagnostics); }), new Promise((_, reject) => { timer = setTimeout(() => reject(Error('Owned server startup timed out')), 15000); })]).finally(() => clearTimeout(timer));
  const base = `http://127.0.0.1:${ready.port}`;
  browser = await chromium.launch({ headless: true, args: ['--enable-unsafe-swiftshader'] });
  page = await browser.newPage({ viewport: { width: 1540, height: 1100 }, acceptDownloads: true });
  page.on('pageerror', error => report.errors.push(error.message));
  page.on('dialog', dialog => dialog.accept());
  const runs = [];
  page.on('request', request => { if (request.url().endsWith('/api/run') && request.method() === 'POST') runs.push(request.postDataJSON()); });
  await page.route('**/api/tour-preference', route => route.fulfill({ json: { enabled: false } }));
  await page.route('**/app.js', async route => {
    const response=await route.fetch(),source=await response.text(),anchor='    applyDisplayPreset(project.view);';
    assert(source.includes(anchor));
    await route.fulfill({response,body:source.replace(anchor,`${anchor}\n    if(globalThis.__agentFailAfterView)throw Error("Controlled post-view failure");`)});
  });
  await page.goto(base);
  await page.waitForFunction(() => document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
  const initial = { format: 'mbdyn-studio/1', model: ready.model, view: { study: { input: 'bodies/arm/mass', values: [.6, 1.4] } } };
  const open = async project => { await page.locator('#projectFile').setInputFiles({ name: 'robot-joint.mbdyn-studio', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(project)) }); await page.waitForFunction(() => document.querySelector('#documentName')?.textContent === '3D revolute pendulum'); await page.locator('[data-step="simulate"]').click(); await page.waitForFunction(() => document.querySelector('#studyValues')?.value === '0.6, 1.4'); };
  await open(initial);
  await page.locator('#modelTree [data-entity="body"]').click();
  const runResponse = page.waitForResponse(response => response.url().endsWith('/api/run') && response.request().method() === 'POST');
  await page.locator('#runButton').click();
  const baseline = await (await runResponse).json();
  assert.equal(baseline.ok, true, baseline.error);
  await page.waitForFunction(() => !document.querySelector('#runButton').disabled);
  const baselineRunId = await page.locator('#runId').textContent();
  const agentOpen = async () => { if (await page.locator('#agentPanel').isHidden()) await page.locator('#agentButton').click(); await page.waitForFunction(() => !document.querySelector('#agentSend').disabled); };
  const agentClose = async () => { if (await page.locator('#agentPanel').isVisible()) await page.locator('#agentClose').click(); };
  const send = async text => { await agentOpen(); const count = await page.locator('.agent-review').count(); await page.locator('#agentInput').fill(text); await page.locator('#agentSend').click(); await page.waitForFunction(() => !document.querySelector('#agentSend').disabled); return { count, review: page.locator('.agent-review').last() }; };
  const propose = async text => { const item = await send(text); assert.equal(await page.locator('.agent-review').count(), item.count+1); return item.review; };
  const exported = async () => { await agentClose(); const pending = page.waitForEvent('download'); await page.locator('#saveButton').click(); const download = await pending; return JSON.parse(await readFile(await download.path(), 'utf8')); };
  const clickHistory = async id => { await agentClose(); await page.locator(id).click(); };

  let review = await propose('Study: prepare a mass study at 0.5, 1 and 2 kg. Do not run.');
  assert.equal(await page.locator('#studyValues').inputValue(), '0.6, 1.4');
  assert.equal(runs.length, 1);
  assert.match(await review.textContent(), /No baseline model value is changed/);
  await mkdir('tests/evidence', { recursive: true });
  await page.screenshot({ path: 'tests/evidence/agent-study-review.png' });
  await review.getByRole('button', { name: 'Apply proposal', exact: true }).click();
  await page.waitForFunction(() => document.querySelector('#studyValues')?.value === '0.5, 1, 2');
  const applied = await exported();
  assert.deepEqual(applied.model, ready.model);
  assert.equal(applied.result.runId, baseline.runId);
  assert(applied.result.csvText.length > 100);
  assert.deepEqual(applied.view.study.values, [.5, 1, 2]);
  assert.equal(await page.locator('#runId').textContent(), baselineRunId);
  await clickHistory('#undoButton');
  assert.equal(await page.locator('#studyValues').inputValue(), '0.6, 1.4');
  const undone = await exported();
  assert.deepEqual(undone.view.study.values, [.6, 1.4]);
  assert.equal(undone.result.csvText, applied.result.csvText);
  await clickHistory('#redoButton');
  assert.equal(await page.locator('#studyValues').inputValue(), '0.5, 1, 2');
  assert.equal(runs.length, 1);
  record('Reviewed study-only Apply/Undo/Redo preserves exact baseline, result identity and full CSV; setup persists in project export');

  review = await propose('Study: prepare the same mass study. Do not run.');
  await page.locator('#studyValues').fill('0.7, 1.3');
  await review.getByRole('button', { name: 'Apply proposal', exact: true }).click();
  await page.waitForFunction(() => document.querySelector('#agentMessages').textContent.includes('changed since this proposal'));
  assert.equal(await page.locator('#studyValues').inputValue(), '0.7, 1.3');
  assert.equal(runs.length, 1);
  record('A newer live study draft rejects the reviewed proposal');

  let release, received;
  const blocked = new Promise(resolve => { received = resolve; });
  const validationGate = new Promise(resolve => { release = resolve; });
  let hold = true;
  await page.route('**/api/validate', async route => {
    if (hold && route.request().postDataJSON().model?.bodies?.[0]?.mass === 2) { hold = false; received(); await validationGate; }
    await route.continue();
  });
  await agentOpen();
  const reviewsBefore = await page.locator('.agent-review').count();
  await page.locator('#agentInput').fill('Study: prepare a mass study. Do not run.'); await page.locator('#agentSend').click();
  await bounded(blocked,'study case validation gate');
  await page.locator('#modelTree [data-entity="body"]').click();
  await page.locator('#spatial-body-arm-mass').fill('1.25');
  release();
  await page.waitForFunction(() => !document.querySelector('#agentSend').disabled);
  assert.equal(await page.locator('.agent-review').count(), reviewsBefore);
  assert.equal(await page.locator('#spatial-body-arm-mass').inputValue(), '1.25');
  await page.locator('#spatial-body-arm-mass').press('Tab');
  await page.unroute('**/api/validate');
  await clickHistory('#undoButton');
  record('Typed-but-unblurred model input invalidates study case validation before review or Apply');

  review = await propose('Study: prepare 0.5, 1 and 2 kg, then run the study.');
  assert.equal(runs.length, 1);
  await review.getByRole('button', { name: 'Apply and run study', exact: true }).click();
  await page.waitForFunction(() => !document.querySelector('#runButton').disabled && document.querySelectorAll('#studyTable tbody tr').length > 0, null, { timeout: 30000 });
  assert.equal(runs.length, 4);
  assert.deepEqual(runs.slice(1).map(request => request.model.bodies[0].mass), [.5, 1, 2]);
  const studySaved = await exported();
  record('Only explicit reviewed study execution invokes the existing bounded runner; three real MBDyn cases solved');

  const summaryReply = page.waitForResponse(response => response.url().endsWith('/api/agent/chat'));
  await send('ResultSummary: explain the current recorded result. Do not run.');
  const summary = (await (await summaryReply).json()).toolResults.find(item => item.name === 'current_result_summary').result;
  assert.equal(summary.available, true);
  assert.equal(summary.runId, studySaved.result.runId);
  const retained = await (await page.request.get(`${base}/api/runs/${summary.runId}/summary.json`)).json();
  assert.deepEqual(summary.metrics, Object.fromEntries(Object.entries(retained.metrics).filter(([, value]) => typeof value === 'number' || typeof value === 'boolean')));
  assert.equal(runs.length, 4);
  await page.getByText('Inspect recorded numeric metrics and units', { exact: true }).last().click();
  await page.locator('#agentMessages').evaluate(element => { element.scrollTop = element.scrollHeight; });
  await page.screenshot({ path: 'tests/evidence/agent-result-summary.png' });
  record('Assistant reads actual matching local run metrics, without CSV or a new run, and exposes inspectable recorded evidence');

  const beforeFailure=await exported();
  await page.locator('#studyValues').fill('0.65, 1.35');
  await page.evaluate(()=>{globalThis.__agentFailAfterView=true;});
  const examples=await(await page.request.get(`${base}/api/examples`)).json();
  const other={format:'mbdyn-studio/1',model:examples.examples.find(item=>item.id==='mass-spring').model,view:{study:{input:'parameters/stiffness',values:[50,200]}}};
  await page.locator('#projectFile').setInputFiles({name:'rejected.mbdyn-studio',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(other))});
  await page.waitForFunction(()=>document.querySelector('#noticeText')?.textContent.includes('Controlled post-view failure'));
  await page.evaluate(()=>{globalThis.__agentFailAfterView=false;});
  assert.equal(await page.locator('#studyValues').inputValue(),'0.65, 1.35');
  const afterFailure=await exported();
  assert.deepEqual(afterFailure.model,beforeFailure.model);
  assert.deepEqual(afterFailure.view.study,beforeFailure.view.study);
  assert.equal(afterFailure.result.runId,beforeFailure.result.runId);
  assert.equal(afterFailure.result.csvText,beforeFailure.result.csvText);
  assert.equal(await page.locator('#studyTable tbody tr').count(),3);
  record('Controlled failure after applying project view rolls back study setup, typed draft, all cases and exact recorded result/CSV');

  review = await propose('FrameLinks: use datum A and datum B for the hinge ends. Do not run.');
  await review.getByRole('button', { name: 'Apply proposal', exact: true }).click();
  await page.waitForFunction(() => document.querySelector('#agentMessages').textContent.includes('Linked joint frames'));
  const linked = await exported();
  assert.equal(linked.model.frameLinks.length, 2);
  assert(linked.model.frameLinks.every(link => ['datumA', 'datumB'].includes(link.frame)));
  await clickHistory('#undoButton');
  const unlinked = await exported();
  assert.equal(unlinked.model.frameLinks?.length || 0, 0);
  assert.equal(runs.length, 4);
  record('Named-frame placement is reviewed, validated, serialized and Undoable without guessing CAD geometry');

  review = await propose('Rename the robot joint. Do not run.');
  await review.getByRole('button', { name: 'Discard proposal', exact: true }).click();
  assert.equal((await exported()).model.name, ready.model.name);
  review = await propose('StudyWrongRun: prepare the mass study, then run the study.');
  assert.equal(await review.getByRole('button', { name: 'Apply and run study', exact: true }).count(), 0);
  await review.getByRole('button', { name: 'Apply proposal', exact: true }).click();
  assert.equal(runs.length, 4);
  record('Discard leaves the model intact; an incorrect baseline-run tool cannot execute a study or baseline');
  assert.deepEqual(report.errors, []);
  report.ok = true;
  console.log(JSON.stringify({ ok: true, checks: report.checks.length, actualMBDynRuns: runs.length, scope: report.scope }));
} catch (error) {
  report.ok = false; report.failure = error.stack; report.serverDiagnostics = diagnostics.slice(-5000);
  if(page){report.failureState=await page.evaluate(()=>({notice:document.querySelector('#noticeText')?.textContent,agent:document.querySelector('#agentMessages')?.textContent.slice(-4000),study:document.querySelector('#studyValues')?.value})).catch(()=>null); await page.screenshot({path:'tests/evidence/agent-workflows-failure.png',fullPage:true}).catch(()=>{});}
  console.error(error); process.exitCode = 1;
} finally {
  await mkdir('tests/evidence', { recursive: true });
  await writeFile('tests/evidence/agent-workflows-ui.json', JSON.stringify(report, null, 2));
  if (browser) await browser.close();
  service.kill(); lines.close();
}
