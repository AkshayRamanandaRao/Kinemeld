/** Real UI + backend validation, with controlled AI replies and a counted, non-executing Run boundary. */
import './workspace-shim.mjs';
import assert from "node:assert/strict";
import { chromium } from "playwright";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const output = fileURLToPath(new URL("./evidence/", import.meta.url));
await mkdir(output, { recursive: true });
const report = {
  started: new Date().toISOString(),
  scope: "Browser application and real backend validation; deterministic AI transport fixtures; solver requests intercepted before execution.",
  checks: [], errors: [], runRequests: [],
};
const browser = await chromium.launch({ headless: true, args: ["--enable-unsafe-swiftshader"] });
const page = await browser.newPage({ viewport: { width: 1540, height: 980 } });
page.on("pageerror", error => report.errors.push(error.message));
const replies = [];
let validationBarrier = null;
const validationRequests = [];
const chats = [];

function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
}

async function bounded(promise, label) {
  let timer;
  try {
    return await Promise.race([promise, new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error(`Timed out waiting for ${label}`)), 15000);
    })]);
  } finally {
    clearTimeout(timer);
  }
}

function response(model = null, extra = {}) {
  return {
    ok: true, provider: "ollama", chatModel: "fixture:tools",
    answer: "Controlled proposal for UI boundary verification.",
    actions: model ? [{ type: "set_parameters", values: { length: model.parameters.length, angle: model.parameters.angle } }] : [],
    proposedModel: model, validation: { valid: true, issues: [] }, toolResults: [],
    runRequested: false, requiresUserRun: true, ...extra,
  };
}

function edited(body, values) {
  const model = structuredClone(body.model);
  Object.assign(model.parameters, values);
  return model;
}

async function idle() {
  await page.waitForFunction(() => !document.querySelector("#agentSend").disabled && document.querySelector("#agentStatus").textContent !== "Thinking locally…");
}

async function send(text, factory) {
  const received = deferred();
  replies.push({ factory, received });
  await page.locator("#agentInput").fill(text);
  await page.locator("#agentSend").click();
  return bounded(received.promise, "the chat request");
}

async function field(name, expected) {
  await page.waitForFunction(({ name, expected }) => Number(document.querySelector(`#field-${name}`)?.value) === expected, { name, expected });
}

async function changeLength(value) {
  await page.locator("#field-length").fill(String(value));
  await page.locator("#field-length").press("Tab");
  await field("length", value);
}

async function undo() {
  // The agent panel overlaps the toolbar at some window sizes; close it using its real control.
  await page.locator("#agentClose").click();
  await page.locator("#undoButton").click();
  await page.locator("#agentButton").click();
  await idle();
}

await page.route("**/api/agent/status", route => route.fulfill({
  json: { ok: true, provider: "ollama", available: true, localOnly: true, models: [{ name: "fixture:tools", size: 2000000 }], defaultModel: "fixture:tools", detail: "Controlled local AI transport for UI tests." },
}));
await page.route("**/api/agent/chat", async route => {
  const queued = replies.shift();
  assert(queued, "Unexpected chat request");
  const body = route.request().postDataJSON();
  chats.push(body);
  queued.received.resolve(body);
  await route.fulfill({ json: await queued.factory(body) });
});
await page.route("**/api/validate", async route => {
  const body = route.request().postDataJSON();
  validationRequests.push(structuredClone(body.model));
  if (validationBarrier && body.model.parameters?.length === validationBarrier.length) {
    const gate = validationBarrier;
    validationBarrier = null;
    gate.received.resolve();
    await gate.release.promise;
  }
  await route.continue();
});
await page.route("**/api/run", async route => {
  report.runRequests.push(route.request().postDataJSON());
  await route.fulfill({ status: 503, json: { ok: false, error: "UI test intercepted the authorized solver request; no solver was executed." } });
});

try {
  await page.goto(process.env.MBDYN_STUDIO_URL || "http://127.0.0.1:8768");
  await page.waitForSelector("#field-length");
  await field("length", 1);
  await page.locator("#agentButton").click();
  await idle();
  assert.equal(await page.locator("#agentModel").inputValue(), "fixture:tools");

  const validationCount = validationRequests.length;
  const original = await send("Set length to 2.25 m and angle to 17 degrees. Do not run.", body =>
    response(edited(body, { length: 2.25, angle: 17 }), { answer: '<img src="x" onerror="window.__unsafeAgent=true">' }));
  await idle();
  await field("length", 2.25);
  await field("angle", 17);
  assert(validationRequests.slice(validationCount).some(model => model.parameters.length === 2.25), "UI must call the actual backend validator before applying the proposal");
  assert.equal(await page.locator("#agentMessages img").count(), 0);
  assert.equal(await page.evaluate(() => window.__unsafeAgent), undefined);
  assert.equal(report.runRequests.length, 0);
  await page.screenshot({ path: path.join(output, "agent-proposal-applied.png") });
  await undo();
  await field("length", original.model.parameters.length);
  await field("angle", original.model.parameters.angle);
  report.checks.push({ name: "Validated AI proposal auto-applies atomically, renders prose as text, and one Undo restores both parameters", ok: true });

  await send("Set length to minus 3 m.", body => response(edited(body, { length: -3 })));
  await idle();
  await field("length", original.model.parameters.length);
  assert.match(await page.locator("#agentMessages").textContent(), /proposed changes were not applied/i);
  assert.equal(report.runRequests.length, 0);
  report.checks.push({ name: "UI independently rejects a physically invalid proposal even when the agent claims it is valid", ok: true });

  for (const text of ["Explain the current model.", "Do not run this simulation; just explain it."]) {
    await send(text, () => response(null, { runRequested: true, requiresUserRun: false }));
    await idle();
    assert.equal(report.runRequests.length, 0, `No run is authorized by: ${text}`);
  }
  await send("Please run the simulation.", () => response(null, { runRequested: true, requiresUserRun: true }));
  await idle();
  assert.equal(report.runRequests.length, 0, "Backend requiresUserRun gate must be honored");
  report.checks.push({ name: "No solver call for explanatory/negated prompts or a backend response requiring user Run", ok: true });

  await send("Set length to 1.5 m and then run the simulation.", body => response(edited(body, { length: 1.5 }), { runRequested: true, requiresUserRun: false }));
  await idle();
  await field("length", 1.5);
  assert.equal(report.runRequests.length, 1);
  assert.equal(report.runRequests[0].model.parameters.length, 1.5);
  assert.match(await page.locator("#notice").textContent(), /UI test intercepted the authorized solver request/);
  report.checks.push({ name: "An explicit run request invokes the existing Run handler exactly once using the validated updated model", ok: true });
  await undo();
  await field("length", 1);

  const releaseChat = deferred();
  await send("Set length to 2 m and then run the simulation.", async body => {
    await releaseChat.promise;
    return response(edited(body, { length: 2 }), { runRequested: true, requiresUserRun: false });
  });
  await changeLength(3);
  releaseChat.resolve();
  await idle();
  await field("length", 3);
  assert.equal(report.runRequests.length, 1);
  assert.match(await page.locator("#agentMessages").textContent(), /model, STEP attachments or another operation changed.*No proposed changes were applied/s);
  await undo();
  await field("length", 1);
  report.checks.push({ name: "Project edit while AI is pending rejects the stale proposal and run, without inserting an agent undo entry", ok: true });

  const gate = { length: 2.75, received: deferred(), release: deferred() };
  validationBarrier = gate;
  await send("Set length to 2.75 m and then run it.", body => response(edited(body, { length: 2.75 }), { runRequested: true, requiresUserRun: false }));
  await bounded(gate.received.promise, "the proposal validation request");
  await changeLength(4);
  gate.release.resolve();
  await idle();
  await field("length", 4);
  assert.equal(report.runRequests.length, 1);
  await undo();
  await field("length", 1);
  report.checks.push({ name: "Project edit during proposal validation is rechecked before applying or running", ok: true });

  assert.equal(replies.length, 0);
  assert.deepEqual(report.errors, []);
  assert(chats.every(chat => chat.chatModel === "fixture:tools" && chat.model.kind === "pendulum"));
  report.chatRequests = chats.length;
  report.validationRequests = validationRequests.length;
  report.ok = true;
  console.log(JSON.stringify({ ok: true, checks: report.checks.length, chatRequests: chats.length, authorizedRunRequests: report.runRequests.length, scope: report.scope }));
} catch (error) {
  report.ok = false;
  report.failure = error.stack;
  await page.screenshot({ path: path.join(output, "agent-ui-failure.png"), fullPage: true }).catch(() => {});
  console.error(error);
  process.exitCode = 1;
} finally {
  report.completed = new Date().toISOString();
  await writeFile(path.join(output, "agent-ui-verification.json"), JSON.stringify(report, null, 2));
  await browser.close();
}
