/** Browser validation of actual pinned upstream solver runs and node postprocessing. */
import assert from "node:assert/strict";
import { chromium } from "playwright";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const dir = fileURLToPath(new URL("./evidence/", import.meta.url));
await mkdir(dir, { recursive: true });
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
try {
  const base = process.env.MBDYN_STUDIO_URL || "http://127.0.0.1:8767";
  await page.goto(base);
  await page.waitForFunction(() =>
    document
      .querySelector("#solverStatus")
      ?.textContent.includes("MBDyn ready"),
  );
  const catalog = (
    await (await page.request.get(`${base}/api/source-examples`)).json()
  ).examples;
  assert(catalog.filter((item) => item.enabled).length >= 3);
  await page.evaluate(async () => {
    const { MechanismView } = await import("/viewport.js");
    const original = MechanismView.prototype.setSample;
    MechanismView.prototype.setSample = function (sample) {
      original.call(this, sample);
      if (this.model.kind === "source-example" && sample)
        window.__sourcePose = {
          sample,
          offset: this.sourceParts.offset.toArray(),
          positions: [...this.sourceParts.nodes.entries()].map(([id, mesh]) => [
            id,
            mesh.position.toArray(),
          ]),
        };
    };
  });
  for (const entry of catalog.filter((item) => item.enabled)) {
    await page.locator("#examplesButton").click();
    const card = page
      .locator(".example-card")
      .filter({
        has: page.getByRole("heading", { name: entry.title, exact: true }),
      });
    assert.match(await card.textContent(), /GPL-2\.0/);
    await card.getByRole("button", { name: /Open example/ }).click();
    await page.waitForFunction(
      () => document.querySelector("#validationBadge")?.textContent === "Ready",
    );
    assert.equal(await page.locator("#durationInput").isDisabled(), true);
    assert.equal(await page.locator("#previewButton").isDisabled(), true);
    await page.locator("#deckButton").click();
    await page.locator("#documentDialog").waitFor({ state: "visible" });
    assert.match(
      await page.locator("#documentBody").textContent(),
      /begin: data/i,
    );
    await page.locator("#documentDialog [data-close]").last().click();
    const responseEvent = page.waitForResponse(
      (r) =>
        r.url().endsWith("/api/source-run") && r.request().method() === "POST",
      { timeout: 200000 },
    );
    await page.locator("#runButton").click();
    const result = await (await responseEvent).json();
    assert.equal(result.ok, true, result.error);
    assert.equal(result.source, "MBDyn");
    await page.waitForFunction(
      () =>
        document.querySelector("#resultSource")?.textContent === "MBDyn solver",
    );
    assert.equal(
      await page.locator("#nodeSelect option").count(),
      entry.nodes.length,
    );
    assert.equal(await page.locator("#plot polyline").count(), 3);
    await page
      .locator("#nodeSelect")
      .selectOption(String(entry.nodes.at(-1).id));
    await page.locator("#measureNode").selectOption(String(entry.nodes[0].id));
    await page
      .locator("#signalSelect")
      .selectOption({ label: "Node Euler 1–2–3 · X / Y / Z" });
    assert.match(await page.locator("#plot").getAttribute("aria-label"), /deg/);
    const index = Math.floor(result.samples.length * 0.4);
    await page.locator("#timeSlider").fill(String(index));
    const pose = await page.evaluate(() => window.__sourcePose);
    const sample = result.samples[index];
    assert.equal(pose.sample.time, sample.time);
    for (const node of sample.nodes) {
      const actual = pose.positions.find(([id]) => id === String(node.id))?.[1];
      assert.deepEqual(actual, [
        node.x + pose.offset[0],
        node.y + pose.offset[1],
        node.z + pose.offset[2],
      ]);
    }
    const sourceFirst = sample.nodes.find(
      (node) => node.id === entry.nodes[0].id,
    );
    const sourceLast = sample.nodes.find(
      (node) => node.id === entry.nodes.at(-1).id,
    );
    const expected = Math.hypot(
      sourceFirst.x - sourceLast.x,
      sourceFirst.y - sourceLast.y,
      sourceFirst.z - sourceLast.z,
    ).toFixed(5);
    assert.match(
      await page.locator("#sourceProbe").textContent(),
      new RegExp(`Distance ${expected.replace(".", "\\.")} m`),
    );
    await page.screenshot({ path: path.join(dir, `source-${entry.id}.png`) });
    const downloadEvent = page.waitForEvent("download");
    await page.locator("#csvButton").click();
    const download = await downloadEvent;
    const file = path.join(dir, `source-${entry.id}.csv`);
    await download.saveAs(file);
    const lines = (await readFile(file, "utf8"))
      .trim()
      .split(/\r?\n/)
      .filter((line) => !line.startsWith("#"));
    assert.equal(
      lines.length - 1,
      result.metrics.sampleCount * entry.nodes.length,
    );
    for (const column of [
      "time_s",
      "node_id",
      "x_m",
      "euler123_x_deg",
      "velocity_x_m_s",
      "angular_velocity_x_rad_s",
    ])
      assert(lines[0].split(",").includes(column));
    report.checks.push({
      id: entry.id,
      ok: true,
      runId: result.runId,
      frames: result.metrics.sampleCount,
      nodes: entry.nodes.length,
      exportRows: lines.length - 1,
      visualTime: sample.time,
    });
    console.log(
      `${entry.id}: pinned deck, real solve, trajectories, node probe and complete CSV passed`,
    );
  }
  const blocked = catalog.find((item) => !item.enabled);
  if (blocked) {
    await page.locator("#examplesButton").click();
    const card = page
      .locator(".example-card")
      .filter({
        has: page.getByRole("heading", { name: blocked.title, exact: true }),
      });
    await card.getByRole("button", { name: "Why unavailable?" }).click();
    assert.match(
      await page.locator("#documentBody").textContent(),
      /initial assembly/i,
    );
    report.checks.push({
      id: blocked.id,
      ok: true,
      scope: "failure and remediation shown; not runnable",
    });
  }
  assert.deepEqual(report.errors, []);
  report.ok = true;
} catch (error) {
  report.ok = false;
  report.failure = error.stack;
  process.exitCode = 1;
  console.error(error);
  await page
    .screenshot({
      path: path.join(dir, "source-ui-failure.png"),
      fullPage: true,
    })
    .catch(() => {});
} finally {
  report.completed = new Date().toISOString();
  await writeFile(
    path.join(dir, "source-ui-verification.json"),
    JSON.stringify(report, null, 2),
  );
  await browser.close();
}
