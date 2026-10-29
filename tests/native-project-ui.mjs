/** Exercise the desktop UI's project protocol against a controlled native bridge. */
import './workspace-shim.mjs';
import assert from "node:assert/strict";
import { chromium } from "playwright";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";

const output = fileURLToPath(new URL("./evidence/", import.meta.url));
await mkdir(output, { recursive: true });
const report = { started: new Date().toISOString(), checks: [], errors: [] };
const browser = await chromium.launch({
  headless: true,
  args: ["--enable-unsafe-swiftshader"],
});
const page = await browser.newPage({
  viewport: { width: 1440, height: 960 },
  acceptDownloads: true,
});
page.on("pageerror", (error) => report.errors.push(error.message));
await page.route("**/api/tour-preference", route => route.fulfill({ json: { enabled: false } }));
await page.addInitScript(() => {
  window.__nativeTest = {
    project: null,
    notifications: [],
    accepted: 0,
    failSave: false,
  };
  window.mbdynNative = {
    notify(op) {
      window.__nativeTest.notifications.push(op);
    },
    async call(op, payload = {}) {
      const state = window.__nativeTest;
      if (op === "save") {
        if (state.failSave)
          throw new Error(
            "The project changed on disk after it was opened/saved.",
          );
        state.project = structuredClone({
          format: "mbdyn-studio/1",
          schemaVersion: 1,
          model: payload.model,
          result: payload.result,
          view: payload.view,
          assets: payload.assets,
        });
        return { path: "C:/test/project.mbdyn-studio", backup: null };
      }
      if (op === "open")
        return {
          project: structuredClone(state.project),
          path: "C:/test/project.mbdyn-studio",
        };
      if (op === "accept-open") {
        state.accepted++;
        return {token:"1"};
      }
      if (op === "finalize-open") return {token:payload.token,dirtyRevision:"1"};
      if (op === "clean-open") return {token:payload.token,dirtyRevision:payload.dirtyRevision,clean:true};
      throw new Error(`Unsupported test operation: ${op}`);
    },
  };
});
try {
  await page.goto(process.env.MBDYN_STUDIO_URL || "http://127.0.0.1:8767");
  await page.waitForFunction(() =>
    document
      .querySelector("#solverStatus")
      ?.textContent.includes("MBDyn ready"),
  );
  assert(await page.locator("#saveAsButton").isVisible());
  await page.locator("#examplesButton").click();
  await page
    .locator(".example-card")
    .filter({
      has: page.getByRole("heading", {
        name: "Damped oscillator",
        exact: true,
      }),
    })
    .getByRole("button", { name: /Open example/ })
    .click();
  await page.waitForFunction(
    () => document.querySelector("#validationBadge")?.textContent === "Ready",
  );
  const mesh = Buffer.from(`solid sample\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 10 0 0\nvertex 0 10 0\nendloop\nendfacet\nendsolid sample\n`);
  const examples = await (await page.request.get(new URL("/api/examples", page.url()).href)).json();
  const legacyProject = {
    format: "mbdyn-studio/1", model: examples.examples.find(item => item.id === "mass-spring").model,
    assets: { reference: { schemaVersion: 1, format: "stl", name: "sample.stl", unit: "mm", data: mesh.toString("base64"),
      sha256: createHash("sha256").update(mesh).digest("hex"), byteLength: mesh.length, triangleCount: 1 } },
  };
  await page.evaluate(project => { window.__nativeTest.project = project; }, legacyProject);
  await page.locator("#importButton").click();
  await page.waitForFunction(() => document.querySelector("#referenceStatus")?.textContent.includes("sample.stl"));
  const event = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/run") &&
      response.request().method() === "POST",
    { timeout: 200000 },
  );
  await page.locator("#runButton").click();
  const result = await (await event).json();
  assert.equal(result.ok, true, result.error);
  await page.waitForFunction(
    () =>
      document.querySelector("#resultSource")?.textContent === "MBDyn solver",
  );
  await page.locator("#stepFile").setInputFiles("examples/step-suspension/Assembly 1 - Hub.step");
  await page.waitForFunction(()=>document.querySelector("#stepStatus")?.textContent.includes("STEP solids"),null,{timeout:60000});
  await page.locator("#timeSlider").fill("35");
  const savedTime = await page.locator("#timeOutput").textContent();
  await page.locator("#saveButton").click();
  await page.waitForFunction(() =>
    document.querySelector("#notice")?.textContent.includes("Project saved to"),
  );
  const saved = await page.evaluate(() => window.__nativeTest.project);
  assert.equal(saved.model.kind, "mass-spring");
  assert.equal(saved.result.source, "MBDyn");
  assert.equal(saved.assets.reference.unit,"mm");
  assert.equal(saved.assets.step.files[0].name,"Assembly 1 - Hub.step");
  assert(saved.result.csvText.split("\n").length > result.samples.length);
  assert.equal(saved.view.frame, 35);
  assert(
    (await page.evaluate(() => window.__nativeTest.notifications)).includes(
      "dirty",
    ),
  );
  await page.locator("#field-stiffness").fill("160");
  await page.locator("#field-stiffness").press("Tab");
  await page.locator("#referenceRemoveButton").click();
  await page.locator("#importButton").click();
  await page.waitForFunction(() =>
    document.querySelector("#notice")?.textContent.includes("Project opened"),
  );
  assert.equal(await page.locator("#field-stiffness").inputValue(), "100");
  assert.match(
    await page.locator("#resultSource").textContent(),
    /Saved result · recorded MBDyn/,
  );
  assert.match(await page.locator("#referenceStatus").textContent(),/sample.stl \(mm\)/);
  assert.match(await page.locator("#stepStatus").textContent(),/STEP solids/);
  assert.equal(await page.locator("#timeOutput").textContent(), savedTime);
  const downloadEvent = page.waitForEvent("download");
  await page.locator("#csvButton").click();
  const download = await downloadEvent;
  const csv = path.join(output, "native-restored.csv");
  await download.saveAs(csv);
  assert.equal(
    (await readFile(csv, "utf8"))
      .split("\n")
      .filter((line) => line && !line.startsWith("#")).length - 1,
    result.metrics.sampleCount,
  );
  report.checks.push({
    name: "Native save and reopen retain model, actual result, full CSV and viewing frame",
    ok: true,
    runId: result.runId,
  });
  await page.evaluate(() => {
    window.__nativeTest.failSave = true;
  });
  await page.locator("#saveButton").click();
  await page.waitForFunction(() =>
    document
      .querySelector("#notice")
      ?.textContent.includes("project changed on disk"),
  );
  assert.equal(await page.locator("#field-stiffness").inputValue(), "100");
  report.checks.push({
    name: "Save conflict reported without losing the current model",
    ok: true,
  });
  await page.evaluate(() => {
    window.__nativeTest.project.model.kind = "unknown-kind";
  });
  await page.locator("#importButton").click();
  await page.waitForFunction(() =>
    document
      .querySelector("#notice")
      ?.textContent.includes("Project was not opened"),
  );
  assert.equal(await page.locator("#field-stiffness").inputValue(), "100");
  assert(
    (await page.evaluate(() => window.__nativeTest.notifications)).includes(
      "discard-open",
    ),
  );
  report.checks.push({
    name: "Invalid project is rejected without adopting it",
    ok: true,
  });
  assert.deepEqual(report.errors, []);
  report.ok = true;
} catch (error) {
  report.ok = false;
  report.failure = error.stack;
  process.exitCode = 1;
  console.error(error);
} finally {
  report.completed = new Date().toISOString();
  await writeFile(
    path.join(output, "native-project-ui-verification.json"),
    JSON.stringify(report, null, 2),
  );
  await browser.close();
}
