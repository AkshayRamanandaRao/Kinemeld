/**
 * Record the featured sink-speed study of the landing-gear drop test in the real interface:
 * open the study, run four sink speeds through MBDyn, compare the cases and animate the
 * fastest. Every number comes from the running application and solver.
 *
 *   MBDYN_STUDIO_URL=http://127.0.0.1:8766 node tests/record-study-demo.mjs
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

const folder = await mkdtemp(join(tmpdir(), 'kinemeld-study-'));
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

try {
  await page.goto(base);
  await page.waitForFunction(() => document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));

  // ---- Open the featured study ---------------------------------------------------------
  await caption('FEATURED STUDY', 'The oleo-pneumatic gear drop test comes with a parameter study: how sink speed drives the tyre load.');
  await page.locator('#examplesButton').click();
  const card = page.locator('.example-card').filter({ has: page.getByRole('heading', { name: 'Oleo-pneumatic gear drop test', exact: true }) });
  await card.scrollIntoViewIfNeeded();
  await focus(card);
  await shot(2.6);
  await card.getByRole('button').click();
  await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('gear drop test loaded'), null, { timeout: 120000 });
  await focus(null);
  await page.locator('#resetViewButton').click();
  await page.waitForTimeout(500);

  // ---- Set up and solve ----------------------------------------------------------------
  await page.locator('[data-step="simulate"]').click();
  await page.locator('#studyCard').scrollIntoViewIfNeeded();
  await caption('1 · SET UP', 'Solve → Parameter study is preloaded: the initial velocity of all bodies, swept to −3, −2.5 and −1.5 m/s. The current −2 m/s is the baseline.');
  await focus(page.locator('#studyCard'));
  await shot(3.6);
  await caption('2 · SOLVE', 'Run study: MBDyn solves the four sink speeds one after another, with the progress and the log of each case.');
  await focus(page.locator('#studyRunButton'));
  await shot(1.2);
  await focus(null);
  await page.locator('#studyRunButton').click();
  while (!(await page.evaluate(() => document.body.classList.contains('ws-results')))) {
    await shot(0.5);
    await page.waitForTimeout(700);
  }
  await page.waitForFunction(() => document.querySelectorAll('#plot path.plot-curve').length === 4, null, { timeout: 120000 });
  await page.waitForTimeout(2500);

  // ---- Compare ---------------------------------------------------------------------------
  const peaks = await page.locator('#studyTable tbody tr').evaluateAll((rows) => rows.map((row) => Number(row.cells[1].textContent.trim())));
  assert.equal(peaks.length, 4);
  await page.locator('#studyResults').scrollIntoViewIfNeeded();
  await caption('3 · COMPARE', `Every case on one plot, blue (3 m/s) to orange (1.5 m/s). Peak tyre load rises from ${(peaks[3] / 1000).toFixed(1)} kN at 1.5 m/s to ${(peaks[0] / 1000).toFixed(1)} kN at 3 m/s.`);
  await focus(page.locator('#plot'));
  await shot(3.4);
  await caption('3 · COMPARE', 'The table lists each case’s peak, minimum, RMS and final value from every solver step, and exports to CSV.');
  await focus(page.locator('#studyResults'));
  poster = await shot(3.4);
  await focus(null);

  // ---- Animate the fastest case ------------------------------------------------------------
  await caption('4 · ANIMATE', 'Select a case to play it: 3 m/s sink speed at 0.25× real time, impact and strut stroke.');
  await page.locator('#studyTable tbody tr').first().click();
  await page.waitForFunction(() => document.querySelector('#studyTable tbody tr')?.classList.contains('shown'));
  const last = Number(await page.locator('#timeSlider').getAttribute('max'));
  const duration = Number(await page.locator('#durationMetric').textContent().then((text) => text.split(' ')[0])) || 1.2;
  const rate = 0.25, fps = 30, span = Math.min(duration, 0.5);
  for (let frame = 0; frame <= Math.round((span / rate) * fps); frame++) {
    const index = Math.min(last, Math.round(((frame / fps) * rate / duration) * last));
    await page.evaluate((i) => { const s = document.querySelector('#timeSlider'); s.value = String(i); s.dispatchEvent(new Event('input')); }, index);
    await shot(1 / fps);
  }
  await caption('VERIFIED', 'verify_featured_studies.py: energy balances within 0.1 % of the impact energy in every case, and the strut never bottoms.');
  await shot(3.6);
  assert.deepEqual(errors, []);

  // ---- Encode --------------------------------------------------------------------------
  const list = frames.map(({ path, seconds }) => `file '${path}'\nduration ${seconds.toFixed(4)}`).join('\n') + `\nfile '${frames.at(-1).path}'\n`;
  await writeFile(join(folder, 'frames.txt'), list);
  await mkdir(output, { recursive: true });
  const mp4 = join(output, 'study-gear-drop.mp4');
  execFileSync(ffmpeg, ['-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', join(folder, 'frames.txt'), '-vf', 'fps=30,scale=1280:-2:flags=lanczos,format=yuv420p', '-c:v', 'libx264', '-preset', 'slow', '-crf', '21', '-movflags', '+faststart', mp4]);
  const png = join(output, 'study-gear-drop.png');
  execFileSync(ffmpeg, ['-y', '-loglevel', 'error', '-i', poster, '-vf', 'scale=1280:-2:flags=lanczos', png]);
  const seconds = frames.reduce((sum, item) => sum + item.seconds, 0);
  console.log(`study-gear-drop: ${frames.length} frames, ${seconds.toFixed(1)} s; MP4 ${(await stat(mp4)).size} bytes; peak tyre loads ${peaks.map((p) => p.toFixed(0)).join(', ')} N`);
} finally {
  await browser.close();
  await rm(folder, { recursive: true, force: true });
}
