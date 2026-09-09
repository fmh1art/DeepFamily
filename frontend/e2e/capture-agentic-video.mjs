// Build a silent, captioned historical-run walkthrough. Never invokes inference.
// Frames are actual current-UI excerpts; their display time is editorial, not latency.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync, spawn } from "node:child_process";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium, expect } from "@playwright/test";
import { assertFrameFits, recordingOrigin, replayPolicy } from "./agentic-video-support.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const sha = (bytes) => createHash("sha256").update(bytes).digest("hex");
const sourcePaths = ["frontend/e2e/capture-agentic-video.mjs", "frontend/e2e/agentic-video.css",
  "frontend/e2e/agentic-video-support.mjs"];
const evidencePath = "experiments/evidence/agentic-question-only-smoke-2026-09-09.json";
const evidenceBytes = await readFile(path.join(root, evidencePath));
const evidence = JSON.parse(evidenceBytes);
const observation = evidence.runs.find((item) => item.run_id === "run_e2f9348452df475c");
assert.ok(observation, "Recorded observation is missing");
const runBytes = await readFile(path.join(root, observation.path));
assert.equal(sha(runBytes), observation.sha256, "Historical execution changed");
const run = JSON.parse(runBytes);
assert.equal(run.status, "completed");
assert.equal(run.question, evidence.question);
assert.equal(run.discovery_hops.length, 12);
assert.equal(run.preparation_attempts.length, 1);
assert.equal(run.analysis_notebook.filter((cell) => cell.phase === "debug").length, 0);
assert.equal(run.report.sections.length, 5);
assert.equal(sha(run.report.markdown), observation.report_sha256);

const origin = recordingOrigin(process.env.ASKDU_E2E_BASE_URL ?? "http://127.0.0.1:8080");
await mkdir(path.join(root, "artifacts/demo"), { recursive: true });
// Every attempt gets a fresh directory; failed recording never replaces an accepted cut.
const outputDirectory = await mkdtemp(path.join(root, "artifacts/demo/agentic-replay-"));
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1600, height: 900 },
  reducedMotion: "reduce", bypassCSP: true, serviceWorkers: "block" });
const page = await context.newPage();
const errors = [];
const denied = [];
const bundles = [];
const frames = [];
let replayedPosts = 0;
page.on("pageerror", (error) => errors.push(error.message));
await context.route("**/*", async (route) => {
  const request = route.request();
  const policy = replayPolicy({ url: request.url(), method: request.method(),
    body: request.method() === "POST" ? request.postDataJSON() : undefined }, origin, run);
  if (policy === "deny") {
    denied.push({ method: request.method(), pathname: new URL(request.url()).pathname });
    return route.abort();
  }
  if (policy === "replay") {
    if (request.method() === "POST") replayedPosts += 1;
    return route.fulfill({ status: request.method() === "POST" ? 202 : 200, json: run });
  }
  if (policy === "environment") {
    const response = await route.fetch();
    assert.ok(response.ok());
    const environment = await response.json();
    assert.equal(environment.planner_mode, "agentic");
    assert.equal(environment.environment_id, run.environment_id);
    return route.fulfill({ response, json: environment });
  }
  return route.continue();
});

async function excerpt(locator) {
  await expect(locator).toBeVisible();
  return locator.evaluate((element) => {
    const copy = element.cloneNode(true);
    // The live textarea value is a property, not an HTML attribute.
    const originalInputs = element.querySelectorAll("textarea");
    copy.querySelectorAll("textarea").forEach((input, index) => { input.textContent = originalInputs[index].value; });
    return copy.outerHTML;
  });
}

async function frame({ name, title, caption, seconds, html, card, note = "Current UI excerpts · recorded run · editorial timing, not model latency" }) {
  await page.evaluate(({ title, caption, html, card, note }) => {
    document.querySelector("#askdu-recorded-film")?.remove();
    const film = document.createElement("section");
    film.id = "askdu-recorded-film";
    film.innerHTML = '<header><small></small><h1></h1></header><div class="film-content"></div><footer></footer>';
    film.querySelector("header small").textContent = note;
    film.querySelector("h1").textContent = title;
    film.querySelector("footer").textContent = caption;
    const content = film.querySelector(".film-content");
    if (card) {
      const article = document.createElement("article");
      article.className = "film-card";
      for (const [tag, text] of [["h2", card.title], ["p", card.body], ["small", card.note]]) {
        const element = document.createElement(tag);
        element.textContent = text;
        article.append(element);
      }
      content.append(article);
    } else content.innerHTML = html;
    document.body.append(film);
  }, { title, caption, html, card, note });
  const film = page.locator("#askdu-recorded-film");
  const filename = `${String(frames.length + 1).padStart(2, "0")}-${name}.png`;
  await film.screenshot({ path: path.join(outputDirectory, filename), animations: "disabled" });
  const content = await film.locator(".film-content").evaluate((element) => ({
    scrollWidth: element.scrollWidth, clientWidth: element.clientWidth,
    scrollHeight: element.scrollHeight, clientHeight: element.clientHeight,
  }));
  assertFrameFits(await film.boundingBox(), content);
  const bytes = await readFile(path.join(outputDirectory, filename));
  const start = frames.reduce((sum, item) => sum + item.seconds, 0);
  frames.push({ filename, sha256: sha(bytes), title, caption, note, seconds, start_seconds: start });
  await film.evaluate((element) => element.remove());
}

try {
  await page.goto(origin.href, { waitUntil: "networkidle" });
  const bundlePaths = await page.locator('script[src], link[rel="stylesheet"]').evaluateAll(
    (elements) => elements.map((element) => element.getAttribute("src") ?? element.getAttribute("href")),
  );
  assert.ok(bundlePaths.length >= 2);
  for (const relative of bundlePaths) {
    assert.match(relative, /^\/assets\/[^/]+\.(js|css)$/);
    const response = await page.request.get(new URL(relative, origin).href);
    assert.ok(response.ok());
    const digest = sha(await response.body());
    assert.equal(digest, sha(await readFile(path.join(root, "frontend/dist", relative))));
    bundles.push({ path: relative, sha256: digest });
  }
  await page.addStyleTag({ content: await readFile(path.join(root, sourcePaths[1]), "utf8") });
  await frame({ name: "title", title: "Ask, Don’t Upload", seconds: 8,
    caption: "One question → Discover → Prepare → Analyze → An evidence-linked report",
    card: { title: "A question-driven agentic data workflow", body: `Only task input: ${run.question}`,
      note: "A saved real-model development run shown in the current UI. No new inference during recording." } });
  await page.getByRole("textbox", { name: "Your analytical question" }).fill(run.question);
  await frame({ name: "ask", title: "1 · Ask the analytical question", seconds: 8,
    caption: "No filename, schema, join path, analysis dimensions or weights were supplied.",
    html: await excerpt(page.locator(".question-composer")) });
  await page.getByRole("button", { name: /Run hands-off analysis/ }).click();
  await expect(page.locator("#report-title")).toHaveText(run.report.title);
  assert.equal(replayedPosts, 1);
  const workbench = page.getByTestId("research-workflow");
  await workbench.getByRole("tab", { name: /CoDA-Bench Discover/ }).click();
  await workbench.getByRole("button", { name: /^Show hop 1:/ }).click();
  await expect(workbench.locator(".network-nodes .community")).toHaveCount(30);
  await frame({ name: "communities", title: "2 · Discovery starts at the authorized environment", seconds: 10,
    caption: "Hop 1 / 12 · All 30 communities are visible. Files expand only when encountered.",
    html: await excerpt(workbench.locator(".discovery-network-workbench")),
    note: "Recorded root step · current UI excerpt · candidate list omitted from this video frame" });
  await workbench.getByRole("button", { name: "Show hop 5: Inspect asset" }).click();
  await expect(workbench.locator(".network-transitions .current")).toHaveCount(1);
  await frame({ name: "hop", title: "3 · Inspect a source inside a community", seconds: 10,
    caption: "Hop 5 / 12 · Current hop is emphasized; earlier hops remain visible as dashed paths.",
    html: await excerpt(workbench.locator(".discovery-network-workbench")),
    note: "Recorded hop 5 · current UI excerpt · lower schema and candidate panels omitted" });
  await workbench.getByRole("button", { name: /^Show hop 12:/ }).click();
  await expect(workbench.locator(".discovery-output-files")).toContainText("Quality of life index by countries 2020.csv");
  await frame({ name: "sources", title: "4 · Discovery output: an inspected, selected CSV", seconds: 10,
    caption: "The source covers several quality-of-life dimensions. It is dated data, not immigration-policy evidence.",
    html: await excerpt(workbench.locator(".stage-io-discovery")) });
  await workbench.getByRole("tab", { name: /DeepPrep Prepare/ }).click();
  await workbench.locator(".prep-input-data").getByRole("button", { name: "Show all 10 fields" }).click();
  await workbench.locator(".schema-change-details > summary").click();
  await expect(workbench.locator(".prepared-table-preview")).toContainText("80 rows");
  await frame({ name: "schemas", title: "5 · Preparation makes the transformation visible", seconds: 14,
    caption: "Input schema → selected operators → output schema and actual table preview. Raw records are not fabricated.",
    html: await excerpt(workbench.locator(".prep-data-io")),
    note: "Recorded output · all schema fields shown · data preview excerpt: first 3 rows, first 3 of 10 columns" });
  await frame({ name: "tree", title: "6 · Inspect the selected operator path", seconds: 10,
    caption: "This run has one successful candidate: CastType → DropNulls → Sort → Terminate. No backtracking occurred.",
    html: await excerpt(workbench.locator(".prep-tree-workbench")) });
  await workbench.getByRole("tab", { name: /DeepAnalyze Analyze/ }).click();
  const codeCell = workbench.locator(".notebook-cell.code").nth(1);
  await codeCell.locator(".notebook-cell-details > summary").click();
  const executeCell = codeCell.locator("xpath=following-sibling::li[1]");
  await executeCell.locator(".notebook-cell-details > summary").click();
  await expect(codeCell).toContainText("SELECT");
  await expect(executeCell).toContainText("Denmark");
  await frame({ name: "execute", title: "7 · Analysis exposes code and execution feedback", seconds: 12,
    caption: "SQL is compiled from a validated plan and executed locally. This run has 10 Code / Execute pairs and no Debug.",
    html: `<ol class="analysis-notebook">${await excerpt(codeCell)}${await excerpt(executeCell)}</ol>` });
  await frame({ name: "report", title: "8 · The deliverable is a report, not a one-line ranking", seconds: 12,
    caption: "The summary distinguishes an overall dataset ranking from a universal recommendation.",
    html: await excerpt(page.locator(".report-cover")) });
  await frame({ name: "dimensions", title: "9 · Compare dimensions and inspect their evidence", seconds: 14,
    caption: "Different dimensions favor different countries. Each section links to the executed artifacts it cites.",
    html: `<div class="report-narrative-grid">${await excerpt(page.locator(".report-narrative-grid > article").nth(2))}${await excerpt(page.locator(".report-narrative-grid > article").nth(3))}</div>` });
  await frame({ name: "chart", title: "10 · Make the computed comparison readable", seconds: 12,
    caption: "Chart excerpt of the primary executed result. The full UI also provides the underlying result table.",
    html: await excerpt(page.locator(".report-result-section").first()) });
  await frame({ name: "conclusion", title: "11 · Give a conditional conclusion and explicit limits", seconds: 16,
    caption: "No invented universal weighting. Missing current policies and personal eligibility remain stated limitations.",
    html: `${await excerpt(page.locator(".report-conclusion"))}${await excerpt(page.locator(".report-limitations"))}` });
  await frame({ name: "close", title: "Question-only input. Inspectable evidence. A scoped report.", seconds: 8,
    caption: "Internal silent review cut · public artifact and author narration are still pending",
    card: { title: "Explore the workflow, then read the evidence", body: "Revisit a discovery hop, inspect a preparation operator, open a code cell, or follow a report citation.",
      note: "Selected post-fix development run, not held-out evaluation. Separate registry footage demonstrates controlled cross-stage repair." } });
  assert.deepEqual(errors, []);
  assert.deepEqual(denied, []);
} finally {
  await browser.close();
}

// Encode the fixed-duration screenshots asynchronously so callers can report progress.
const video = path.join(outputDirectory, "walkthrough.mp4");
const args = ["-nostdin", "-hide_banner", "-loglevel", "warning"];
for (const item of frames) args.push("-loop", "1", "-framerate", "25", "-t", String(item.seconds), "-i", path.join(outputDirectory, item.filename));
args.push("-filter_complex", `${frames.map((_, index) => `[${index}:v]`).join("")}concat=n=${frames.length}:v=1:a=0,format=yuv420p[outv]`,
  "-map", "[outv]", "-an", "-c:v", "libx264", "-threads", "2", "-preset", "medium", "-crf", "18",
  "-g", "50", "-movflags", "+faststart", "-metadata", "title=Ask, Don't Upload - Recorded Agentic Run, Editorial Timing", video);
await new Promise((resolve, reject) => {
  const process = spawn("ffmpeg", args, { stdio: ["ignore", "ignore", "inherit"] });
  process.once("error", reject);
  process.once("exit", (code) => code === 0 ? resolve() : reject(new Error(`ffmpeg exited ${code}`)));
});
const media = JSON.parse(execFileSync("ffprobe", ["-v", "error", "-show_format", "-show_streams", "-of", "json", video], { encoding: "utf8" }));
const duration = frames.reduce((sum, item) => sum + item.seconds, 0);
assert.equal(Number(media.format.duration), duration);
assert.equal(media.streams.length, 1);
assert.equal(media.streams[0].codec_name, "h264");
assert.equal(media.streams[0].width, 1600);
assert.equal(media.streams[0].height, 900);
assert.equal(media.streams[0].pix_fmt, "yuv420p");
const sources = {};
for (const source of sourcePaths) sources[source] = sha(await readFile(path.join(root, source)));
const manifest = {
  schema_version: "askdu-agentic-video-v1", capture_kind: "historical_model_run_current_ui_excerpts",
  original_run: { path: observation.path, sha256: observation.sha256, run_id: run.run_id },
  original_report_sha256: observation.report_sha256, evidence_path: evidencePath, evidence_sha256: sha(evidenceBytes),
  demo_surface_sha256: execFileSync(path.join(root, "scripts/hash_demo_surface.sh"), { cwd: root, encoding: "utf8" }).trim(),
  source_sha256: sources, served_bundles: bundles, frames, duration_seconds: duration,
  video: { filename: "walkthrough.mp4", sha256: sha(await readFile(video)), bytes: Number(media.format.size) },
  model_calls_during_capture: 0, intercepted_post_requests: replayedPosts, unexpected_requests: denied,
  browser_errors: errors, audio_streams: 0,
  limitations: ["Fixed-duration DOM excerpts, not a continuous live interaction or latency measurement.",
    "Only one selected post-fix development run; no claim of first-pass accuracy, backtracking, or Debug.",
    "Original report remains unchanged. Not a new report generation or a validation of immigration suitability.",
    "Silent internal review cut; no author narration, two-author review, public release, or submission readiness."],
};
// A manifest is written only after every capture, route assertion and encoding check passes.
await writeFile(path.join(outputDirectory, "capture.json"), `${JSON.stringify(manifest, null, 2)}\n`);
console.log(JSON.stringify({ outputDirectory, video, duration, sha256: manifest.video.sha256, modelCalls: 0 }, null, 2));
