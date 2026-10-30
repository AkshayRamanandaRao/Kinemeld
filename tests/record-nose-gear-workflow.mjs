/**
 * Record the end-to-end showcase on the aircraft nose gear in the real interface: the eleven
 * original STEP parts imported one by one, bodies and links, CAD attachment, joints placed on
 * the CAD pin holes, mass from CAD, a prescribed shock-strut stroke, the MBDyn solve and
 * post-processing. Every number comes from the running application and solver.
 *
 *   MBDYN_STUDIO_URL=http://127.0.0.1:8766 node tests/record-nose-gear-workflow.mjs
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
const PARTS = 'examples/open-aircraft-nose-gear/parts';
// Import order: file index n becomes STEP part "n:part-1".
const FILES = [
  ['03-strut.step', 'Strut'], ['01-piston.step', 'Piston'], ['02-shaft.step', 'Axle shaft'], ['05-wheel-hub.step', 'Wheel hub'],
  ['04-upper-link.step', 'Upper torque link'], ['06-lower-link.step', 'Lower torque link'], ['07-upper-pin-bolt.step', 'Upper pin bolt'],
  ['08-scissor-pin-bolt.step', 'Scissor pin bolt'], ['09-lower-pin-bolt.step', 'Lower pin bolt'], ['10-wheel-left.step', 'Left wheel'], ['11-wheel-right.step', 'Right wheel'],
];
// Body frames on the pivots, in metres (the parts were written with the axle 0.35 m up).
const PIN = { strut: 0.616195, lower: 0.4, upperY: -0.07, lowerY: -0.056641, wheelX: 0.206667 };

const folder = await mkdtemp(join(tmpdir(), 'kinemeld-nose-gear-'));
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
async function ring(box) {
  await page.evaluate((box) => {
    let ring = document.querySelector('#demoFocus');
    if (!ring) { ring = document.createElement('div'); ring.id = 'demoFocus'; document.body.append(ring); }
    ring.hidden = !box;
    if (box) Object.assign(ring.style, { left: `${box.x - 5}px`, top: `${box.y - 5}px`, width: `${box.width + 10}px`, height: `${box.height + 10}px` });
  }, box);
}
/** Outline the control the next action uses. */
async function focus(locator) {
  await ring(locator ? await locator.boundingBox() : null);
}
async function shot(seconds) {
  // Modal dialogs render above the page, so keep the caption and outline inside the open one.
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
  await page.locator('.inspector').evaluate((element) => { element.scrollTop = 0; });
}
/** Set several fields, then outline them together and hold so the new values can be read. */
async function edit(pairs, hold = 1.5) {
  for (const [id, value] of pairs) await setField(id, value);
  await page.locator(`#${pairs[0][0]}`).scrollIntoViewIfNeeded();
  const boxes = (await Promise.all(pairs.map(([id]) => page.locator(`#${id}`).boundingBox()))).filter(Boolean);
  const left = Math.min(...boxes.map((b) => b.x)), top = Math.min(...boxes.map((b) => b.y));
  await ring({ x: left, y: top, width: Math.max(...boxes.map((b) => b.x + b.width)) - left, height: Math.max(...boxes.map((b) => b.y + b.height)) - top });
  await shot(hold);
  await ring(null);
}
async function rename(name) {
  await page.getByLabel('Body name').fill(name);
  await page.getByLabel('Body name').dispatchEvent('change');
}
async function fit(hold = 0) {
  await page.locator('#resetViewButton').click();
  await page.waitForTimeout(400);
  if (hold) await shot(hold);
}
/** Outline a group of controls together. */
async function ringAll(locators) {
  const boxes = (await Promise.all(locators.map((item) => item.boundingBox()))).filter(Boolean);
  const top = Math.min(...boxes.map((b) => b.y)), bottom = Math.max(...boxes.map((b) => b.y + b.height));
  const left = Math.min(...boxes.map((b) => b.x)), right = Math.max(...boxes.map((b) => b.x + b.width));
  await ring({ x: left, y: top, width: right - left, height: bottom - top });
}
/** Choose the parent and joint type, add the body, name it and put its frame on its pivot. */
async function addBodyWithJoint(parent, type, name, id, pose) {
  const add = page.getByRole('button', { name: 'Add 3D body + joint' });
  await page.getByLabel('Parent body').selectOption(parent);
  await page.getByLabel('New 3D joint type').selectOption(type);
  await add.scrollIntoViewIfNeeded();
  await ringAll([page.getByLabel('Parent body'), page.getByLabel('New 3D joint type'), add]);
  await shot(1.1);
  await add.click();
  await ring(null);
  await page.locator('.inspector').evaluate((element) => { element.scrollTop = 0; });
  await rename(name);
  await edit([[`spatial-body-${id}-pose-x`, pose[0]], [`spatial-body-${id}-pose-y`, pose[1]], [`spatial-body-${id}-pose-z`, pose[2]]], 1.2);
}
/** Close a kinematic loop or tie a body to ground with "Connect existing bodies". */
async function connect(a, b, type) {
  const add = page.getByRole('button', { name: 'Add connection / close loop' });
  await page.getByLabel('First connection body').selectOption(a);
  await page.getByLabel('Second connection body').selectOption(b);
  await page.getByLabel('Connection joint type').selectOption(type);
  await add.scrollIntoViewIfNeeded();
  await ringAll([page.getByLabel('First connection body'), page.getByLabel('Second connection body'), page.getByLabel('Connection joint type'), add]);
  await shot(1.4);
  await add.click();
  await ring(null);
  await shot(0.6);
}

// ---- Camera: the 3D view is reached through its MechanismView, as in the interaction tests ----
async function camera() {
  return page.evaluate(() => ({ target: window.__view.controls.target.toArray(), position: window.__view.camera.position.toArray() }));
}
/** Move the camera smoothly to look at a model point from a direction at a distance. */
async function glide(point, direction, distance, steps = 14) {
  const start = await camera();
  const end = await page.evaluate(({ point, direction, distance }) => {
    const view = window.__view, offset = view.sourceParts.offset, length = Math.hypot(...direction);
    const target = [point[0] + offset.x, point[1] + offset.y, point[2] + offset.z];
    return { target, position: target.map((value, i) => value + direction[i] / length * distance) };
  }, { point, direction, distance });
  for (let i = 1; i <= steps; i++) {
    const s = i / steps, ease = s * s * (3 - 2 * s);
    const mix = (a, b) => a.map((value, k) => value + (b[k] - value) * ease);
    await page.evaluate(({ target, position }) => {
      const view = window.__view;
      view.controls.target.fromArray(target);
      view.camera.position.fromArray(position);
      view.controls.update();
    }, { target: mix(start.target, end.target), position: mix(start.position, end.position) });
    await shot(1 / 30);
  }
}
const tooltip = () => page.locator('#viewTooltip').evaluate((element) => element.hidden ? '' : element.textContent);
/**
 * Hover the CAD until the tooltip reports the wanted feature near a model point, then hold.
 * Candidates are rim vertices (or, for a cylinder, surface points) facing the camera.
 */
async function hoverFeature(point, want, radius) {
  const candidates = await page.evaluate(({ point, radius }) => {
    const view = window.__view, offset = view.sourceParts.offset;
    view.renderer.render(view.scene, view.camera);
    const at = new view.camera.position.constructor(point[0] + offset.x, point[1] + offset.y, point[2] + offset.z);
    const rect = view.renderer.domElement.getBoundingClientRect(), found = [];
    const screen = (p) => { const q = p.clone().project(view.camera); return { x: rect.left + (q.x + 1) / 2 * rect.width, y: rect.top + (1 - q.y) / 2 * rect.height, depth: p.distanceTo(view.camera.position) }; };
    for (const line of view.stepView.rimLines) {
      line.geometry.computeBoundingSphere();
      const centre = line.localToWorld(line.geometry.boundingSphere.center.clone());
      if (Math.abs(line.geometry.boundingSphere.radius - radius) > 0.0012) continue;
      // On the pin axis through the point (along x), within a part's width.
      if (Math.hypot(centre.y - at.y, centre.z - at.z) > 0.002 || Math.abs(centre.x - at.x) > 0.06) continue;
      const positions = line.geometry.getAttribute('position');
      for (let i = 0; i < positions.count; i += 4) found.push(screen(line.localToWorld(new at.constructor().fromBufferAttribute(positions, i))));
    }
    if (!found.length) found.push(screen(at));
    return found.sort((a, b) => a.depth - b.depth).slice(0, 24);
  }, { point, radius });
  for (const candidate of candidates) {
    await page.mouse.move(candidate.x, candidate.y);
    await page.waitForTimeout(120);
    if (want.test(await tooltip())) return candidate;
  }
  throw new Error(`No ${want} near ${point}: ${await tooltip()}`);
}
/** Pick a joint's anchor (and axis) from a CAD feature. */
async function placeJoint(joint, point, direction, want, radius, label) {
  await select(`joint-${joint}`);
  const pick = page.locator(`#spatial-joint-${joint}-pick`);
  await pick.scrollIntoViewIfNeeded();
  await focus(pick);
  await shot(0.8);
  await pick.click();
  await focus(null);
  await glide(point, direction, 0.42);
  const target = await hoverFeature(point, want, radius);
  await shot(1.5);
  await page.mouse.click(target.x, target.y);
  await page.waitForFunction((id) => new RegExp(`Joint ${id} placed on`).test(document.querySelector('#notice')?.textContent || ''), joint);
  const notice = await page.locator('#notice').textContent();
  await caption('1 · PRE-PROCESSING · JOINTS FROM CAD', `${label}: ${notice.split('. ')[0].replace(/^Joint \S+ placed on /, 'placed on ')}.`);
  await page.mouse.move(4, 4);
  await shot(1.6);
}

try {
  await page.goto(base);
  await page.waitForFunction(() => document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
  await page.evaluate(async () => {
    const { MechanismView } = await import('/viewport.js');
    const original = MechanismView.prototype.setModel;
    MechanismView.prototype.setModel = function (...args) { window.__view = this; return original.apply(this, args); };
  });
  await caption('KINEMELD · AIRCRAFT NOSE GEAR', 'From eleven original STEP parts to a solved landing-gear linkage: import the CAD, build the bodies and joints, solve the shock-strut stroke with MBDyn and review the torque-link kinematics.');
  await shot(3.4);

  // ---- Pre-processing: CAD, one part at a time ----------------------------------------------------
  await caption('1 · PRE-PROCESSING', 'Start a new 3D assembly. It holds one body to build from.');
  await act(page.locator('#newButton'), async () => {
    await page.locator('#newButton').click();
    await page.waitForFunction(() => document.querySelector('#viewportName')?.textContent.includes('Untitled'));
  });
  for (const [index, [file, name]] of FILES.entries()) {
    await caption('1 · PRE-PROCESSING · IMPORT CAD', `Part ${index + 1} of ${FILES.length}: ${name} (${file}). Each STEP file keeps its units, placement and product name.`);
    await page.locator('#stepButton').click();
    const button = page.locator(index ? '#stepAdd' : '#stepImport');
    await focus(button);
    await shot(index < 2 ? 1.0 : 0.45);
    if (index) await button.click();
    await page.locator('#stepFile').setInputFiles(join(PARTS, file));
    await page.waitForFunction((count) => new RegExp(`^${count} STEP files`).test(document.querySelector('#stepDetail')?.textContent || ''), index + 1, { timeout: 240000 });
    await focus(null);
    if (index < 2) await shot(1.0);
    await page.locator('#stepClose').click();
    await fit();
    await shot(index < 2 ? 1.4 : 0.9);
  }
  await caption('1 · PRE-PROCESSING · IMPORT CAD', 'Strut, piston, axle, hub, two torque links, three pin bolts and two wheels: the whole gear, as designed.');
  await shot(2.2);

  // ---- Bodies and links ---------------------------------------------------------------------------
  await caption('1 · PRE-PROCESSING · BODIES', 'Name the first body Strut and put its frame on the upper torque-link pin, 616 mm above the ground.');
  await select('body');
  await rename('Strut');
  await edit([['spatial-body-body1-pose-z', PIN.strut]], 1.6);
  await caption('1 · PRE-PROCESSING · LINKS', 'Mount the strut to the airframe: a weld to ground.');
  await connect('ground', 'body1', 'weld');
  await caption('1 · PRE-PROCESSING · LINKS', 'The piston, axle and hub slide in the strut: a prismatic joint. Their frame sits on the axle.');
  await addBodyWithJoint('body1', 'prismatic', 'Piston and axle', 'body2', [0, 0, 0.35]);
  await caption('1 · PRE-PROCESSING · LINKS', 'The upper torque link turns on the strut lug: a revolute joint.');
  await addBodyWithJoint('body1', 'revolute', 'Upper torque link', 'body3', [0, PIN.upperY, PIN.strut]);
  await caption('1 · PRE-PROCESSING · LINKS', 'The lower torque link hangs from the upper one at the scissor pin: a spherical joint keeps the planar loop free of redundant constraints.');
  await addBodyWithJoint('body3', 'spherical', 'Lower torque link', 'body4', [0, PIN.lowerY, PIN.lower]);
  await caption('1 · PRE-PROCESSING · LINKS', 'Close the scissor loop: the lower link meets the hub lug in a universal joint.');
  await connect('body2', 'body4', 'universal');
  await caption('1 · PRE-PROCESSING · LINKS', 'Each wheel turns on the axle: two revolute joints.');
  await addBodyWithJoint('body2', 'revolute', 'Left wheel', 'body5', [-PIN.wheelX, 0, 0.35]);
  await addBodyWithJoint('body2', 'revolute', 'Right wheel', 'body6', [PIN.wheelX, 0, 0.35]);

  // ---- Attach the CAD ------------------------------------------------------------------------------
  await caption('1 · PRE-PROCESSING · ATTACH CAD', 'Attach every part to its body; from now on it moves with that body. The pin bolts go with the links they hold.');
  await page.locator('#stepButton').click();
  const owners = ['body1', 'body2', 'body2', 'body2', 'body3', 'body4', 'body3', 'body4', 'body4', 'body5', 'body6'];
  for (const [index, body] of owners.entries()) {
    await page.locator('#stepPart').selectOption(`${index}:part-1`);
    await page.locator('#stepBody').selectOption(body);
    await act(page.locator('#stepBind'), () => page.locator('#stepBind').click(), index < 2 ? 0.8 : 0.3, index < 2 ? 0.5 : 0);
  }
  assert.match(await page.locator('#stepDetail').textContent(), /11 attached/);
  await shot(1.2);
  await page.locator('#stepClose').click();
  await fit(1.2);

  // ---- Joints from the CAD ---------------------------------------------------------------------------
  await caption('1 · PRE-PROCESSING · JOINTS FROM CAD', 'Place each joint on the CAD: Pick from CAD, then point at the pin hole. The rim gives the pin centre and axis.');
  await placeJoint('joint2', [0.025, -0.025, 0.48], [1, -1, 0.35], /Cylinder Ø\d+\.\d mm · axis [−+]z/, 0, 'Shock-strut slide on the piston');
  await placeJoint('joint3', [0, PIN.upperY, PIN.strut], [1, -0.45, 0.3], /Circle Ø1[5-7]\.\d mm · axis [−+]x/, 0.008, 'Upper torque-link pin');
  await placeJoint('joint4', [0, -0.182980, 0.482552], [1, -0.45, 0.3], /Circle Ø1[5-7]\.\d mm · axis [−+]x/, 0.008, 'Scissor pin');
  await placeJoint('joint5', [0, PIN.lowerY, PIN.lower], [1, -0.45, 0.25], /Circle Ø1[5-7]\.\d mm · axis [−+]x/, 0.008, 'Lower torque-link pin');
  await placeJoint('joint6', [-PIN.wheelX, 0, 0.35], [-1, -0.4, 0.3], /Circle Ø40\.0 mm · axis [−+]x/, 0.02, 'Left wheel bearing');
  await placeJoint('joint7', [PIN.wheelX, 0, 0.35], [1, -0.4, 0.3], /Circle Ø40\.0 mm · axis [−+]x/, 0.02, 'Right wheel bearing');
  await fit(1.2);

  // ---- Mass from CAD -----------------------------------------------------------------------------------
  await caption('1 · PRE-PROCESSING · MASS FROM CAD', 'Compute each body’s mass, centre of mass and inertia from its solids: aluminium alloy (2700 kg/m³) for the structure, 1100 kg/m³ for the wheels.');
  await page.locator('#stepButton').click();
  for (const [part, density, hold] of [['0:part-1', 2700, 1.6], ['1:part-1', 2700, 1.4], ['4:part-1', 2700, 0.6], ['5:part-1', 2700, 0.6], ['9:part-1', 1100, 0.6], ['10:part-1', 1100, 0.6]]) {
    await page.locator('#stepPart').selectOption(part);
    await page.locator('#stepMassDensity').fill(String(density));
    await page.locator('#stepMassCalculateBody').click();
    await page.waitForFunction(() => /Mass: /.test(document.querySelector('#stepMassResult')?.textContent || ''), null, { timeout: 240000 });
    await page.locator('#stepMassResult').scrollIntoViewIfNeeded();
    await act(page.locator('#stepMassApply'), async () => {
      await page.locator('#stepMassApply').click();
      await page.waitForFunction(() => document.querySelector('#stepMassApply')?.disabled);
    }, hold, 0);
  }
  await page.locator('#stepClose').click();
  await select('node-body2');
  await page.locator('#spatial-body-body2-mass').scrollIntoViewIfNeeded();
  await edit([['spatial-body-body2-mass', await page.locator('#spatial-body-body2-mass').inputValue()]], 1.6);

  // ---- Prescribed stroke ---------------------------------------------------------------------------------
  await caption('1 · PRE-PROCESSING · MOTION', 'Prescribe the shock-strut stroke on the slide: 80 mm up and back in 2 s, as the strut compresses and extends.');
  await select('joint-joint2');
  const motion = page.getByRole('button', { name: 'Add prescribed slider motion' });
  await act(motion, () => motion.click(), 0.9, 0);
  await edit([['spatial-joint-joint2-motion-amplitude', 0.04], ['spatial-joint-joint2-motion-frequencyHz', 0.5]], 2);

  // ---- Solve -------------------------------------------------------------------------------------------
  await caption('2 · SOLVE', 'Simulate 2 s at 2 ms steps, then validate: inputs, step budget and mobility are checked before MBDyn runs.');
  await page.locator('[data-step="simulate"]').click();
  await setField('durationInput', 2);
  await setField('stepInput', 0.002);
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

  // ---- Post-processing ---------------------------------------------------------------------------------
  const slider = result.samples.map((sample) => sample.sliders.find((item) => item.id === 'joint2').position);
  const stroke = Math.max(...slider) - Math.min(...slider);
  const fold = result.samples.map((sample) => sample.nodes.find((node) => node.id === 'body3').rx);
  const swing = Math.max(...fold) - Math.min(...fold);
  await caption('3 · POST-PROCESSING', `MBDyn finished: ${result.samples.length.toLocaleString()} samples. The slide follows the prescribed ${(stroke * 1000).toFixed(0)} mm stroke.`);
  await page.locator('#signalSelect').selectOption({ label: 'Slider position (reconstructed)' });
  await page.locator('#jointSelect').selectOption('joint2');
  await page.locator('#trailsToggle').check();
  await select('node-body4');
  await fit();
  await shot(2.6);
  await caption('3 · POST-PROCESSING', `Plot the upper torque link’s rotation: the scissor folds through ${swing.toFixed(1)}° as the strut compresses. Playback in real time.`);
  await page.locator('#signalSelect').selectOption({ label: 'Node Euler 1–2–3 · X / Y / Z' });
  await page.locator('#nodeSelect').selectOption('body3');
  await page.waitForTimeout(400);
  const fps = 30, duration = result.samples.at(-1).time, times = result.samples.map((sample) => sample.time);
  let index = 0;
  for (let frame = 0; frame <= Math.round(duration * fps); frame++) {
    const t = Math.min(duration, frame / fps);
    while (index < times.length - 1 && times[index + 1] <= t) index++;
    await page.evaluate((i) => { const s = document.querySelector('#timeSlider'); s.value = String(i); s.dispatchEvent(new Event('input')); }, index);
    const path = await shot(1 / fps);
    if (frame === Math.round(duration * fps / 2)) poster = path;
  }
  await page.locator('#signalSelect').selectOption({ label: 'Joint reaction force on B · world X / Y / Z' });
  await page.locator('#jointSelect').selectOption('joint2');
  const axial = result.samples.map((sample) => sample.jointReactions.find((item) => item.id === 'joint2').force.z);
  await caption('3 · POST-PROCESSING', `The slide’s reaction is the force the strut must deliver to move the axle, wheels and links: ${Math.min(...axial).toFixed(0)} to ${Math.max(...axial).toFixed(0)} N along the strut. CSV export keeps every solver step.`);
  await page.waitForTimeout(400);
  await shot(3.6);
  await caption('KINEMATIC ILLUSTRATION', 'The source CAD overlaps in places and the scissor uses spherical and universal joints to avoid redundant constraints: kinematics only, not certified loads.');
  await shot(3.2);
  assert.deepEqual(errors, []);

  // ---- Encode --------------------------------------------------------------------------
  const list = frames.map(({ path, seconds }) => `file '${path}'\nduration ${seconds.toFixed(4)}`).join('\n') + `\nfile '${frames.at(-1).path}'\n`;
  await writeFile(join(folder, 'frames.txt'), list);
  await mkdir(output, { recursive: true });
  const mp4 = join(output, 'workflow-nose-gear.mp4');
  execFileSync(ffmpeg, ['-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', join(folder, 'frames.txt'), '-vf', 'fps=30,scale=1280:-2:flags=lanczos,format=yuv420p', '-c:v', 'libx264', '-preset', 'slow', '-crf', '21', '-movflags', '+faststart', mp4]);
  execFileSync(ffmpeg, ['-y', '-loglevel', 'error', '-i', poster, '-vf', 'scale=1280:-2:flags=lanczos', join(output, 'workflow-nose-gear.png')]);
  const seconds = frames.reduce((sum, item) => sum + item.seconds, 0);
  console.log(`workflow-nose-gear: ${frames.length} frames, ${seconds.toFixed(1)} s; MP4 ${(await stat(mp4)).size} bytes; stroke ${(stroke * 1000).toFixed(1)} mm; torque link ${swing.toFixed(2)}°; run ${result.runId}`);
} finally {
  await browser.close();
  await rm(folder, { recursive: true, force: true });
}
