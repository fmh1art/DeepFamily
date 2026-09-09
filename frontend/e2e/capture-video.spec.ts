import { mkdir } from "node:fs/promises";
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

const paperTitle =
  "Ask, Don’t Upload: A Question-Driven Agentic System for Closed-Loop Data Discovery, Preparation, and Analysis";
const storyboardDirectory = path.resolve(
  process.cwd(),
  process.env.ASKDU_VIDEO_STORYBOARD_DIR ?? "../artifacts/demo/storyboard",
);

test.use({
  viewport: { width: 1600, height: 900 },
  reducedMotion: "reduce",
});

type CardContent = {
  eyebrow: string;
  title: string;
  body: string;
  footer: string;
};

type CaptionContent = {
  step: string;
  title: string;
  body: string;
};

function artifactLine() {
  const configured = process.env.ASKDU_ARTIFACT_URL?.trim();
  if (!configured) return "Public artifact URL pending author release";
  const parsed = new URL(configured);
  if (parsed.protocol !== "https:" || parsed.username || parsed.password) {
    throw new Error("ASKDU_ARTIFACT_URL must be a credential-free HTTPS URL");
  }
  return `Artifact: ${configured}`;
}

async function installVideoOverlay(page: Page) {
  await page.addStyleTag({ url: "/video-overlay.css" });
  await page.evaluate(() => {
    document.documentElement.classList.add("askdu-video-recording");
    const card = document.createElement("section");
    card.id = "askdu-video-card";
    card.innerHTML = `
      <div class="eyebrow"></div>
      <h1></h1>
      <p class="body"></p>
      <div class="footer"></div>
    `;
    const caption = document.createElement("section");
    caption.id = "askdu-video-caption";
    caption.innerHTML = `
      <div class="step"></div>
      <div><h2></h2><p></p></div>
    `;
    document.body.append(card, caption);
  });
}

async function showCard(page: Page, content: CardContent) {
  await page.evaluate((value: CardContent) => {
    const card = document.querySelector<HTMLElement>("#askdu-video-card");
    if (!card) throw new Error("video title card is not installed");
    const eyebrow = card.querySelector<HTMLElement>(".eyebrow");
    const title = card.querySelector<HTMLElement>("h1");
    const body = card.querySelector<HTMLElement>(".body");
    const footer = card.querySelector<HTMLElement>(".footer");
    if (!eyebrow || !title || !body || !footer) throw new Error("video title card is incomplete");
    eyebrow.textContent = value.eyebrow;
    title.textContent = value.title;
    body.textContent = value.body;
    footer.textContent = value.footer;
    card.classList.add("visible");
  }, content);
  const card = page.locator("#askdu-video-card");
  await expect(card).toHaveClass(/visible/);
  await expect(card.locator("h1")).toHaveText(content.title);
  await expect(card.locator(".body")).toHaveText(content.body);
}

async function hideCard(page: Page) {
  await page.locator("#askdu-video-card").evaluate((element) => element.classList.remove("visible"));
}

async function showCaption(page: Page, content: CaptionContent) {
  await page.evaluate((value: CaptionContent) => {
    const caption = document.querySelector<HTMLElement>("#askdu-video-caption");
    if (!caption) throw new Error("video caption is not installed");
    const step = caption.querySelector<HTMLElement>(".step");
    const title = caption.querySelector<HTMLElement>("h2");
    const body = caption.querySelector<HTMLElement>("p");
    if (!step || !title || !body) throw new Error("video caption is incomplete");
    step.textContent = value.step;
    title.textContent = value.title;
    body.textContent = value.body;
    caption.classList.add("visible");
  }, content);
  const caption = page.locator("#askdu-video-caption");
  await expect(caption).toHaveClass(/visible/);
  await expect(caption.locator(".step")).toHaveText(content.step);
  await expect(caption.locator("h2")).toHaveText(content.title);
  await expect(caption.locator("p")).toHaveText(content.body);
}

async function hideCaption(page: Page) {
  await page
    .locator("#askdu-video-caption")
    .evaluate((element) => element.classList.remove("visible"));
}

async function captureFrame(
  page: Page,
  filename: string,
) {
  if (!/^\d{2}-[a-z-]+\.png$/.test(filename)) {
    throw new Error("storyboard frame metadata is invalid");
  }
  await page.evaluate(() => document.fonts.ready.then(() => undefined));
  await page.screenshot({
    path: path.join(storyboardDirectory, filename),
    animations: "disabled",
    scale: "css",
  });
}

test("captures a stable closed-loop and honest-stopping video storyboard", async ({ page }) => {
  test.setTimeout(120_000);
  await mkdir(storyboardDirectory, { recursive: true });

  await page.goto("/", { waitUntil: "networkidle" });
  await expect(page.getByText("10 files", { exact: true })).toBeVisible();
  await installVideoOverlay(page);

  await showCard(page, {
    eyebrow: "VLDB 2027 Demo · Rehearsal Cut",
    title: paperTitle,
    body: "One analytical question drives discovery, preparation, analysis, repair, and an evidence-grounded report.",
    footer: "Deterministic registry mode · Production Compose path",
  });
  await captureFrame(page, "01-title.png");
  await hideCard(page);

  await showCaption(page, {
    step: "1 · Ask",
    title: "One question. No data upload.",
    body: "The task begins inside a pinned, authorized ten-table environment.",
  });
  await captureFrame(page, "02-ask.png");

  await page.getByRole("button", { name: /Join repair/ }).click();
  await showCaption(page, {
    step: "2 · Execute",
    title: "Compile the question into testable obligations.",
    body: "The system chooses and verifies its first source without a table picker or join hint.",
  });
  await captureFrame(page, "03-execute.png");
  await page.getByRole("button", { name: /Run hands-off analysis/ }).click();
  await expect(page.locator(".report-panel.completed")).toBeVisible();

  await page.locator(".technical-audit > summary").click();
  await page.locator(".system-grid").scrollIntoViewIfNeeded();
  await showCaption(page, {
    step: "3 · Discover",
    title: "Execution exposes an analytically insufficient source set.",
    body: "The first table has SHSAT counts, but the requested demographic measures are missing.",
  });
  await captureFrame(page, "04-discover.png");

  await page.getByTestId("repair-impact").scrollIntoViewIfNeeded();
  await showCaption(page, {
    step: "4 · Repair",
    title: "Analysis reopens Discovery.",
    body: "A typed violation adds the missing source, replays preparation, and releases the report.",
  });
  await captureFrame(page, "05-repair.png");

  await page.locator(".report-panel.completed").scrollIntoViewIfNeeded();
  await page.locator(".report-details > summary").click();
  await page.getByRole("tab", { name: /Black\/Hispanic student percentage/ }).click();
  await page.getByTestId("claim-lineage").scrollIntoViewIfNeeded();
  await showCaption(page, {
    step: "5 · Verify",
    title: "Trace a reported number back to executed evidence.",
    body: "Claim → artifact → materialized state → two checksummed source profiles.",
  });
  await captureFrame(page, "06-verify.png");

  await hideCaption(page);
  await page.locator(".question-shell > summary").click();
  await page.locator(".question-composer").scrollIntoViewIfNeeded();
  await page.getByRole("button", { name: /Honest data gap/ }).click();
  await captureFrame(page, "07-transition.png");
  await showCaption(page, {
    step: "6 · Challenge",
    title: "Autonomy includes knowing when to stop.",
    body: "If the authorized environment lacks required evidence, the system returns a typed data gap—not a report.",
  });
  await captureFrame(page, "08-challenge.png");
  await page.getByRole("button", { name: /Run hands-off analysis/ }).click();
  await expect(page.locator(".report-panel.diagnosis")).toBeVisible();
  await page.locator(".report-panel.diagnosis").scrollIntoViewIfNeeded();
  await captureFrame(page, "09-diagnosis.png");

  await hideCaption(page);
  await showCard(page, {
    eyebrow: "Report or typed diagnosis",
    title: "Closed-loop analysis with inspectable evidence",
    body: artifactLine(),
    footer: "Ask, Don’t Upload · Captioned deterministic fallback",
  });
  await captureFrame(page, "10-close.png");
});
