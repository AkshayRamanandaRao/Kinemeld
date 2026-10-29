/** Real solver → browser plots, exported channels and rendered engineering poses. */
import './workspace-shim.mjs';
import assert from "node:assert/strict";
import { chromium } from "playwright";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const output = fileURLToPath(new URL("./evidence/", import.meta.url));
await mkdir(output, { recursive: true });
const browser = await chromium.launch({
  headless: true,
  args: ["--enable-unsafe-swiftshader"],
});
const page = await browser.newPage({
  viewport: { width: 1440, height: 960 },
  acceptDownloads: true,
});
const report = { started: new Date().toISOString(), checks: [], errors: [] };
page.on("pageerror", (error) => report.errors.push(error.message));
const cases = [
  {
    kind: "suspension",
    title: "Quarter-car road bump",
    field: "suspensionDamping",
    quantity: "Body / wheel acceleration",
    csv: "tire_force_N",
  },
  {
    kind: "landing-gear-drop",
    title: "Landing-gear drop test",
    field: "sinkVelocity",
    quantity: "Strut / tire force",
    csv: "strut_compression_m",
  },
  {
    kind: "gear-deployment",
    title: null,
    field: "mainLength",
    quantity: "Loop closure residual",
    csv: "closure_error_m",
  },
];
try {
  await page.goto(process.env.MBDYN_STUDIO_URL || "http://127.0.0.1:8766");
  await page.waitForFunction(() =>
    document
      .querySelector("#solverStatus")
      ?.textContent.includes("MBDyn ready"),
  );
  await page.evaluate(async () => {
    const { MechanismView } = await import("/viewport.js");
    const original = MechanismView.prototype.setSample;
    MechanismView.prototype.setSample = function (sample) {
      original.call(this, sample);
      if (!sample || !this.industryParts) return;
      const p = this.industryParts;
      window.__industryPose = {
        kind: this.model.kind,
        sample,
        first: this.bob.position.toArray(),
        second: this.bob2?.position.toArray(),
        radius: p.radius,
        lift: p.lift,
        braceB: p.b?.position.toArray(),
        braceC: p.c?.position.toArray(),
        wheels: p.wheels?.position.toArray(),
      };
    };
  });
  for (const item of cases) {
    await page.locator("#examplesButton").click();
    if (!item.title) {
      const examples = await (
        await page.request.get(new URL("/api/examples", page.url()).href)
      ).json();
      item.title = examples.examples.find((ex) => ex.id === item.kind).title;
    }
    const card = page.locator(".example-card").filter({
      has: page.getByRole("heading", { name: item.title, exact: true }),
    });
    assert.equal(await card.count(), 1);
    await card.getByRole("button", { name: /Open example/ }).click();
    await page.waitForSelector(`#field-${item.field}`);
    await page.waitForFunction(
      () => document.querySelector("#validationBadge")?.textContent === "Ready",
    );
    const responseEvent = page.waitForResponse(
      (r) => r.url().endsWith("/api/run") && r.request().method() === "POST",
      { timeout: 195000 },
    );
    await page.locator("#runButton").click();
    const result = await (await responseEvent).json();
    assert.equal(result.ok, true, result.error);
    assert.equal(result.source, "MBDyn");
    await page.waitForFunction(
      () =>
        document.querySelector("#resultSource")?.textContent === "MBDyn solver",
    );
    await page.locator("#signalSelect").selectOption({ label: item.quantity });
    assert.equal(
      await page.locator("#signalTitle").textContent(),
      item.quantity,
    );
    assert.equal(
      await page.locator("#plot polyline").count(),
      item.kind === "gear-deployment" ? 1 : 2,
    );
    for (const points of await page
      .locator("#plot polyline")
      .evaluateAll((nodes) =>
        nodes.map((node) => node.getAttribute("points")),
      )) {
      assert(points.length > 100 && !/NaN|Infinity/.test(points));
    }
    const index = Math.floor(result.samples.length * 0.42);
    await page.locator("#timeSlider").fill(String(index));
    const pose = await page.evaluate(() => window.__industryPose);
    const sample = result.samples[index];
    assert.equal(pose.kind, item.kind);
    assert.equal(pose.sample.time, sample.time);
    if (item.kind === "gear-deployment") {
      assert.deepEqual(pose.braceB, [sample.bx, 0, sample.bz + pose.lift]);
      assert.deepEqual(pose.braceC, [sample.cx, 0, sample.cz + pose.lift]);
      assert.deepEqual(pose.wheels, [
        sample.wheelX,
        0,
        sample.wheelZ + pose.lift,
      ]);
    } else {
      assert.deepEqual(pose.first, [
        0,
        0,
        sample.zSprung + (item.kind === "suspension" ? 1.15 : pose.radius),
      ]);
      assert.deepEqual(pose.second, [0, 0, sample.zUnsprung + pose.radius]);
    }
    await page
      .locator(".inspector")
      .evaluate((element) => (element.scrollTop = 0));
    await page.screenshot({
      path: path.join(output, `${item.kind}-mbdyn.png`),
    });
    const event = page.waitForEvent("download");
    await page.locator("#csvButton").click();
    const download = await event;
    const csvPath = path.join(output, `${item.kind}-results.csv`);
    await download.saveAs(csvPath);
    const lines = (await readFile(csvPath, "utf8"))
      .trim()
      .split(/\r?\n/)
      .filter((line) => !line.startsWith("#"));
    assert(lines[0].split(",").includes(item.csv));
    assert.equal(lines.length - 1, result.metrics.sampleCount);
    await page.locator("#helpButton").click();
    await page.locator("#documentDialog").waitFor({ state: "visible" });
    assert((await page.locator("#documentBody").textContent()).length > 500);
    await page.locator("#documentDialog [data-close]").last().click();
    await page.locator('[data-view="topology"]').click();
    assert(await page.locator(".industry-topology").isVisible());
    await page.locator('[data-view="scene"]').click();
    const field = page.locator(`#field-${item.field}`);
    const old = await field.inputValue();
    await field.fill(String(Number(old) * 1.05));
    await field.press("Tab");
    await page.waitForFunction(() =>
      document.querySelector("#resultSource")?.textContent.includes("Stale"),
    );
    assert(await page.locator("#playButton").isDisabled());
    await page.locator("#undoButton").click();
    assert.equal(await field.inputValue(), old);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(200);
    const sizes = await page.evaluate(() => [
      document.documentElement.scrollWidth,
      innerWidth,
    ]);
    assert(sizes[0] <= sizes[1] + 1, `${item.kind} mobile overflow: ${sizes}`);
    assert(await page.locator("#signalSelect").isVisible());
    await page.screenshot({
      path: path.join(output, `${item.kind}-mobile.png`),
      fullPage: true,
    });
    await page.setViewportSize({ width: 1440, height: 960 });
    report.checks.push({
      kind: item.kind,
      ok: true,
      runId: result.runId,
      nativeSamples: result.metrics.sampleCount,
      displayedSamples: result.samples.length,
      actualPoseTime: sample.time,
    });
    console.log(
      `${item.kind}: real solve, channels, pose, CSV, guide, stale state and mobile passed`,
    );
  }
  await page.locator("#examplesButton").click();
  await page
    .locator(".example-card")
    .filter({
      has: page.getByRole("heading", {
        name: "Quarter-car road bump",
        exact: true,
      }),
    })
    .getByRole("button", { name: /Open example/ })
    .click();
  await page.locator("#field-bumpHeight").fill("0.2");
  await page.locator("#field-bumpHeight").press("Tab");
  const warningResponse = page.waitForResponse(
    (r) => r.url().endsWith("/api/preview") && r.request().method() === "POST",
  );
  await page.locator("#previewButton").click();
  const warningResult = await (await warningResponse).json();
  assert.equal(warningResult.metrics.contactAssumptionViolated, true);
  await page.waitForFunction(() =>
    document
      .querySelector("#notice")
      ?.textContent.includes(
        "continuous-contact suspension assumption is invalid",
      ),
  );
  assert.match(
    await page.locator("#resultSource").textContent(),
    /Reference preview/,
  );
  report.checks.push({
    name: "Negative tire load produces explicit model-limit guidance",
    ok: true,
  });
  assert.deepEqual(report.errors, []);
  report.ok = true;
} catch (error) {
  report.ok = false;
  report.failure = error.stack;
  await page
    .screenshot({
      path: path.join(output, "industry-failure.png"),
      fullPage: true,
    })
    .catch(() => {});
  console.error(error);
  process.exitCode = 1;
} finally {
  report.completed = new Date().toISOString();
  await writeFile(
    path.join(output, "industry-ui-verification.json"),
    JSON.stringify(report, null, 2),
  );
  await browser.close();
}
