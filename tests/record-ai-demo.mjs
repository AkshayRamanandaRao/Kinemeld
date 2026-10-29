/**
 * Record the AI assistant setting up links, contact and initial conditions for the wheel-end
 * drop test with a real local Ollama model, then the review, solve and result. Nothing is
 * scripted on the model side: the request goes through /api/agent/chat to the selected model.
 *
 *   AI_MODEL=qwen3.5:4b MBDYN_STUDIO_URL=http://127.0.0.1:8766 node tests/record-ai-demo.mjs
 *
 * Waiting time while the model reads the request is condensed in the video; the caption
 * states how long the response actually took on the recording machine.
 */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdtemp, mkdir, readFile, rm, stat, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { execFileSync } from 'node:child_process';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const base = process.env.MBDYN_STUDIO_URL || 'http://127.0.0.1:8766';
const chatModel = process.env.AI_MODEL || 'qwen3.5:4b';
const ffmpeg = process.env.FFMPEG || 'ffmpeg';
const output = resolve('docs/demos');
const REQUEST = 'Connect the wheel to the knuckle with a revolute wheel bearing about the x axis at both body origins. '
  + 'Add a sphere-plane tyre contact on the wheel: radius 0.208 m at the wheel origin, against the floor plane through the world origin with normal +z, '
  + 'stiffness 20000 N/m and damping 100 N·s/m. Then raise both bodies to z = 0.6 m with an initial velocity of -1 m/s in z, '
  + 'and set the study to 1.5 s with a 0.0005 s step.';

// Starting point: the shipped wheel-end CAD with mass from the solids, but no links, contact or drop.
const shipped = JSON.parse(await readFile('examples/open-wheel-end/wheel-end-drop.mbdyn-studio', 'utf8'));
const start = structuredClone(shipped);
start.model.name = 'Wheel-end drop test · links not yet defined';
start.model.joints = [];
delete start.model.contacts;
start.model.simulation = { duration: 0.5, step: 0.001 };
for (const body of start.model.bodies) { body.pose.z = 0; body.velocity.vz = 0; body.velocity.wx = 0; }

const folder = await mkdtemp(join(tmpdir(), 'kinemeld-ai-'));
const frames = [];
const browser = await chromium.launch({
  headless: true,
  args: ['--enable-unsafe-swiftshader'],
  ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } : {}),
});
const page = await browser.newPage({ viewport: { width: 1440, height: 810 }, deviceScaleFactor: 1 });
const errors = [];
page.on('pageerror', (error) => errors.push(error.message));
page.on('dialog', (dialog) => dialog.accept());
await page.route('**/api/tour-preference', (route) => route.fulfill({ json: { enabled: false } }));

async function caption(stage, text) {
  await page.evaluate(({ stage, text }) => {
    let box = document.querySelector('#demoCaption');
    if (!box) {
      const style = document.createElement('style');
      style.textContent = `#demoCaption{position:fixed;left:40%;bottom:40px;transform:translateX(-50%);z-index:200;max-width:760px;padding:10px 18px;border-radius:10px;background:rgba(17,24,36,.92);color:#fff;font:500 15px/1.45 Plex,system-ui,sans-serif;box-shadow:0 8px 30px rgba(0,0,0,.25);pointer-events:none}
#demoCaption b{display:block;font:600 11px/1.4 PlexMono,monospace;letter-spacing:.08em;color:#8fb8ff;margin-bottom:2px}
#notice{display:none!important}`;
      document.head.append(style);
      box = document.createElement('div');
      box.id = 'demoCaption';
      document.body.append(box);
    }
    box.innerHTML = `<b>${stage}</b>${text}`;
  }, { stage, text });
}
async function shot(seconds) {
  const path = join(folder, `f${String(frames.length).padStart(5, '0')}.png`);
  await page.screenshot({ path });
  frames.push({ path, seconds });
}
/** Type the request a few characters per frame so the viewer can read it being entered. */
async function typeRequest(text) {
  const input = page.locator('#agentInput');
  for (let i = 0; i <= text.length; i += 12) {
    await input.fill(text.slice(0, i));
    await shot(1 / 15);
  }
  await input.fill(text);
  await shot(1.5);
}

try {
  await page.goto(base);
  await page.waitForFunction(() => document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
  await page.locator('#projectFile').setInputFiles({ name: 'wheel-end-start.mbdyn-studio', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(start)) });
  await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('Project imported and validated'), null, { timeout: 240000 });
  await page.locator('#resetViewButton').click();
  await caption('AI-ASSISTED PRE-PROCESSING', 'Starting point: knuckle and wheel bodies with their STEP parts attached and mass computed from the solids. No links, contact or loads yet.');
  await shot(3.2);

  await page.locator('#agentButton').click();
  await page.waitForFunction((name) => [...document.querySelectorAll('#agentModel option')].some((option) => option.value === name), chatModel, { timeout: 30000 });
  await page.locator('#agentModel').selectOption(chatModel);
  await caption('AI ASSISTANT · LOCAL MODEL', `The assistant runs ${chatModel} locally through Ollama. It can only propose validated model edits; nothing changes until you apply them.`);
  await shot(3);
  await caption('AI ASSISTANT · REQUEST', 'Describe the links, contact and initial conditions in engineering terms.');
  await typeRequest(REQUEST);

  const started = Date.now();
  const response = page.waitForResponse((r) => r.url().endsWith('/api/agent/chat'), { timeout: 1800000 });
  response.catch(() => {}); // a failure elsewhere should report its own error
  await page.locator('#agentSend').click();
  await page.waitForTimeout(400);
  await caption('AI ASSISTANT · THINKING', `${chatModel} reads the model and the request on the CPU and calls the model-editing tools.`);
  await shot(2.4);
  // Headless Chromium renders WebGL in software; freeze the page while no frames are captured so
  // the local model gets the CPU. The request is already in flight; the measured time is the model's.
  const session = await page.context().newCDPSession(page);
  await session.send('Page.setWebLifecycleState', { state: 'frozen' });
  const answered = await response;
  const seconds = Math.round((Date.now() - started) / 1000);
  await session.send('Page.setWebLifecycleState', { state: 'active' });
  const reply = await answered.json();
  assert(reply.ok !== false, JSON.stringify(reply));
  const review = page.locator('.agent-review').last();
  await review.waitFor({ timeout: 60000 });
  await review.scrollIntoViewIfNeeded();
  await caption('AI ASSISTANT · REVIEW', `Proposal returned after ${seconds} s on this CPU-only machine (waiting condensed). The edits are listed and validated; review them before applying.`);
  await shot(5);

  await review.getByRole('button', { name: /Apply/ }).click();
  await page.waitForFunction(() => document.querySelector('#agentMessages')?.textContent.includes('Use Undo to restore the previous model'));
  await page.locator('#agentClose').click();
  await page.locator('#resetViewButton').click();
  await page.waitForTimeout(500);
  await caption('AI ASSISTANT · APPLIED', 'Applied as one undoable change: the revolute bearing symbol, the tyre contact floor and the raised drop position appear in the 3D view.');
  await shot(4);
  await page.locator('[data-entity="joint-' + (await page.evaluate(() => document.querySelector('#modelTree [data-entity^="joint-"]')?.dataset.entity.slice(6))) + '"]').click();
  await shot(3);

  await page.locator('[data-step="simulate"]').click();
  await page.locator('#validateButton').click();
  await page.waitForFunction(() => document.querySelector('#validationBadge')?.textContent === 'Ready', null, { timeout: 60000 });
  await caption('SOLVE', 'The checks pass: one bearing, a free wheel end and a contact. Run MBDyn.');
  await shot(3);
  const run = page.waitForResponse((r) => r.url().endsWith('/api/run') && r.request().method() === 'POST', { timeout: 600000 });
  await page.locator('#runButton').click();
  const result = await (await run).json();
  assert(result.ok, JSON.stringify(result.error));
  await page.waitForFunction(() => document.querySelector('#resultSource')?.textContent.includes('MBDyn'));
  await page.locator('#signalSelect').selectOption({ label: 'Contact normal force (reconstructed)' });
  await page.locator('#resetViewButton').click();
  const peakIndex = result.samples.reduce((best, sample, i, all) => (sample.contactStates[0].force > all[best].contactStates[0].force ? i : best), 0);
  await page.evaluate((i) => { const s = document.querySelector('#timeSlider'); s.value = String(i); s.dispatchEvent(new Event('input')); }, peakIndex);
  await page.waitForTimeout(400);
  const peak = result.samples[peakIndex].contactStates[0].force;
  await caption('POST-PROCESSING', `MBDyn solved the assistant-built model: ${result.samples.length.toLocaleString()} samples, peak tyre load ${(peak / 1000).toFixed(2)} kN at first impact.`);
  await shot(4.5);
  assert.deepEqual(errors, []);

  const list = frames.map(({ path, seconds }) => `file '${path}'\nduration ${seconds.toFixed(4)}`).join('\n') + `\nfile '${frames.at(-1).path}'\n`;
  await writeFile(join(folder, 'frames.txt'), list);
  await mkdir(output, { recursive: true });
  const mp4 = join(output, 'ai-assistant-setup.mp4');
  execFileSync(ffmpeg, ['-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', join(folder, 'frames.txt'), '-vf', 'fps=30,scale=1280:-2:flags=lanczos,format=yuv420p', '-c:v', 'libx264', '-preset', 'slow', '-crf', '21', '-movflags', '+faststart', mp4]);
  execFileSync(ffmpeg, ['-y', '-loglevel', 'error', '-sseof', '-12', '-i', mp4, '-frames:v', '1', join(output, 'ai-assistant-setup.png')]);
  console.log(`ai-assistant-setup: ${chatModel} answered in ${seconds} s; actions ${JSON.stringify(reply.actions)}; MP4 ${(await stat(mp4)).size} bytes; run ${result.runId}`);
} finally {
  await browser.close();
  await rm(folder, { recursive: true, force: true });
}
