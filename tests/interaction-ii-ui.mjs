/** Interaction II: pick hole rims, measure between them, drag a joint along its axis, and measure at an animated frame. */
import './workspace-shim.mjs';
import assert from 'node:assert/strict';
import { chromium } from 'playwright';

const base = process.env.MBDYN_STUDIO_URL || 'http://127.0.0.1:8768';
const browser = await chromium.launch({ headless: true, args: ['--enable-unsafe-swiftshader'] });
const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
const errors = [];
page.on('pageerror', (error) => errors.push(error.message));
page.on('dialog', (dialog) => dialog.accept());
await page.route('**/api/tour-preference', (route) => route.fulfill({ json: { enabled: false } }));
const value = async (field) => Number(await page.locator(`#spatial-joint-hub_axis-${field}`).inputValue());
const tooltip = (pattern) => page.waitForFunction((source) => new RegExp(source).test(document.querySelector('#viewTooltip')?.textContent || ''), pattern.source, { timeout: 10000 });
/** Look at the displayed hub from its open end; screen position of a point on its nearer (or farther) Ø55 rim. */
async function rimPoint(far = false) {
  return page.evaluate((far) => {
    const view = window.__view;
    const rims = view.stepView.rimLines.filter((line) => {
      line.geometry.computeBoundingSphere();
      return line.geometry.boundingSphere.radius > 0.027 && line.geometry.boundingSphere.radius < 0.028;
    });
    const centre = (line) => line.localToWorld(line.geometry.boundingSphere.center.clone());
    // Aim at the displayed hub (the midpoint of its two Ø55 rims), from its open end.
    const middle = centre(rims[0]).add(centre(rims[1])).multiplyScalar(0.5);
    view.controls.target.copy(middle);
    view.camera.position.copy(middle).add(new middle.constructor(-0.42, -0.22, 0.26));
    view.controls.update();
    // Projection uses the camera matrices a render refreshes.
    view.renderer.render(view.scene, view.camera);
    rims.sort((a, b) => centre(a).distanceTo(view.camera.position) - centre(b).distanceTo(view.camera.position));
    const rim = far ? rims.at(-1) : rims[0], positions = rim.geometry.getAttribute('position');
    // The rim vertex facing the camera and above the axis is clear of the tyre.
    let best = null;
    for (let i = 0; i < positions.count; i++) {
      const point = rim.localToWorld(new middle.constructor().fromBufferAttribute(positions, i));
      const score = point.distanceTo(view.camera.position) - (point.z - centre(rim).z);
      if (!best || score < best.score) best = { point, score };
    }
    best.point.project(view.camera);
    const rect = view.renderer.domElement.getBoundingClientRect();
    return { x: rect.left + (best.point.x + 1) / 2 * rect.width, y: rect.top + (1 - best.point.y) / 2 * rect.height };
  }, far);
}
try {
  await page.goto(base);
  await page.waitForFunction(() => document.querySelector('#solverStatus')?.textContent.includes('MBDyn ready'));
  await page.evaluate(async () => {
    const { MechanismView } = await import('/viewport.js');
    const original = MechanismView.prototype.setModel;
    MechanismView.prototype.setModel = function (...args) { window.__view = this; return original.apply(this, args); };
  });
  await page.locator('#examplesButton').click();
  await page.locator('.example-card').filter({ has: page.getByRole('heading', { name: 'Wheel-end drop test', exact: true }) }).getByRole('button').click();
  await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('Wheel-end drop test loaded'), null, { timeout: 240000 });
  await page.locator('[data-step="model"]').click();
  assert(await page.evaluate(() => window.__view.stepView.rimLines.length >= 4), 'the hub reports its rims');

  // Place the hub bearing on the hub's Ø55 rim: the anchor moves to the rim centre on the axis.
  await page.locator('#modelTree [data-entity="joint-hub_axis"]').click();
  await page.locator('#spatial-joint-hub_axis-pick').click();
  let target = await rimPoint();
  await page.mouse.move(target.x, target.y);
  await tooltip(/Circle Ø55\.0 mm · axis [−+]x/);
  await page.mouse.click(target.x, target.y);
  await page.waitForFunction(() => document.querySelector('#notice')?.textContent.includes('Joint hub_axis placed on'));
  const rimX = await value('anchorA-x');
  assert(Math.abs(Math.abs(rimX) - 0.035) < 1e-6, `rim centre x ${rimX}`);
  for (const field of ['anchorA-y', 'anchorA-z']) assert(Math.abs(await value(field)) < 1e-9);
  assert.equal(await value('anchorB-x'), rimX);

  // Measure from one end rim to the other: the hub is 70 mm long and the rims are parallel.
  await page.locator('#measureViewButton').click();
  target = await rimPoint();
  await page.mouse.click(target.x, target.y);
  target = await rimPoint(true);
  await page.mouse.move(target.x, target.y);
  await tooltip(/Circle Ø55\.0 mm/);
  await page.mouse.click(target.x, target.y);
  const measured = await page.locator('#pickText').textContent();
  assert.match(measured, /Distance 70\.00 mm .*axes 0\.00° apart/);
  await page.keyboard.press('Escape');

  // Shift-drag the bearing symbol: it slides along its axis in whole millimetres.
  await rimPoint();
  const glyph = await page.evaluate((x) => {
    const view = window.__view, offset = view.sourceParts.offset;
    view.renderer.render(view.scene, view.camera);
    const point = view.camera.position.clone().set(-0.04 + x + offset.x, -0.0875 + offset.y, 0.6 + offset.z);
    point.project(view.camera);
    const rect = view.renderer.domElement.getBoundingClientRect();
    return { x: rect.left + (point.x + 1) / 2 * rect.width, y: rect.top + (1 - point.y) / 2 * rect.height };
  }, rimX);
  await page.mouse.move(glyph.x, glyph.y);
  await tooltip(/drag to move it/);
  await page.keyboard.down('Shift');
  await page.mouse.down();
  await page.mouse.move(glyph.x + 60, glyph.y + 25, { steps: 8 });
  await tooltip(/Move along its axis by \d+ mm/);
  await page.mouse.up();
  await page.keyboard.up('Shift');
  await page.waitForFunction(() => /Joint hub_axis moved along its axis by \d+ mm/.test(document.querySelector('#notice')?.textContent || ''));
  const slid = await value('anchorA-x');
  assert(Math.abs(slid - rimX) > 0.002, `the anchor moved along x (${rimX} → ${slid})`);
  assert(Math.abs(Math.round((slid - rimX) * 1000) - (slid - rimX) * 1000) < 1e-6, 'moves in whole millimetres');
  for (const field of ['anchorA-y', 'anchorA-z']) assert(Math.abs(await value(field)) < 1e-9, `${field} stays on the axis`);
  assert.equal(await value('anchorB-x'), slid);
  await page.locator('#undoButton').click();
  assert.equal(await value('anchorA-x'), rimX);

  // Run, then measure at an animated frame: features follow the displayed pose, not the initial one.
  const response = page.waitForResponse((r) => r.url().endsWith('/api/run') && r.request().method() === 'POST', { timeout: 300000 });
  await page.locator('#runButton').click();
  assert((await (await response).json()).ok);
  await page.waitForFunction(() => document.querySelector('#resultSource')?.textContent.includes('MBDyn'));
  await page.locator('#timeSlider').evaluate((slider) => { slider.value = String(Math.round(Number(slider.max) * 0.15)); slider.dispatchEvent(new Event('input', { bubbles: true })); });
  await page.waitForTimeout(300);
  await page.locator('#measureViewButton').click();
  assert.match(await page.locator('#pickText').textContent(), /Measure at t = [\d.]+ s/);
  target = await rimPoint();
  await page.mouse.move(target.x, target.y);
  await tooltip(/Circle Ø55\.0 mm/);
  const gap = await page.evaluate(() => {
    const view = window.__view;
    const rims = view.stepView.rimLines.map((line) => line.localToWorld(line.geometry.boundingSphere.center.clone()));
    return Math.min(...rims.map((centre) => centre.distanceTo(view.featureGroup.position)));
  });
  assert(gap < 1e-6, `the preview sits on the displayed rim (${gap} m away)`);
  await page.keyboard.press('Escape');
  assert.deepEqual(errors, []);
  console.log(`Interaction II: bearing placed on the Ø55 rim, rims 70 mm apart, Shift-drag moved it ${((slid - rimX) * 1000).toFixed(0)} mm along its axis, and measurement follows the animated pose.`);
} finally {
  await browser.close();
}
