/**
 * Record the landing-gear spin-up drag study in the real interface: the tyre's friction, the
 * friction study solved by MBDyn, the drag compared across friction coefficients, the wheel
 * spinning down at touchdown and the drag carried by the axle. Every number comes from the
 * running application and solver.
 *
 *   MBDYN_STUDIO_URL=http://127.0.0.1:8766 node tests/record-friction-demo.mjs
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

const folder = await mkdtemp(join(tmpdir(), 'kinemeld-friction-'));
const frames = [];
let poster = null;
const browser = await chromium.launch({
  headless: true,
  args: ['--enable-unsafe-swiftshader'],
  ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } : {}),
});
const page = await browser.newPage({ viewport: { width: 1440, height: 810 }, deviceScaleFactor: 1 });
const errors = [];
page.on('pageerror', (error) => errors.push(error.message));
await page.route('**/api/tour-preference', (route) => route.fulfill({ json: { enabled: false } }));

async function caption(stage, text) {
  await page.evaluate(({ stage, text }) => {
    let box = document.querySelector('#demoCaption');
    if (!box) {
      const style = document.createElement('style');
      style.textContent = `#demoCaption{position:fixed;left:50%;bottom:40px;transform:translateX(-50%);z-index:200;max-width:900px;padding:10px 18px;border-radius:10px;background:rgba(17,24,36,.92);color:#fff;font:500 15px/1.45 Plex,system-ui,sans-serif;box-shadow:0 8px 30px rgba(0,0,0,.25);pointer-events:none}
#demoCaption b{display:block;font:600 11px/1.4 PlexMono,monospace;letter-spacing:.08em;color:#8fb8ff;margin-bottom:2px}
#demoFocus{position:fixed;z-index:199;border:3px solid #ed9a17;border-radius:8px;box-shadow:0 0 0 4px rgba(237,154,23,.25);pointer-events:none}
#notice{display:none!important}`;
      document.head.append(style);
      box = document.createElement('div');
      box.id = 'demoCaption';
      document.body.append(box);
    }
    box.innerHTML = `<b>${stage}</b>${text}`;
  }, { stage, text });
}
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
  await page.evaluate(() => {
    const target = [...document.querySelectorAll('dialog[open]')].at(-1) || document.body;
    for (const id of ['demoCaption', 'demoFocus']) {
      const element = document.getElementById(id);
      if (element && element.parentElement !== target) target.append(element);
    }
  });
  const path = join(folder, `f${String(frames.length).padStart(5, '0')}.png`);
  await page.screenshot({ path });
  frames.push({ path, seconds });
  return path;
}
async function seek(time) {
  await page.evaluate((time) => {
    const slider = document.querySelector('#timeSlider'), end = Number(document.querySelector('#durationMetric')?.textContent.split(' ')[0]) || 0.4;
    slider.value = String(Math.round(Number(slider.max) * time / end));
    slider.dispatchEvent(new Event('input'));
  }, time);
}

try {
  await page.goto(base);
  await page.waitForFunction(() => document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
  // Keep a handle on the 3D view so the touchdown can be framed on the wheel.
  await page.evaluate(async () => {
    const { MechanismView } = await import('/viewport.js');
    const original = MechanismView.prototype.setModel;
    MechanismView.prototype.setModel = function (...args) { window.__view = this; return original.apply(this, args); };
  });

  // ---- Open the featured study ---------------------------------------------------------
  await caption('FEATURED STUDY', 'At touchdown the runway drags a still wheel up to speed. Drop rigs spin the wheel backwards instead and drop it on a still platform: the spin-up drag test.');
  await page.locator('#examplesButton').click();
  const card = page.locator('.example-card').filter({ has: page.getByRole('heading', { name: 'Landing-gear spin-up drag', exact: true }) });
  await card.scrollIntoViewIfNeeded();
  await focus(card);
  await shot(3.4);
  await card.getByRole('button').click();
  await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('spin-up drag'), null, { timeout: 120000 });
  await focus(null);
  await page.locator('#resetViewButton').click();
  await page.waitForTimeout(500);

  // ---- The tyre's friction -------------------------------------------------------------------
  await page.locator('[data-step="model"]').click();
  await page.locator('#modelTree [data-entity="contact-tyre"]').click();
  await page.locator('#spatial-contact-tyre-friction').scrollIntoViewIfNeeded();
  await caption('1 · CONTACT', 'The tyre is a damped sphere-plane contact with Coulomb friction μ = 0.55, regularised over 0.5 m/s of slip. The wheel starts at −136 rad/s: 30 m/s at the tyre surface.');
  const friction = page.locator('label').filter({ has: page.locator('#spatial-contact-tyre-friction') });
  const slip = page.locator('label').filter({ has: page.locator('#spatial-contact-tyre-slipVelocity') });
  const [a, b] = [await friction.boundingBox(), await slip.boundingBox()];
  await page.evaluate(({ a, b }) => {
    let ring = document.querySelector('#demoFocus');
    if (!ring) { ring = document.createElement('div'); ring.id = 'demoFocus'; document.body.append(ring); }
    ring.hidden = false;
    Object.assign(ring.style, { left: `${a.x - 5}px`, top: `${a.y - 5}px`, width: `${a.width + 10}px`, height: `${b.y + b.height - a.y + 10}px` });
  }, { a, b });
  await shot(4.2);
  await focus(null);

  // ---- Solve the friction study --------------------------------------------------------------
  await page.locator('[data-step="simulate"]').click();
  await page.locator('#studyCard').scrollIntoViewIfNeeded();
  await caption('2 · STUDY', 'Solve → Parameter study is preloaded: the tyre friction coefficient at 0.3 and 0.8 around the 0.55 baseline.');
  await focus(page.locator('#studyCard'));
  await shot(3.4);
  await caption('2 · STUDY', 'Run study: MBDyn solves the three drops one after another.');
  await focus(page.locator('#studyRunButton'));
  await shot(1.2);
  await focus(null);
  await page.locator('#studyRunButton').click();
  while (!(await page.evaluate(() => document.body.classList.contains('ws-results')))) {
    await shot(0.5);
    await page.waitForTimeout(700);
  }
  await page.waitForFunction(() => document.querySelectorAll('#plot path.plot-curve').length === 3, null, { timeout: 120000 });
  await page.waitForTimeout(2500);

  // ---- Compare ---------------------------------------------------------------------------
  const peaks = await page.locator('#studyTable tbody tr').evaluateAll((rows) => rows.map((row) => Number(row.cells[1].textContent.trim())));
  assert.equal(peaks.length, 3);
  assert(peaks[0] < peaks[1] && peaks[1] < peaks[2], `peak drag rises with friction: ${peaks}`);
  await page.locator('#studyResults').scrollIntoViewIfNeeded();
  await caption('3 · COMPARE', `Friction force for each case. Peak drag rises from ${(peaks[0] / 1000).toFixed(1)} kN at μ = 0.3 to ${(peaks[2] / 1000).toFixed(1)} kN at μ = 0.8, and higher friction stops the slip sooner.`);
  await focus(page.locator('#plot'));
  await shot(4.0);
  await caption('3 · COMPARE', 'The table gives each case’s peak, minimum, RMS and final value from every solver step, and exports to CSV.');
  await focus(page.locator('#studyResults'));
  poster = await shot(3.4);
  await focus(null);

  // ---- Animate the baseline through touchdown ------------------------------------------------
  await caption('4 · TOUCHDOWN', 'μ = 0.55 at 1/25 real time: the tyre lands, friction stops the reverse spin within about 50 ms, and the drag follows the vertical load.');
  await page.locator('#studyTable tbody tr').nth(1).click();
  await page.waitForFunction(() => document.querySelectorAll('#studyTable tbody tr')[1]?.classList.contains('shown'));
  // Frame the wheel so its reverse spin and the stop are visible.
  await page.mouse.move(4, 4);
  await page.evaluate(() => {
    const view = window.__view;
    view.followEntity = 'node-wheel';
    const wheel = view.followPoint();
    view.followEntity = null;
    const away = view.camera.position.clone().sub(view.controls.target).normalize().multiplyScalar(1.8);
    view.controls.target.copy(wheel).add(new wheel.constructor(0, 0, 0.15));
    view.camera.position.copy(view.controls.target).add(away);
    view.controls.update();
  });
  await page.waitForTimeout(600);
  const fps = 30, rate = 0.04, start = 0.05, end = 0.17;
  for (let frame = 0; frame <= Math.round(((end - start) / rate) * fps); frame++) {
    await seek(start + (frame / fps) * rate);
    await shot(1 / fps);
  }
  await shot(1.2);

  // ---- The axle carries the drag ---------------------------------------------------------------
  await page.locator('#signalSelect').selectOption({ label: 'Joint reaction force on B · world X / Y / Z' });
  await page.locator('#jointSelect').selectOption('axle');
  await seek(0.1);
  await page.waitForTimeout(800);
  await caption('5 · AXLE LOAD', 'Joint reaction at the axle: the fore-aft (X) load equals the tyre drag — the spin-up load the gear structure must carry.');
  await focus(page.locator('#plot'));
  await shot(4.0);
  await focus(null);
  await caption('VERIFIED', 'verify_featured_studies.py: the wheel’s angular momentum matches the friction impulse, drag equals μ × vertical load while sliding, and friction absorbs exactly the spin energy.');
  await shot(4.2);
  assert.deepEqual(errors, []);

  // ---- Encode --------------------------------------------------------------------------
  const list = frames.map(({ path, seconds }) => `file '${path}'\nduration ${seconds.toFixed(4)}`).join('\n') + `\nfile '${frames.at(-1).path}'\n`;
  await writeFile(join(folder, 'frames.txt'), list);
  await mkdir(output, { recursive: true });
  const mp4 = join(output, 'study-spin-up.mp4');
  execFileSync(ffmpeg, ['-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', join(folder, 'frames.txt'), '-vf', 'fps=30,scale=1280:-2:flags=lanczos,format=yuv420p', '-c:v', 'libx264', '-preset', 'slow', '-crf', '21', '-movflags', '+faststart', mp4]);
  const png = join(output, 'study-spin-up.png');
  execFileSync(ffmpeg, ['-y', '-loglevel', 'error', '-i', poster, '-vf', 'scale=1280:-2:flags=lanczos', png]);
  const seconds = frames.reduce((sum, item) => sum + item.seconds, 0);
  console.log(`study-spin-up: ${frames.length} frames, ${seconds.toFixed(1)} s; MP4 ${(await stat(mp4)).size} bytes; peak drag ${peaks.map((p) => p.toFixed(0)).join(', ')} N`);
} finally {
  await browser.close();
  await rm(folder, { recursive: true, force: true });
}
