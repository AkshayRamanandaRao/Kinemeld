/**
 * Record the complete wheel-end drop workflow in the real interface: new assembly, STEP import,
 * bodies and links, CAD attachment and mass, contact and initial conditions, MBDyn solve and
 * post-processing. Every number comes from the running application and solver.
 *
 *   MBDYN_STUDIO_URL=http://127.0.0.1:8766 node tests/record-workflow-demo.mjs
 */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdtemp, mkdir, rm, stat, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { execFileSync } from 'node:child_process';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const base = process.env.MBDYN_STUDIO_URL || 'http://127.0.0.1:8766';
const ffmpeg = process.env.FFMPEG || 'ffmpeg';
const output = resolve('docs/demos');
const STEP = 'examples/step-suspension';
const PARTS = ['Assembly 1 - Knuckle_Left Knuckle.step', 'Assembly 1 - Hub.step', 'Assembly 1 - Front Tyre.step'].map((name) => join(STEP, name));
const BEARING = { x: -0.04, y: -0.0875 };

const folder = await mkdtemp(join(tmpdir(), 'kinemeld-workflow-'));
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

/** Show the stage and instruction for the current step over the interface. */
async function caption(stage, text) {
  await page.evaluate(({ stage, text }) => {
    let box = document.querySelector('#demoCaption');
    if (!box) {
      const style = document.createElement('style');
      style.textContent = `#demoCaption{position:fixed;left:50%;bottom:40px;transform:translateX(-50%);z-index:200;max-width:880px;padding:10px 18px;border-radius:10px;background:rgba(17,24,36,.92);color:#fff;font:500 15px/1.45 Plex,system-ui,sans-serif;box-shadow:0 8px 30px rgba(0,0,0,.25);pointer-events:none}
#demoCaption b{display:block;font:600 11px/1.4 PlexMono,monospace;letter-spacing:.08em;color:#8fb8ff;margin-bottom:2px}
#demoFocus{position:fixed;z-index:199;border:3px solid #ed9a17;border-radius:8px;box-shadow:0 0 0 4px rgba(237,154,23,.25);pointer-events:none;transition:none}
#notice{display:none!important}`;
      document.head.append(style);
      box = document.createElement('div');
      box.id = 'demoCaption';
      document.body.append(box);
    }
    box.innerHTML = `<b>${stage}</b>${text}`;
  }, { stage, text });
}
/** Outline the control the next action uses. */
async function focus(locator) {
  const box = locator ? await locator.boundingBox() : null;
  await page.evaluate((box) => {
    let ring = document.querySelector('#demoFocus');
    if (!ring) { ring = document.createElement('div'); ring.id = 'demoFocus'; document.body.append(ring); }
    ring.hidden = !box;
    if (box) Object.assign(ring.style, { left: `${box.x - 5}px`, top: `${box.y - 5}px`, width: `${box.width + 10}px`, height: `${box.height + 10}px` });
  }, box);
}
async function shot(seconds) {
  const path = join(folder, `f${String(frames.length).padStart(5, '0')}.png`);
  await page.screenshot({ path });
  frames.push({ path, seconds });
}
/** Highlight a control, hold, act, and hold on the result. */
async function act(locator, run, before = 0.9, after = 1.2) {
  await locator.scrollIntoViewIfNeeded();
  await focus(locator);
  await shot(before);
  await run();
  await page.waitForTimeout(250);
  await focus(null);
  if (after) await shot(after);
}
async function setField(id, value) {
  const field = page.locator(`#${id}`);
  await field.scrollIntoViewIfNeeded();
  await field.fill(String(value));
  await field.dispatchEvent('change');
}
async function select(entity) {
  await page.locator(`#modelTree [data-entity="${entity}"]`).click();
}
async function step(name) {
  await page.locator(`[data-step="${name}"]`).click();
  await page.waitForTimeout(300);
}

try {
  await page.goto(base);
  await page.waitForFunction(() => document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
  await caption('KINEMELD · WHEEL-END DROP TEST', 'Build an automotive wheel-end drop test from original STEP parts, solve it with MBDyn and review the results.');
  await shot(2.6);

  // ---- Pre-processing -------------------------------------------------------------------
  await caption('1 · PRE-PROCESSING', 'Start a new 3D assembly. It contains one body to build from.');
  await act(page.locator('#newButton'), async () => {
    await page.locator('#newButton').click();
    await page.waitForFunction(() => document.querySelector('#viewportName')?.textContent.includes('Untitled'));
  });

  await caption('1 · PRE-PROCESSING · IMPORT CAD', 'Import the original knuckle, hub and tyre STEP files. Parts keep their CAD units and coordinates.');
  await act(page.locator('#stepButton'), () => page.locator('#stepButton').click(), 0.9, 0.6);
  await act(page.locator('#stepImport'), async () => {
    await page.locator('#stepFile').setInputFiles(PARTS);
    await page.waitForFunction(() => document.querySelector('#stepDetail')?.textContent.includes('3 STEP files'), null, { timeout: 240000 });
  }, 0.9, 2.2);
  await page.locator('#stepClose').click();
  await page.locator('#resetViewButton').click();
  await page.waitForTimeout(400);
  await shot(1.6);

  await caption('1 · PRE-PROCESSING · BODIES', 'Name the first body Knuckle and put its frame at the wheel-bearing centre.');
  await select('body');
  await act(page.getByLabel('Body name'), async () => {
    await page.getByLabel('Body name').fill('Knuckle');
    await page.getByLabel('Body name').dispatchEvent('change');
    await setField('spatial-body-body1-pose-x', BEARING.x);
    await setField('spatial-body-body1-pose-y', BEARING.y);
  });

  await caption('1 · PRE-PROCESSING · LINKS', 'Add the Hub to the Knuckle with a revolute wheel bearing.');
  const addBody = page.getByRole('button', { name: 'Add 3D body + joint' });
  await page.getByLabel('Parent body').selectOption('body1');
  await page.getByLabel('New 3D joint type').selectOption('revolute');
  await act(addBody, () => addBody.click());
  await page.getByLabel('Body name').fill('Hub');
  await page.getByLabel('Body name').dispatchEvent('change');
  for (const axis of ['x', 'y', 'z']) await setField(`spatial-body-body2-pose-${axis}`, 0);

  await caption('1 · PRE-PROCESSING · LINKS', 'Weld the Tyre to the Hub. Each body later gets its own material.');
  await page.getByLabel('Parent body').selectOption('body2');
  await page.getByLabel('New 3D joint type').selectOption('weld');
  await act(addBody, () => addBody.click());
  await page.getByLabel('Body name').fill('Tyre');
  await page.getByLabel('Body name').dispatchEvent('change');
  for (const axis of ['x', 'y', 'z']) await setField(`spatial-body-body3-pose-${axis}`, 0);
  await shot(1.2);

  await caption('1 · PRE-PROCESSING · ATTACH CAD', 'Attach each STEP solid to its body. The solid then follows that body’s motion.');
  await page.locator('#stepButton').click();
  for (const [part, body] of [['0:part-1', 'body1'], ['1:part-1', 'body2'], ['2:part-1', 'body3']]) {
    await page.locator('#stepPart').selectOption(part);
    await page.locator('#stepBody').selectOption(body);
    await act(page.locator('#stepBind'), () => page.locator('#stepBind').click(), 0.6, 0.5);
  }
  assert.match(await page.locator('#stepDetail').textContent(), /3 attached/);

  await page.locator('#stepClose').click();

  await caption('1 · PRE-PROCESSING · ASSEMBLE', 'Place the Hub and Tyre frames at the bearing centre: the parts move into the knuckle.');
  for (const body of ['body2', 'body3']) {
    await select(`node-${body}`);
    await setField(`spatial-body-${body}-pose-x`, BEARING.x);
    await setField(`spatial-body-${body}-pose-y`, BEARING.y);
  }
  await page.locator('#resetViewButton').click();
  await page.waitForTimeout(400);
  await shot(2);

  await caption('1 · PRE-PROCESSING · JOINT FRAMES', 'Set the bearing anchors at the body origins and its axis along x; the weld sits at the same point.');
  await select('joint-joint1');
  for (const [field, value] of [['anchorB-z', 0], ['axisA-x', 1], ['axisA-y', 0], ['axisB-x', 1], ['axisB-y', 0]]) await setField(`spatial-joint-joint1-${field}`, value);
  await shot(1.6);
  await select('joint-joint2');
  await setField('spatial-joint-joint2-anchorB-z', 0);
  await shot(1.2);

  await caption('1 · PRE-PROCESSING · MASS FROM CAD', 'Compute mass, centre of mass and inertia from each solid: steel knuckle and hub, rubber tyre.');
  await page.locator('#stepButton').click();
  for (const [part, density] of [['0:part-1', 7850], ['1:part-1', 7850], ['2:part-1', 1100]]) {
    await page.locator('#stepPart').selectOption(part);
    await page.locator('#stepMassDensity').fill(String(density));
    await page.locator('#stepMassCalculate').click();
    await page.waitForFunction(() => /Mass: /.test(document.querySelector('#stepMassResult')?.textContent || ''), null, { timeout: 240000 });
    await act(page.locator('#stepMassApply'), async () => {
      await page.locator('#stepMassApply').click();
      await page.waitForFunction(() => document.querySelector('#stepMassApply')?.disabled);
    }, 1.1, 0.4);
  }
  await page.locator('#stepClose').click();

  await caption('1 · PRE-PROCESSING · CONTACT', 'Add a sphere-plane tyre contact: 0.208 m radius on the floor plane, 20 kN/m stiffness and 100 N·s/m damping.');
  await select('node-body3');
  const addContact = page.getByRole('button', { name: 'Add sphere-plane contact' });
  await page.getByLabel('Body for sphere contact').selectOption('body3');
  await act(addContact, () => addContact.click());
  for (const [field, value] of [['radius', 0.208], ['planePoint-z', 0], ['stiffness', 20000], ['damping', 100]]) await setField(`spatial-contact-contact1-${field}`, value);
  await shot(1.6);

  await caption('1 · PRE-PROCESSING · INITIAL CONDITIONS', 'Raise all three bodies to 0.6 m and give them a downward velocity of 1 m/s.');
  for (const [entity, body] of [['body', 'body1'], ['node-body2', 'body2'], ['node-body3', 'body3']]) {
    await select(entity);
    await setField(`spatial-body-${body}-pose-z`, 0.6);
    await setField(`spatial-body-${body}-velocity-vz`, -1);
  }
  await page.locator('#resetViewButton').click();
  await page.waitForTimeout(400);
  await shot(2);

  // ---- Solve ---------------------------------------------------------------------------
  await caption('2 · SOLVE', 'Set a 1.5 s study at 0.5 ms steps, then validate: inputs, step budget and mobility are checked before MBDyn runs.');
  await step('simulate');
  await setField('durationInput', 1.5);
  await setField('stepInput', 0.0005);
  await act(page.locator('#validateButton'), async () => {
    await page.locator('#validateButton').click();
    await page.waitForFunction(() => document.querySelector('#validationBadge')?.textContent === 'Ready', null, { timeout: 60000 });
  }, 0.9, 2.4);

  await caption('2 · SOLVE', 'Run MBDyn. The console shows the solver output.');
  const response = page.waitForResponse((r) => r.url().endsWith('/api/run') && r.request().method() === 'POST', { timeout: 600000 });
  await focus(page.locator('#runButton'));
  await shot(0.9);
  await page.locator('#runButton').click();
  await focus(null);
  const result = await (await response).json();
  assert(result.ok, JSON.stringify(result.error));
  await page.waitForFunction(() => document.querySelector('#resultSource')?.textContent.includes('MBDyn'));

  // ---- Post-processing -----------------------------------------------------------------
  await caption('3 · POST-PROCESSING', `MBDyn finished: ${result.samples.length.toLocaleString()} samples. Plot the tyre contact force and trace the wheel.`);
  await page.locator('#signalSelect').selectOption({ label: 'Contact normal force (reconstructed)' });
  await select('node-body3');
  await page.locator('#trailsToggle').check();
  await page.locator('#resetViewButton').click();
  await page.waitForTimeout(500);
  await shot(2.2);
  await caption('3 · POST-PROCESSING', 'Playback at 0.25× real time: free fall, tyre impact, rebound and a second bounce.');
  const rate = 0.25, fps = 30, duration = result.samples.at(-1).time;
  const times = result.samples.map((sample) => sample.time);
  let index = 0;
  for (let frame = 0; frame <= Math.round((duration / rate) * fps); frame++) {
    const t = Math.min(duration, (frame / fps) * rate);
    while (index < times.length - 1 && times[index + 1] <= t) index++;
    await page.evaluate((i) => { const s = document.querySelector('#timeSlider'); s.value = String(i); s.dispatchEvent(new Event('input')); }, index);
    await shot(1 / fps);
  }
  const peak = Math.max(...result.samples.map((sample) => sample.contactStates[0].force));
  await caption('3 · POST-PROCESSING', `Peak tyre load ${(peak / 1000).toFixed(2)} kN. Hover the plot for values at any time; CSV export keeps every solver step.`);
  const plot = await page.locator('#plot').boundingBox();
  const peakTime = result.samples.find((sample) => sample.contactStates[0].force === peak).time;
  await page.mouse.move(plot.x + 50 + (plot.width - 62) * (peakTime / duration), plot.y + plot.height * 0.45);
  await page.waitForTimeout(300);
  await shot(3.2);
  assert.deepEqual(errors, []);

  // ---- Encode --------------------------------------------------------------------------
  const list = frames.map(({ path, seconds }) => `file '${path}'\nduration ${seconds.toFixed(4)}`).join('\n') + `\nfile '${frames.at(-1).path}'\n`;
  await writeFile(join(folder, 'frames.txt'), list);
  await mkdir(output, { recursive: true });
  const mp4 = join(output, 'workflow-wheel-end.mp4');
  execFileSync(ffmpeg, ['-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', join(folder, 'frames.txt'), '-vf', 'fps=30,scale=1280:-2:flags=lanczos,format=yuv420p', '-c:v', 'libx264', '-preset', 'slow', '-crf', '21', '-movflags', '+faststart', mp4]);
  const poster = join(output, 'workflow-wheel-end.png');
  execFileSync(ffmpeg, ['-y', '-loglevel', 'error', '-sseof', '-1.5', '-i', mp4, '-frames:v', '1', poster]);
  const seconds = frames.reduce((sum, item) => sum + item.seconds, 0);
  console.log(`workflow-wheel-end: ${frames.length} captured frames, ${seconds.toFixed(1)} s; MP4 ${(await stat(mp4)).size} bytes; peak tyre load ${peak.toFixed(0)} N; run ${result.runId}`);
} finally {
  await browser.close();
  await rm(folder, { recursive: true, force: true });
}
