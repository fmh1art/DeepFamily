// Capture a registered, historical model run through the current Web components.
// No inference: API writes are intercepted; only same-origin reads are permitted.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium, expect } from "@playwright/test";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const sourcePath = "frontend/e2e/capture-agentic-replay.mjs";
const stylePath = "frontend/e2e/agentic-replay-plate.css";
const evidencePath = "experiments/evidence/agentic-question-only-smoke-2026-09-09.json";
const sha = (bytes) => createHash("sha256").update(bytes).digest("hex");
const evidenceBytes = await readFile(path.join(root, evidencePath));
const evidence = JSON.parse(evidenceBytes);
const observation = evidence.runs.find((run) => run.run_id === "run_e2f9348452df475c");
assert.ok(observation, "Registered completed model observation is missing");
const runBytes = await readFile(path.join(root, observation.path));
assert.equal(sha(runBytes), observation.sha256, "Historical run bytes have changed");
const run = JSON.parse(runBytes);
assert.equal(run.status, "completed");
assert.equal(run.question, evidence.question);
assert.equal(run.preparation_attempts.length, 1);
assert.equal(run.analysis_notebook.filter((step) => step.phase === "debug").length, 0);
assert.equal(run.report.sections.length, 5);
assert.equal(sha(run.report.markdown), observation.report_sha256);

const baseURL = new URL(process.env.ASKDU_E2E_BASE_URL ?? "http://127.0.0.1:8080");
assert.ok(["127.0.0.1", "localhost", "[::1]"].includes(baseURL.hostname));
assert.equal(baseURL.protocol, "http:");
assert.ok(!baseURL.username && !baseURL.password && !baseURL.search);
const outputDirectory = path.join(root, "paper/figures/agentic-replay-v1");
await mkdir(outputDirectory, { recursive: true });
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: 1600, height: 1100 }, deviceScaleFactor: 3,
  reducedMotion: "reduce", bypassCSP: true,
});
const page = await context.newPage();
const errors = [];
let replayRequests = 0;
page.on("pageerror", (error) => errors.push(error.message));
await page.route("**/*", async (route) => {
  const request = route.request();
  const url = new URL(request.url());
  if (url.origin !== baseURL.origin) return route.abort();
  if (url.pathname === "/api/v1/runs" && request.method() === "POST") {
    assert.deepEqual(request.postDataJSON(), { question: run.question });
    replayRequests += 1;
    return route.fulfill({ status: 202, json: run });
  }
  if (url.pathname === `/api/v1/runs/${run.run_id}` && request.method() === "GET") {
    return route.fulfill({ json: run });
  }
  if (request.method() !== "GET" || url.pathname.startsWith("/api/v1/runs")) {
    return route.abort();
  }
  if (url.pathname === "/api/v1/environments/current") {
    const response = await route.fetch();
    const environment = await response.json();
    assert.equal(environment.planner_mode, "agentic");
    assert.equal(environment.environment_id, run.environment_id);
    return route.fulfill({ response, json: environment });
  }
  return route.continue();
});

const outputs = {};
const pendingFiles = new Map();
async function record(name, bytes, extra = {}) {
  const relative = `paper/figures/agentic-replay-v1/${name}`;
  pendingFiles.set(relative, bytes);
  outputs[relative] = { sha256: sha(bytes), bytes: bytes.length, ...extra };
}
async function screenshot(name, locator) {
  const bytes = await locator.screenshot({ animations: "disabled" });
  await record(name, bytes, {
    format: "png", pixel_width: bytes.readUInt32BE(16), pixel_height: bytes.readUInt32BE(20),
  });
}

async function screenshotRecordedView(name, locator) {
  await locator.evaluate((element, question) => {
    const label = document.createElement("div");
    label.className = "recorded-view-label";
    label.textContent = `Recorded run · ${question} · no new inference`;
    label.style.cssText = "padding:12px 20px;background:#fff6e8;color:#172033;font:16px/1.4 Arial,sans-serif;border-bottom:1px solid #b58130;grid-column:1/-1";
    element.prepend(label);
  }, run.question);
  try { await screenshot(name, locator); }
  finally { await locator.locator(":scope > .recorded-view-label").evaluate((el) => el.remove()); }
}

try {
  await page.goto(baseURL.href, { waitUntil: "networkidle" });
  // Bind the served JS/CSS to the locally built UI instead of trusting a port number.
  const bundlePaths = await page.locator('script[src], link[rel="stylesheet"]').evaluateAll(
    (elements) => elements.map((element) => element.getAttribute("src") ?? element.getAttribute("href")),
  );
  for (const bundlePath of bundlePaths) {
    assert.match(bundlePath, /^\/assets\/[^/]+\.(js|css)$/);
    const response = await page.request.get(new URL(bundlePath, baseURL).href);
    assert.ok(response.ok());
    assert.equal(sha(await response.body()), sha(await readFile(path.join(root, "frontend/dist", bundlePath))));
  }
  await page.getByRole("textbox", { name: "Your analytical question" }).fill(run.question);
  await page.getByRole("button", { name: /Run hands-off analysis/ }).click();
  await expect(page.locator("#report-title")).toHaveText(run.report.title);
  assert.equal(replayRequests, 1);
  const workbench = page.getByTestId("research-workflow");
  await workbench.getByRole("tab", { name: /CoDA-Bench Discover/ }).click();
  const selectedOutput = await workbench.locator(".discovery-output-files").evaluate((el) => el.outerHTML);
  await workbench.getByRole("button", { name: "Show hop 5: Inspect asset" }).click();
  const network = await workbench.locator(".discovery-network").evaluate((el) => el.outerHTML);
  await screenshotRecordedView("discovery.png", workbench);

  await workbench.getByRole("tab", { name: /DeepPrep Prepare/ }).click();
  await workbench.locator(".schema-change-details > summary").click();
  const tree = await workbench.locator(".prep-tree-board").evaluate((el) => el.outerHTML);
  const typeDifference = await workbench.locator(".schema-change-details .stage-schema-list").evaluate((el) => el.outerHTML);
  const table = await workbench.locator(".prepared-table-preview").evaluate((el) => el.outerHTML);
  await screenshotRecordedView("preparation.png", workbench);

  await workbench.getByRole("tab", { name: /DeepAnalyze Analyze/ }).click();
  const codeCell = workbench.locator(".notebook-cell.code").nth(1);
  await codeCell.locator(".notebook-cell-details > summary").click();
  const code = await codeCell.locator(".notebook-code-wrap").evaluate((el) => el.outerHTML);
  const reportOutline = await workbench.locator(".analysis-report-dimensions").evaluate((el) => el.outerHTML);
  await screenshotRecordedView("analysis.png", workbench.locator(".analysis-data-io"));
  await screenshotRecordedView("report.png", page.locator(".report-narrative"));

  // Arrange actual DOM excerpts for print. No event, result, schema, code, or sentence is fabricated.
  await page.evaluate(({ network, selectedOutput, tree, typeDifference, table, code, reportOutline, question }) => {
    const plate = document.createElement("section");
    plate.id = "agentic-replay-plate";
    plate.innerHTML = `<header><strong>Recorded model run · current UI excerpts</strong><span class="question"></span></header>
      <div class="replay-panels">
        <article class="replay-panel discovery"><h2>a · Discover</h2><p>Hop 5 / 12 · inside community 28</p>${network}
          <h3>Final selected file</h3>${selectedOutput}</article>
        <article class="replay-panel preparation"><h2>b · Prepare</h2>${tree}
          <h3>Recorded type: input → output</h3>${typeDifference}${table}
          <p class="excerpt-note">Preview: first 3 rows, 2 of 10 columns.</p></article>
        <article class="replay-panel analysis"><h2>c · Analyze → Report</h2>${code}
          <h3>Five report sections</h3>${reportOutline}
          <p class="excerpt-note">Concludes with conditional recommendations and missing-policy limitations.</p></article>
      </div><footer>Historical run · one successful preparation path · no Debug or backtracking. DOM excerpts rearranged for print.</footer>`;
    plate.querySelector(".question").textContent = `Only task input: ${question}`;
    document.body.append(plate);
    document.documentElement.classList.add("capturing-agentic-replay");
  }, { network, selectedOutput, tree, typeDifference, table, code, reportOutline, question: run.question });
  await page.addStyleTag({ content: await readFile(path.join(root, stylePath), "utf8") });
  const plate = page.locator("#agentic-replay-plate");
  // Applying print CSS can invalidate the previous font/layout readiness state.
  // Locator screenshots wait for stable geometry and fonts. Measure that same
  // settled layout, not the transient box immediately after style insertion.
  await screenshot("overview.png", plate);
  const box = await plate.boundingBox();
  assert.ok(box && box.width === 1000);
  if (box.height > 750) {
    const debugDirectory = await mkdtemp(path.join(tmpdir(), "askdu-replay-layout-"));
    await plate.screenshot({ path: path.join(debugDirectory, "plate.png") });
    console.error(JSON.stringify({ debugDirectory, panels: await plate.locator(".replay-panel").evaluateAll(
      (panels) => panels.map((panel) => ({
        panel: panel.className, height: panel.getBoundingClientRect().height,
        children: [...panel.children].map((child) => ({
          element: child.className || child.tagName, height: child.getBoundingClientRect().height,
        })),
      })),
    ) }));
  }
  assert.ok(box.height <= 750, `Plate too tall for a readable paper layout: ${box?.height}`);
  assert.equal(outputs["paper/figures/agentic-replay-v1/overview.png"].pixel_width, box.width * 3);
  assert.equal(outputs["paper/figures/agentic-replay-v1/overview.png"].pixel_height, Math.ceil(box.height) * 3);
  const pdf = await page.pdf({ width: "1000px", height: `${Math.ceil(box.height)}px`, printBackground: true, margin: { top: 0, right: 0, bottom: 0, left: 0 } });
  await record("overview.pdf", pdf, { format: "browser-vector-pdf" });
  await plate.evaluate((el) => { el.style.filter = "grayscale(1)"; });
  await screenshot("overview-gray.png", plate);
  assert.deepEqual(errors, []);
  const manifest = {
    schema_version: "askdu-agentic-replay-capture-v1",
    capture_kind: "historical_model_run_in_current_ui",
    source_script: sourcePath, source_sha256: sha(await readFile(path.join(root, sourcePath))),
    style_path: stylePath, style_sha256: sha(await readFile(path.join(root, stylePath))),
    evidence_path: evidencePath, evidence_sha256: sha(evidenceBytes),
    original_run: { path: observation.path, sha256: observation.sha256, run_id: run.run_id },
    original_report_sha256: observation.report_sha256,
    excerpt: { graph_hop: 5, selected_source_hop: 12, preview_rows: 3, preview_columns: 2 },
    demo_surface_sha256: execFileSync(path.join(root, "scripts/hash_demo_surface.sh"), { cwd: root, encoding: "utf8" }).trim(),
    capture_notes: [
      "Actual DOM excerpts rearranged and typeset for print; current full UI captures are provided separately.",
      "Graph is recorded hop 5; selected file is recorded hop 12. Other panels show terminal outputs.",
      "Prepared preview shows only the first three rows and first two columns in the overview, with an explicit excerpt label.",
      "Model prose remains in its original language. A completed report is not a factuality certificate.",
    ],
    visible_panels: ["a", "b", "c"], css_width: box.width, css_height: box.height, device_scale_factor: 3,
    model_calls_during_capture: 0, replayed_post_requests: replayRequests,
    browser_errors: errors, outputs,
  };
  // A failed capture/geometry assertion must not replace previously verified files.
  // Publish only once every capture assertion has passed; write the manifest last.
  for (const [relative, bytes] of pendingFiles) await writeFile(path.join(root, relative), bytes);
  await writeFile(path.join(outputDirectory, "capture.json"), `${JSON.stringify(manifest, null, 2)}\n`);
  console.log(JSON.stringify({ outputDirectory, width: box.width, height: box.height, replayRequests, modelCalls: 0 }));
} finally {
  await browser.close();
}
