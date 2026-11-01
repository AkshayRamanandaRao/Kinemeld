import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdtemp, mkdir, rm, stat } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { execFileSync } from 'node:child_process';

// Each recording plays back an actual MBDyn solution of a featured study at a stated rate.
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const base = process.env.MBDYN_STUDIO_URL || 'http://127.0.0.1:8766';
const ffmpeg = process.env.FFMPEG || 'ffmpeg';
const output = resolve('docs/demos'), fps = 30;
const studies = [
  { name: 'robot-arm', title: 'Robot arm inverse dynamics', rate: 1, caption: 'Base turning at 45°/s, shoulder and elbow oscillating · motor torques from inverse dynamics' },
  { name: 'quarter-car', title: 'Double-wishbone quarter-car', rate: 0.5, caption: 'Wheel-pad force 3.2 ± 1.6 kN at 0.8 Hz · camber gain and bump steer' },
  { name: 'gear-drop', title: 'Oleo-pneumatic gear drop test', rate: 0.2, caption: '290 kg carriage dropped at 2 m/s · gas, orifice and stop forces' },
  { name: 'aircraft-nose-gear', title: 'Aircraft nose-gear kinematics', rate: 0.5, caption: 'Original 11-part STEP assembly · 80 mm shock-strut stroke folds the torque links · kinematic illustration' },
  { name: 'oleo-strut', title: 'Oleo strut on a wheel-end fixture', rate: 0.25, caption: 'Original STEP wheel end on a gas/oil strut · 50 mm stroke · gas, orifice and stop forces' },
  { name: 'wheel-end-drop', title: 'Wheel-end drop test', rate: 0.25, caption: 'Original STEP knuckle, hub and tyre · 1 m/s drop onto a rigid floor · tyre load and rebound' },
  { name: 'slider-crank', title: 'Slider-crank engine run-up', rate: 0.5, caption: '2 N·m motor against a 90 N·s/m pumping load · crank speed run-up' },
  { name: 'gyroscopic-top', title: 'Gyroscopic top', rate: 0.5, caption: '120 rad/s spin on a spherical tip · precession with nutation cusps' },
  { name: 'tumbling-handle', title: 'Tumbling T-handle', rate: 1, caption: 'Zero gravity, spin about the intermediate principal axis · Dzhanibekov flips' },
  { name: 'chaotic-pendulums', title: 'Chaotic double pendulums', rate: 1, caption: 'Identical pendulums released 0.001° apart · divergence after ~3 s' },
];
const target = process.argv[2];
if (target && !studies.some((item) => item.name === target)) throw Error(`Unknown demo: ${target}`);
await mkdir(output, { recursive: true });
const browser = await chromium.launch({
  headless: true,
  args: ['--enable-unsafe-swiftshader'],
  ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } : {}),
});
try {
  for (const item of studies.filter((value) => !target || value.name === target)) {
    const folder = await mkdtemp(join(tmpdir(), 'kinemeld-demo-'));
    const page = await browser.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 }), errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    page.on('dialog', (dialog) => dialog.accept());
    await page.route('**/api/tour-preference', (route) => route.fulfill({ json: { enabled: false } }));
    try {
      await page.goto(base);
      await page.waitForFunction(() => document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
      await page.locator('#examplesButton').click();
      await page.locator('.example-card').filter({ has: page.getByRole('heading', { name: item.title, exact: true }) }).getByRole('button').click();
      await page.waitForFunction(() => !document.querySelector('#examplesDialog').open, null, { timeout: 240000 });
      if (item.name === 'aircraft-nose-gear') assert.doesNotMatch(await page.locator('body').innerText(), /KINEMATIC ONLY|loads invalid|source overlaps/);
      const response = page.waitForResponse((r) => r.url().endsWith('/api/run') && r.request().method() === 'POST', { timeout: 300000 });
      await page.locator('#runButton').click();
      const result = await (await response).json();
      assert(result.ok, JSON.stringify(result.error));
      await page.waitForFunction(() => document.querySelector('#resultSource')?.textContent.includes('MBDyn'));
      await page.locator('#presentButton').click();
      const duration = result.samples.at(-1).time;
      await page.evaluate(({ caption, rate }) => {
        document.body.classList.add('recording');
        document.querySelector('#notice').hidden = true;
        document.querySelector('#viewportDescription').textContent = `${caption} · MBDyn 1.7.3 · ${rate === 1 ? 'real time' : `${rate}× speed`}`;
      }, item);
      await page.waitForTimeout(1200);
      const times = result.samples.map((sample) => sample.time);
      const count = Math.round((duration / item.rate) * fps) + 1;
      for (let frame = 0; frame < count; frame++) {
        const t = Math.min(duration, (frame / fps) * item.rate);
        let index = 0;
        while (index < times.length - 1 && Math.abs(times[index + 1] - t) <= Math.abs(times[index] - t)) index++;
        await page.evaluate((value) => {
          const slider = document.querySelector('#timeSlider');
          slider.value = String(value);
          slider.dispatchEvent(new Event('input'));
          return new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)));
        }, index);
        await page.screenshot({ path: join(folder, `frame-${String(frame).padStart(4, '0')}.png`) });
      }
      assert.deepEqual(errors, []);
      const mp4 = join(output, `${item.name}.mp4`), gif = join(output, `${item.name}.gif`);
      execFileSync(ffmpeg, ['-hide_banner', '-loglevel', 'error', '-y', '-framerate', String(fps), '-i', join(folder, 'frame-%04d.png'),
        '-vf', 'tpad=start_mode=clone:start_duration=0.8:stop_mode=clone:stop_duration=1.5', '-c:v', 'libx264', '-crf', '21', '-preset', 'slow',
        '-pix_fmt', 'yuv420p', '-movflags', '+faststart', mp4], { stdio: 'inherit' });
      execFileSync(ffmpeg, ['-hide_banner', '-loglevel', 'error', '-y', '-i', mp4, '-filter_complex',
        'fps=15,scale=720:-2:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=160:stats_mode=diff[p];[s1][p]paletteuse=dither=sierra2_4a:diff_mode=rectangle',
        '-loop', '0', gif], { stdio: 'inherit' });
      for (const file of [mp4, gif]) {
        assert((await stat(file)).size > 1000, `Empty recording: ${file}`);
        execFileSync(ffmpeg, ['-hide_banner', '-loglevel', 'error', '-i', file, '-f', 'null', '-'], { stdio: 'inherit' });
      }
      console.log(`${item.name}: ${count} frames of a ${duration} s MBDyn solution at ${item.rate}×; MP4 ${(await stat(mp4)).size} bytes; GIF ${(await stat(gif)).size} bytes`);
    } finally {
      await page.close();
      await rm(folder, { recursive: true, force: true });
    }
  }
} finally {
  await browser.close();
}
